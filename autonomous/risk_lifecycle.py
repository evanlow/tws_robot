"""Strategy equity curve and loss-limit controls.

This module consumes realized autonomous outcome evidence and produces a
pre-trade risk-lifecycle decision.  It is defensive by design: when configured
limits are breached, new entries can be blocked before scanning/planning.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional


@dataclass
class StrategyEquityPoint:
    """One point in the strategy-level equity curve."""

    timestamp: datetime
    symbol: str
    realized_pnl: float
    realized_r_multiple: float
    cumulative_pnl: float
    cumulative_r: float

    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp.isoformat(),
            "symbol": self.symbol,
            "realized_pnl": round(self.realized_pnl, 2),
            "realized_r_multiple": round(self.realized_r_multiple, 6),
            "cumulative_pnl": round(self.cumulative_pnl, 2),
            "cumulative_r": round(self.cumulative_r, 6),
        }


@dataclass
class LossLimitDecision:
    """Decision from the risk-lifecycle guard."""

    allowed: bool
    reason: str
    daily_r: float = 0.0
    weekly_r: float = 0.0
    monthly_r: float = 0.0
    consecutive_losses: int = 0
    max_drawdown_r: float = 0.0
    equity_curve: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "allowed": self.allowed,
            "reason": self.reason,
            "daily_r": round(self.daily_r, 6),
            "weekly_r": round(self.weekly_r, 6),
            "monthly_r": round(self.monthly_r, 6),
            "consecutive_losses": self.consecutive_losses,
            "max_drawdown_r": round(self.max_drawdown_r, 6),
            "equity_curve": list(self.equity_curve),
        }


class StrategyEquityCurveBuilder:
    """Build a cumulative strategy equity curve from outcome records."""

    def build(self, records: Iterable[Dict[str, Any]]) -> List[StrategyEquityPoint]:
        outcomes = [_outcome_row(record) for record in records]
        outcomes = [row for row in outcomes if row is not None]
        outcomes.sort(key=lambda row: row["timestamp"])

        cumulative_pnl = 0.0
        cumulative_r = 0.0
        curve: List[StrategyEquityPoint] = []
        for row in outcomes:
            cumulative_pnl += row["realized_pnl"]
            cumulative_r += row["realized_r_multiple"]
            curve.append(
                StrategyEquityPoint(
                    timestamp=row["timestamp"],
                    symbol=row["symbol"],
                    realized_pnl=row["realized_pnl"],
                    realized_r_multiple=row["realized_r_multiple"],
                    cumulative_pnl=cumulative_pnl,
                    cumulative_r=cumulative_r,
                )
            )
        return curve

    def max_drawdown_r(self, curve: List[StrategyEquityPoint]) -> float:
        peak = 0.0
        max_dd = 0.0
        for point in curve:
            peak = max(peak, point.cumulative_r)
            max_dd = max(max_dd, peak - point.cumulative_r)
        return max_dd


class LossLimitGuard:
    """Evaluate realized outcome evidence against loss limits."""

    def __init__(
        self,
        *,
        enabled: bool = True,
        max_daily_loss_r: float = 2.0,
        max_weekly_loss_r: float = 4.0,
        max_monthly_loss_r: float = 6.0,
        max_consecutive_losses: int = 3,
        max_drawdown_r: float = 6.0,
    ) -> None:
        self.enabled = enabled
        self.max_daily_loss_r = max_daily_loss_r
        self.max_weekly_loss_r = max_weekly_loss_r
        self.max_monthly_loss_r = max_monthly_loss_r
        self.max_consecutive_losses = max_consecutive_losses
        self.max_drawdown_r = max_drawdown_r
        self.curve_builder = StrategyEquityCurveBuilder()

    def evaluate(
        self,
        records: Iterable[Dict[str, Any]],
        *,
        now: Optional[datetime] = None,
    ) -> LossLimitDecision:
        if not self.enabled:
            return LossLimitDecision(True, "risk lifecycle guard disabled")

        ref = now or datetime.now(timezone.utc)
        records = list(records)
        rows = [_outcome_row(record) for record in records]
        rows = [row for row in rows if row is not None]
        curve = self.curve_builder.build(records)
        daily_r = _sum_since(rows, ref - timedelta(days=1))
        weekly_r = _sum_since(rows, ref - timedelta(days=7))
        monthly_r = _sum_since(rows, ref - timedelta(days=30))
        consecutive_losses = _consecutive_losses(rows)
        max_dd = self.curve_builder.max_drawdown_r(curve)
        curve_dict = [point.to_dict() for point in curve]

        if self.max_daily_loss_r > 0 and daily_r <= -abs(self.max_daily_loss_r):
            return LossLimitDecision(False, f"daily loss {daily_r:.2f}R breached limit", daily_r, weekly_r, monthly_r, consecutive_losses, max_dd, curve_dict)
        if self.max_weekly_loss_r > 0 and weekly_r <= -abs(self.max_weekly_loss_r):
            return LossLimitDecision(False, f"weekly loss {weekly_r:.2f}R breached limit", daily_r, weekly_r, monthly_r, consecutive_losses, max_dd, curve_dict)
        if self.max_monthly_loss_r > 0 and monthly_r <= -abs(self.max_monthly_loss_r):
            return LossLimitDecision(False, f"monthly loss {monthly_r:.2f}R breached limit", daily_r, weekly_r, monthly_r, consecutive_losses, max_dd, curve_dict)
        if consecutive_losses >= self.max_consecutive_losses > 0:
            return LossLimitDecision(False, f"consecutive losses {consecutive_losses} breached limit", daily_r, weekly_r, monthly_r, consecutive_losses, max_dd, curve_dict)
        if max_dd >= self.max_drawdown_r > 0:
            return LossLimitDecision(False, f"max drawdown {max_dd:.2f}R breached limit", daily_r, weekly_r, monthly_r, consecutive_losses, max_dd, curve_dict)

        return LossLimitDecision(True, "risk lifecycle limits clear", daily_r, weekly_r, monthly_r, consecutive_losses, max_dd, curve_dict)


def _outcome_row(record: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if record.get("evidence_type") != "autonomous_outcome":
        return None
    outcome = record.get("outcome") or {}
    if not outcome.get("realized"):
        return None
    r_value = _float(outcome.get("realized_r_multiple"))
    pnl = _float(outcome.get("realized_pnl")) or 0.0
    if r_value is None:
        return None
    ts = _parse_ts(record.get("timestamp"))
    return {
        "timestamp": ts,
        "symbol": str(record.get("symbol") or ""),
        "realized_pnl": pnl,
        "realized_r_multiple": r_value,
    }


def _sum_since(rows: List[Dict[str, Any]], cutoff: datetime) -> float:
    return sum(row["realized_r_multiple"] for row in rows if row["timestamp"] >= cutoff)


def _consecutive_losses(rows: List[Dict[str, Any]]) -> int:
    ordered = sorted(rows, key=lambda row: row["timestamp"], reverse=True)
    count = 0
    for row in ordered:
        if row["realized_r_multiple"] < 0:
            count += 1
            continue
        break
    return count


def _parse_ts(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value)
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
        except ValueError:
            pass
    return datetime.now(timezone.utc)


def _float(value: Any) -> Optional[float]:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
