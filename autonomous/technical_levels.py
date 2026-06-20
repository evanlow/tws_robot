"""Support/resistance helpers for autonomous trading signals.

These functions are intentionally pure and data-feed agnostic.  They consume
OHLC bars and return candidate technical levels that downstream planners can use
for stop and target construction.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional


def _as_float(value: Any) -> Optional[float]:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if out > 0 else None


def compute_support_resistance_levels(
    daily_bars: List[Dict[str, Any]],
    current_price: float,
    *,
    lookback_days: int = 30,
    support_buffer_pct: float = 0.005,
    resistance_buffer_pct: float = 0.005,
) -> Dict[str, Any]:
    """Return technical support/resistance levels around ``current_price``.

    Support is selected as the nearest recent low below current price.
    Resistance is selected as the nearest recent high above current price.

    A small buffer avoids treating a same-price tick as a valid level.  Returned
    values are rounded to two decimals for order-planning compatibility.
    """

    if current_price <= 0 or lookback_days <= 0:
        return _empty("invalid inputs")

    bars = [b for b in daily_bars if isinstance(b, dict)][-lookback_days:]
    if len(bars) < 5:
        return _empty("insufficient bars")

    support_candidates = []
    resistance_candidates = []
    support_cutoff = current_price * (1.0 - support_buffer_pct)
    resistance_cutoff = current_price * (1.0 + resistance_buffer_pct)

    for bar in bars:
        low = _as_float(bar.get("low"))
        high = _as_float(bar.get("high"))
        if low is not None and low <= support_cutoff:
            support_candidates.append(low)
        if high is not None and high >= resistance_cutoff:
            resistance_candidates.append(high)

    support = max(support_candidates) if support_candidates else None
    resistance = min(resistance_candidates) if resistance_candidates else None

    sources = []
    if support is not None:
        sources.append("nearest_recent_low_below_price")
    if resistance is not None:
        sources.append("nearest_recent_high_above_price")

    return {
        "support_price": round(support, 2) if support is not None else None,
        "resistance_price": round(resistance, 2) if resistance is not None else None,
        "support_source": "nearest_recent_low_below_price" if support is not None else None,
        "resistance_source": "nearest_recent_high_above_price" if resistance is not None else None,
        "lookback_days": lookback_days,
        "bars_used": len(bars),
        "valid": support is not None or resistance is not None,
        "reason": "; ".join(sources) if sources else "no valid levels around current price",
    }


def _empty(reason: str) -> Dict[str, Any]:
    return {
        "support_price": None,
        "resistance_price": None,
        "support_source": None,
        "resistance_source": None,
        "lookback_days": None,
        "bars_used": 0,
        "valid": False,
        "reason": reason,
    }
