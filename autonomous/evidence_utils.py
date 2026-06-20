"""Shared helpers for working with realized evidence records."""

from __future__ import annotations

from typing import Any, Dict, Optional


def _realized_r(record: Dict[str, Any]) -> Optional[float]:
    outcome = record.get("outcome") or {}
    if not outcome.get("realized"):
        return None
    value = outcome.get("realized_r_multiple")
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
