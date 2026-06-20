"""Drawdown-based sizing governor.

The governor translates a strategy drawdown percentage into a sizing multiplier.
It is designed to reduce or halt new exposure when the autonomous strategy is
under pressure.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict


@dataclass
class DrawdownDecision:
    drawdown_pct: float
    multiplier: float
    halted: bool
    reason: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "drawdown_pct": round(self.drawdown_pct, 6),
            "multiplier": round(self.multiplier, 6),
            "halted": self.halted,
            "reason": self.reason,
        }


class DrawdownGovernor:
    """Map current strategy drawdown to an exposure multiplier."""

    def __init__(self, *, enabled: bool = True, current_drawdown_pct: float = 0.0) -> None:
        self.enabled = enabled
        self.current_drawdown_pct = max(0.0, float(current_drawdown_pct or 0.0))

    def evaluate(self, drawdown_pct: float | None = None) -> DrawdownDecision:
        if not self.enabled:
            return DrawdownDecision(0.0, 1.0, False, "drawdown governor disabled")

        dd = self.current_drawdown_pct if drawdown_pct is None else max(0.0, float(drawdown_pct or 0.0))
        if dd > 0.08:
            return DrawdownDecision(dd, 0.0, True, "drawdown above 8%; halt new entries")
        if dd >= 0.06:
            return DrawdownDecision(dd, 0.25, False, "drawdown 6-8%; reduce size to 25%")
        if dd >= 0.04:
            return DrawdownDecision(dd, 0.50, False, "drawdown 4-6%; reduce size to 50%")
        if dd >= 0.02:
            return DrawdownDecision(dd, 0.75, False, "drawdown 2-4%; reduce size to 75%")
        return DrawdownDecision(dd, 1.0, False, "drawdown below 2%; full size allowed")
