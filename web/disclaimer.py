"""Risk disclaimer acceptance management for TWS Robot.

Tracks whether the user has accepted the current version of the Risk &
Liability Disclaimer.  Acceptance is persisted in a JSON file so users are
not prompted on every launch.  When the disclaimer version changes the file
is treated as stale and the user must re-accept.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Bump this string whenever the disclaimer text changes materially.
RISK_DISCLAIMER_VERSION = "risk_disclaimer_v1"

# Default path for the acceptance file.  Can be overridden via the
# ``DISCLAIMER_ACCEPTANCE_FILE`` environment variable or by passing a path
# directly to the helper functions.
_DEFAULT_ACCEPTANCE_FILE = Path(
    os.environ.get("DISCLAIMER_ACCEPTANCE_FILE", "disclaimer_acceptance.json")
)


def _acceptance_file_path() -> Path:
    """Return the configured acceptance file path."""
    env_path = os.environ.get("DISCLAIMER_ACCEPTANCE_FILE")
    if env_path:
        return Path(env_path)
    return _DEFAULT_ACCEPTANCE_FILE


def is_accepted(file_path: Optional[Path] = None) -> bool:
    """Return ``True`` if the current disclaimer version has been accepted.

    Parameters
    ----------
    file_path:
        Override the acceptance file path (mainly used in tests).
    """
    path = file_path or _acceptance_file_path()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return (
            data.get("accepted_disclaimer") is True
            and data.get("disclaimer_version") == RISK_DISCLAIMER_VERSION
        )
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return False


def save_acceptance(
    app_version: str = "unknown",
    file_path: Optional[Path] = None,
) -> None:
    """Persist the disclaimer acceptance record.

    Parameters
    ----------
    app_version:
        Application version / commit hash to include in the record.
    file_path:
        Override the acceptance file path (mainly used in tests).
    """
    path = file_path or _acceptance_file_path()
    record = {
        "accepted_disclaimer": True,
        "disclaimer_version": RISK_DISCLAIMER_VERSION,
        "accepted_at": datetime.now(timezone.utc).isoformat(),
        "app_version": app_version,
    }
    try:
        path.write_text(json.dumps(record, indent=2), encoding="utf-8")
        logger.info("Disclaimer acceptance saved: version=%s", RISK_DISCLAIMER_VERSION)
    except OSError as exc:
        logger.error("Could not save disclaimer acceptance: %s", exc)
        raise


def get_acceptance_record(file_path: Optional[Path] = None) -> dict:
    """Return the raw acceptance record dict, or an empty dict if absent.

    Parameters
    ----------
    file_path:
        Override the acceptance file path (mainly used in tests).
    """
    path = file_path or _acceptance_file_path()
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}
