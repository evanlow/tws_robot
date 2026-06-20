"""Fractional edge-based sizing helper.

The helper converts an edge estimate into an optional cap. It is conservative:
it is disabled by default, requires a minimum evidence count before applying a
positive cap, and cannot widen an existing cap unless explicitly allowed.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional


@dataclass
class FractionalSizingDecision:
    enabled: bool
    applied: bool
    raw_fraction: float = 0.0
    adjusted_fraction: float = 0.0
    cap_value: Optional[float] = None
    reasons: list[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "enabled": self.enabled,
            "applied": self.applied,
            "raw_fraction": round(self.raw_fraction, 6),
            "adjusted_fraction": round(self.adjusted_fraction, 6),
            "cap_value": round(self.cap_value, 2) if self.cap_value is not None else None,
            "reasons": list(self.reasons),
        }


class FractionalEdgeSizer:
    """Compute an optional fractional edge cap from an edge estimate."""

    def __init__(
        self,
        *,
        enabled: bool = False,
        fraction: float = 0.10,
        min_trades: int = 100,
        max_position_pct: float = 0.01,
        retirement_mode_max_pct: float = 0.005,
        allow_size_increase: bool = False,
        can_reduce_size: bool = True,
    ) -> None:
        self.enabled = enabled
        self.fraction = fraction
        self.min_trades = min_trades
        self.max_position_pct = max_position_pct
        self.retirement_mode_max_pct = retirement_mode_max_pct
        self.allow_size_increase = allow_size_increase
        self.can_reduce_size = can_reduce_size

    def evaluate(
        self,
        *,
        equity: float,
        current_cap_value: float,
        edge_estimate: Optional[Dict[str, Any]],
        observed_trades: int = 0,
    ) -> FractionalSizingDecision:
        if not self.enabled:
            return FractionalSizingDecision(False, False, reasons=["fractional edge sizing disabled"])
        if not edge_estimate:
            return FractionalSizingDecision(True, False, reasons=["edge estimate unavailable"])

        p = _num(edge_estimate.get("p_win"))
        avg_win_r = _num(edge_estimate.get("avg_win_r"))
        avg_loss_r = _num(edge_estimate.get("avg_loss_r"))
        confidence = _num(edge_estimate.get("confidence")) or 0.0
        if p is None or avg_win_r is None or avg_loss_r is None or avg_loss_r <= 0:
            return FractionalSizingDecision(True, False, reasons=["edge estimate incomplete"])

        b = avg_win_r / avg_loss_r
        raw = p - ((1.0 - p) / b) if b > 0 else 0.0
        adjusted = max(0.0, raw) * self.fraction * max(0.0, min(1.0, confidence))
        max_pct = min(self.max_position_pct, self.retirement_mode_max_pct)
        final_fraction = min(max_pct, adjusted)
        cap_value = max(0.0, equity * final_fraction)
        reasons = [
            f"raw_fraction={raw:.4f}",
            f"adjusted_fraction={adjusted:.4f}",
            f"observed_trades={observed_trades}",
        ]

        if raw <= 0:
            if self.can_reduce_size:
                return FractionalSizingDecision(
                    True,
                    True,
                    raw_fraction=raw,
                    adjusted_fraction=final_fraction,
                    cap_value=0.0,
                    reasons=reasons + ["non-positive fraction; reduce to zero"],
                )
            return FractionalSizingDecision(True, False, raw_fraction=raw, reasons=reasons)

        if observed_trades < self.min_trades:
            return FractionalSizingDecision(
                True,
                False,
                raw_fraction=raw,
                adjusted_fraction=final_fraction,
                cap_value=cap_value,
                reasons=reasons + [f"insufficient evidence; need {self.min_trades} trades"],
            )

        if not self.allow_size_increase and cap_value >= current_cap_value:
            return FractionalSizingDecision(
                True,
                False,
                raw_fraction=raw,
                adjusted_fraction=final_fraction,
                cap_value=cap_value,
                reasons=reasons + ["cap above current cap; increase not allowed"],
            )

        return FractionalSizingDecision(
            True,
            True,
            raw_fraction=raw,
            adjusted_fraction=final_fraction,
            cap_value=cap_value,
            reasons=reasons,
        )


def _num(value: Any) -> Optional[float]:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
