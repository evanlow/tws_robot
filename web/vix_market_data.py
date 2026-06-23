"""SPY + VIX market data provider for the autonomous market-regime gate."""

from __future__ import annotations

import logging
from typing import Any, Callable, Dict, Tuple

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
            "source": "yfinance",
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
    if vix_open <= 0 and vix_current <= 0:
        payload["vix_error"] = "VIX data unavailable"
    elif vix_open <= 0:
        payload["vix_error"] = "VIX open price unavailable; intraday direction check disabled"
    elif vix_current <= 0:
        payload["vix_error"] = "VIX current price unavailable"
    return payload


def ibkr_with_yfinance_fallback_spy_provider(bridge_getter: Any) -> "Callable[[], Dict[str, Any]]":
    """Return a SPY price provider that prefers IBKR and falls back to yfinance.

    ``bridge_getter`` is a zero-argument callable that returns the active
    TWSBridge (or ``None`` when not connected).  At call time the provider:

    1. Checks whether the bridge is connected and has a live SPY quote with
       both ``open`` and ``last`` prices from IBKR.
    2. If so, returns IBKR prices tagged ``source: "IBKR"``.
    3. Otherwise falls back to the yfinance provider (``spy_vix_price_from_yfinance``).

    This keeps the SPY gate accurate — IBKR data is real-time, while yfinance
    can be up to 15 minutes delayed for non-subscribers.
    """
    def _provider() -> Dict[str, Any]:
        try:
            bridge = bridge_getter()
            if bridge is not None and getattr(bridge, "is_connected", False):
                # Ensure SPY is subscribed before trying to read the quote.
                # subscribe_market_data is idempotent for already-subscribed symbols.
                try:
                    bridge.subscribe_market_data(["SPY"])
                except Exception:
                    logger.debug("IBKR SPY subscription failed; will fall back to yfinance", exc_info=True)

                getter = getattr(bridge, "get_latest_market_data_quote", None)
                if callable(getter):
                    quote = getter("SPY") or {}
                    open_price = quote.get("open") or 0.0
                    last_price = quote.get("last") or 0.0
                    if open_price > 0 and last_price > 0:
                        logger.info(
                            "SPY gate using IBKR feed: open=%.2f current=%.2f",
                            open_price,
                            last_price,
                        )
                        payload: Dict[str, Any] = {
                            "open": open_price,
                            "current": last_price,
                            "spy_open": open_price,
                            "spy_current": last_price,
                            "source": "IBKR",
                            "market_data_type": quote.get("market_data_type", "UNKNOWN"),
                        }
                        vix_open, vix_current = _ticker_open_last_yfinance()
                        payload["vix_open"] = vix_open
                        payload["vix_current"] = vix_current
                        if vix_open <= 0 and vix_current <= 0:
                            payload["vix_error"] = "VIX data unavailable"
                        return payload
                    logger.debug(
                        "IBKR SPY quote incomplete (open=%.2f last=%.2f); falling back to yfinance",
                        open_price,
                        last_price,
                    )
        except Exception:
            logger.debug("IBKR SPY price lookup failed; falling back to yfinance", exc_info=True)

        logger.info("SPY gate falling back to yfinance")
        return spy_vix_price_from_yfinance()

    return _provider


def _ticker_open_last_yfinance() -> Tuple[float, float]:
    """Fetch VIX open/last via yfinance, returning zeros on failure."""
    try:
        import yfinance as yf  # type: ignore[import]
        return _ticker_open_last(yf, "^VIX")
    except Exception:
        logger.debug("yfinance VIX lookup failed", exc_info=True)
        return 0.0, 0.0


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
