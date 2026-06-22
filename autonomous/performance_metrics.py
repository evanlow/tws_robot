"""Performance metrics for realized autonomous outcome evidence.

This module is analytics-only.  It summarizes realized outcome records for
evidence learning and does not alter sizing, risk gates, or execution behavior.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from statistics import median
from typing import Any, Dict, Iterable, List, Optional

from autonomous.evidence_utils import _realized_r


@dataclass(frozen=True)
class PerformanceOutcome:
    """Normalized realized outcome used for metric calculation."""

    timestamp: datetime
    symbol: str
    r_multiple: float
    realized_pnl: float = 0.0
    slippage_pct: Optional[float] = None
    commission: float = 0.0
    partial_fill: bool = False

    @property
    def slippage_bps(self) -> Optional[float]:
        if self.slippage_pct is None:
            return None
        return abs(self.slippage_pct) * 10_000.0


@dataclass
class PerformanceMetrics:
    """Risk-adjusted and trade-quality metrics from realized outcomes."""

    trade_count: int
    win_count: int
    loss_count: int
    breakeven_count: int
    win_rate: float
    avg_r: float
    median_r: float
    total_r: float
    avg_win_r: float
    avg_loss_r: float
    expected_r: float
    profit_factor: float
    sharpe: Optional[float]
    rolling_sharpe: Optional[float]
    sortino: Optional[float]
    max_drawdown_r: float
    consecutive_losses: int
    downside_deviation: Optional[float]
    volatility_r: Optional[float]
    avg_slippage_bps: Optional[float]
    max_slippage_bps: Optional[float]
    avg_commission: Optional[float]
    total_commission: float
    partial_fill_rate: float
    outcomes: List[PerformanceOutcome] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "trade_count": self.trade_count,
            "win_count": self.win_count,
            "loss_count": self.loss_count,
            "breakeven_count": self.breakeven_count,
            "win_rate": round(self.win_rate, 6),
            "avg_r": round(self.avg_r, 6),
            "median_r": round(self.median_r, 6),
            "total_r": round(self.total_r, 6),
            "avg_win_r": round(self.avg_win_r, 6),
            "avg_loss_r": round(self.avg_loss_r, 6),
            "expected_r": round(self.expected_r, 6),
            "profit_factor": _round_optional(self.profit_factor),
            "profit_factor_unbounded": math.isinf(self.profit_factor),
            "sharpe": _round_optional(self.sharpe),
            "rolling_sharpe": _round_optional(self.rolling_sharpe),
            "sortino": _round_optional(self.sortino),
            "max_drawdown_r": round(self.max_drawdown_r, 6),
            "consecutive_losses": self.consecutive_losses,
            "downside_deviation": _round_optional(self.downside_deviation),
            "volatility_r": _round_optional(self.volatility_r),
            "avg_slippage_bps": _round_optional(self.avg_slippage_bps),
            "max_slippage_bps": _round_optional(self.max_slippage_bps),
            "avg_commission": _round_optional(self.avg_commission),
            "total_commission": round(self.total_commission, 6),
            "partial_fill_rate": round(self.partial_fill_rate, 6),
        }


class PerformanceMetricsCalculator:
    """Calculate EL1 metrics from realized autonomous evidence."""

    def __init__(self, *, rolling_window: int = 30) -> None:
        self.rolling_window = max(1, int(rolling_window or 30))

    def outcomes_from_records(self, records: Iterable[Dict[str, Any]]) -> List[PerformanceOutcome]:
        outcomes = [_outcome_from_record(record) for record in records]
        out = [row for row in outcomes if row is not None]
        out.sort(key=lambda row: row.timestamp)
        return out

    def calculate(self, records: Iterable[Dict[str, Any]]) -> PerformanceMetrics:
        outcomes = self.outcomes_from_records(records)
        values = [row.r_multiple for row in outcomes]
        wins = [value for value in values if value > 0]
        losses = [value for value in values if value < 0]
        breakeven = [value for value in values if value == 0]
        trade_count = len(values)
        total_r = sum(values)
        avg_r = total_r / trade_count if trade_count else 0.0
        slippage_values = [
            row.slippage_bps for row in outcomes if row.slippage_bps is not None
        ]
        total_commission = sum(row.commission for row in outcomes)

        return PerformanceMetrics(
            trade_count=trade_count,
            win_count=len(wins),
            loss_count=len(losses),
            breakeven_count=len(breakeven),
            win_rate=len(wins) / trade_count if trade_count else 0.0,
            avg_r=avg_r,
            median_r=median(values) if values else 0.0,
            total_r=total_r,
            avg_win_r=sum(wins) / len(wins) if wins else 0.0,
            avg_loss_r=sum(losses) / len(losses) if losses else 0.0,
            expected_r=avg_r,
            profit_factor=_profit_factor(wins, losses),
            sharpe=_sharpe(values),
            rolling_sharpe=_sharpe(values[-self.rolling_window:]),
            sortino=_sortino(values),
            max_drawdown_r=_max_drawdown(values),
            consecutive_losses=_consecutive_losses(outcomes),
            downside_deviation=_downside_deviation(values),
            volatility_r=_sample_stdev(values),
            avg_slippage_bps=(sum(slippage_values) / len(slippage_values)) if slippage_values else None,
            max_slippage_bps=max(slippage_values) if slippage_values else None,
            avg_commission=(total_commission / trade_count) if trade_count else None,
            total_commission=total_commission,
            partial_fill_rate=(
                sum(1 for row in outcomes if row.partial_fill) / trade_count if trade_count else 0.0
            ),
            outcomes=outcomes,
        )


def calculate_performance_metrics(
    records: Iterable[Dict[str, Any]],
    *,
    rolling_window: int = 30,
) -> PerformanceMetrics:
    """Convenience wrapper for calculating EL1 metrics."""

    return PerformanceMetricsCalculator(rolling_window=rolling_window).calculate(records)


def _outcome_from_record(record: Dict[str, Any]) -> Optional[PerformanceOutcome]:
    r_multiple = _realized_r(record)
    if r_multiple is None:
        return None
    outcome = record.get("outcome") or {}
    raw_commission = outcome.get("commission")
    # Fall back to total_commission only when commission is absent entirely;
    # an explicit commission=0.0 must be preserved to avoid inflating totals.
    commission_value = raw_commission if raw_commission is not None else outcome.get("total_commission")
    return PerformanceOutcome(
        timestamp=_parse_ts(record.get("timestamp")),
        symbol=str(record.get("symbol") or ""),
        r_multiple=r_multiple,
        realized_pnl=_float(outcome.get("realized_pnl")) or 0.0,
        slippage_pct=_slippage_pct(outcome),
        commission=_float(commission_value) or 0.0,
        partial_fill=bool(outcome.get("partial_fill")),
    )


def _slippage_pct(outcome: Dict[str, Any]) -> Optional[float]:
    values = [
        _float(outcome.get("entry_slippage_pct")),
        _float(outcome.get("exit_slippage_pct")),
        _float(outcome.get("slippage_pct")),
        _float(outcome.get("avg_slippage_pct")),
    ]
    values = [value for value in values if value is not None]
    if not values:
        return None
    return sum(abs(v) for v in values) / len(values)


def _profit_factor(wins: List[float], losses: List[float]) -> float:
    gross_profit = sum(wins)
    gross_loss = abs(sum(losses))
    if gross_loss == 0:
        return float("inf") if gross_profit > 0 else 0.0
    return gross_profit / gross_loss


def _max_drawdown(values: List[float]) -> float:
    equity = 0.0
    peak = 0.0
    max_dd = 0.0
    for value in values:
        equity += value
        peak = max(peak, equity)
        max_dd = max(max_dd, peak - equity)
    return max_dd


def _consecutive_losses(outcomes: List[PerformanceOutcome]) -> int:
    max_count = 0
    count = 0
    for row in sorted(outcomes, key=lambda item: item.timestamp):
        if row.r_multiple < 0:
            count += 1
            max_count = max(max_count, count)
        else:
            count = 0
    return max_count


def _sharpe(values: List[float]) -> Optional[float]:
    stdev = _sample_stdev(values)
    if stdev is None or stdev == 0:
        return None
    avg = sum(values) / len(values)
    return avg / stdev * math.sqrt(len(values))


def _sortino(values: List[float]) -> Optional[float]:
    downside_dev = _downside_deviation(values)
    if downside_dev is None or downside_dev == 0:
        return None
    avg = sum(values) / len(values)
    return avg / downside_dev * math.sqrt(len(values))


def _downside_deviation(values: List[float]) -> Optional[float]:
    if not values or not any(value < 0 for value in values):
        return None
    downside = [min(0.0, value) for value in values]
    variance = sum(value * value for value in downside) / len(downside)
    return math.sqrt(variance)


def _sample_stdev(values: List[float]) -> Optional[float]:
    if len(values) < 2:
        return None
    avg = sum(values) / len(values)
    variance = sum((value - avg) ** 2 for value in values) / (len(values) - 1)
    return math.sqrt(variance)


def _parse_ts(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
        except ValueError:
            pass
    return datetime.min.replace(tzinfo=timezone.utc)


def _float(value: Any) -> Optional[float]:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if math.isfinite(out) else None


def _round_optional(value: Optional[float]) -> Optional[float]:
    if value is None:
        return None
    if math.isinf(value):
        return None
    return round(value, 6)
