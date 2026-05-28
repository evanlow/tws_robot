"""Stock Analysis API — fair value, support/resistance, position appraisal.

GET /api/stocks/<ticker>/analysis
    Returns comprehensive stock analysis including fair value estimate,
    support/resistance zones, Bollinger Bands context, and open position appraisal.
"""

import logging
import math
import re
from typing import Any, Dict, List, Optional

import numpy as np
from flask import Blueprint, jsonify

from strategies.base_strategy import StrategyState
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
            if all(
                isinstance(b[k], (int, float)) and math.isfinite(b[k])
                for k in ("open", "high", "low", "close")
                if b.get(k) is not None
            )
        ]

        # Current price
        current_price = fundamentals.get("current_price")
        if current_price is not None and not math.isfinite(current_price):
            current_price = None
        if not current_price and bars:
            close = bars[-1]["close"]
            current_price = close if isinstance(close, (int, float)) and math.isfinite(close) else None

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

        # --- Bollinger Bands ---
        bollinger_bands = _compute_bollinger_bands(bars, current_price)

        # --- Price Context Narrative ---
        price_context = _build_price_context(
            current_price=current_price,
            fair_value=fair_value,
            technical_levels=technical_levels,
            range_52w=range_52w,
            bollinger_bands=bollinger_bands,
        )

        # --- Active strategy signals ---
        active_strategy_signals = _get_active_bollinger_signals(ticker)

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
            "bollinger_bands": bollinger_bands,
            "momentum_status": technical_levels.get("momentum_status"),
            "technical_position": technical_levels.get("technical_position"),
            "price_context": price_context,
            "active_strategy_signals": active_strategy_signals,
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


def _compute_bollinger_bands(
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


def _get_active_bollinger_signals(ticker: str) -> List[Dict[str, Any]]:
    """Retrieve active Bollinger strategy signals for a given ticker.

    Queries the StrategyRegistry for any Bollinger strategies tracking the
    ticker and returns their current indicator values and recent signals.
    """
    try:
        svc = get_services()
        registry = svc.strategy_registry
        results = []

        for strategy in registry.get_all_strategies():
            # Check if it's a Bollinger strategy tracking this ticker
            if (
                hasattr(strategy, "middle_band")
                and strategy.state == StrategyState.RUNNING
                and ticker in strategy.config.symbols
            ):
                indicators = strategy.get_indicator_values(ticker)
                if not indicators:
                    continue

                # Find most recent signal for this ticker
                last_signal = None
                for sig in reversed(strategy.signals_to_emit):
                    if sig.symbol == ticker:
                        last_signal = {
                            "type": sig.signal_type.value,
                            "strength": sig.strength.name,
                            "confidence": sig.confidence,
                            "reason": sig.reason,
                            "timestamp": sig.timestamp.isoformat() if sig.timestamp else None,
                        }
                        break

                results.append({
                    "strategy_name": strategy.config.name,
                    "state": strategy.state.value,
                    "indicators": indicators,
                    "last_signal": last_signal,
                })

        return results
    except Exception as exc:
        logger.debug("Could not fetch active strategy signals: %s", exc)
        return []


def _build_price_context(
    current_price: float,
    fair_value: Dict[str, Any],
    technical_levels: Dict[str, Any],
    range_52w: Dict[str, Any],
    bollinger_bands: Optional[Dict[str, Any]] = None,
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

    # Bollinger Bands position
    if bollinger_bands and bollinger_bands.get("status") != "insufficient_data":
        bb_status = bollinger_bands["status"]
        if bb_status == "below_lower_band":
            parts.append(
                "Price is below the Bollinger lower band — statistically oversold."
            )
        elif bb_status == "near_lower_band":
            parts.append(
                "Price is near the Bollinger lower band — approaching oversold territory."
            )
        elif bb_status == "above_upper_band":
            parts.append(
                "Price is above the Bollinger upper band — statistically overbought."
            )
        elif bb_status == "near_upper_band":
            parts.append(
                "Price is near the Bollinger upper band — approaching overbought territory."
            )

    return " ".join(parts) if parts else "Insufficient data for price context analysis."
