"""Valuation Service — estimates fair value range for a stock.

Uses trailing/forward P/E and analyst targets (where available) to produce
a blended fair value range.  Returns a structured dict suitable for the
Stock Analysis API response.
"""

import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


def estimate_fair_value(
    fundamentals: Dict[str, Any],
    current_price: Optional[float] = None,
) -> Dict[str, Any]:
    """Estimate a fair value range from fundamental data.

    Parameters
    ----------
    fundamentals : dict
        Output of ``data.fundamentals.fetch_fundamentals`` or equivalent.
    current_price : float, optional
        Override current price (otherwise uses fundamentals' value).

    Returns
    -------
    dict
        Keys: low, high, method, status, confidence, methods_used, unavailable_reason
    """
    price = current_price or fundamentals.get("current_price")
    if not price or price <= 0:
        return _unavailable("Current price unavailable")

    methods_used = []
    estimates = []

    # --- Method 1: Historical P/E ---
    eps_trailing = fundamentals.get("eps_trailing")
    pe_trailing = fundamentals.get("pe_trailing")
    if eps_trailing and eps_trailing > 0 and pe_trailing and pe_trailing > 0:
        # Use a range around the trailing P/E (±20% band)
        low_pe = pe_trailing * 0.8
        high_pe = pe_trailing * 1.2
        est_low = eps_trailing * low_pe
        est_high = eps_trailing * high_pe
        if est_low > 0 and est_high > 0:
            estimates.append((est_low, est_high))
            methods_used.append("historical_pe")

    # --- Method 2: Forward P/E ---
    eps_forward = fundamentals.get("eps_forward")
    pe_forward = fundamentals.get("pe_forward")
    if eps_forward and eps_forward > 0 and pe_forward and pe_forward > 0:
        low_pe = pe_forward * 0.85
        high_pe = pe_forward * 1.15
        est_low = eps_forward * low_pe
        est_high = eps_forward * high_pe
        if est_low > 0 and est_high > 0:
            estimates.append((est_low, est_high))
            methods_used.append("forward_pe")

    # --- Method 3: Analyst targets ---
    target_low = fundamentals.get("target_low_price")
    target_high = fundamentals.get("target_high_price")
    target_mean = fundamentals.get("target_mean_price")
    if target_mean and target_mean > 0:
        low = target_low if (target_low and target_low > 0) else target_mean * 0.9
        high = target_high if (target_high and target_high > 0) else target_mean * 1.1
        estimates.append((low, high))
        methods_used.append("analyst_targets")

    if not estimates:
        return _unavailable(
            "Fair value estimate unavailable due to insufficient earnings/valuation data."
        )

    # Blend: average of lows and average of highs
    blended_low = sum(e[0] for e in estimates) / len(estimates)
    blended_high = sum(e[1] for e in estimates) / len(estimates)

    # Ensure low < high
    if blended_low > blended_high:
        blended_low, blended_high = blended_high, blended_low

    # Round to 2 decimals
    blended_low = round(blended_low, 2)
    blended_high = round(blended_high, 2)

    # Determine valuation status
    status = _valuation_status(price, blended_low, blended_high)

    # Confidence based on number of methods
    confidence = "low" if len(methods_used) == 1 else ("medium" if len(methods_used) == 2 else "high")

    return {
        "low": blended_low,
        "high": blended_high,
        "method": "blended_pe" if len(methods_used) > 1 else methods_used[0],
        "status": status,
        "confidence": confidence,
        "methods_used": methods_used,
        "unavailable_reason": None,
    }


def _valuation_status(price: float, fair_low: float, fair_high: float) -> str:
    """Classify current price relative to fair value range."""
    if price < fair_low:
        return "potentially_undervalued"
    elif price > fair_high:
        return "potentially_overvalued"
    else:
        return "fairly_valued"


def _unavailable(reason: str) -> Dict[str, Any]:
    """Return a standard unavailable response."""
    return {
        "low": None,
        "high": None,
        "method": None,
        "status": "unavailable",
        "confidence": None,
        "methods_used": [],
        "unavailable_reason": reason,
    }
