"""Live research data sources for the FX Research Dashboard.

This module routes live FX data requests to the configured provider.
Other sections (S$NEER proxy, MAS policy, macro pressure, signal summary)
remain safe unavailable placeholders until future phases implement them.
"""

from web.fx.config import (
    FX_MARKET_WATCH_PAIRS,
    get_fx_provider,
    get_fx_provider_timeout_seconds,
)
from web.fx.providers.yfinance_provider import fetch_fx_market_watch_items


def get_live_fx_market_data() -> dict:
    """Return live/delayed FX market watch data from the configured provider.

    All exceptions are caught and converted into a safe unavailable response
    so the dashboard never crashes due to provider failures.
    """
    try:
        provider = get_fx_provider()
        if provider == "yfinance":
            timeout = get_fx_provider_timeout_seconds()
            return fetch_fx_market_watch_items(FX_MARKET_WATCH_PAIRS, timeout=timeout)
        return {
            "available": False,
            "message": f"Unsupported FX provider: {provider}",
            "items": [],
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "available": False,
            "message": f"Live FX research data source unavailable: {exc}",
            "items": [],
        }


def get_live_sneer_proxy_data() -> dict:
    """Placeholder for future S$NEER proxy live data integration."""
    return {
        "available": False,
        "message": "Live S$NEER proxy data source not configured.",
    }


def get_live_mas_policy_data() -> dict:
    """Placeholder for future MAS policy data integration."""
    return {
        "available": False,
        "message": "Live MAS policy data source not configured.",
    }


def get_live_signal_summary() -> dict:
    """Placeholder for future live signal generation."""
    return {
        "available": False,
        "message": "Live signal data source not configured.",
        "items": [],
    }
