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


_OVERSOLD_STATUSES = frozenset({"below_lower_band", "near_lower_band"})

# Mapping from internal momentum code to human-readable label.
MOMENTUM_CONFIRMATION_LABELS: Dict[str, str] = {
    "still_falling":       "Still Falling",
    "failed_bounce":       "Failed Bounce",
    "no_confirmation_yet": "No Confirmation Yet",
    "stabilising":         "Stabilising",
    "early_rebound":       "Early Rebound",
    "confirmed_rebound":   "Confirmed Rebound",
    "insufficient_data":   "Insufficient Data",
}


def compute_oversold_momentum_confirmation(
    bars: List[Dict[str, Any]],
    bollinger_status: str,
    period: int = 20,
    std_dev: float = 2.0,
) -> Dict[str, Any]:
    """Compute a momentum confirmation indicator for oversold stocks.

    Only meaningful when *bollinger_status* is ``"below_lower_band"`` or
    ``"near_lower_band"``.  For all other statuses the three returned fields
    are ``None`` / empty so the screener column can display ``"--"``.

    Parameters
    ----------
    bars:
        OHLCV bars sorted oldest → newest (same list passed to
        ``compute_bollinger_bands``).
    bollinger_status:
        The status string already computed by ``compute_bollinger_bands``.
    period:
        Bollinger Bands period used when computing lower band values
        (default 20, must match the value used in ``compute_bollinger_bands``).
    std_dev:
        Standard deviation multiplier (default 2.0).

    Returns
    -------
    dict
        Keys: ``momentum_confirmation`` (str | None),
        ``momentum_label`` (str | None),
        ``momentum_reasons`` (list[str]).
    """
    _not_applicable: Dict[str, Any] = {
        "momentum_confirmation": None,
        "momentum_label": None,
        "momentum_reasons": [],
    }
    _insufficient: Dict[str, Any] = {
        "momentum_confirmation": "insufficient_data",
        "momentum_label": "Insufficient Data",
        "momentum_reasons": ["Not enough price history to assess momentum"],
    }

    if bollinger_status not in _OVERSOLD_STATUSES:
        return _not_applicable

    # We need at least period+1 bars to compute a current and a previous lower
    # Bollinger Band for the "Early Rebound" / "Failed Bounce" checks.
    if len(bars) < period + 1:
        return _insufficient

    latest_close = float(bars[-1]["close"])
    previous_close = float(bars[-2]["close"])
    close_2_days_ago = float(bars[-3]["close"]) if len(bars) >= period + 2 else None

    # Current lower Bollinger Band (last *period* bars)
    closes_current = np.array([b["close"] for b in bars[-period:]], dtype=float)
    sma_current = float(np.mean(closes_current))
    std_current = float(np.std(closes_current))
    lower_band = sma_current - std_dev * std_current

    # Previous lower Bollinger Band (bars[-period-1:-1])
    closes_prev = np.array([b["close"] for b in bars[-period - 1:-1]], dtype=float)
    sma_prev = float(np.mean(closes_prev))
    std_prev = float(np.std(closes_prev))
    previous_lower_band = sma_prev - std_dev * std_prev

    # 5-day SMA (or fewer bars if history is short)
    sma_5_count = min(5, len(bars))
    sma_5 = float(np.mean([b["close"] for b in bars[-sma_5_count:]]))

    reasons: List[str] = []

    # --- Failed Bounce -------------------------------------------------------
    # Price had temporarily recovered inside the band (previous close above
    # previous lower band) but has now dropped back below the current lower band.
    if (
        bollinger_status == "below_lower_band"
        and previous_close > previous_lower_band
        and latest_close < lower_band
    ):
        reasons.append("Price recovered briefly but closed back below lower Bollinger Band")
        return {
            "momentum_confirmation": "failed_bounce",
            "momentum_label": "Failed Bounce",
            "momentum_reasons": reasons,
        }

    # --- Still Falling -------------------------------------------------------
    # Latest close is below both the previous close and the current lower band.
    if latest_close < previous_close and latest_close < lower_band:
        reasons.append("Latest close below previous close")
        reasons.append("Latest close below lower Bollinger Band")
        return {
            "momentum_confirmation": "still_falling",
            "momentum_label": "Still Falling",
            "momentum_reasons": reasons,
        }

    # --- Early Rebound -------------------------------------------------------
    # Price has just closed back above the lower band after the previous bar
    # was at or below the previous lower band.
    if latest_close > lower_band and previous_close <= previous_lower_band:
        reasons.append("Closed back inside lower Bollinger Band")
        if latest_close > previous_close:
            reasons.append("Latest close above previous close")
        return {
            "momentum_confirmation": "early_rebound",
            "momentum_label": "Early Rebound",
            "momentum_reasons": reasons,
        }

    # --- Confirmed Rebound ---------------------------------------------------
    # Price is above the 5-day SMA with two consecutive higher closes.
    if (
        close_2_days_ago is not None
        and latest_close > sma_5
        and latest_close > previous_close
        and previous_close > close_2_days_ago
    ):
        reasons.append("Price above 5-day moving average")
        reasons.append("2 consecutive higher closes")
        return {
            "momentum_confirmation": "confirmed_rebound",
            "momentum_label": "Confirmed Rebound",
            "momentum_reasons": reasons,
        }

    # --- Stabilising ---------------------------------------------------------
    # Selling pressure is easing: latest close is at or above the previous.
    if latest_close >= previous_close:
        reasons.append("Latest close at or above previous close")
        return {
            "momentum_confirmation": "stabilising",
            "momentum_label": "Stabilising",
            "momentum_reasons": reasons,
        }

    # --- No Confirmation Yet -------------------------------------------------
    return {
        "momentum_confirmation": "no_confirmation_yet",
        "momentum_label": "No Confirmation Yet",
        "momentum_reasons": ["No clear rebound evidence yet"],
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
