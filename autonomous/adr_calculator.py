"""Average Daily Range (ADR) calculator for autonomous target pricing.

Computes a stock's ADR from recent daily high/low data and derives
an intraday target price suitable for same-day exits.

The calculator is intentionally pure: it takes a list of daily bars
(dicts with ``high`` and ``low`` keys) and returns an :class:`ADRResult`
dataclass.  No I/O, no side effects, no broker calls.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Dict, List, Optional


@dataclass
class ADRResult:
    """Result of an ADR calculation for a single symbol."""

    adr: float  # average daily range in price terms
    adr_pct: float  # adr / reference_price
    lookback_days_used: int  # actual number of bars used
    valid: bool  # True if calculation produced a usable result

    def to_dict(self) -> Dict[str, Any]:
        return {
            "adr": round(self.adr, 4),
            "adr_pct": round(self.adr_pct, 6),
            "lookback_days_used": self.lookback_days_used,
            "valid": self.valid,
        }


def calculate_adr(
    daily_bars: List[Dict[str, Any]],
    reference_price: float,
    lookback_days: int = 14,
    min_bars_required: int = 5,
) -> ADRResult:
    """Calculate ADR from a list of daily OHLCV bar dicts.

    Parameters
    ----------
    daily_bars:
        List of dicts with at least ``high`` and ``low`` keys.
        Expected sorted oldest→newest (only the last *lookback_days*
        bars are used).
    reference_price:
        Current/last price for computing ADR%.  Must be > 0.
    lookback_days:
        Number of recent trading days to average over.
    min_bars_required:
        Minimum number of valid bars needed to produce a result.
        If fewer bars are available, returns ``valid=False``.

    Returns
    -------
    ADRResult with ``valid=True`` when computation succeeded, or
    ``valid=False`` with zeroed fields on insufficient data.
    """
    if reference_price <= 0 or not daily_bars:
        return ADRResult(adr=0.0, adr_pct=0.0, lookback_days_used=0, valid=False)

    # Take the last N bars
    recent = daily_bars[-lookback_days:]

    # Filter to bars with valid high/low
    ranges: List[float] = []
    for bar in recent:
        high = bar.get("high")
        low = bar.get("low")
        if high is None or low is None:
            continue
        try:
            h = float(high)
            lo = float(low)
        except (TypeError, ValueError):
            continue
        if not (math.isfinite(h) and math.isfinite(lo)):
            continue
        if h <= 0 or lo <= 0 or h < lo:
            continue
        ranges.append(h - lo)

    if len(ranges) < min_bars_required:
        return ADRResult(adr=0.0, adr_pct=0.0, lookback_days_used=len(ranges), valid=False)

    adr = sum(ranges) / len(ranges)
    adr_pct = adr / reference_price

    return ADRResult(
        adr=adr,
        adr_pct=adr_pct,
        lookback_days_used=len(ranges),
        valid=True,
    )


def compute_adr_target_price(
    entry_price: float,
    adr: float,
    target_fraction: float = 0.50,
    min_target_pct: float = 0.005,
    max_target_pct: float = 0.03,
    resistance_price: Optional[float] = None,
    respect_resistance_cap: bool = True,
) -> Optional[float]:
    """Derive an intraday target price from ADR.

    Parameters
    ----------
    entry_price:
        The planned entry / limit price.  Must be > 0.
    adr:
        Average daily range in price terms.  Must be > 0.
    target_fraction:
        Fraction of ADR to target (e.g. 0.50 = half the daily range).
    min_target_pct:
        Floor for the target move as a fraction of entry_price.
    max_target_pct:
        Cap for the target move as a fraction of entry_price.
    resistance_price:
        Optional resistance level.  When provided and
        ``respect_resistance_cap=True``, the target is capped at
        resistance (never placed above a known ceiling).
    respect_resistance_cap:
        Whether to cap the target at resistance_price.

    Returns
    -------
    The computed target price, or ``None`` if inputs are invalid.
    The target is guaranteed > entry_price for valid inputs.
    """
    if entry_price <= 0 or adr <= 0 or target_fraction <= 0:
        return None

    target_move = adr * target_fraction
    target_move_pct = target_move / entry_price

    # Clamp to [min_target_pct, max_target_pct]
    clamped_pct = max(min_target_pct, min(target_move_pct, max_target_pct))
    target_price = entry_price * (1.0 + clamped_pct)

    # Respect resistance cap if configured
    if (
        respect_resistance_cap
        and resistance_price is not None
        and resistance_price > entry_price
        and target_price > resistance_price
    ):
        target_price = resistance_price

    # Final safety: target must be above entry
    if target_price <= entry_price:
        # Apply minimum floor to ensure target > entry
        target_price = entry_price * (1.0 + min_target_pct)

    return round(target_price, 2)
