"""Commission-aware minimum-profitability gate for autonomous trades.

A directionally correct trade can still finish net negative when the share
quantity is too small relative to round-trip broker commissions.  This guard
estimates the expected net result of a planned share buy *before* it is
submitted and rejects trades whose expected net profit (gross profit at target
minus estimated entry and exit commissions) falls below a configured minimum.

The guard is intentionally conservative: when the exact broker commission is
unknown ahead of submission it uses a flat ``estimated_commission_per_order``
estimate per leg, and it refuses (fail-closed) any plan that does not present a
positive expected gross profit at its target price.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Dict, Optional


@dataclass
class ProfitabilityDecision:
    """Result of checking whether a planned trade clears commissions."""

    allowed: bool
    reason: str
    quantity: Optional[int] = None
    entry_price: Optional[float] = None
    target_price: Optional[float] = None
    gross_profit: Optional[float] = None
    entry_commission: Optional[float] = None
    exit_commission: Optional[float] = None
    round_trip_commission: Optional[float] = None
    net_profit: Optional[float] = None
    required_net_profit: Optional[float] = None
    min_quantity_for_profit: Optional[int] = None
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        def _r(value: Optional[float]) -> Optional[float]:
            return round(value, 4) if value is not None else None

        return {
            "allowed": self.allowed,
            "reason": self.reason,
            "quantity": self.quantity,
            "entry_price": _r(self.entry_price),
            "target_price": _r(self.target_price),
            "gross_profit": _r(self.gross_profit),
            "entry_commission": _r(self.entry_commission),
            "exit_commission": _r(self.exit_commission),
            "round_trip_commission": _r(self.round_trip_commission),
            "net_profit": _r(self.net_profit),
            "required_net_profit": _r(self.required_net_profit),
            "min_quantity_for_profit": self.min_quantity_for_profit,
            "warnings": list(self.warnings),
        }


class ProfitabilityGate:
    """Estimate commission-adjusted net profit before order submission."""

    def __init__(
        self,
        *,
        enabled: bool = False,
        estimated_commission_per_order: float = 1.0,
        min_net_profit_usd: float = 0.0,
        min_net_profit_pct_of_trade: float = 0.0,
    ) -> None:
        self.enabled = enabled
        self.estimated_commission_per_order = max(0.0, float(estimated_commission_per_order))
        self.min_net_profit_usd = max(0.0, float(min_net_profit_usd))
        self.min_net_profit_pct_of_trade = max(0.0, float(min_net_profit_pct_of_trade))

    def evaluate_buy_shares(
        self,
        *,
        symbol: str,
        quantity: int,
        entry_price: float,
        target_price: Optional[float],
    ) -> ProfitabilityDecision:
        """Evaluate a planned BUY_SHARES leg against commission economics."""

        if not self.enabled:
            return ProfitabilityDecision(True, "commission-aware profitability gate disabled")

        try:
            qty = int(quantity)
        except (TypeError, ValueError):
            qty = 0
        entry = _positive_float(entry_price)
        target = _positive_float(target_price)

        if qty <= 0 or entry is None:
            # No tradable size / price to evaluate — leave the decision to the
            # other sizing and cash gates rather than inventing economics here.
            return ProfitabilityDecision(
                True,
                f"{symbol}: profitability gate skipped (no quantity/price to evaluate)",
            )

        entry_commission = self.estimated_commission_per_order
        exit_commission = self.estimated_commission_per_order
        round_trip = entry_commission + exit_commission
        trade_value = entry * qty
        required = max(self.min_net_profit_usd, self.min_net_profit_pct_of_trade * trade_value)

        if target is None or target <= entry:
            return ProfitabilityDecision(
                False,
                (
                    f"{symbol}: no positive expected gross profit "
                    f"(target {('%.4f' % target) if target is not None else 'unavailable'} "
                    f"<= entry {entry:.4f}); cannot clear estimated round-trip "
                    f"commission {round_trip:.2f}"
                ),
                quantity=qty,
                entry_price=entry,
                target_price=target,
                entry_commission=entry_commission,
                exit_commission=exit_commission,
                round_trip_commission=round_trip,
                required_net_profit=required,
            )

        gross_per_share = target - entry
        gross_profit = gross_per_share * qty
        net_profit = gross_profit - round_trip
        min_quantity = self._min_quantity_for_profit(
            gross_per_share=gross_per_share,
            entry=entry,
            round_trip=round_trip,
            required_usd=self.min_net_profit_usd,
            min_pct=self.min_net_profit_pct_of_trade,
        )

        if net_profit < required:
            min_qty_str = (
                f"{min_quantity}" if min_quantity is not None else "unattainable at this target"
            )
            return ProfitabilityDecision(
                False,
                (
                    f"{symbol}: expected net profit {net_profit:.2f} USD "
                    f"(gross {gross_profit:.2f} - round-trip commission {round_trip:.2f}) "
                    f"below minimum {required:.2f} USD for {qty} share(s); "
                    f"min quantity to clear commissions: {min_qty_str}"
                ),
                quantity=qty,
                entry_price=entry,
                target_price=target,
                gross_profit=gross_profit,
                entry_commission=entry_commission,
                exit_commission=exit_commission,
                round_trip_commission=round_trip,
                net_profit=net_profit,
                required_net_profit=required,
                min_quantity_for_profit=min_quantity,
            )

        return ProfitabilityDecision(
            True,
            (
                f"{symbol}: expected net profit {net_profit:.2f} USD clears minimum "
                f"{required:.2f} USD after estimated round-trip commission {round_trip:.2f}"
            ),
            quantity=qty,
            entry_price=entry,
            target_price=target,
            gross_profit=gross_profit,
            entry_commission=entry_commission,
            exit_commission=exit_commission,
            round_trip_commission=round_trip,
            net_profit=net_profit,
            required_net_profit=required,
            min_quantity_for_profit=min_quantity,
        )

    @staticmethod
    def _min_quantity_for_profit(
        *,
        gross_per_share: float,
        entry: float,
        round_trip: float,
        required_usd: float,
        min_pct: float,
    ) -> Optional[int]:
        """Smallest integer quantity whose expected net profit clears both the
        absolute (USD) and percentage thresholds, or ``None`` when no quantity
        can satisfy the percentage threshold at this target."""

        if gross_per_share <= 0:
            return None

        # Absolute-USD threshold: gross_per_share * q - round_trip >= required_usd
        q_usd = (required_usd + round_trip) / gross_per_share

        # Percentage-of-trade threshold:
        #   gross_per_share * q - round_trip >= min_pct * entry * q
        #   q * (gross_per_share - min_pct * entry) >= round_trip
        denom = gross_per_share - min_pct * entry
        if min_pct > 0:
            if denom <= 0:
                return None
            q_pct = round_trip / denom
        else:
            q_pct = 0.0

        q = max(q_usd, q_pct)
        if q <= 0:
            return 1
        # Subtract a tiny epsilon before the ceiling so floating-point rounding
        # error (e.g. an exact integer represented as 4.0000000001) does not
        # inflate the required quantity by one whole share.
        return max(1, math.ceil(q - 1e-9))


def _positive_float(value: Any) -> Optional[float]:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if out > 0 else None
