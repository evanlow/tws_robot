"""Technical Levels Service — detects support/resistance zones from 1Y OHLCV data.

Uses pivot-point clustering to identify price zones where the stock has
repeatedly reversed.  Zones are labelled with confidence (Low/Medium/High)
and a plain-English reason string.
"""

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Minimum number of bars required for meaningful analysis
_MIN_BARS = 20

# How close (as fraction of price) two pivots must be to cluster together
_CLUSTER_TOLERANCE = 0.02  # 2%

# Minimum touches for a zone to qualify
_MIN_TOUCHES = 2


def detect_support_resistance(
    bars: List[Dict[str, Any]],
    current_price: Optional[float] = None,
) -> Dict[str, Any]:
    """Detect support and resistance zones from OHLCV bars.

    Parameters
    ----------
    bars : list[dict]
        OHLCV bars sorted oldest→newest (from ``fetch_price_history``).
    current_price : float, optional
        Current price for context labelling.

    Returns
    -------
    dict
        Keys: support (list), resistance (list), range_52w, momentum_status
    """
    if not bars or len(bars) < _MIN_BARS:
        return _empty_result()

    highs = [b["high"] for b in bars]
    lows = [b["low"] for b in bars]
    closes = [b["close"] for b in bars]

    # 52-week (1-year) range
    year_high = max(highs)
    year_low = min(lows)
    price = current_price or closes[-1]

    range_size = year_high - year_low
    position_percentile = (
        round(((price - year_low) / range_size) * 100, 1)
        if range_size > 0 else 50.0
    )

    # Find swing pivots
    swing_highs = _find_swing_highs(highs, window=5)
    swing_lows = _find_swing_lows(lows, window=5)

    # Cluster pivots into zones
    resistance_zones = _cluster_pivots(swing_highs, year_high, is_resistance=True)
    support_zones = _cluster_pivots(swing_lows, year_low, is_resistance=False)

    # Always include 52-week extremes as major zones
    _ensure_extreme_zone(support_zones, year_low, "52-week low", is_resistance=False)
    _ensure_extreme_zone(resistance_zones, year_high, "52-week high", is_resistance=True)

    # Filter: only keep zones with enough touches
    support_zones = [z for z in support_zones if z["touches"] >= _MIN_TOUCHES]
    resistance_zones = [z for z in resistance_zones if z["touches"] >= _MIN_TOUCHES]

    # Classify relative to current price
    support_zones = [z for z in support_zones if z["high"] <= price * 1.02]
    resistance_zones = [z for z in resistance_zones if z["low"] >= price * 0.98]

    # Sort: support descending (nearest first), resistance ascending
    support_zones.sort(key=lambda z: -z["low"])
    resistance_zones.sort(key=lambda z: z["low"])

    # Assign confidence
    for zone in support_zones + resistance_zones:
        zone["confidence"] = _confidence_label(zone["touches"])
        # Remove internal 'touches' key from final output
        del zone["touches"]

    # Momentum status (simple: based on recent closes vs moving averages)
    momentum = _assess_momentum(closes)

    # Technical position
    technical_position = _technical_position(price, support_zones, resistance_zones)

    return {
        "support": support_zones[:5],  # top 5 zones
        "resistance": resistance_zones[:5],
        "range_52w": {
            "low": round(year_low, 2),
            "high": round(year_high, 2),
            "position_percentile": position_percentile,
        },
        "momentum_status": momentum,
        "technical_position": technical_position,
    }


def _find_swing_highs(highs: List[float], window: int = 5) -> List[float]:
    """Find local maxima in the highs series."""
    pivots = []
    for i in range(window, len(highs) - window):
        if highs[i] == max(highs[i - window:i + window + 1]):
            pivots.append(highs[i])
    return pivots


def _find_swing_lows(lows: List[float], window: int = 5) -> List[float]:
    """Find local minima in the lows series."""
    pivots = []
    for i in range(window, len(lows) - window):
        if lows[i] == min(lows[i - window:i + window + 1]):
            pivots.append(lows[i])
    return pivots


def _cluster_pivots(
    pivots: List[float],
    extreme: float,
    is_resistance: bool,
) -> List[Dict[str, Any]]:
    """Cluster pivot points into zones."""
    if not pivots:
        return []

    sorted_pivots = sorted(pivots)
    zones: List[Dict[str, Any]] = []
    used = [False] * len(sorted_pivots)

    for i, pivot in enumerate(sorted_pivots):
        if used[i]:
            continue
        cluster = [pivot]
        used[i] = True
        for j in range(i + 1, len(sorted_pivots)):
            if pivot > 0 and abs(sorted_pivots[j] - pivot) / pivot <= _CLUSTER_TOLERANCE:
                cluster.append(sorted_pivots[j])
                used[j] = True

        zone_low = round(min(cluster), 2)
        zone_high = round(max(cluster), 2)
        # Widen slightly for zone representation
        spread = (zone_high - zone_low) if zone_high > zone_low else zone_low * 0.005
        if spread < zone_low * 0.005:
            zone_low = round(zone_low - zone_low * 0.003, 2)
            zone_high = round(zone_high + zone_high * 0.003, 2)

        reason = _zone_reason(cluster, extreme, is_resistance)
        zones.append({
            "low": zone_low,
            "high": zone_high,
            "touches": len(cluster),
            "reason": reason,
        })

    return zones


def _ensure_extreme_zone(
    zones: List[Dict[str, Any]],
    extreme_price: float,
    label: str,
    is_resistance: bool,
) -> None:
    """Ensure the 52-week extreme appears as a zone."""
    for zone in zones:
        if extreme_price > 0 and abs(zone["low"] - extreme_price) / extreme_price <= _CLUSTER_TOLERANCE:
            zone["reason"] = f"{label} and {zone['reason']}"
            zone["touches"] = max(zone["touches"], 2)
            return
    # Add as a new zone
    spread = extreme_price * 0.01
    zones.append({
        "low": round(extreme_price - spread * 0.5, 2) if not is_resistance else round(extreme_price - spread, 2),
        "high": round(extreme_price + spread * 0.5, 2) if not is_resistance else round(extreme_price, 2),
        "touches": 2,
        "reason": label,
    })


def _zone_reason(cluster: List[float], extreme: float, is_resistance: bool) -> str:
    """Generate a plain-English reason for a zone."""
    avg = sum(cluster) / len(cluster)
    touches = len(cluster)

    if extreme > 0 and abs(avg - extreme) / extreme <= _CLUSTER_TOLERANCE:
        prefix = "52-week high area" if is_resistance else "52-week low area"
    else:
        prefix = "prior swing high area" if is_resistance else "prior swing low area"

    if touches >= 4:
        return f"{prefix} with multiple touches ({touches}x)"
    elif touches >= 2:
        return f"{prefix} with repeated touches"
    else:
        return prefix


def _confidence_label(touches: int) -> str:
    """Map touch count to confidence label."""
    if touches >= 4:
        return "high"
    elif touches >= 2:
        return "medium"
    return "low"


def _assess_momentum(closes: List[float]) -> str:
    """Simple momentum assessment from closes."""
    if len(closes) < 20:
        return "insufficient_data"

    # Compare current close to 20-day and 50-day moving averages
    ma20 = sum(closes[-20:]) / 20
    ma50 = sum(closes[-50:]) / 50 if len(closes) >= 50 else ma20

    current = closes[-1]

    if current > ma20 > ma50:
        return "uptrend"
    elif current < ma20 < ma50:
        return "downtrend"
    elif ma20 > 0 and abs(current - ma20) / ma20 < 0.02:
        return "sideways"
    else:
        return "volatile"


def _technical_position(
    price: float,
    support_zones: List[Dict[str, Any]],
    resistance_zones: List[Dict[str, Any]],
) -> str:
    """Describe where price sits relative to support/resistance."""
    if support_zones:
        nearest_support = support_zones[0]
        if price <= nearest_support["high"] and price >= nearest_support["low"]:
            return "near_support"
        elif price < nearest_support["low"]:
            return "below_support"

    if resistance_zones:
        nearest_resistance = resistance_zones[0]
        if price >= nearest_resistance["low"] and price <= nearest_resistance["high"]:
            return "near_resistance"
        elif price > nearest_resistance["high"]:
            return "breakout"

    return "middle_of_range"


def _empty_result() -> Dict[str, Any]:
    """Return empty result when insufficient data."""
    return {
        "support": [],
        "resistance": [],
        "range_52w": {"low": None, "high": None, "position_percentile": None},
        "momentum_status": "insufficient_data",
        "technical_position": "insufficient_data",
    }
