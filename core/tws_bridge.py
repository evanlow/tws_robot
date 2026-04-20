"""Bridge between the TWS/IB Gateway API and the web ServiceManager.

When the user clicks *Connect* on the dashboard, this module opens a real
TCP socket to TWS, subscribes to account updates, and forwards every
callback into the ``ServiceManager`` so the dashboard can display live
account data (equity, positions, P&L, market prices).

Usage (from the connection API route)::

    from core.tws_bridge import TWSBridge
    bridge = TWSBridge(service_manager, config)
    bridge.connect()   # blocks until ready or timeout
    ...
    bridge.disconnect()
"""

import logging
import threading
import time
from datetime import datetime
from typing import Any, Dict, Optional

from ibapi.client import EClient
from ibapi.contract import Contract
from ibapi.wrapper import EWrapper

from core.event_bus import Event, EventType

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Lightweight EWrapper/EClient that forwards data into ServiceManager
# ---------------------------------------------------------------------------

class _BridgeApp(EWrapper, EClient):
    """IB API app whose sole job is to push data into *ServiceManager*."""

    def __init__(self, svc: Any, account: str) -> None:
        EClient.__init__(self, self)
        self._svc = svc
        self._account = account

        # Connection handshake flags
        self._connected = False
        self._ready = False  # set after nextValidId

    # -- connection lifecycle -----------------------------------------------

    def connectAck(self) -> None:
        self._connected = True
        logger.info("TWS connection acknowledged")

    def nextValidId(self, orderId: int) -> None:
        self._ready = True
        logger.info("TWS ready — next valid order ID: %s", orderId)

    def connectionClosed(self) -> None:
        self._connected = False
        self._ready = False
        logger.warning("TWS connection closed")
        self._svc.event_bus.publish(Event(
            EventType.CONNECTION_LOST,
            data={},
            source="TWSBridge",
        ))

    # -- account data -------------------------------------------------------

    def updateAccountValue(self, key: str, val: str, currency: str,
                           accountName: str) -> None:
        if currency != "BASE":
            return
        if key == "TotalCashBalance":
            self._svc.update_account_summary({"cash_balance": _to_float(val)})
        elif key == "NetLiquidationByCurrency":
            equity = _to_float(val)
            self._svc.update_account_summary({"equity": equity})
            # Keep the risk-manager equity in sync (hold lock for atomicity)
            rm = self._svc.risk_manager
            with self._svc._lock:
                rm.current_equity = equity
                # On first real equity update, reset peak to actual value
                # instead of the default initial_capital placeholder.
                if not rm._equity_initialized:
                    rm.peak_equity = equity
                    rm._equity_initialized = True
                elif equity > rm.peak_equity:
                    rm.peak_equity = equity
                # First equity update also sets the daily start if still default
                if rm.daily_start_equity == rm.initial_capital:
                    rm.daily_start_equity = equity
        elif key == "BuyingPower":
            self._svc.update_account_summary({"buying_power": _to_float(val)})

        self._svc.event_bus.publish(Event(
            EventType.ACCOUNT_UPDATE,
            data={"key": key, "value": val, "currency": currency},
            source="TWSBridge",
        ))

    def updatePortfolio(self, contract: Contract, position, marketPrice: float,
                        marketValue: float, averageCost: float,
                        unrealizedPNL: float, realizedPNL: float,
                        accountName: str) -> None:
        symbol = contract.localSymbol or contract.symbol
        pos_float = float(position)
        sec_type = contract.secType or ""
        is_short_option = (pos_float < 0 and sec_type == "OPT")

        if pos_float == 0:
            self._svc.remove_position(symbol)
        else:
            entry_price = averageCost
            current_price = marketPrice
            pnl_pct = (
                (current_price - entry_price) / abs(entry_price)
                if entry_price else 0.0
            )
            pos_data = {
                "quantity": pos_float,
                "entry_price": entry_price,
                "current_price": current_price,
                "market_value": marketValue,
                "unrealized_pnl": unrealizedPNL,
                "unrealized_pnl_pct": pnl_pct,
                "realized_pnl": realizedPNL,
                "side": "LONG" if pos_float > 0 else "SHORT",
                "sec_type": sec_type,
                "exchange": contract.primaryExchange or contract.exchange or "",
                "currency": contract.currency or "",
            }
            # For short options, store premium collected (entry cost) for
            # retention tracking.  averageCost from TWS is the per-unit cost
            # the seller received (positive value).  pos_float is negative
            # for short positions and marketValue is negative for shorts,
            # so abs() normalises both to positive dollar amounts.
            if is_short_option:
                pos_data["premium_collected"] = abs(pos_float) * abs(entry_price)
                pos_data["current_liability"] = abs(marketValue)
            self._svc.update_position(symbol, pos_data)

        # Strategy metrics are recomputed once at accountDownloadEnd() to
        # avoid O(N²) work during burst position updates.

        self._svc.event_bus.publish(Event(
            EventType.PORTFOLIO_UPDATE,
            data={"symbol": symbol, "position": pos_float},
            source="TWSBridge",
        ))

    def accountDownloadEnd(self, accountName: str) -> None:
        logger.info("Account download complete for %s", accountName)
        # Recompute strategy metrics once after the full position snapshot
        # has been received, rather than after every individual position
        # callback, to avoid O(N²) work during burst updates.
        self._svc.recompute_strategy_metrics()

    # -- market data (tick prices) ------------------------------------------

    def tickPrice(self, reqId, tickType, price: float, attrib) -> None:
        # Optionally forward tick data; not critical for the dashboard bug.
        pass

    # -- error handling -----------------------------------------------------

    def error(self, reqId, _errorTime, errorCode: int, errorString: str,
              advancedOrderRejectJson="") -> None:
        # Informational messages (data-farm connections)
        if errorCode in (2104, 2106, 2158):
            logger.debug("TWS info %s: %s", errorCode, errorString)
            return
        # Critical connection errors
        if errorCode in (502, 503, 504, 1100, 2110):
            logger.error("TWS connection error %s: %s", errorCode, errorString)
            self._connected = False
            return
        logger.warning("TWS error %s (reqId %s): %s", errorCode, reqId,
                       errorString)


# ---------------------------------------------------------------------------
# Public bridge class
# ---------------------------------------------------------------------------

class TWSBridge:
    """Manage a TWS API connection on behalf of the web layer.

    Parameters
    ----------
    svc : ServiceManager
        The shared service manager that owns positions / account state.
    config : dict
        Must contain ``host``, ``port``, ``client_id``, ``account``.
    """

    def __init__(self, svc: Any, config: Dict[str, Any]) -> None:
        self._svc = svc
        self._config = config
        self._app: Optional[_BridgeApp] = None
        self._thread: Optional[threading.Thread] = None

    # -- public API ---------------------------------------------------------

    def connect(self, timeout: int = 10) -> bool:
        """Open the socket to TWS, start the reader thread, and subscribe
        to account updates.  Returns ``True`` when ready.
        """
        host = self._config["host"]
        port = self._config["port"]
        client_id = self._config["client_id"]
        account = self._config.get("account", "")

        logger.info("TWSBridge: connecting to %s:%s (client %s)", host, port,
                     client_id)

        self._app = _BridgeApp(self._svc, account)
        self._app.connect(host, port, client_id)

        self._thread = threading.Thread(target=self._app.run, daemon=True,
                                        name="tws-bridge-reader")
        self._thread.start()

        # Wait for the handshake (connectAck + nextValidId)
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self._app._connected and self._app._ready:
                break
            time.sleep(0.1)

        if not (self._app._connected and self._app._ready):
            logger.error("TWSBridge: connection timed out after %ss", timeout)
            self.disconnect()
            return False

        logger.info("TWSBridge: connected — requesting account updates")

        # Configure delayed market data (will auto-upgrade to live if
        # the user has subscriptions).
        try:
            self._app.reqMarketDataType(3)
        except Exception:
            pass

        # Subscribe to real-time account + portfolio updates
        self._app.reqAccountUpdates(True, account)
        return True

    def disconnect(self) -> None:
        """Cancel subscriptions and tear down the socket."""
        if self._app is None:
            return
        try:
            if self._app.isConnected():
                account = self._config.get("account", "")
                self._app.reqAccountUpdates(False, account)
                self._app.disconnect()
        except Exception as exc:
            logger.debug("TWSBridge: disconnect error (benign): %s", exc)
        finally:
            self._app = None
            self._thread = None

    @property
    def is_connected(self) -> bool:
        return (self._app is not None
                and self._app._connected
                and self._app._ready)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _to_float(val: Any) -> float:
    """Safely convert a string or number to float."""
    try:
        return float(val)
    except (TypeError, ValueError):
        return 0.0
