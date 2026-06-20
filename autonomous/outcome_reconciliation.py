"""Realized outcome reconciliation for autonomous evidence.

The reconciler turns closed autonomous trade lifecycle records into realized
outcome evidence records.  It is accounting-only: it does not submit, cancel, or
modify broker orders.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional

from autonomous.evidence_store import SCHEMA_VERSION
from autonomous.trade_store import AutonomousTrade, CLOSED


@dataclass
class FillSummary:
    """Aggregated fill details for one side of a trade."""

    quantity: int
    avg_price: float
    total_value: float
    commission: float = 0.0
    fills: List[Dict[str, Any]] = field(default_factory=list)
    partial: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "quantity": self.quantity,
            "avg_price": round(self.avg_price, 6),
            "total_value": round(self.total_value, 2),
            "commission": round(self.commission, 4),
            "partial": self.partial,
            "fills": list(self.fills),
        }


@dataclass
class OutcomeReconciliation:
    """Accounting result for one closed autonomous trade."""

    autonomous_trade_id: str
    symbol: str
    realized: bool
    quantity: int
    entry_price: float
    exit_price: float
    realized_pnl: float
    realized_r_multiple: Optional[float]
    exit_reason: Optional[str]
    entry_slippage: Optional[float]
    entry_slippage_pct: Optional[float]
    exit_slippage: Optional[float]
    total_commission: float
    partial_fill: bool
    entry_fill: FillSummary
    exit_fill: FillSummary
    entry_order_id: Optional[int] = None
    exit_order_id: Optional[int] = None
    notes: List[str] = field(default_factory=list)

    def to_outcome_dict(self) -> Dict[str, Any]:
        return {
            "realized": self.realized,
            "exit_price": round(self.exit_price, 6),
            "realized_pnl": round(self.realized_pnl, 2),
            "realized_r_multiple": (
                round(self.realized_r_multiple, 6)
                if self.realized_r_multiple is not None
                else None
            ),
            "exit_reason": self.exit_reason,
            "quantity": self.quantity,
            "entry_price": round(self.entry_price, 6),
            "entry_slippage": round(self.entry_slippage, 6) if self.entry_slippage is not None else None,
            "entry_slippage_pct": round(self.entry_slippage_pct, 6) if self.entry_slippage_pct is not None else None,
            "exit_slippage": round(self.exit_slippage, 6) if self.exit_slippage is not None else None,
            "commission": round(self.total_commission, 4),
            "partial_fill": self.partial_fill,
            "entry_fill": self.entry_fill.to_dict(),
            "exit_fill": self.exit_fill.to_dict(),
            "notes": list(self.notes),
        }

    def to_evidence_record(self, *, base_record: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        base_record = base_record or {}
        base_order = base_record.get("order") or {}
        order_block = dict(base_order)
        if self.entry_order_id is not None:
            order_block.setdefault("order_id", self.entry_order_id)
        if self.exit_order_id is not None:
            order_block["exit_order_id"] = self.exit_order_id
        return {
            "schema_version": SCHEMA_VERSION,
            "evidence_type": "autonomous_outcome",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "autonomous_trade_id": self.autonomous_trade_id,
            "symbol": self.symbol,
            "strategy_bucket": base_record.get("strategy_bucket") or {},
            "planned_risk": base_record.get("planned_risk") or {},
            "trade_plan": base_record.get("trade_plan") or {},
            "order": order_block,
            "outcome": self.to_outcome_dict(),
        }


class OutcomeReconciler:
    """Reconcile closed autonomous trades into outcome evidence records."""

    def reconcile_trade(
        self,
        trade: AutonomousTrade,
        *,
        entry_fills: Optional[Iterable[Dict[str, Any]]] = None,
        exit_fills: Optional[Iterable[Dict[str, Any]]] = None,
        base_evidence_record: Optional[Dict[str, Any]] = None,
    ) -> Optional[OutcomeReconciliation]:
        if trade.status != CLOSED:
            return None
        qty = int(trade.quantity or 0)
        if qty <= 0:
            return None

        entry_fill = aggregate_fills(
            entry_fills,
            fallback_quantity=qty,
            fallback_price=trade.entry_filled_price or trade.entry_limit_price,
        )
        exit_fill = aggregate_fills(
            exit_fills,
            fallback_quantity=qty,
            fallback_price=trade.exit_price,
        )
        if entry_fill is None or exit_fill is None:
            return None

        realized_pnl = ((exit_fill.avg_price - entry_fill.avg_price) * min(entry_fill.quantity, exit_fill.quantity))
        total_commission = entry_fill.commission + exit_fill.commission
        realized_pnl -= total_commission

        planned_risk = (base_evidence_record or {}).get("planned_risk") or {}
        risk_per_share = _positive_float(planned_risk.get("risk_per_share"))
        realized_r = None
        matched_qty = min(entry_fill.quantity, exit_fill.quantity)
        if risk_per_share is not None and risk_per_share > 0 and matched_qty > 0:
            realized_r = realized_pnl / (risk_per_share * matched_qty)

        entry_slippage = None
        entry_slippage_pct = None
        if trade.entry_limit_price and trade.entry_limit_price > 0:
            entry_slippage = entry_fill.avg_price - trade.entry_limit_price
            entry_slippage_pct = entry_slippage / trade.entry_limit_price

        target_price = _positive_float((base_evidence_record or {}).get("trade_plan", {}).get("target_price"))
        exit_slippage = None
        if target_price is not None:
            exit_slippage = exit_fill.avg_price - target_price

        partial = entry_fill.partial or exit_fill.partial or entry_fill.quantity != exit_fill.quantity
        notes = []
        if partial:
            notes.append("partial fill detected")
        if risk_per_share is None:
            notes.append("realized R unavailable: planned risk_per_share missing")

        return OutcomeReconciliation(
            autonomous_trade_id=trade.autonomous_trade_id,
            symbol=trade.symbol,
            realized=True,
            quantity=matched_qty,
            entry_price=entry_fill.avg_price,
            exit_price=exit_fill.avg_price,
            realized_pnl=realized_pnl,
            realized_r_multiple=realized_r,
            exit_reason=trade.exit_reason,
            entry_slippage=entry_slippage,
            entry_slippage_pct=entry_slippage_pct,
            exit_slippage=exit_slippage,
            total_commission=total_commission,
            partial_fill=partial,
            entry_fill=entry_fill,
            exit_fill=exit_fill,
            entry_order_id=trade.entry_order_id,
            exit_order_id=trade.exit_order_id,
            notes=notes,
        )

    def reconcile_closed_trades(
        self,
        trades: Iterable[AutonomousTrade],
        *,
        evidence_records: Optional[Iterable[Dict[str, Any]]] = None,
    ) -> List[OutcomeReconciliation]:
        evidence_by_order = _evidence_by_order_id(evidence_records or [])
        out: List[OutcomeReconciliation] = []
        for trade in trades:
            base = evidence_by_order.get(trade.entry_order_id)
            result = self.reconcile_trade(trade, base_evidence_record=base)
            if result is not None:
                out.append(result)
        return out


def aggregate_fills(
    fills: Optional[Iterable[Dict[str, Any]]],
    *,
    fallback_quantity: int,
    fallback_price: Optional[float],
) -> Optional[FillSummary]:
    rows = list(fills or [])
    if not rows:
        if fallback_price is None or fallback_quantity <= 0:
            return None
        value = fallback_quantity * float(fallback_price)
        return FillSummary(
            quantity=fallback_quantity,
            avg_price=float(fallback_price),
            total_value=value,
            commission=0.0,
            fills=[],
            partial=False,
        )

    qty_total = 0
    value_total = 0.0
    commission_total = 0.0
    normalized: List[Dict[str, Any]] = []
    for row in rows:
        qty = int(row.get("quantity") or row.get("filled_quantity") or 0)
        price = _positive_float(row.get("price") or row.get("fill_price") or row.get("avg_price"))
        if qty <= 0 or price is None:
            continue
        commission = float(row.get("commission") or 0.0)
        qty_total += qty
        value_total += qty * price
        commission_total += commission
        normalized.append({
            "quantity": qty,
            "price": price,
            "commission": commission,
            "time": row.get("time") or row.get("timestamp"),
        })
    if qty_total <= 0:
        return None
    avg = value_total / qty_total
    return FillSummary(
        quantity=qty_total,
        avg_price=avg,
        total_value=value_total,
        commission=commission_total,
        fills=normalized,
        partial=qty_total < fallback_quantity,
    )


def _latest_evidence_by_symbol(records: Iterable[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """Index evidence records by symbol, keeping the first (newest) record per symbol.

    Assumes *records* are ordered newest-first (as returned by
    ``TradeEvidenceStore.recent()``).
    """
    out: Dict[str, Dict[str, Any]] = {}
    for record in records:
        symbol = record.get("symbol")
        if symbol:
            out.setdefault(str(symbol), record)
    return out


def _evidence_by_order_id(records: Iterable[Dict[str, Any]]) -> Dict[int, Dict[str, Any]]:
    """Index evidence records by their entry order_id, keeping the first (newest) match.

    Assumes *records* are ordered newest-first (as returned by
    ``TradeEvidenceStore.recent()``).
    """
    out: Dict[int, Dict[str, Any]] = {}
    for record in records:
        order_id = (record.get("order") or {}).get("order_id")
        if order_id is not None:
            try:
                key = int(order_id)
            except (TypeError, ValueError):
                continue
            out.setdefault(key, record)
    return out


def _positive_float(value: Any) -> Optional[float]:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if out > 0 else None
