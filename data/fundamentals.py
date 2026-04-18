"""Fundamentals Data Fetcher — retrieves and caches stock fundamental data.

Uses ``yfinance`` (already in requirements.txt) to fetch fundamental data
such as P/E ratio, EPS, revenue, margins, analyst targets, and more.

Results are cached in SQLite via the portfolio persistence layer so that
repeated lookups within the cache TTL don't hit the external API.

Usage::

    from data.fundamentals import get_fundamentals

    data = get_fundamentals("GOOG")
"""

import logging
import math
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Cache TTL: how long (in seconds) before fundamentals are considered stale.
_CACHE_TTL_SECONDS = 86400  # 24 hours

# Keys in the fundamentals dict that hold non-numeric (string) values and
# should be skipped by the numeric sanitizer.
_STRING_KEYS = frozenset({
    "symbol", "fetched_at", "name", "sector", "industry", "recommendation_key",
})


def _safe_get(info: Dict[str, Any], key: str, default: Any = None) -> Any:
    """Get a value from a dict, returning *default* if missing or None."""
    val = info.get(key)
    return val if val is not None else default


def _sanitize_numeric(value: Any) -> Optional[float]:
    """Convert *value* to a float, returning ``None`` for non-numeric data.

    yfinance occasionally returns placeholder strings (e.g. ``"?"``),
    ``Infinity``, or ``NaN`` for unavailable metrics.  This helper
    ensures we only pass proper finite numbers to the API / frontend.
    """
    if value is None:
        return None
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    # Reject NaN and Infinity
    if math.isnan(f) or math.isinf(f):
        return None
    return f


def fetch_fundamentals(symbol: str) -> Dict[str, Any]:
    """Fetch fundamental data for *symbol* via yfinance.

    Parameters
    ----------
    symbol : str
        Ticker symbol (e.g. ``"GOOG"``, ``"SLV"``).

    Returns
    -------
    dict
        Fundamental data with normalised keys.  Returns an empty dict
        with ``"error"`` key if the fetch fails.
    """
    try:
        import yfinance as yf
    except ImportError:
        logger.error("yfinance is not installed — cannot fetch fundamentals")
        return {"error": "yfinance not installed", "symbol": symbol}

    try:
        ticker = yf.Ticker(symbol)
        info = ticker.info or {}
    except Exception as exc:
        logger.error("yfinance fetch failed for %s: %s", symbol, exc)
        return {"error": str(exc), "symbol": symbol}

    result: Dict[str, Any] = {
        "symbol": symbol,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "name": _safe_get(info, "longName", _safe_get(info, "shortName", symbol)),
        "sector": _safe_get(info, "sector"),
        "industry": _safe_get(info, "industry"),
        "market_cap": _safe_get(info, "marketCap"),
        "enterprise_value": _safe_get(info, "enterpriseValue"),

        # Valuation ratios
        "pe_trailing": _safe_get(info, "trailingPE"),
        "pe_forward": _safe_get(info, "forwardPE"),
        "peg_ratio": _safe_get(info, "pegRatio"),
        "price_to_book": _safe_get(info, "priceToBook"),
        "price_to_sales": _safe_get(info, "priceToSalesTrailing12Months"),
        "ev_to_ebitda": _safe_get(info, "enterpriseToEbitda"),

        # Profitability
        "profit_margin": _safe_get(info, "profitMargins"),
        "operating_margin": _safe_get(info, "operatingMargins"),
        "gross_margin": _safe_get(info, "grossMargins"),
        "roe": _safe_get(info, "returnOnEquity"),
        "roa": _safe_get(info, "returnOnAssets"),

        # Growth & earnings
        "eps_trailing": _safe_get(info, "trailingEps"),
        "eps_forward": _safe_get(info, "forwardEps"),
        "revenue": _safe_get(info, "totalRevenue"),
        "revenue_per_share": _safe_get(info, "revenuePerShare"),
        "revenue_growth": _safe_get(info, "revenueGrowth"),
        "earnings_growth": _safe_get(info, "earningsGrowth"),

        # Balance sheet
        "total_cash": _safe_get(info, "totalCash"),
        "total_debt": _safe_get(info, "totalDebt"),
        "debt_to_equity": _safe_get(info, "debtToEquity"),
        "current_ratio": _safe_get(info, "currentRatio"),
        "book_value": _safe_get(info, "bookValue"),

        # Dividends
        "dividend_yield": _safe_get(info, "dividendYield"),
        "dividend_rate": _safe_get(info, "dividendRate"),
        "payout_ratio": _safe_get(info, "payoutRatio"),

        # Analyst targets
        "target_mean_price": _safe_get(info, "targetMeanPrice"),
        "target_high_price": _safe_get(info, "targetHighPrice"),
        "target_low_price": _safe_get(info, "targetLowPrice"),
        "recommendation_key": _safe_get(info, "recommendationKey"),
        "number_of_analyst_opinions": _safe_get(info, "numberOfAnalystOpinions"),

        # Price data
        "current_price": _safe_get(info, "currentPrice", _safe_get(info, "regularMarketPrice")),
        "previous_close": _safe_get(info, "previousClose"),
        "fifty_two_week_high": _safe_get(info, "fiftyTwoWeekHigh"),
        "fifty_two_week_low": _safe_get(info, "fiftyTwoWeekLow"),
        "fifty_day_average": _safe_get(info, "fiftyDayAverage"),
        "two_hundred_day_average": _safe_get(info, "twoHundredDayAverage"),
        "beta": _safe_get(info, "beta"),

        # Volume
        "avg_volume": _safe_get(info, "averageVolume"),
        "avg_volume_10d": _safe_get(info, "averageDailyVolume10Day"),
    }

    # Sanitize all numeric fields — yfinance may return placeholder strings
    # (e.g. "?"), Infinity, or NaN for unavailable data.
    for key, value in result.items():
        if key not in _STRING_KEYS and value is not None:
            result[key] = _sanitize_numeric(value)

    return result


def fetch_price_history(
    symbol: str,
    period: str = "1y",
    interval: str = "1d",
) -> List[Dict[str, Any]]:
    """Fetch historical OHLCV bars for technical analysis.

    Parameters
    ----------
    symbol : str
        Ticker symbol.
    period : str
        yfinance period string (e.g. ``"1y"``, ``"6mo"``, ``"2y"``).
    interval : str
        Bar interval (``"1d"``, ``"1wk"``, etc.).

    Returns
    -------
    list[dict]
        List of OHLCV dicts sorted oldest→newest.
    """
    try:
        import yfinance as yf
    except ImportError:
        logger.error("yfinance not installed — cannot fetch price history")
        return []

    try:
        ticker = yf.Ticker(symbol)
        df = ticker.history(period=period, interval=interval)
        if df is None or df.empty:
            return []

        bars: List[Dict[str, Any]] = []
        for ts, row in df.iterrows():
            bars.append({
                "timestamp": str(ts),
                "open": float(row.get("Open", 0)),
                "high": float(row.get("High", 0)),
                "low": float(row.get("Low", 0)),
                "close": float(row.get("Close", 0)),
                "volume": int(row.get("Volume", 0)),
            })
        return bars
    except Exception as exc:
        logger.error("Price history fetch failed for %s: %s", symbol, exc)
        return []


def get_fundamentals(
    symbol: str,
    use_cache: bool = True,
) -> Dict[str, Any]:
    """Get fundamentals for *symbol*, using cache when available.

    Parameters
    ----------
    symbol : str
        Ticker symbol.
    use_cache : bool
        When True, check the persistence layer for cached data before
        fetching from yfinance.

    Returns
    -------
    dict
        Fundamental data dict.
    """
    if use_cache:
        try:
            from data.portfolio_persistence import get_cached_fundamentals, cache_fundamentals
            cached = get_cached_fundamentals(symbol, ttl_seconds=_CACHE_TTL_SECONDS)
            if cached is not None:
                logger.debug("Using cached fundamentals for %s", symbol)
                return cached
        except Exception:
            logger.debug("Cache lookup failed for %s, fetching fresh", symbol)

    data = fetch_fundamentals(symbol)

    # Store in cache if successful
    if "error" not in data and use_cache:
        try:
            from data.portfolio_persistence import cache_fundamentals
            cache_fundamentals(symbol, data)
        except Exception:
            logger.debug("Failed to cache fundamentals for %s", symbol)

    return data
