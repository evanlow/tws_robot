"""Reconcile autonomous trade records with broker/order fill state.

The autonomous runners submit entry and exit orders, while the broker (or a
paper adapter/test double) reports fills asynchronously.  This module bridges
that gap by updating :class:`autonomous.trade_store.TradeStore` records when a
matching order reaches a terminal filled state.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Iterable, List, Optional

from autonomous.trade_store import CLOSED, ENTRY_PENDING, EXIT_PENDING, OPEN, TradeStore

logger = logging.getLogger(__name__)


OrdersProvider = Callable[[], Iterable[Any]]
OrderLookupProvider = Callable[[int], Any]


@dataclass
class ReconciliationResult:
    """Summary of one reconciliation pass."""

    entry_fills: int = 0
    exit_fills: int = 0
    notes: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "entry_fills": self.entry_fills,
            "exit_fills": self.exit_fills,
            "notes": list(self.notes),
        }


class TradeReconciler:
    """Update autonomous trade lifecycle records from filled orders.

    ``orders_provider`` should return the application's known order snapshots,
    newest or oldest.  The reconciler searches from the end so append-only
    order-status logs naturally resolve to the latest status.

    ``order_lookup_provider`` is optional and useful for adapter-style objects
    exposing ``get_order(order_id)``.
    """

    def __init__(
        self,
        trade_store: TradeStore,
        *,
        orders_provider: Optional[OrdersProvider] = None,
        order_lookup_provider: Optional[OrderLookupProvider] = None,
    ) -> None:
        self._store = trade_store
        self._orders_provider = orders_provider
        self._order_lookup_provider = order_lookup_provider

    def reconcile(self, now: Optional[datetime] = None) -> ReconciliationResult:
        moment = now or datetime.now(timezone.utc)
        result = ReconciliationResult()
        orders = self._safe_orders()

        for trade in self._store.list_all():
            trade_type = str(getattr(trade, "trade_type", "")).upper()
            if trade_type != "BUY_SHARES":
                continue

            if trade.status in {ENTRY_PENDING, OPEN} and trade.entry_filled_price is None:
                fill = self._find_filled_order(trade.entry_order_id, orders)
                if fill is not None:
                    price = fill.fill_price or trade.entry_limit_price
                    update_fields = {
                        "entry_filled_price": price,
                    }
                    if trade.status == ENTRY_PENDING:
                        update_fields["status"] = OPEN
                    self._store.update_trade(
                        trade.autonomous_trade_id,
                        **update_fields,
                    )
                    result.entry_fills += 1
                    result.notes.append(
                        f"entry filled: {trade.symbol} order={trade.entry_order_id}"
                    )
                continue

            if trade.status == EXIT_PENDING and trade.exit_order_id is not None:
                fill = self._find_filled_order(trade.exit_order_id, orders)
                if fill is None:
                    continue
                exit_price = (
                    fill.fill_price or trade.exit_price or trade.entry_limit_price
                )
                entry_price = trade.entry_filled_price or trade.entry_limit_price
                realised = (exit_price - entry_price) * int(trade.quantity)
                notes = list(trade.notes or [])
                notes.append(
                    f"exit fill reconciled from order {trade.exit_order_id}"
                )
                self._store.update_trade(
                    trade.autonomous_trade_id,
                    status=CLOSED,
                    exit_price=round(float(exit_price), 4),
                    realised_pnl=round(float(realised), 2),
                    exit_time=moment,
                    notes=notes,
                )
                result.exit_fills += 1
                result.notes.append(
                    f"exit filled: {trade.symbol} order={trade.exit_order_id}"
                )

        return result

    def _safe_orders(self) -> List[Any]:
        if self._orders_provider is None:
            return []
        try:
            return list(self._orders_provider() or [])
        except Exception:  # pragma: no cover - defensive
            logger.exception("orders_provider raised during reconciliation")
            return []

    def _find_filled_order(self, order_id: Any, orders: List[Any]) -> Optional["_Fill"]:
        try:
            oid = int(order_id)
        except (TypeError, ValueError):
            return None

        if self._order_lookup_provider is not None:
            try:
                found = self._order_lookup_provider(oid)
            except Exception:  # pragma: no cover - defensive
                logger.exception("order_lookup_provider raised for order_id=%s", oid)
                found = None
            fill = _Fill.from_order(found, expected_order_id=oid)
            if fill is not None:
                return fill

        for order in reversed(orders):
            fill = _Fill.from_order(order, expected_order_id=oid)
            if fill is not None:
                return fill
        return None


@dataclass
class _Fill:
    order_id: int
    fill_price: Optional[float] = None
    filled_quantity: Optional[float] = None

    @classmethod
    def from_order(cls, order: Any, expected_order_id: int) -> Optional["_Fill"]:
        if order is None:
            return None
        order_id = _extract_order_id(order)
        if order_id != expected_order_id:
            return None
        status = _normalise_status(_get(order, "status", "order_status"))
        if status not in {"FILLED", "COMPLETE", "COMPLETED"}:
            return None
        remaining = _as_float(_get(order, "remaining", "remaining_qty"))
        if remaining is not None and remaining > 0:
            return None
        return cls(
            order_id=order_id,
            fill_price=_as_float(_get(
                order,
                "avg_fill_price",
                "avgFillPrice",
                "average_fill_price",
                "fill_price",
                "price",
            )),
            filled_quantity=_as_float(_get(
                order,
                "filled",
                "filled_qty",
                "filled_quantity",
                "quantity",
            )),
        )


def _extract_order_id(order: Any) -> Optional[int]:
    value = _get(order, "broker_order_id", "order_id", "orderId", "id")
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _get(order: Any, *names: str) -> Any:
    if order is None:
        return None
    if isinstance(order, dict):
        for name in names:
            if name in order:
                return order.get(name)
        return None
    for name in names:
        if hasattr(order, name):
            return getattr(order, name)
    return None


def _as_float(value: Any) -> Optional[float]:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if out >= 0 else None


def _normalise_status(value: Any) -> str:
    return str(value or "").strip().replace(" ", "_").upper()
