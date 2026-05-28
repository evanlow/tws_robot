"""FX configuration module — mode management and research-only safety constants.

Data mode is controlled by the FX_DATA_MODE environment variable:
  not_configured  — safe empty-state default (default when unset)
  demo            — deterministic, realistic sample research data
  live_research   — connects to a configured FX data provider for live/delayed data
"""

import os

VALID_FX_DATA_MODES = {"not_configured", "demo", "live_research"}
DEFAULT_FX_DATA_MODE = "not_configured"

RESEARCH_ONLY_STATUS = {
    "execution_status": "Disabled",
    "live_trading": "Disabled",
    "order_placement": "Disabled",
}

# ---------------------------------------------------------------------------
# FX provider configuration
# ---------------------------------------------------------------------------

DEFAULT_FX_PROVIDER = "yfinance"
VALID_FX_PROVIDERS = {"yfinance"}
DEFAULT_FX_PROVIDER_TIMEOUT_SECONDS = 10

FX_MARKET_WATCH_PAIRS = [
    {"pair": "USD/SGD", "symbol": "USDSGD=X"},
    {"pair": "EUR/SGD", "symbol": "EURSGD=X"},
    {"pair": "GBP/SGD", "symbol": "GBPSGD=X"},
    {"pair": "JPY/SGD", "symbol": "JPYSGD=X"},
    {"pair": "AUD/SGD", "symbol": "AUDSGD=X"},
    {"pair": "USD/CNH", "symbol": "USDCNH=X"},
    {"pair": "USD/JPY", "symbol": "USDJPY=X"},
    {"pair": "EUR/USD", "symbol": "EURUSD=X"},
]


def get_fx_provider() -> str:
    """Return the active FX data provider from the FX_PROVIDER environment variable.

    Falls back to the default provider if the value is missing or invalid.
    """
    raw = os.environ.get("FX_PROVIDER", DEFAULT_FX_PROVIDER).lower().strip()
    if raw not in VALID_FX_PROVIDERS:
        return DEFAULT_FX_PROVIDER
    return raw


def get_fx_provider_timeout_seconds() -> int:
    """Return the FX provider HTTP timeout from FX_PROVIDER_TIMEOUT_SECONDS.

    Falls back to the default timeout if the value is missing or invalid.
    """
    raw = os.environ.get(
        "FX_PROVIDER_TIMEOUT_SECONDS", str(DEFAULT_FX_PROVIDER_TIMEOUT_SECONDS)
    ).strip()
    try:
        val = int(raw)
        if val > 0:
            return val
    except (ValueError, TypeError):
        pass
    return DEFAULT_FX_PROVIDER_TIMEOUT_SECONDS


def get_fx_data_mode() -> str:
    """Return the active FX data mode from the FX_DATA_MODE environment variable.

    If an invalid value is supplied, fails safely back to 'not_configured'.
    """
    raw = os.environ.get("FX_DATA_MODE", DEFAULT_FX_DATA_MODE).lower().strip()
    if raw not in VALID_FX_DATA_MODES:
        return DEFAULT_FX_DATA_MODE
    return raw


def is_demo_mode() -> bool:
    """Return True when FX_DATA_MODE is set to 'demo'."""
    return get_fx_data_mode() == "demo"


def is_live_research_mode() -> bool:
    """Return True when FX_DATA_MODE is set to 'live_research'."""
    return get_fx_data_mode() == "live_research"
