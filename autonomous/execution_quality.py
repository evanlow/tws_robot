"""Execution-quality guard for autonomous order plans.

The guard evaluates spread, likely slippage, and price-runaway conditions before
an autonomous order is submitted.  It is data-feed agnostic: callers provide a
small market snapshot when available.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional


@dataclass
class ExecutionQualityDecision:
    """Result of checking whether execution quality is acceptable."""

    allowed: bool
    reason: str
    spread_pct: Optional[float] = None
    slippage_pct: Optional[float] = None
    price_move_pct: Optional[float] = None
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "allowed": self.allowed,
            "reason": self.reason,
            "spread_pct": round(self.spread_pct, 6) if self.spread_pct is not None else None,
            "slippage_pct": round(self.slippage_pct, 6) if self.slippage_pct is not None else None,
            "price_move_pct": round(self.price_move_pct, 6) if self.price_move_pct is not None else None,
            "warnings": list(self.warnings),
        }


class ExecutionQualityGuard:
    """Check bid/ask/last quality before order submission."""

    def __init__(
        self,
        *,
        enabled: bool = True,
        max_spread_pct: float = 0.003,
        max_slippage_pct: float = 0.005,
        max_price_move_pct: float = 0.01,
        block_on_missing_quote: bool = False,
    ) -> None:
        self.enabled = enabled
        self.max_spread_pct = max_spread_pct
        self.max_slippage_pct = max_slippage_pct
        self.max_price_move_pct = max_price_move_pct
        self.block_on_missing_quote = block_on_missing_quote

    def evaluate_buy_limit(
        self,
        *,
        symbol: str,
        limit_price: float,
        reference_price: float,
        bid: Any = None,
        ask: Any = None,
        last: Any = None,
    ) -> ExecutionQualityDecision:
        """Evaluate a BUY limit plan against available quote data."""

        if not self.enabled:
            return ExecutionQualityDecision(True, "execution quality guard disabled")

        bid_f = _positive_float(bid)
        ask_f = _positive_float(ask)
        last_f = _positive_float(last) or reference_price
        warnings: list[str] = []
        spread_pct: Optional[float] = None
        slippage_pct: Optional[float] = None

        if bid_f is None or ask_f is None:
            msg = f"{symbol}: bid/ask unavailable"
            if self.block_on_missing_quote:
                return ExecutionQualityDecision(False, msg, warnings=[msg])
            warnings.append(msg)
        else:
            if ask_f < bid_f:
                msg = f"{symbol}: crossed quotes (ask {ask_f} < bid {bid_f})"
                return ExecutionQualityDecision(False, msg, warnings=warnings)
            mid = (bid_f + ask_f) / 2.0
            if mid > 0:
                spread_pct = (ask_f - bid_f) / mid
                if spread_pct > self.max_spread_pct:
                    return ExecutionQualityDecision(
                        False,
                        f"{symbol}: spread {spread_pct:.4%} > max {self.max_spread_pct:.4%}",
                        spread_pct=spread_pct,
                        warnings=warnings,
                    )

            if ask_f > 0 and limit_price > 0:
                slippage_pct = max(0.0, (ask_f - limit_price) / limit_price)
                if slippage_pct > self.max_slippage_pct:
                    return ExecutionQualityDecision(
                        False,
                        f"{symbol}: ask above limit by {slippage_pct:.4%} > max {self.max_slippage_pct:.4%}",
                        spread_pct=spread_pct,
                        slippage_pct=slippage_pct,
                        warnings=warnings,
                    )

        price_move_pct = None
        if last_f is not None and reference_price > 0:
            price_move_pct = max(0.0, (last_f - reference_price) / reference_price)
            if price_move_pct > self.max_price_move_pct:
                return ExecutionQualityDecision(
                    False,
                    f"{symbol}: price moved {price_move_pct:.4%} above reference > max {self.max_price_move_pct:.4%}",
                    price_move_pct=price_move_pct,
                    warnings=warnings,
                )

        return ExecutionQualityDecision(
            True,
            "execution quality acceptable",
            spread_pct=spread_pct,
            slippage_pct=slippage_pct,
            price_move_pct=price_move_pct,
            warnings=warnings,
        )


def _positive_float(value: Any) -> Optional[float]:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if out > 0 else None
