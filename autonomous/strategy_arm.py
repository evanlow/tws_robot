"""Strategy-arm learning analytics.

This module groups realized evidence records into repeatable strategy arms and
scores them with simple, transparent statistics.  It is analytics-only: it does
not automatically change live execution.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional

from autonomous.evidence_utils import _realized_r


@dataclass
class StrategyArmStats:
    """Realized performance for one strategy arm."""

    arm_id: str
    trades: int = 0
    wins: int = 0
    losses: int = 0
    total_r: float = 0.0
    sum_sq_r: float = 0.0

    def add_r(self, r_multiple: float) -> None:
        self.trades += 1
        if r_multiple > 0:
            self.wins += 1
        else:
            self.losses += 1
        self.total_r += r_multiple
        self.sum_sq_r += r_multiple * r_multiple

    @property
    def avg_r(self) -> float:
        return self.total_r / self.trades if self.trades else 0.0

    @property
    def win_rate(self) -> float:
        return self.wins / self.trades if self.trades else 0.0

    @property
    def std_r(self) -> float:
        if self.trades <= 1:
            return 0.0
        mean = self.avg_r
        variance = max(0.0, (self.sum_sq_r / self.trades) - mean * mean)
        return math.sqrt(variance)

    def ucb_score(self, *, total_trades: int, exploration: float = 1.0) -> float:
        if self.trades <= 0:
            return float("inf")
        bonus = exploration * math.sqrt(max(0.0, math.log(max(total_trades, 1)) / self.trades))
        return self.avg_r + bonus

    def to_dict(self, *, total_trades: Optional[int] = None, exploration: float = 1.0) -> Dict[str, Any]:
        out = {
            "arm_id": self.arm_id,
            "trades": self.trades,
            "wins": self.wins,
            "losses": self.losses,
            "win_rate": round(self.win_rate, 6),
            "avg_r": round(self.avg_r, 6),
            "total_r": round(self.total_r, 6),
            "std_r": round(self.std_r, 6),
        }
        if total_trades is not None:
            score = self.ucb_score(total_trades=total_trades, exploration=exploration)
            out["ucb_score"] = score if math.isinf(score) else round(score, 6)
        return out


class StrategyArmLearner:
    """Build strategy-arm statistics from evidence records."""

    def __init__(self, *, exploration: float = 1.0) -> None:
        self.exploration = exploration

    def arm_id_for_record(self, record: Dict[str, Any]) -> str:
        bucket = record.get("strategy_bucket") or {}
        parts = [
            bucket.get("signal_label") or "unknown_signal",
            bucket.get("quality_label") or "unknown_quality",
            bucket.get("momentum_label") or "unknown_momentum",
            bucket.get("market_classification") or "unknown_market",
            bucket.get("vix_level_regime") or "unknown_vix",
        ]
        return "|".join(str(p) for p in parts)

    def build_stats(self, records: Iterable[Dict[str, Any]]) -> Dict[str, StrategyArmStats]:
        arms: Dict[str, StrategyArmStats] = {}
        for record in records:
            r_multiple = _realized_r(record)
            if r_multiple is None:
                continue
            arm_id = self.arm_id_for_record(record)
            arms.setdefault(arm_id, StrategyArmStats(arm_id=arm_id)).add_r(r_multiple)
        return arms

    def rank_arms(self, records: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
        arms = self.build_stats(records)
        total = sum(arm.trades for arm in arms.values())
        ranked = [
            arm.to_dict(total_trades=total, exploration=self.exploration)
            for arm in arms.values()
        ]
        ranked.sort(key=lambda row: row.get("ucb_score", row.get("avg_r", 0.0)), reverse=True)
        return ranked
