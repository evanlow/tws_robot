"""Risk-per-trade and volatility-aware position sizing.

The sizer is deliberately conservative: it can only reduce a base cash/equity
cap.  It never increases exposure beyond the existing hard caps.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Dict, Optional


@dataclass
class SizingDecision:
    """Result of sizing one BUY_SHARES leg."""

    quantity: int
    required_cash: float
    binding_cap: str
    caps: Dict[str, Any] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "quantity": self.quantity,
            "required_cash": round(self.required_cash, 2),
            "binding_cap": self.binding_cap,
            "caps": self.caps,
            "notes": list(self.notes),
        }


class PositionSizer:
    """Compute final share quantity from cash, risk, and volatility caps."""

    def __init__(
        self,
        *,
        risk_per_trade_sizing_enabled: bool = True,
        max_risk_per_trade_equity_pct: float = 0.002,
        volatility_sizing_enabled: bool = True,
        volatility_reference_pct: float = 0.02,
        volatility_min_size_multiplier: float = 0.25,
    ) -> None:
        self.risk_per_trade_sizing_enabled = risk_per_trade_sizing_enabled
        self.max_risk_per_trade_equity_pct = max_risk_per_trade_equity_pct
        self.volatility_sizing_enabled = volatility_sizing_enabled
        self.volatility_reference_pct = volatility_reference_pct
        self.volatility_min_size_multiplier = volatility_min_size_multiplier

    def size_buy_shares(
        self,
        *,
        symbol: str,
        entry_price: float,
        stop_price: Optional[float],
        base_cap_value: float,
        equity: float,
        adr_pct: Optional[float] = None,
    ) -> SizingDecision:
        """Return final quantity and cap diagnostics for one long-share leg."""

        caps: Dict[str, Any] = {
            "base_cap_value": round(base_cap_value, 2),
            "entry_price": entry_price,
            "equity": equity,
        }
        notes: list[str] = []

        cap_values = {"cash_equity_cap": max(0.0, base_cap_value)}

        if self.risk_per_trade_sizing_enabled:
            risk_per_share = None
            if stop_price is not None and stop_price > 0 and entry_price > stop_price:
                risk_per_share = entry_price - stop_price
                max_risk_dollars = max(0.0, equity * self.max_risk_per_trade_equity_pct)
                risk_cap_value = math.floor(max_risk_dollars / risk_per_share) * entry_price
                cap_values["risk_per_trade_cap"] = max(0.0, risk_cap_value)
                caps["risk_per_share"] = round(risk_per_share, 4)
                caps["max_risk_dollars"] = round(max_risk_dollars, 2)
            else:
                notes.append("risk_per_trade sizing skipped: no valid stop_price")
                caps["risk_per_trade_skipped"] = True

        if self.volatility_sizing_enabled:
            vol = _positive_float(adr_pct)
            if vol is not None:
                raw_multiplier = self.volatility_reference_pct / vol
                multiplier = max(self.volatility_min_size_multiplier, min(1.0, raw_multiplier))
                cap_values["volatility_cap"] = base_cap_value * multiplier
                caps["volatility_pct"] = round(vol, 6)
                caps["volatility_reference_pct"] = self.volatility_reference_pct
                caps["volatility_multiplier"] = round(multiplier, 4)
            else:
                notes.append("volatility sizing skipped: adr_pct unavailable")
                caps["volatility_sizing_skipped"] = True

        binding_cap = min(cap_values, key=cap_values.get)
        final_cap = cap_values[binding_cap]
        quantity = int(math.floor(final_cap / entry_price)) if entry_price > 0 else 0
        required_cash = quantity * entry_price
        caps["cap_values"] = {k: round(v, 2) for k, v in cap_values.items()}
        caps["final_cap_value"] = round(final_cap, 2)

        if quantity <= 0:
            notes.append(
                f"{symbol}: final cap ${final_cap:,.2f} cannot buy 1 share at ${entry_price:,.2f}"
            )

        return SizingDecision(
            quantity=quantity,
            required_cash=required_cash,
            binding_cap=binding_cap,
            caps=caps,
            notes=notes,
        )


def _positive_float(value: Any) -> Optional[float]:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if out > 0 else None
