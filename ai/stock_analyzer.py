"""Stock Deep-Dive Analyzer — on-demand per-stock analysis.

Combines fundamental data, technical context, and position data to produce
a comprehensive LLM-powered deep-dive report for a single stock held in
the portfolio.

Usage::

    from ai.stock_analyzer import StockAnalyzer

    analyzer = StockAnalyzer()
    result = analyzer.analyze_stock("GOOG", position_data, fundamentals, technicals)
"""

import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def compute_technical_context(
    current_price: float,
    history: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Derive simple technical indicators from price history.

    Parameters
    ----------
    current_price : float
        The latest price.
    history : list[dict], optional
        List of OHLCV dicts with keys: ``close``, ``high``, ``low``,
        ``volume``.  Must be sorted oldest→newest.

    Returns
    -------
    dict
        Technical context with SMA, RSI, 52-week range, etc.
    """
    result: Dict[str, Any] = {"current_price": current_price}
    if not history or len(history) < 2:
        return result

    closes = [_safe_float(bar.get("close", bar.get("Close"))) for bar in history]
    closes = [c for c in closes if c > 0]
    if not closes:
        return result

    # Simple Moving Averages
    if len(closes) >= 50:
        result["sma_50"] = round(sum(closes[-50:]) / 50, 2)
    if len(closes) >= 200:
        result["sma_200"] = round(sum(closes[-200:]) / 200, 2)

    # RSI (14-period)
    if len(closes) >= 15:
        gains, losses = [], []
        for i in range(-14, 0):
            change = closes[i] - closes[i - 1]
            if change >= 0:
                gains.append(change)
                losses.append(0)
            else:
                gains.append(0)
                losses.append(abs(change))
        avg_gain = sum(gains) / 14
        avg_loss = sum(losses) / 14
        if avg_loss > 0:
            rs = avg_gain / avg_loss
            result["rsi_14"] = round(100 - (100 / (1 + rs)), 1)
        else:
            result["rsi_14"] = 100.0

    # 52-week high/low (approximate from available data)
    highs = [_safe_float(bar.get("high", bar.get("High"))) for bar in history]
    lows = [_safe_float(bar.get("low", bar.get("Low"))) for bar in history]
    recent_highs = [h for h in highs[-252:] if h > 0]
    recent_lows = [l for l in lows[-252:] if l > 0]
    if recent_highs:
        result["high_52w"] = max(recent_highs)
    if recent_lows:
        result["low_52w"] = min(recent_lows)

    # Price relative to 52w range
    if "high_52w" in result and "low_52w" in result:
        range_52w = result["high_52w"] - result["low_52w"]
        if range_52w > 0:
            result["pct_from_52w_high"] = round(
                (current_price - result["high_52w"]) / result["high_52w"], 4,
            )
            result["position_in_range"] = round(
                (current_price - result["low_52w"]) / range_52w, 4,
            )

    # Trend: compare price to SMAs
    trends = []
    if "sma_50" in result:
        if current_price > result["sma_50"]:
            trends.append("above 50-day SMA (bullish)")
        else:
            trends.append("below 50-day SMA (bearish)")
    if "sma_200" in result:
        if current_price > result["sma_200"]:
            trends.append("above 200-day SMA (long-term bullish)")
        else:
            trends.append("below 200-day SMA (long-term bearish)")
    result["trend_signals"] = trends

    return result


class StockAnalyzer:
    """Produces an AI-powered deep-dive analysis for a single stock."""

    def analyze_stock(
        self,
        symbol: str,
        position: Dict[str, Any],
        fundamentals: Optional[Dict[str, Any]] = None,
        technical_context: Optional[Dict[str, Any]] = None,
        use_ai: bool = True,
    ) -> Dict[str, Any]:
        """Run the deep-dive analysis.

        Parameters
        ----------
        symbol : str
            Ticker symbol (e.g., ``"GOOG"``).
        position : dict
            Position data (entry_price, quantity, unrealized_pnl, etc.).
        fundamentals : dict, optional
            Fundamental data from :mod:`data.fundamentals`.
        technical_context : dict, optional
            Technical indicators from :func:`compute_technical_context`.
        use_ai : bool
            Whether to use the LLM for the narrative.  When ``False``,
            only structured data is returned.

        Returns
        -------
        dict
            Keys: ``symbol``, ``position``, ``fundamentals``,
            ``technicals``, ``ai_analysis`` (or ``None``).
        """
        fundamentals = fundamentals or {}
        technical_context = technical_context or {}

        result: Dict[str, Any] = {
            "symbol": symbol,
            "position": position,
            "fundamentals": fundamentals,
            "technicals": technical_context,
            "ai_analysis": None,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        if not use_ai:
            return result

        try:
            from ai.client import get_client
            from ai.prompts import Prompts

            client = get_client()
            if client is None:
                return result

            position_json = json.dumps(position, indent=2, default=str)
            fundamentals_json = json.dumps(fundamentals, indent=2, default=str)
            technical_json = json.dumps(technical_context, indent=2, default=str)

            system_prompt = Prompts.STOCK_DEEP_DIVE.format(
                symbol=symbol,
                position_json=position_json,
                fundamentals_json=fundamentals_json,
                technical_json=technical_json,
            )
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Provide a deep-dive analysis for {symbol}."},
            ]
            raw = client.chat(messages)
            ai_result = _parse_ai_json(raw)
            if ai_result:
                result["ai_analysis"] = ai_result

        except Exception:
            logger.exception("AI stock deep-dive failed for %s", symbol)

        return result


def _parse_ai_json(raw: str) -> Optional[Dict[str, Any]]:
    """Best-effort parse of an LLM JSON response."""
    if not raw:
        return None
    text = raw.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        lines = [l for l in lines if not l.strip().startswith("```")]
        text = "\n".join(lines)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        logger.warning("Failed to parse AI JSON for stock deep-dive: %s...", text[:200])
        return None
