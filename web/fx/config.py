"""FX configuration module — mode management and research-only safety constants.

Data mode is controlled by the FX_DATA_MODE environment variable:
  not_configured  — safe empty-state default (default when unset)
  demo            — deterministic, realistic sample research data
  live_research   — placeholder; fails safely (not yet implemented)
"""

import os

VALID_FX_DATA_MODES = {"not_configured", "demo", "live_research"}
DEFAULT_FX_DATA_MODE = "not_configured"

RESEARCH_ONLY_STATUS = {
    "execution_status": "Disabled",
    "live_trading": "Disabled",
    "order_placement": "Disabled",
}


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
