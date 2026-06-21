"""Automatic broker-fill ingestion for autonomous live trades.

The ingestor consumes broker execution snapshots, updates the autonomous trade
store, records order lifecycle transitions, and emits realized outcome evidence
when a matched trade closes.  It is accounting-only: it never submits, cancels,
or modifies broker orders.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Iterable, List, Optional

from autonomous.evidence_store import TradeEvidenceStore
from autonomous.order_lifecycle import (
    ENTRY,
    STOP,
    TARGET,
    OrderLifecycleEvent,
    OrderLifecycleState,
    OrderLifecycleStore,
)
from autonomous.outcome_evidence_writer import OutcomeEvidenceWriter
from autonomous.outcome_reconciliation import OutcomeReconciler, aggregate_fills
from autonomous.trade_store import CLOSED, EXIT_PENDING, OPEN, AutonomousTrade, TradeStore

logger = logging.getLogger(__name__)


BrokerFillEventsProvider = Callable[[], Iterable[Dict[str, Any]]]


@dataclass
class BrokerFillIngestionResult:
    """Summary of one broker-fill ingestion pass."""

    fills_seen: int = 0
    entry_fills: int = 0
    exit_fills: int = 0
    trades_closed: int = 0
    outcomes_emitted: int = 0
    lifecycle_events: List[Dict[str, Any]] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "fills_seen": self.fills_seen,
            "entry_fills": self.entry_fills,
            "exit_fills": self.exit_fills,
            "trades_closed": self.trades_closed,
            "outcomes_emitted": self.outcomes_emitted,
            "lifecycle_events": list(self.lifecycle_events),
            "notes": list(self.notes),
        }


class BrokerFillIngestor:
    """Reconcile broker execution fills into autonomous trade/evidence stores."""

    def __init__(
        self,
        trade_store: TradeStore,
        *,
        lifecycle_store: Optional[OrderLifecycleStore] = None,
        outcome_writer: Optional[OutcomeEvidenceWriter] = None,
        evidence_store: Optional[TradeEvidenceStore] = None,
        outcome_reconciler: Optional[OutcomeReconciler] = None,
    ) -> None:
        self._trade_store = trade_store
        self._lifecycle_store = lifecycle_store
        self._outcome_writer = outcome_writer
        self._evidence_store = evidence_store
        self._outcome_reconciler = outcome_reconciler or OutcomeReconciler()

    def ingest(self, fill_events: Iterable[Dict[str, Any]]) -> BrokerFillIngestionResult:
        result = BrokerFillIngestionResult()
        events = [_normalise_fill_event(row) for row in fill_events or []]
        events = [event for event in events if event is not None]
        result.fills_seen = len(events)
        if not events:
            return result

        trades = self._trade_store.list_all()
        for event in events:
            matched = False
            for index, trade in enumerate(trades):
                role = _match_fill_role(trade, event)
                if role is None:
                    continue
                matched = True
                self._apply_fill(trade, role, event, result)
                latest = self._trade_store.get(trade.autonomous_trade_id)
                if latest is not None:
                    trades[index] = latest
                break
            if not matched:
                result.notes.append(
                    f"unmatched broker fill: order_id={event.get('order_id')} "
                    f"execution_id={event.get('execution_id')}"
                )
        return result

    def _apply_fill(
        self,
        trade: AutonomousTrade,
        role: str,
        event: Dict[str, Any],
        result: BrokerFillIngestionResult,
    ) -> None:
        if role == ENTRY:
            fills, changed = _merge_fill(list(trade.entry_fills or []), event)
            if not changed:
                return
            summary = aggregate_fills(
                fills,
                fallback_quantity=int(trade.quantity),
                fallback_price=trade.entry_limit_price,
            )
            fields: Dict[str, Any] = {"entry_fills": fills}
            state = OrderLifecycleState.PARTIALLY_FILLED
            if summary is not None:
                fields["entry_filled_price"] = round(summary.avg_price, 6)
                if summary.quantity >= int(trade.quantity):
                    state = OrderLifecycleState.FILLED
            self._trade_store.update_trade(trade.autonomous_trade_id, **fields)
            self._record_lifecycle(
                result,
                trade=trade,
                role=ENTRY,
                state=state,
                order_id=trade.entry_order_id,
                reason="broker entry fill ingested",
                metadata={"fill": dict(event), "fill_summary": summary.to_dict() if summary else None},
            )
            result.entry_fills += 1
            return

        fills, changed = _merge_fill(list(trade.exit_fills or []), event)
        if not changed:
            return
        summary = aggregate_fills(
            fills,
            fallback_quantity=int(trade.quantity),
            fallback_price=trade.exit_price,
        )
        fields = {"exit_fills": fills, "exit_order_id": int(event["order_id"])}
        if summary is not None:
            fields["exit_price"] = round(summary.avg_price, 6)
        exit_reason = _exit_reason_for(trade, int(event["order_id"]))
        if exit_reason:
            fields["exit_reason"] = exit_reason

        state = OrderLifecycleState.PARTIALLY_FILLED
        if summary is not None and summary.quantity >= _close_quantity(trade):
            state = OrderLifecycleState.FILLED
            fields["status"] = CLOSED
            fields["exit_time"] = _event_time(event) or datetime.now(timezone.utc)
            fields["realised_pnl"] = _realised_pnl(trade, fills)
            notes = list(trade.notes or [])
            notes.append(
                f"reconciled: broker fill ingestion closed trade "
                f"(order #{event['order_id']})"
            )
            fields["notes"] = notes
        elif trade.status == OPEN:
            fields["status"] = EXIT_PENDING

        self._trade_store.update_trade(trade.autonomous_trade_id, **fields)
        updated = self._trade_store.get(trade.autonomous_trade_id) or trade
        self._record_lifecycle(
            result,
            trade=updated,
            role=role,
            state=state,
            order_id=int(event["order_id"]),
            reason="broker exit fill ingested",
            metadata={"fill": dict(event), "fill_summary": summary.to_dict() if summary else None},
        )
        result.exit_fills += 1
        if updated.status == CLOSED:
            self._record_lifecycle(
                result,
                trade=updated,
                role=ENTRY,
                state=OrderLifecycleState.CLOSED,
                order_id=updated.entry_order_id,
                reason=f"trade closed by broker fill order #{event['order_id']}",
                metadata={"exit_order_id": int(event["order_id"]), "exit_reason": updated.exit_reason},
            )
            result.trades_closed += 1
            self._emit_outcome(updated, result)

    def _record_lifecycle(
        self,
        result: BrokerFillIngestionResult,
        *,
        trade: AutonomousTrade,
        role: str,
        state: OrderLifecycleState,
        order_id: int,
        reason: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        if self._lifecycle_store is None:
            return
        lifecycle_id = _lifecycle_id_for(trade, role, order_id)
        parent_id = trade.entry_lifecycle_id if role in {TARGET, STOP} else None
        try:
            event = self._lifecycle_store.record_transition(
                lifecycle_id=lifecycle_id,
                state=state,
                symbol=trade.symbol,
                order_role=role,
                broker_order_id=order_id,
                autonomous_trade_id=trade.autonomous_trade_id,
                parent_lifecycle_id=parent_id,
                reason=reason,
                metadata=metadata or {},
            )
            result.lifecycle_events.append(event.to_dict())
        except OSError:  # pragma: no cover - defensive
            logger.exception("failed to record broker fill lifecycle event")

    def _emit_outcome(
        self,
        trade: AutonomousTrade,
        result: BrokerFillIngestionResult,
    ) -> None:
        if trade.outcome_emitted:
            return
        if self._outcome_writer is None:
            result.notes.append(
                f"outcome not emitted for {trade.autonomous_trade_id}: no writer configured"
            )
            return
        reconciliation = self._outcome_reconciler.reconcile_trade(
            trade,
            entry_fills=trade.entry_fills,
            exit_fills=trade.exit_fills,
            base_evidence_record=self._base_evidence_for(trade.entry_order_id),
        )
        if reconciliation is None:
            result.notes.append(
                f"outcome not emitted for {trade.autonomous_trade_id}: reconciliation incomplete"
            )
            return
        path = self._outcome_writer.append_outcome(reconciliation.to_evidence_record())
        if path is None:
            result.notes.append(
                f"outcome not emitted for {trade.autonomous_trade_id}: writer failed"
            )
            return
        self._trade_store.update_trade(trade.autonomous_trade_id, outcome_emitted=True)
        result.outcomes_emitted += 1

    def _base_evidence_for(self, entry_order_id: Optional[int]) -> Optional[Dict[str, Any]]:
        if self._evidence_store is None or entry_order_id is None:
            return None
        try:
            order_id = int(entry_order_id)
        except (TypeError, ValueError):
            return None
        for record in self._evidence_store.recent(limit=1000):
            try:
                record_order_id = int((record.get("order") or {}).get("order_id"))
            except (TypeError, ValueError):
                continue
            if record_order_id == order_id:
                return record
        return None


def _normalise_fill_event(row: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if not isinstance(row, dict):
        return None
    order_id = _int_or_none(_first(row, "order_id", "broker_order_id", "orderId"))
    qty = _positive_float(_first(row, "quantity", "shares", "filled", "filled_quantity"))
    price = _positive_float(_first(row, "price", "fill_price", "avg_price", "last_fill_price"))
    if order_id is None or qty is None or price is None:
        return None
    execution_id = _first(row, "execution_id", "exec_id", "execId")
    if not execution_id:
        execution_id = f"order:{order_id}:{qty:g}:{price:g}:{_first(row, 'timestamp', 'time') or ''}"
    commission = _float_or_none(_first(row, "commission", "commission_amount"))
    return {
        "execution_id": str(execution_id),
        "order_id": order_id,
        "symbol": _first(row, "symbol", "local_symbol"),
        "side": _first(row, "side", "action"),
        "quantity": int(qty) if float(qty).is_integer() else qty,
        "price": float(price),
        "commission": commission,
        "timestamp": _first(row, "timestamp", "time"),
        "exchange": _first(row, "exchange", "exchange_name"),
        "liquidity": _first(row, "liquidity", "last_liquidity"),
    }


def _match_fill_role(trade: AutonomousTrade, event: Dict[str, Any]) -> Optional[str]:
    if trade.status not in {OPEN, EXIT_PENDING, CLOSED}:
        return None
    order_id = int(event["order_id"])
    if order_id == int(trade.entry_order_id):
        return ENTRY
    if trade.target_order_id is not None and order_id == int(trade.target_order_id):
        return TARGET
    if trade.stop_order_id is not None and order_id == int(trade.stop_order_id):
        return STOP
    if trade.exit_order_id is not None and order_id == int(trade.exit_order_id):
        return _exit_role_for_reason(trade.exit_reason)
    return None


def _merge_fill(fills: List[Dict[str, Any]], event: Dict[str, Any]) -> tuple[List[Dict[str, Any]], bool]:
    key = str(event.get("execution_id") or "")
    for idx, existing in enumerate(fills):
        if str(existing.get("execution_id") or "") != key:
            continue
        merged = dict(existing)
        changed = False
        for field, value in event.items():
            if value is not None and merged.get(field) != value:
                merged[field] = value
                changed = True
        if changed:
            fills[idx] = merged
        return fills, changed
    fills.append(dict(event))
    return fills, True


def _close_quantity(trade: AutonomousTrade) -> int:
    entry = aggregate_fills(
        trade.entry_fills,
        fallback_quantity=int(trade.quantity),
        fallback_price=trade.entry_filled_price or trade.entry_limit_price,
    )
    if entry is not None and entry.quantity > 0:
        return min(entry.quantity, int(trade.quantity))
    return int(trade.quantity)


def _realised_pnl(trade: AutonomousTrade, exit_fills: List[Dict[str, Any]]) -> Optional[float]:
    entry = aggregate_fills(
        trade.entry_fills,
        fallback_quantity=int(trade.quantity),
        fallback_price=trade.entry_filled_price or trade.entry_limit_price,
    )
    exit_summary = aggregate_fills(
        exit_fills,
        fallback_quantity=int(trade.quantity),
        fallback_price=trade.exit_price,
    )
    if entry is None or exit_summary is None:
        return None
    qty = min(entry.quantity, exit_summary.quantity)
    pnl = (exit_summary.avg_price - entry.avg_price) * qty
    pnl -= entry.commission + exit_summary.commission
    return round(float(pnl), 2)


def _exit_reason_for(trade: AutonomousTrade, order_id: int) -> Optional[str]:
    if trade.target_order_id is not None and order_id == int(trade.target_order_id):
        return "TAKE_PROFIT"
    if trade.stop_order_id is not None and order_id == int(trade.stop_order_id):
        return "STOP_LOSS"
    return trade.exit_reason


def _exit_role_for_reason(reason: Optional[str]) -> str:
    if str(reason or "").upper() == "STOP_LOSS":
        return STOP
    return TARGET


def _lifecycle_id_for(trade: AutonomousTrade, role: str, order_id: int) -> str:
    if role == ENTRY and trade.entry_lifecycle_id:
        return trade.entry_lifecycle_id
    if role == TARGET and trade.target_lifecycle_id:
        return trade.target_lifecycle_id
    if role == STOP and trade.stop_lifecycle_id:
        return trade.stop_lifecycle_id
    return f"{trade.autonomous_trade_id}:{role}:{order_id}"


def _event_time(event: Dict[str, Any]) -> Optional[datetime]:
    value = event.get("timestamp")
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        try:
            parsed = datetime.fromisoformat(text)
        except ValueError:
            return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed
    return None


def _first(mapping: Dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in mapping and mapping.get(key) is not None:
            return mapping.get(key)
    return None


def _int_or_none(value: Any) -> Optional[int]:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _float_or_none(value: Any) -> Optional[float]:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _positive_float(value: Any) -> Optional[float]:
    out = _float_or_none(value)
    return out if out is not None and out > 0 else None
