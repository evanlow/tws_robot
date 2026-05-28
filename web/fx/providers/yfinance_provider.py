"""yfinance FX data provider for the FX Research Dashboard.

Fetches live/delayed FX price data from Yahoo Finance via the yfinance library.
This provider is for research display only and does not place orders or connect
to any broker or order execution system.
"""

from __future__ import annotations

import logging
from datetime import timezone

try:
    import yfinance as yf

    _YFINANCE_AVAILABLE = True
except ImportError:  # pragma: no cover
    _YFINANCE_AVAILABLE = False

from web.fx.indicators import pct_change

logger = logging.getLogger(__name__)

# Minimum weekly % change (in percentage points, e.g. 0.25 = 0.25%) to trigger a bias signal
_SIGNAL_THRESHOLD_PCT = 0.25


def _classify_sgd_bias(weekly_change_pct: float | None) -> str:
    """Classify signal bias for SGD cross pairs.

    A rising FX rate (e.g. USD/SGD higher) means SGD weakened → Short SGD.
    A falling FX rate means SGD strengthened → Long SGD.
    """
    if weekly_change_pct is None:
        return "Neutral"
    if weekly_change_pct > _SIGNAL_THRESHOLD_PCT:
        return "Short SGD"
    if weekly_change_pct < -_SIGNAL_THRESHOLD_PCT:
        return "Long SGD"
    return "Neutral"


def _classify_generic_bias(weekly_change_pct: float | None) -> str:
    """Classify signal bias for non-SGD pairs (e.g. EUR/USD, USD/JPY)."""
    if weekly_change_pct is None:
        return "Neutral"
    if weekly_change_pct > _SIGNAL_THRESHOLD_PCT:
        return "Bullish"
    if weekly_change_pct < -_SIGNAL_THRESHOLD_PCT:
        return "Bearish"
    return "Neutral"


def _compute_signal_bias(pair: str, weekly_change_pct: float | None) -> str:
    """Return the appropriate signal bias label for the given pair."""
    if "SGD" in pair:
        return _classify_sgd_bias(weekly_change_pct)
    return _classify_generic_bias(weekly_change_pct)


def _fetch_pair_data(symbol: str, pair: str, timeout: int) -> dict | None:
    """Fetch and compute market watch fields for a single FX pair.

    Returns a populated item dict on success, or None if data is unusable.
    """
    try:
        ticker = yf.Ticker(symbol)
        hist = ticker.history(period="7d", timeout=timeout)
        if hist is None or hist.empty or len(hist) < 2:
            logger.debug("Insufficient history for %s (%s)", pair, symbol)
            return None

        close = hist["Close"]
        last_price = float(close.iloc[-1])
        daily_chg = pct_change(float(close.iloc[-1]), float(close.iloc[-2]))
        weekly_chg = pct_change(float(close.iloc[-1]), float(close.iloc[0]))

        last_ts = close.index[-1]
        try:
            as_of = last_ts.to_pydatetime().astimezone(timezone.utc).isoformat()
        except Exception:
            as_of = str(last_ts)

        signal_bias = _compute_signal_bias(pair, weekly_chg)

        return {
            "pair": pair,
            "last_price": round(last_price, 6),
            "daily_change_pct": round(daily_chg, 4) if daily_chg is not None else 0.0,
            "weekly_change_pct": round(weekly_chg, 4) if weekly_chg is not None else 0.0,
            "signal_bias": signal_bias,
            "notes": "Live/delayed research data from yfinance",
            "data_source": "yfinance",
            "as_of": as_of,
        }
    except Exception as exc:
        logger.warning("Failed to fetch FX data for %s (%s): %s", pair, symbol, exc)
        return None


def fetch_fx_market_watch_items(pairs: list[dict], timeout: int = 10) -> dict:
    """Fetch live/delayed FX market watch data from yfinance for the given pairs.

    Each entry in ``pairs`` must have 'pair' (display name) and 'symbol'
    (Yahoo Finance ticker, e.g. 'USDSGD=X') keys.

    If a symbol fails to return usable data it is skipped rather than crashing
    the entire dashboard.

    Args:
        pairs: List of pair config dicts.
        timeout: HTTP timeout in seconds passed to the yfinance request.

    Returns:
        Standard market watch result dict with 'available', and 'items' keys.
    """
    if not _YFINANCE_AVAILABLE:
        return {
            "available": False,
            "message": "yfinance package is not installed.",
            "items": [],
        }

    items = []
    for pair_info in pairs:
        result = _fetch_pair_data(
            symbol=pair_info["symbol"],
            pair=pair_info["pair"],
            timeout=timeout,
        )
        if result is not None:
            items.append(result)

    if not items:
        return {
            "available": False,
            "message": "Live FX research data source unavailable or returned no usable data.",
            "items": [],
        }

    return {
        "available": True,
        "items": items,
    }
