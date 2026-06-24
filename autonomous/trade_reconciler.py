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

from autonomous.trade_store import CLOSED, ENTRY_PENDING, EXIT_PENDING, FAILED, OPEN, TradeStore

logger = logging.getLogger(__name__)


OrdersProvider = Callable[[], Iterable[Any]]
OrderLookupProvider = Callable[[int], Any]
CancelOrderProvider = Callable[[int], bool]


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

    # If an EXIT_PENDING trade has no matching broker order snapshot for long
    # enough, assume submission never became active and reopen for retry.
    _STALE_UNCONFIRMED_EXIT_SECONDS = 60.0

    def __init__(
        self,
        trade_store: TradeStore,
        *,
        orders_provider: Optional[OrdersProvider] = None,
        order_lookup_provider: Optional[OrderLookupProvider] = None,
        cancel_order_provider: Optional[CancelOrderProvider] = None,
    ) -> None:
        self._store = trade_store
        self._orders_provider = orders_provider
        self._order_lookup_provider = order_lookup_provider
        self._cancel_order_provider = cancel_order_provider

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
                if trade.entry_filled_price is None:
                    notes = list(trade.notes or [])
                    notes.append(
                        "exit pending without entry fill; marked FAILED for manual review"
                    )
                    self._store.update_trade(
                        trade.autonomous_trade_id,
                        status=FAILED,
                        exit_reason=(trade.exit_reason or "INVALID_EXIT_PENDING"),
                        exit_price=None,
                        realised_pnl=None,
                        notes=notes,
                    )
                    result.notes.append(
                        f"invalid exit pending: {trade.symbol} order={trade.exit_order_id}"
                    )
                    continue

                fill = self._find_filled_order(trade.exit_order_id, orders)
                if fill is not None:
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
                    continue

                # Broker may reject/cancel an exit order.  In that case,
                # keeping the trade EXIT_PENDING forever hides the failure and
                # blocks re-evaluation. Revert to OPEN so exits can be retried.
                terminal = self._find_terminal_nonfill_order(trade.exit_order_id, orders)
                if terminal is None:
                    if self._is_stale_unconfirmed_exit(trade, moment):
                        # The exit order was not observed at the broker, but it
                        # may simply be a working order we have not seen in this
                        # snapshot.  Reverting to OPEN and resubmitting WITHOUT
                        # first cancelling the original would orphan a live SELL
                        # and the retry could double-fill, flipping the long
                        # into a SHORT.  Cancel the original first; only revert
                        # once the cancel is confirmed.  If we cannot confirm
                        # the cancel, fail closed and keep EXIT_PENDING.
                        if not self._cancel_exit_order_before_revert(trade):
                            result.notes.append(
                                "exit cancel unconfirmed: "
                                f"{trade.symbol} order={trade.exit_order_id}; "
                                "kept EXIT_PENDING to avoid oversell"
                            )
                            continue
                        notes = list(trade.notes or [])
                        notes.append(
                            "exit order "
                            f"{trade.exit_order_id} not observed at broker after "
                            f"{int(self._STALE_UNCONFIRMED_EXIT_SECONDS)}s; "
                            "cancelled and reverted to OPEN for retry"
                        )
                        self._store.update_trade(
                            trade.autonomous_trade_id,
                            status=OPEN,
                            exit_order_id=None,
                            exit_time=None,
                            notes=notes,
                        )
                        result.notes.append(
                            "exit unconfirmed: "
                            f"{trade.symbol} order={trade.exit_order_id}"
                        )
                    continue
                notes = list(trade.notes or [])
                reason_suffix = terminal.reason_suffix()
                notes.append(
                    "exit order "
                    f"{trade.exit_order_id} ended as {terminal.status}"
                    f"{reason_suffix}; "
                    "reverted to OPEN for retry"
                )
                self._store.update_trade(
                    trade.autonomous_trade_id,
                    status=OPEN,
                    exit_order_id=None,
                    exit_time=None,
                    notes=notes,
                )
                result.notes.append(
                    "exit not active: "
                    f"{trade.symbol} order={trade.exit_order_id} "
                    f"status={terminal.status}{reason_suffix}"
                )

        return result

    def _cancel_exit_order_before_revert(self, trade: Any) -> bool:
        """Cancel a trade's working exit order before reverting it to OPEN.

        Returns ``True`` when it is safe to revert (the order was cancelled,
        or no cancel hook is configured so the caller retains legacy
        behaviour) and ``False`` when the cancel could not be confirmed and
        the trade must stay ``EXIT_PENDING`` to avoid orphaning a live SELL
        order that could later double-fill.
        """
        if self._cancel_order_provider is None:
            # No cancel capability wired (e.g. unit tests / adapters without
            # order cancellation).  Preserve legacy revert behaviour.
            return True
        order_id = getattr(trade, "exit_order_id", None)
        if order_id is None:
            return True
        try:
            cancelled = self._cancel_order_provider(int(order_id))
        except Exception:  # pragma: no cover - defensive
            logger.warning(
                "cancel_order_provider raised cancelling exit order %s; "
                "keeping EXIT_PENDING to avoid oversell",
                order_id,
            )
            return False
        return bool(cancelled)

    def _is_stale_unconfirmed_exit(self, trade: Any, moment: datetime) -> bool:
        exit_time = getattr(trade, "exit_time", None)
        if isinstance(exit_time, str):
            try:
                exit_time = datetime.fromisoformat(exit_time)
            except ValueError:
                return False
        if not isinstance(exit_time, datetime):
            return False
        if exit_time.tzinfo is None:
            exit_time = exit_time.replace(tzinfo=timezone.utc)
        age_seconds = (moment - exit_time).total_seconds()
        return age_seconds >= self._STALE_UNCONFIRMED_EXIT_SECONDS

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

    def _find_terminal_nonfill_order(
        self,
        order_id: Any,
        orders: List[Any],
    ) -> Optional["_TerminalOrder"]:
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
            terminal = _TerminalOrder.from_order(found, expected_order_id=oid)
            if terminal is not None:
                return terminal

        for order in reversed(orders):
            terminal = _TerminalOrder.from_order(order, expected_order_id=oid)
            if terminal is not None:
                return terminal
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


@dataclass
class _TerminalOrder:
    order_id: int
    status: str
    error_code: Optional[int] = None
    error_message: Optional[str] = None

    @classmethod
    def from_order(cls, order: Any, expected_order_id: int) -> Optional["_TerminalOrder"]:
        if order is None:
            return None
        order_id = _extract_order_id(order)
        if order_id != expected_order_id:
            return None
        status = _normalise_status(_get(order, "status", "order_status"))
        if status not in {"REJECTED", "CANCELLED", "API_CANCELLED", "INACTIVE", "EXPIRED"}:
            return None
        code_raw = _get(order, "error_code", "errorCode", "reject_code")
        try:
            error_code = int(code_raw) if code_raw is not None else None
        except (TypeError, ValueError):
            error_code = None
        message = _get(order, "error_message", "errorString", "reason", "message")
        error_message = str(message) if message else None
        return cls(
            order_id=order_id,
            status=status,
            error_code=error_code,
            error_message=error_message,
        )

    def reason_suffix(self) -> str:
        parts = []
        if self.error_code is not None:
            parts.append(f"code {self.error_code}")
        if self.error_message:
            parts.append(self.error_message)
        if not parts:
            return ""
        return " (" + ": ".join(parts) + ")"


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
