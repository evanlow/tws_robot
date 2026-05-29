"""Shared technical analysis helpers.

Contains pure-function utilities that are used by both the single-ticker
stock analysis API and the S&P 500 screener service.
"""

from typing import Any, Dict, List, Optional

import numpy as np

# Human-readable labels for each Bollinger Bands status code.
BOLLINGER_STATUS_LABELS: Dict[str, str] = {
    "below_lower_band": "Oversold",
    "near_lower_band": "Near Oversold",
    "within_bands": "Neutral",
    "near_upper_band": "Near Overbought",
    "above_upper_band": "Overbought",
    "insufficient_data": "Insufficient Data",
}

# Numeric rank used for default sort (lower = more oversold → shown first in
# "opportunity" sort; higher = more overbought → shown first in "risk" sort).
BOLLINGER_STATUS_RANK: Dict[str, int] = {
    "below_lower_band": 0,
    "near_lower_band": 1,
    "within_bands": 2,
    "near_upper_band": 3,
    "above_upper_band": 4,
    "insufficient_data": 5,
}


def compute_bollinger_bands(
    bars: List[Dict[str, Any]],
    current_price: float,
    period: int = 20,
    std_dev: float = 2.0,
) -> Dict[str, Any]:
    """Compute Bollinger Bands from OHLCV bars.

    Parameters
    ----------
    bars : list[dict]
        OHLCV bars sorted oldest→newest.
    current_price : float
        Current price for %B calculation.
    period : int
        Moving average period (default 20).
    std_dev : float
        Standard deviation multiplier (default 2.0).

    Returns
    -------
    dict
        Keys: upper, middle, lower, bandwidth, percent_b, status
    """
    if len(bars) < period:
        return {
            "upper": None,
            "middle": None,
            "lower": None,
            "bandwidth": None,
            "percent_b": None,
            "status": "insufficient_data",
        }

    closes = np.array([b["close"] for b in bars[-period:]], dtype=float)
    sma = float(np.mean(closes))
    std = float(np.std(closes))

    upper = round(sma + std_dev * std, 2)
    lower = round(sma - std_dev * std, 2)
    middle = round(sma, 2)

    # Bandwidth: (upper - lower) / middle — measures volatility
    bandwidth = round((upper - lower) / middle, 4) if middle > 0 else None

    # %B: where price sits within the bands (0 = lower, 1 = upper)
    band_width_abs = upper - lower
    percent_b = (
        round((current_price - lower) / band_width_abs, 4)
        if band_width_abs > 0 else None
    )

    # Determine status
    if percent_b is not None:
        if percent_b <= 0:
            status = "below_lower_band"
        elif percent_b >= 1:
            status = "above_upper_band"
        elif percent_b <= 0.2:
            status = "near_lower_band"
        elif percent_b >= 0.8:
            status = "near_upper_band"
        else:
            status = "within_bands"
    else:
        status = "insufficient_data"

    return {
        "upper": upper,
        "middle": middle,
        "lower": lower,
        "bandwidth": bandwidth,
        "percent_b": percent_b,
        "status": status,
    }


def calc_52w_percentile(
    price: Optional[float], low: Optional[float], high: Optional[float]
) -> Optional[float]:
    """Return where *price* sits as a percentile within the 52-week range.

    Returns ``None`` when inputs are missing or the range is zero-width.
    """
    if not price or not low or not high or high == low:
        return None
    return round(((price - low) / (high - low)) * 100, 1)
