"""FX Signal Service — data provider for the FX Research Dashboard.

This module provides structured data for the FX Research Dashboard.
When no real data source is configured, it returns empty states with
appropriate messages. It does NOT connect to external APIs, live market
data, or order execution unless explicitly configured.

Data mode is controlled by the FX_DATA_MODE environment variable:
  not_configured  — safe empty-state default (default when unset)
  demo            — deterministic, realistic sample research data
  live_research   — placeholder; fails safely (not yet implemented)
"""

import os


def get_fx_data_mode() -> str:
    """Return the active FX data mode from the FX_DATA_MODE environment variable."""
    return os.environ.get("FX_DATA_MODE", "not_configured").lower()


def is_demo_mode() -> bool:
    """Return True when FX_DATA_MODE is set to 'demo'."""
    return get_fx_data_mode() == "demo"


# ---------------------------------------------------------------------------
# Demo data helpers
# ---------------------------------------------------------------------------


def get_demo_market_watch() -> dict:
    """Return deterministic demo FX market watch data."""
    return {
        "available": True,
        "items": [
            {
                "pair": "USD/SGD",
                "last_price": 1.3500,
                "daily_change_pct": 0.12,
                "weekly_change_pct": -0.30,
                "signal_bias": "Neutral",
                "notes": "SGD consolidating near resistance; watching MAS policy signals",
            },
            {
                "pair": "EUR/SGD",
                "last_price": 1.4600,
                "daily_change_pct": -0.08,
                "weekly_change_pct": 0.20,
                "signal_bias": "Bullish",
                "notes": "EUR/SGD supported by euro area resilience and SGD stability",
            },
            {
                "pair": "GBP/SGD",
                "last_price": 1.7200,
                "daily_change_pct": 0.05,
                "weekly_change_pct": -0.15,
                "signal_bias": "Neutral",
                "notes": "GBP steady; UK data mixed with no clear directional bias",
            },
            {
                "pair": "JPY/SGD",
                "last_price": 0.0089,
                "daily_change_pct": -0.20,
                "weekly_change_pct": -0.50,
                "signal_bias": "Bearish",
                "notes": "JPY weakness persists on yield differentials; BoJ intervention risk elevated",
            },
            {
                "pair": "AUD/SGD",
                "last_price": 0.8800,
                "daily_change_pct": -0.15,
                "weekly_change_pct": -0.25,
                "signal_bias": "Bearish",
                "notes": "AUD soft on China demand concerns and commodity price softness",
            },
            {
                "pair": "USD/CNH",
                "last_price": 7.2300,
                "daily_change_pct": 0.10,
                "weekly_change_pct": 0.30,
                "signal_bias": "Bearish",
                "notes": "CNH under mild pressure from trade uncertainty; watching PBoC fixing",
            },
            {
                "pair": "USD/JPY",
                "last_price": 151.50,
                "daily_change_pct": 0.22,
                "weekly_change_pct": 0.60,
                "signal_bias": "Bearish JPY",
                "notes": "USD/JPY elevated; BoJ intervention risk increases above 152",
            },
            {
                "pair": "EUR/USD",
                "last_price": 1.0820,
                "daily_change_pct": -0.05,
                "weekly_change_pct": 0.10,
                "signal_bias": "Neutral",
                "notes": "EUR/USD rangebound ahead of Fed/ECB data; key level at 1.0800",
            },
        ],
    }


def get_demo_sneer_proxy() -> dict:
    """Return deterministic demo S$NEER proxy data.

    Returns a proxy/research estimate only — not the official MAS S$NEER.
    """
    return {
        "available": True,
        "proxy_index": 101.25,
        "change_1d": 0.08,
        "change_20d": 0.45,
        "z_score": 0.7,
        "interpretation": "SGD mildly firm versus proxy basket",
        "note": (
            "Proxy/research estimate only — not official MAS S$NEER. "
            "Derived from a weighted basket of SGD cross rates."
        ),
    }


def get_demo_mas_policy() -> dict:
    """Return deterministic demo MAS policy context."""
    return {
        "available": True,
        "latest_stance": "Slight appreciation path maintained",
        "next_review_window": "Upcoming semi-annual MAS policy statement",
        "inflation_assessment": "Core inflation moderating, within target band",
        "growth_assessment": "GDP growth subdued, tracking below trend",
        "sgd_policy_bias": "Neutral with mild tightening bias retained",
        "notes": (
            "MAS currently maintains a slight appreciation policy path. "
            "Watching for global growth slowdown and domestic inflation pass-through."
        ),
    }


def get_demo_macro_pressure() -> dict:
    """Return deterministic demo macro pressure factors."""
    return {
        "available": True,
        "items": [
            {
                "name": "US 2Y Yield",
                "current_value": "4.75%",
                "direction": "Rising",
                "sgd_impact": "Pressures SGD",
                "notes": "Higher US yields support USD broadly, weighing on SGD",
            },
            {
                "name": "DXY (USD Index)",
                "current_value": "104.5",
                "direction": "Stable",
                "sgd_impact": "Mild SGD Pressure",
                "notes": "DXY consolidating near resistance; break higher would pressure SGD",
            },
            {
                "name": "Singapore CPI",
                "current_value": "2.9%",
                "direction": "Falling",
                "sgd_impact": "Supports SGD",
                "notes": "Inflation moderating reduces urgency for further MAS tightening",
            },
            {
                "name": "Singapore GDP",
                "current_value": "1.2% YoY",
                "direction": "Falling",
                "sgd_impact": "Neutral",
                "notes": "Growth slowing, tempering SGD policy support from MAS",
            },
            {
                "name": "China / CNH Pressure",
                "current_value": "CNH 7.23/USD",
                "direction": "Stable",
                "sgd_impact": "Mild SGD Pressure",
                "notes": "CNH under mild pressure from trade uncertainty; SGD often tracks CNH",
            },
            {
                "name": "Risk Sentiment",
                "current_value": "Cautious",
                "direction": "Deteriorating",
                "sgd_impact": "Pressures SGD",
                "notes": "Global risk-off environment weighs on EM and Asian currencies",
            },
        ],
    }


def get_demo_signal_summary() -> dict:
    """Return deterministic demo research signal opportunities.

    Labelled as research signals only — not trading advice.
    """
    return {
        "available": True,
        "items": [
            {
                "instrument": "USD/SGD",
                "bias": "Bearish USD/SGD",
                "confidence": 62,
                "time_horizon": "1-2 weeks",
                "supporting_factors": ["S$NEER proxy firm", "USD momentum fading"],
                "invalidation_level": "Above 1.3600",
                "risk_notes": "US yield spike would invalidate the view",
            },
            {
                "instrument": "AUD/SGD",
                "bias": "Bearish AUD/SGD",
                "confidence": 55,
                "time_horizon": "1-3 weeks",
                "supporting_factors": ["China demand softness", "AUD/USD technically weak"],
                "invalidation_level": "Above 0.9000",
                "risk_notes": "China stimulus surprise would invalidate bearish bias",
            },
            {
                "instrument": "EUR/SGD",
                "bias": "Neutral EUR/SGD",
                "confidence": 48,
                "time_horizon": "2-4 weeks",
                "supporting_factors": ["EUR/USD rangebound", "SGD policy steady"],
                "invalidation_level": "Break above 1.4750",
                "risk_notes": "ECB surprise easing would shift bias to bearish EUR/SGD",
            },
        ],
    }


# ---------------------------------------------------------------------------
# Public data getters
# ---------------------------------------------------------------------------


def get_data_status() -> dict:
    """Return the current data source configuration status."""
    if is_demo_mode():
        return {
            "data_mode": "Demo Research Data",
            "execution_status": "Disabled",
            "live_trading": "Disabled",
            "order_placement": "Disabled",
        }
    return {
        "data_mode": "Not Configured",
        "execution_status": "Disabled",
        "live_trading": "Disabled",
        "order_placement": "Disabled",
    }


def get_market_watch() -> dict:
    """Return FX market watch data or empty state if unavailable."""
    if is_demo_mode():
        return get_demo_market_watch()
    return {
        "available": False,
        "message": "No live FX data source configured.",
        "items": [],
    }


def get_sneer_proxy() -> dict:
    """Return S$NEER proxy data or empty state if unavailable."""
    if is_demo_mode():
        return get_demo_sneer_proxy()
    return {
        "available": False,
        "message": "No S$NEER data source configured.",
        "items": [],
    }


def get_mas_policy() -> dict:
    """Return MAS policy data or empty state if unavailable."""
    if is_demo_mode():
        return get_demo_mas_policy()
    return {
        "available": False,
        "message": "No MAS policy data source configured.",
        "items": [],
    }


def get_macro_pressure() -> dict:
    """Return macro pressure data or empty state if unavailable."""
    if is_demo_mode():
        return get_demo_macro_pressure()
    return {
        "available": False,
        "message": "No macro data source configured.",
        "items": [],
    }


def get_signal_summary() -> dict:
    """Return research signal summary or empty state if unavailable."""
    if is_demo_mode():
        return get_demo_signal_summary()
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
