"""FX Signal Service — research-only mock data for the FX Research Dashboard.

This module provides sample/placeholder data for the FX Research Dashboard.
It does NOT connect to external APIs, live market data, or order execution.
All values are illustrative and intended for UI development only.
"""


def get_fx_dashboard_data() -> dict:
    """Return mock FX dashboard data for all five dashboard sections.

    Returns:
        Dictionary with keys: market_watch, sneer_proxy, mas_policy,
        macro_pressure, signal_summary.
    """
    return {
        "market_watch": _get_market_watch(),
        "sneer_proxy": _get_sneer_proxy(),
        "mas_policy": _get_mas_policy(),
        "macro_pressure": _get_macro_pressure(),
        "signal_summary": _get_signal_summary(),
    }


def _get_market_watch() -> list[dict]:
    """Sample SGD-related FX pair data."""
    return [
        {
            "pair": "USD/SGD",
            "last_price": 1.3245,
            "daily_change_pct": -0.12,
            "signal_bias": "Long SGD",
            "notes": "USD weakening on dovish Fed expectations",
        },
        {
            "pair": "EUR/SGD",
            "last_price": 1.4532,
            "daily_change_pct": 0.08,
            "signal_bias": "Neutral",
            "notes": "Consolidating near range midpoint",
        },
        {
            "pair": "JPY/SGD",
            "last_price": 0.008912,
            "daily_change_pct": -0.25,
            "signal_bias": "Long SGD",
            "notes": "JPY under pressure from BoJ policy divergence",
        },
        {
            "pair": "CNH/SGD",
            "last_price": 0.1823,
            "daily_change_pct": 0.03,
            "signal_bias": "Neutral",
            "notes": "Stable; CNH managed within PBoC band",
        },
        {
            "pair": "MYR/SGD",
            "last_price": 0.2987,
            "daily_change_pct": -0.05,
            "signal_bias": "Neutral",
            "notes": "Ringgit range-bound",
        },
        {
            "pair": "AUD/SGD",
            "last_price": 0.8834,
            "daily_change_pct": 0.15,
            "signal_bias": "Short SGD",
            "notes": "AUD supported by commodity rally",
        },
        {
            "pair": "GBP/SGD",
            "last_price": 1.6821,
            "daily_change_pct": 0.22,
            "signal_bias": "Short SGD",
            "notes": "GBP strengthening on hawkish BoE tone",
        },
    ]


def _get_sneer_proxy() -> dict:
    """Sample S$NEER proxy monitor data."""
    return {
        "estimated_sneer_proxy": 101.45,
        "latest_official_sneer": 101.20,
        "estimated_band_zone": "Upper zone",
        "proxy_deviation_pct": 0.25,
        "confidence": "Medium",
        "disclaimer": (
            "MAS does not publish the exact S$NEER basket weights, midpoint, "
            "width, or live band edges. This dashboard uses research estimates only."
        ),
    }


def _get_mas_policy() -> dict:
    """Sample MAS Policy Console data."""
    return {
        "last_decision_date": "2025-10-14",
        "current_stance": "Slight appreciation of S$NEER policy band",
        "slope_changed": False,
        "width_changed": False,
        "centre_changed": False,
        "statement_tone": "Neutral",
        "next_policy_window": "2026-04 (estimated)",
    }


def _get_macro_pressure() -> dict:
    """Sample Macro Pressure Monitor data."""
    return {
        "mas_core_inflation": 2.5,
        "headline_cpi_inflation": 3.1,
        "gdp_growth": 2.8,
        "oil_price_pressure": "Moderate",
        "usd_strength": "Firm",
        "china_cny_pressure": "Mild easing bias",
        "overall_macro_pressure_score": 58,
    }


def _get_signal_summary() -> dict:
    """Sample Research Signal Summary."""
    return {
        "overall_fx_bias": "Mild SGD strength",
        "confidence_score": 62,
        "suggested_action": "Watch only",
        "explanation": (
            "Current research signal: Mild SGD strength bias. Confidence: 62%. "
            "Suggested action: Watch only. Rationale: S$NEER proxy remains in the "
            "upper half of the estimated range, but USD momentum is strong and the "
            "dashboard is using sample data."
        ),
    }
