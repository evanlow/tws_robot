"""Position Appraisal Service — contextualises a user's open position.

Given position data, fair value, and technical levels, produces a
plain-English appraisal of the entry quality and current standing.

IMPORTANT: Never outputs buy/sell/hold recommendations.
"""

import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


def appraise_position(
    position: Optional[Dict[str, Any]],
    current_price: float,
    fair_value: Dict[str, Any],
    technical_levels: Dict[str, Any],
) -> Dict[str, Any]:
    """Appraise an open position relative to fair value and technical levels.

    Parameters
    ----------
    position : dict or None
        Position data with keys: quantity, entry_price, unrealized_pnl, etc.
        None if user has no position in this stock.
    current_price : float
        Current market price.
    fair_value : dict
        Output from ``valuation_service.estimate_fair_value``.
    technical_levels : dict
        Output from ``technical_levels_service.detect_support_resistance``.

    Returns
    -------
    dict
        Position appraisal result.
    """
    if position is None:
        return {"has_position": False}

    quantity = position.get("quantity", 0)
    entry_price = position.get("entry_price", 0)
    unrealized_pnl = position.get("unrealized_pnl", 0)

    if not entry_price or entry_price <= 0:
        return {"has_position": False}

    # P&L calculations
    unrealized_pnl_pct = round(((current_price - entry_price) / entry_price) * 100, 2)

    # Entry vs fair value
    entry_vs_fair_value = _entry_vs_fair_value(entry_price, fair_value)

    # Entry vs support
    entry_vs_support = _entry_vs_support(entry_price, technical_levels)

    # Entry quality label
    entry_quality = _assess_entry_quality(
        entry_price, current_price, fair_value, technical_levels
    )

    # Summary narrative
    summary = _build_summary(
        entry_price=entry_price,
        current_price=current_price,
        quantity=quantity,
        unrealized_pnl_pct=unrealized_pnl_pct,
        entry_vs_fair_value=entry_vs_fair_value,
        entry_vs_support=entry_vs_support,
        entry_quality=entry_quality,
        technical_levels=technical_levels,
    )

    return {
        "has_position": True,
        "quantity": quantity,
        "average_entry": entry_price,
        "unrealised_pnl": round(unrealized_pnl, 2),
        "unrealised_pnl_percent": unrealized_pnl_pct,
        "entry_vs_fair_value": entry_vs_fair_value,
        "entry_vs_support": entry_vs_support,
        "entry_quality": entry_quality,
        "summary": summary,
    }


def _entry_vs_fair_value(entry_price: float, fair_value: Dict[str, Any]) -> str:
    """Classify entry price relative to fair value range."""
    if fair_value.get("status") == "unavailable":
        return "unavailable"
    fv_low = fair_value.get("low")
    fv_high = fair_value.get("high")
    if fv_low is None or fv_high is None:
        return "unavailable"
    if entry_price < fv_low:
        return "below_fair_value"
    elif entry_price > fv_high:
        return "above_fair_value"
    return "within_fair_value"


def _entry_vs_support(entry_price: float, technical_levels: Dict[str, Any]) -> str:
    """Classify entry price relative to support zones."""
    support_zones = technical_levels.get("support", [])
    if not support_zones:
        return "no_support_detected"

    # Check against strongest (nearest) support
    nearest = support_zones[0]
    if entry_price <= nearest.get("high", 0):
        return "near_support"
    elif entry_price > nearest.get("high", 0) * 1.05:
        return "well_above_support"
    return "above_support"


def _assess_entry_quality(
    entry_price: float,
    current_price: float,
    fair_value: Dict[str, Any],
    technical_levels: Dict[str, Any],
) -> str:
    """Produce a quality label for the entry (good/reasonable/weak/unclear)."""
    scores = []

    # Valuation dimension
    fv_status = fair_value.get("status", "unavailable")
    if fv_status != "unavailable":
        fv_low = fair_value.get("low", 0)
        fv_high = fair_value.get("high", 0)
        if entry_price <= fv_low:
            scores.append("good")
        elif entry_price <= fv_high:
            scores.append("reasonable")
        else:
            scores.append("weak")

    # Technical dimension
    support_zones = technical_levels.get("support", [])
    if support_zones:
        nearest_support_high = support_zones[0].get("high", 0)
        if entry_price <= nearest_support_high * 1.02:
            scores.append("good")
        elif entry_price <= nearest_support_high * 1.10:
            scores.append("reasonable")
        else:
            scores.append("weak")

    if not scores:
        return "unclear"

    # Aggregate
    if all(s == "good" for s in scores):
        return "good"
    elif "weak" in scores and "good" not in scores:
        return "weak"
    elif "weak" in scores:
        return "reasonable"
    return "reasonable"


def _build_summary(
    entry_price: float,
    current_price: float,
    quantity: int,
    unrealized_pnl_pct: float,
    entry_vs_fair_value: str,
    entry_vs_support: str,
    entry_quality: str,
    technical_levels: Dict[str, Any],
) -> str:
    """Build a plain-English summary card."""
    parts = []

    # P&L status
    if unrealized_pnl_pct >= 0:
        parts.append(
            f"Position is currently up {unrealized_pnl_pct:.1f}% from average entry."
        )
    else:
        parts.append(
            f"Position is currently down {abs(unrealized_pnl_pct):.1f}% from average entry."
        )

    # Technical position
    tech_pos = technical_levels.get("technical_position", "")
    if tech_pos == "near_support":
        parts.append("Price is near a detected support zone.")
    elif tech_pos == "below_support":
        parts.append("Price is below the nearest detected support zone.")
    elif tech_pos == "near_resistance":
        parts.append("Price is near a detected resistance zone.")
    elif tech_pos == "middle_of_range":
        parts.append("Price is in the middle of its recent trading range.")

    # Entry quality context
    if entry_quality == "good":
        parts.append("Entry appears near strong support and within fair value range.")
    elif entry_quality == "weak":
        parts.append(
            "Entry appears technically weak relative to detected support zones."
        )
    elif entry_quality == "reasonable":
        parts.append(
            "Entry appears reasonable but not at the strongest technical levels."
        )

    # Fair value context
    if entry_vs_fair_value == "above_fair_value":
        parts.append(
            "Entry price is above the estimated fair value range based on current assumptions."
        )
    elif entry_vs_fair_value == "below_fair_value":
        parts.append("Entry price is below the estimated fair value range.")

    return " ".join(parts)
