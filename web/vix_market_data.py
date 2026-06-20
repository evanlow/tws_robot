"""SPY + VIX market data provider for the autonomous market-regime gate."""

from __future__ import annotations

import logging
from typing import Any, Dict, Tuple

logger = logging.getLogger(__name__)


def _ticker_open_last(yf, symbol: str) -> Tuple[float, float]:
    """Return ``(open, last)`` for a yfinance symbol, failing with zeros."""

    ticker = yf.Ticker(symbol)
    try:
        fast_info = ticker.fast_info
        open_price = float(getattr(fast_info, "open", 0.0) or 0.0)
        last_price = float(getattr(fast_info, "last_price", 0.0) or 0.0)
        if open_price > 0 and last_price > 0:
            return open_price, last_price
    except Exception:
        logger.debug("fast_info unavailable for %s", symbol, exc_info=True)

    try:
        hist = ticker.history(period="1d")
        if not hist.empty:
            open_price = float(hist["Open"].iloc[0])
            last_price = float(hist["Close"].iloc[-1])
            if open_price > 0 and last_price > 0:
                return open_price, last_price
    except Exception:
        logger.debug("history fallback unavailable for %s", symbol, exc_info=True)

    return 0.0, 0.0


def spy_vix_price_from_yfinance() -> Dict[str, Any]:
    """Fetch SPY and VIX day-open/current values via yfinance.

    The engine treats zero SPY prices as a bearish/no-trade state.  VIX can be
    configured to fail open or fail closed via ``vix_missing_blocks_trade`` in
    ``AutonomousTradingConfig``; by default it fails open with a warning so
    tests and offline development are not accidentally blocked.
    """

    try:
        import yfinance as yf  # type: ignore[import]
    except Exception:
        logger.exception("Failed to import yfinance for SPY/VIX market data")
        return {
            "open": 0.0,
            "current": 0.0,
            "vix_open": 0.0,
            "vix_current": 0.0,
            "error": "yfinance unavailable — failing SPY gate closed",
        }

    spy_open, spy_current = _ticker_open_last(yf, "SPY")
    vix_open, vix_current = _ticker_open_last(yf, "^VIX")

    payload = {
        "open": spy_open,
        "current": spy_current,
        "spy_open": spy_open,
        "spy_current": spy_current,
        "vix_open": vix_open,
        "vix_current": vix_current,
        "source": "yfinance",
    }
    if spy_open <= 0 or spy_current <= 0:
        payload["error"] = "SPY data unavailable — failing SPY gate closed"
    if vix_open <= 0 or vix_current <= 0:
        payload["vix_error"] = "VIX data unavailable"
    return payload


def install_spy_vix_provider() -> None:
    """Patch ``api_autonomous`` to use the SPY+VIX yfinance provider.

    Kept as a tiny installer so we do not need to duplicate the large
    ``api_autonomous.py`` route module just to improve its default provider.
    Test/operator overrides via ``current_app.config['autonomous_spy_price_provider']``
    still take precedence.
    """

    try:
        from web.routes import api_autonomous
        api_autonomous._spy_price_from_yfinance = spy_vix_price_from_yfinance
    except Exception:
        logger.exception("Failed to install SPY+VIX market data provider")
