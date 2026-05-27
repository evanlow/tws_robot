"""Placeholder live research data sources for the FX Research Dashboard.

This module provides safe placeholder functions for future live FX data
provider integration. No external API calls are made here yet.
"""


def get_live_fx_market_data() -> dict:
    """Placeholder for future FX provider integration."""
    return {
        "available": False,
        "message": "Live FX research data source not configured.",
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
