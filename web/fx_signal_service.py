"""FX Signal Service — orchestration layer for the FX Research Dashboard.

This module is the thin orchestration layer that assembles dashboard data
from the modular ``web.fx`` package. It does NOT connect to external APIs,
live market data, or order execution unless explicitly configured.

Data mode is controlled by the FX_DATA_MODE environment variable:
  not_configured  — safe empty-state default (default when unset)
  demo            — deterministic, realistic sample research data
  live_research   — placeholder; fails safely (not yet implemented)
"""

from web.fx.config import RESEARCH_ONLY_STATUS, get_fx_data_mode, is_demo_mode, is_live_research_mode
from web.fx.demo_data import (
    get_demo_macro_pressure,
    get_demo_market_watch,
    get_demo_mas_policy,
    get_demo_signal_summary,
    get_demo_sneer_proxy,
)
from web.fx.data_sources import (
    get_live_fx_market_data,
    get_live_mas_policy_data,
    get_live_signal_summary,
    get_live_sneer_proxy_data,
)
from web.fx.macro_sources import get_live_macro_pressure


# ---------------------------------------------------------------------------
# Public data getters
# ---------------------------------------------------------------------------


def get_data_status() -> dict:
    """Return the current data source configuration status."""
    mode = get_fx_data_mode()
    if mode == "demo":
        data_mode_label = "Demo Research Data"
    elif mode == "live_research":
        data_mode_label = "Live Research (Unavailable)"
    else:
        data_mode_label = "Not Configured"
    return {
        "data_mode": data_mode_label,
        **RESEARCH_ONLY_STATUS,
    }


def get_market_watch() -> dict:
    """Return FX market watch data or empty state if unavailable."""
    if is_demo_mode():
        return get_demo_market_watch()
    if is_live_research_mode():
        return get_live_fx_market_data()
    return {
        "available": False,
        "message": "No live FX data source configured.",
        "items": [],
    }


def get_sneer_proxy() -> dict:
    """Return S$NEER proxy data or empty state if unavailable."""
    if is_demo_mode():
        return get_demo_sneer_proxy()
    if is_live_research_mode():
        return get_live_sneer_proxy_data()
    return {
        "available": False,
        "message": "No S$NEER data source configured.",
        "items": [],
    }


def get_mas_policy() -> dict:
    """Return MAS policy data or empty state if unavailable."""
    if is_demo_mode():
        return get_demo_mas_policy()
    if is_live_research_mode():
        return get_live_mas_policy_data()
    return {
        "available": False,
        "message": "No MAS policy data source configured.",
        "items": [],
    }


def get_macro_pressure() -> dict:
    """Return macro pressure data or empty state if unavailable."""
    if is_demo_mode():
        return get_demo_macro_pressure()
    if is_live_research_mode():
        return get_live_macro_pressure()
    return {
        "available": False,
        "message": "No macro data source configured.",
        "items": [],
    }


def get_signal_summary() -> dict:
    """Return research signal summary or empty state if unavailable."""
    if is_demo_mode():
        return get_demo_signal_summary()
    if is_live_research_mode():
        return get_live_signal_summary()
    return {
        "available": False,
        "message": "Signal unavailable until required data sources are configured.",
        "items": [],
    }


def get_fx_dashboard_data() -> dict:
    """Return FX dashboard data for all sections.

    Returns:
        Dictionary with keys: data_status, market_watch, sneer_proxy,
        mas_policy, macro_pressure, signal_summary.
    """
    return {
        "data_status": get_data_status(),
        "market_watch": get_market_watch(),
        "sneer_proxy": get_sneer_proxy(),
        "mas_policy": get_mas_policy(),
        "macro_pressure": get_macro_pressure(),
        "signal_summary": get_signal_summary(),
    }
