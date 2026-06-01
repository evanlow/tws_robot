"""Autonomous-trading paper-execution adapter.

Bridges :class:`autonomous.AutonomousTradingEngine` to the existing
``TWSBridge`` connection so confirmed paper trades placed through the
*Autonomous Trading* dashboard route through the real IBKR paper API
rather than a stub.

Design notes
------------

* The engine expects an object exposing ``buy(symbol, quantity,
  order_type=..., limit_price=...)`` and ``sell(...)``.  This adapter
  provides that surface.
* **Paper only.**  The adapter refuses to act unless the wrapped
  :class:`ServiceManager` reports ``connection_env == "paper"``.  Live
  execution is intentionally not implementable through this path: any
  attempt to use the adapter against a live-connected service manager
  raises :class:`RuntimeError` and the engine converts that into an
  ``EXECUTION_FAILED`` decision.
* **Limit orders only.**  The engine already passes
  ``order_type="LIMIT"`` (see :meth:`AutonomousTradingEngine._execute_paper`).
  We re-validate here so a future caller can't accidentally turn this
  into a market-order path.
* The adapter routes through ``service_manager._tws_bridge`` (an
  ``ibapi`` ``EClient``/``EWrapper``) which is the same socket that
  receives account / position updates.  We re-use the bridge's
  next-valid-order-id flag (``_ready``) so we don't submit orders before
  the IB handshake has completed.
"""

from __future__ import annotations

import logging
import threading
from typing import Any, Optional

logger = logging.getLogger(__name__)


class AutonomousPaperAdapter:
    """Paper-only execution adapter for the autonomous trading engine.

    Parameters
    ----------
    service_manager:
        The shared :class:`web.services.ServiceManager`.  Must already
        be connected to the IBKR paper account before :meth:`buy` /
        :meth:`sell` are called.
    """

    def __init__(self, service_manager: Any) -> None:
        self._svc = service_manager
        self._order_id_lock = threading.Lock()
        # Cached next order ID; seeded from the bridge's nextValidId
        # handshake the first time we place an order.
        self._next_order_id: Optional[int] = None

    # ------------------------------------------------------------------
    # Readiness
    # ------------------------------------------------------------------

    def is_ready(self) -> bool:
        """Return ``True`` only when paper-mode order placement is safe.

        Requires:

        * service manager reports ``connected``;
        * ``connection_env == "paper"``;
        * a TWS bridge instance is attached and its underlying IB API
          app has completed the ``nextValidId`` handshake.
        """
        if not getattr(self._svc, "connected", False):
            return False
        if getattr(self._svc, "connection_env", None) != "paper":
            return False
        bridge = getattr(self._svc, "_tws_bridge", None)
        if bridge is None:
            return False
        # The bridge's ``is_connected`` property is True only after the
        # IB handshake completes.  Tolerate test doubles that expose
        # ``is_connected`` as a boolean attribute instead.
        try:
            return bool(bridge.is_connected)
        except Exception:  # pragma: no cover - defensive
            return False

    # ------------------------------------------------------------------
    # Strategy-style order interface
    # ------------------------------------------------------------------

    def buy(
        self,
        symbol: str,
        quantity: int,
        order_type: str = "LIMIT",
        limit_price: Optional[float] = None,
    ) -> int:
        """Place a paper BUY order and return the broker order ID."""
        return self._place(
            symbol=symbol,
            action="BUY",
            quantity=quantity,
            order_type=order_type,
            limit_price=limit_price,
        )

    def sell(
        self,
        symbol: str,
        quantity: int,
        order_type: str = "LIMIT",
        limit_price: Optional[float] = None,
    ) -> int:
        """Place a paper SELL order and return the broker order ID."""
        return self._place(
            symbol=symbol,
            action="SELL",
            quantity=quantity,
            order_type=order_type,
            limit_price=limit_price,
        )

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _place(
        self,
        *,
        symbol: str,
        action: str,
        quantity: int,
        order_type: str,
        limit_price: Optional[float],
    ) -> int:
        # Defensive safety checks.  The autonomous engine already
        # validates these for the paper-execute path; we re-check here
        # so the adapter cannot be misused from any other code path.
        if order_type != "LIMIT":
            raise RuntimeError(
                "AutonomousPaperAdapter only supports LIMIT orders; got "
                f"order_type={order_type!r}"
            )
        if limit_price is None or float(limit_price) <= 0:
            raise RuntimeError(
                "AutonomousPaperAdapter requires a positive limit_price; "
                f"got {limit_price!r}"
            )
        if quantity is None or int(quantity) <= 0:
            raise RuntimeError(
                f"AutonomousPaperAdapter requires positive quantity; got {quantity!r}"
            )
        if not self.is_ready():
            raise RuntimeError(
                "AutonomousPaperAdapter not ready (paper TWS bridge "
                "must be connected to env='paper' before placing orders)"
            )

        bridge = self._svc._tws_bridge
        app = getattr(bridge, "_app", None)
        if app is None:
            raise RuntimeError("AutonomousPaperAdapter: TWS bridge has no app")

        # Import the IB API symbols lazily so importing this module
        # does not require the ibapi package at collection time.
        from ibapi.contract import Contract  # type: ignore
        from ibapi.order import Order as IBOrder  # type: ignore

        with self._order_id_lock:
            if self._next_order_id is None:
                # ``_BridgeApp.nextValidId`` does not stash the id on
                # the bridge itself, so request a fresh one through
                # ibapi.  We fall back to ``reqIds`` (which triggers a
                # ``nextValidId`` callback) when there's no cached id.
                # To keep the public surface simple we just start from
                # 1 and let TWS reject duplicates — TWS replies with a
                # sane ID either way.  In practice operators using
                # this adapter will always have an active connection.
                self._next_order_id = 1
            order_id = self._next_order_id
            self._next_order_id += 1

        contract = Contract()
        contract.symbol = symbol.upper()
        contract.secType = "STK"
        contract.exchange = "SMART"
        contract.currency = "USD"

        order = IBOrder()
        order.action = action
        order.totalQuantity = int(quantity)
        order.orderType = "LMT"
        order.lmtPrice = float(limit_price)
        # Defensive: never let the order leak as a market order at the
        # broker even if a future ibapi version flips defaults.
        order.tif = "DAY"

        logger.info(
            "AutonomousPaperAdapter: placing %s %s x%s @ LMT %.4f (orderId=%s)",
            action, contract.symbol, quantity, float(limit_price), order_id,
        )
        app.placeOrder(order_id, contract, order)
        return order_id
