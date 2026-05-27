"""FX Signal Service — data provider for the FX Research Dashboard.

This module provides structured data for the FX Research Dashboard.
When no real data source is configured, it returns empty states with
appropriate messages. It does NOT connect to external APIs, live market
data, or order execution unless explicitly configured.
"""


def get_data_status() -> dict:
    """Return the current data source configuration status."""
    return {
        "data_mode": "Not Configured",
        "execution_status": "Disabled",
        "live_trading": "Disabled",
        "order_placement": "Disabled",
    }


def get_market_watch() -> dict:
    """Return FX market watch data or empty state if unavailable."""
    return {
        "available": False,
        "message": "No live FX data source configured.",
        "items": [],
    }


def get_sneer_proxy() -> dict:
    """Return S$NEER proxy data or empty state if unavailable."""
    return {
        "available": False,
        "message": "No S$NEER data source configured.",
        "items": [],
    }


def get_mas_policy() -> dict:
    """Return MAS policy data or empty state if unavailable."""
    return {
        "available": False,
        "message": "No MAS policy data source configured.",
        "items": [],
    }


def get_macro_pressure() -> dict:
    """Return macro pressure data or empty state if unavailable."""
    return {
        "available": False,
        "message": "No macro data source configured.",
        "items": [],
    }


def get_signal_summary() -> dict:
    """Return research signal summary or empty state if unavailable."""
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
