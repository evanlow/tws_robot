"""Validation framework for autonomous strategy promotion decisions.

The validation framework summarizes realized evidence records and produces a
promotion report.  It is intentionally advisory; it does not auto-promote live
capital limits.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional


@dataclass
class ValidationThresholds:
    """Promotion thresholds for a strategy bucket or full strategy."""

    min_trades: int = 30
    min_avg_r: float = 0.05
    min_win_rate: float = 0.45
    max_drawdown_r: float = 6.0


@dataclass
class ValidationReport:
    """Validation result from realized evidence."""

    trades: int
    wins: int
    losses: int
    win_rate: float
    avg_r: float
    total_r: float
    max_drawdown_r: float
    passed: bool
    reasons: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "trades": self.trades,
            "wins": self.wins,
            "losses": self.losses,
            "win_rate": round(self.win_rate, 6),
            "avg_r": round(self.avg_r, 6),
            "total_r": round(self.total_r, 6),
            "max_drawdown_r": round(self.max_drawdown_r, 6),
            "passed": self.passed,
            "reasons": list(self.reasons),
        }


class ValidationFramework:
    """Evaluate realized evidence against promotion thresholds."""

    def __init__(self, thresholds: Optional[ValidationThresholds] = None) -> None:
        self.thresholds = thresholds or ValidationThresholds()

    def evaluate(self, records: Iterable[Dict[str, Any]]) -> ValidationReport:
        values: List[float] = []
        for record in records:
            r = _realized_r(record)
            if r is not None:
                values.append(r)

        trades = len(values)
        wins = sum(1 for v in values if v > 0)
        losses = trades - wins
        total_r = sum(values)
        avg_r = total_r / trades if trades else 0.0
        win_rate = wins / trades if trades else 0.0
        max_dd = _max_drawdown(values)

        reasons: List[str] = []
        t = self.thresholds
        if trades < t.min_trades:
            reasons.append(f"trades {trades} < min {t.min_trades}")
        if avg_r < t.min_avg_r:
            reasons.append(f"avg_r {avg_r:.4f} < min {t.min_avg_r:.4f}")
        if win_rate < t.min_win_rate:
            reasons.append(f"win_rate {win_rate:.4f} < min {t.min_win_rate:.4f}")
        if max_dd > t.max_drawdown_r:
            reasons.append(f"max_drawdown_r {max_dd:.4f} > max {t.max_drawdown_r:.4f}")

        passed = not reasons
        if passed:
            reasons.append("validation thresholds passed")

        return ValidationReport(
            trades=trades,
            wins=wins,
            losses=losses,
            win_rate=win_rate,
            avg_r=avg_r,
            total_r=total_r,
            max_drawdown_r=max_dd,
            passed=passed,
            reasons=reasons,
        )


def _realized_r(record: Dict[str, Any]) -> Optional[float]:
    outcome = record.get("outcome") or {}
    if not outcome.get("realized"):
        return None
    try:
        return float(outcome.get("realized_r_multiple"))
    except (TypeError, ValueError):
        return None


def _max_drawdown(values: List[float]) -> float:
    equity = 0.0
    peak = 0.0
    max_dd = 0.0
    for value in values:
        equity += value
        peak = max(peak, equity)
        max_dd = max(max_dd, peak - equity)
    return max_dd
