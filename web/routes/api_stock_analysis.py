"""Stock Analysis API — fair value, support/resistance, position appraisal.

GET /api/stocks/<ticker>/analysis
    Returns comprehensive stock analysis including fair value estimate,
    support/resistance zones, and open position appraisal.
"""

import logging
import math
import re
from typing import Any, Dict, Optional

from flask import Blueprint, jsonify

from web.stock_analysis_services import valuation_service, technical_levels_service, position_appraisal_service
from web.services import get_services

logger = logging.getLogger(__name__)

bp = Blueprint("api_stock_analysis", __name__, url_prefix="/api/stocks")

_TICKER_RE = re.compile(r"^[A-Z0-9]{1,10}(\.[A-Z]{1,5})?$")


@bp.route("/<ticker>/analysis", methods=["GET"])
def stock_analysis(ticker: str):
    """Return comprehensive stock analysis for a given ticker.

    Combines fair value estimation, support/resistance detection, and
    open position appraisal into a single response.
    """
    ticker = ticker.upper()

    if not _TICKER_RE.match(ticker):
        return jsonify({"error": "Invalid ticker symbol.", "ticker": ticker}), 400

    try:
        from data.fundamentals import fetch_fundamentals, fetch_price_history

        # Fetch fundamental data
        fundamentals = fetch_fundamentals(ticker)
        if fundamentals.get("error"):
            logger.warning("Fundamentals fetch issue for %s: %s", ticker, fundamentals.get("error"))

        # Fetch 1-year OHLCV
        raw_bars = fetch_price_history(ticker, period="1y", interval="1d")

        # Filter out bars with non-finite OHLC values
        bars = [
            b for b in raw_bars
            if all(math.isfinite(b[k]) for k in ("open", "high", "low", "close") if b.get(k) is not None)
        ]

        # Current price
        current_price = fundamentals.get("current_price")
        if current_price is not None and not math.isfinite(current_price):
            current_price = None
        if not current_price and bars:
            current_price = bars[-1]["close"]

        if not current_price:
            return jsonify({
                "error": "Unable to retrieve price data for this ticker.",
                "ticker": ticker,
            }), 404

        # --- Fair Value Estimate ---
        fair_value = valuation_service.estimate_fair_value(fundamentals, current_price)

        # --- Technical Levels ---
        technical_levels = technical_levels_service.detect_support_resistance(bars, current_price)

        # --- 52-week range ---
        range_52w = technical_levels.get("range_52w", {})
        if not range_52w.get("low"):
            # Fallback to fundamentals
            range_52w = {
                "low": fundamentals.get("fifty_two_week_low"),
                "high": fundamentals.get("fifty_two_week_high"),
                "position_percentile": _calc_percentile(
                    current_price,
                    fundamentals.get("fifty_two_week_low"),
                    fundamentals.get("fifty_two_week_high"),
                ),
            }

        # --- Open Position ---
        svc = get_services()
        positions = svc.get_positions()
        position = positions.get(ticker)

        open_position = position_appraisal_service.appraise_position(
            position=position,
            current_price=current_price,
            fair_value=fair_value,
            technical_levels=technical_levels,
        )

        # --- Price Context Narrative ---
        price_context = _build_price_context(
            current_price=current_price,
            fair_value=fair_value,
            technical_levels=technical_levels,
            range_52w=range_52w,
        )

        # --- Build response ---
        response = {
            "ticker": ticker,
            "name": fundamentals.get("name", ticker),
            "current_price": round(current_price, 2),
            "range_52w": range_52w,
            "fair_value": fair_value,
            "technical_levels": {
                "support": technical_levels.get("support", []),
                "resistance": technical_levels.get("resistance", []),
            },
            "momentum_status": technical_levels.get("momentum_status"),
            "technical_position": technical_levels.get("technical_position"),
            "price_context": price_context,
            "open_position": open_position,
            "disclaimer": (
                "This analysis is for educational and decision-support purposes only. "
                "It is not financial advice, not a buy/sell recommendation, and does not "
                "consider your full financial situation, risk tolerance, investment "
                "objectives, or tax position. Fair value estimates are assumption-based "
                "and may be wrong."
            ),
        }

        return jsonify(response)

    except Exception as exc:
        logger.error("Stock analysis failed for %s: %s", ticker, exc, exc_info=True)
        return jsonify({"error": "Analysis could not be completed", "ticker": ticker}), 500


def _calc_percentile(
    price: Optional[float], low: Optional[float], high: Optional[float]
) -> Optional[float]:
    """Calculate position percentile within a range."""
    if not price or not low or not high or high == low:
        return None
    return round(((price - low) / (high - low)) * 100, 1)


def _build_price_context(
    current_price: float,
    fair_value: Dict[str, Any],
    technical_levels: Dict[str, Any],
    range_52w: Dict[str, Any],
) -> str:
    """Build a plain-English price context narrative."""
    parts = []

    # Range position
    percentile = range_52w.get("position_percentile")
    if percentile is not None:
        if percentile <= 20:
            parts.append("Current price is near the bottom of the 1-year range.")
        elif percentile >= 80:
            parts.append("Current price is near the top of the 1-year range.")
        else:
            parts.append("Current price is in the middle of the 1-year range.")

    # Valuation
    fv_status = fair_value.get("status", "unavailable")
    if fv_status == "potentially_undervalued":
        parts.append("Valuation may appear reasonable relative to estimated fair value.")
    elif fv_status == "potentially_overvalued":
        parts.append("Price appears elevated relative to estimated fair value.")
    elif fv_status == "fairly_valued":
        parts.append("Price appears within the estimated fair value range.")
    else:
        parts.append("Fair value estimate is unavailable for comparison.")

    # Technical
    tech_pos = technical_levels.get("technical_position", "")
    momentum = technical_levels.get("momentum_status", "")
    if tech_pos == "near_support":
        parts.append("Price is near a detected support zone.")
    elif tech_pos == "below_support":
        parts.append("Price has moved below the nearest support zone.")
    elif tech_pos == "near_resistance":
        parts.append("Price is approaching a resistance zone.")

    if momentum == "downtrend":
        parts.append("Technical momentum remains weak.")
    elif momentum == "uptrend":
        parts.append("Technical momentum appears positive.")

    return " ".join(parts) if parts else "Insufficient data for price context analysis."
