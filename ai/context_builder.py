"""Context builder — serialises live system state into a compact JSON dict
suitable for injection into LLM system prompts.

All functions return plain Python dicts that can be serialised with
``json.dumps``.  They intentionally avoid importing heavy application
modules at the top level so that the module can always be imported even
when optional subsystems are not running.
"""

import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------

def build_trading_context(
    *,
    equity: Optional[float] = None,
    daily_pnl: Optional[float] = None,
    open_positions: Optional[List[Dict[str, Any]]] = None,
    active_strategies: Optional[List[Dict[str, Any]]] = None,
    risk_status: Optional[Dict[str, Any]] = None,
    recent_alerts: Optional[List[Dict[str, Any]]] = None,
) -> str:
    """Build a compact JSON string describing the current trading state.

    All arguments are optional; missing fields are replaced with sensible
    defaults so callers can pass only what they have available.

    Args:
        equity:            Current portfolio equity value.
        daily_pnl:         Today's realised + unrealised P&L.
        open_positions:    List of position dicts (symbol, qty, entry_price,
                           current_price, unrealised_pnl).
        active_strategies: List of strategy dicts (name, status, positions).
        risk_status:       Dict from risk.monitoring (overall_health,
                           health_score, active_alerts count, etc.).
        recent_alerts:     List of recent alert dicts (level, message,
                           timestamp).

    Returns:
        JSON string suitable for embedding in an LLM prompt.
    """
    context: Dict[str, Any] = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "portfolio": {
            "equity": equity,
            "daily_pnl": daily_pnl,
        },
        "open_positions": open_positions or [],
        "active_strategies": active_strategies or [],
        "risk_status": risk_status or {"overall_health": "UNKNOWN"},
        "recent_alerts": (recent_alerts or [])[:10],  # cap at 10 for brevity
    }
    return json.dumps(context, default=_json_default, indent=2)


def positions_to_context(positions: List[Any]) -> List[Dict[str, Any]]:
    """Convert a list of position objects / dicts to a uniform list of dicts.

    Accepts both plain dicts and objects with attributes, so callers can
    pass whatever their position model looks like.
    """
    result = []
    for pos in positions:
        if isinstance(pos, dict):
            result.append(pos)
        else:
            result.append(_obj_to_dict(pos, [
                "symbol", "quantity", "entry_price", "current_price",
                "unrealised_pnl", "side",
            ]))
    return result


def strategies_to_context(strategies: List[Any]) -> List[Dict[str, Any]]:
    """Convert a list of strategy objects / dicts to a uniform list of dicts."""
    result = []
    for strat in strategies:
        if isinstance(strat, dict):
            result.append(strat)
        else:
            result.append(_obj_to_dict(strat, [
                "name", "status", "symbols", "active_positions",
            ]))
    return result


def risk_status_to_context(risk_status: Any) -> Dict[str, Any]:
    """Extract a concise dict from a RiskStatus object or plain dict."""
    if isinstance(risk_status, dict):
        return risk_status

    return _obj_to_dict(risk_status, [
        "overall_health", "health_score",
    ])


def alerts_to_context(alerts: List[Any]) -> List[Dict[str, Any]]:
    """Convert alert objects / dicts to a list of concise dicts."""
    result = []
    for alert in alerts:
        if isinstance(alert, dict):
            result.append(alert)
        else:
            d = _obj_to_dict(alert, ["level", "category", "message", "timestamp"])
            # Normalise enums to their .value strings
            for key in ("level", "category"):
                if hasattr(d.get(key), "value"):
                    d[key] = d[key].value
            result.append(d)
    return result


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _obj_to_dict(obj: Any, keys: List[str]) -> Dict[str, Any]:
    """Extract named attributes from an object into a dict, skipping missing ones."""
    return {k: getattr(obj, k, None) for k in keys}


def _json_default(obj: Any) -> Any:
    """Fallback JSON serialiser for non-serialisable types."""
    if isinstance(obj, datetime):
        return obj.isoformat()
    if hasattr(obj, "value"):  # Enum
        return obj.value
    if hasattr(obj, "__dict__"):
        return obj.__dict__
    return str(obj)
