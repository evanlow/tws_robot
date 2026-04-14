"""AI Risk Alerts — Enhancement 4.

Provides natural-language explanations for emergency events.

Usage::

    from risk.ai_alerts import explain_emergency_event, generate_alert_summary
    from risk.emergency_controls import EmergencyEvent

    md = explain_emergency_event(event)
    digest = generate_alert_summary(events, window_hours=24)
"""

import json
import logging
from datetime import datetime, timezone
from typing import List, Optional

from ai.client import get_client
from ai.prompts import Prompts

logger = logging.getLogger(__name__)


def _event_to_dict(event: "EmergencyEvent") -> dict:  # type: ignore[name-defined]
    """Serialise an EmergencyEvent to a plain dict."""
    if isinstance(event, dict):
        return event
    return {
        "timestamp": getattr(event, "timestamp", datetime.now(timezone.utc)).isoformat()
        if not isinstance(getattr(event, "timestamp", None), str)
        else event.timestamp,
        "level": getattr(event.level, "value", str(event.level))
        if hasattr(event, "level") else "UNKNOWN",
        "reason": getattr(event.reason, "value", str(event.reason))
        if hasattr(event, "reason") else "UNKNOWN",
        "trigger_value": getattr(event, "trigger_value", None),
        "threshold": getattr(event, "threshold", None),
        "message": getattr(event, "message", ""),
        "auto_triggered": getattr(event, "auto_triggered", False),
        "positions_closed": getattr(event, "positions_closed", 0),
        "orders_cancelled": getattr(event, "orders_cancelled", 0),
    }


def explain_emergency_event(event: "EmergencyEvent") -> str:  # type: ignore[name-defined]
    """Generate a plain-English markdown explanation for a single emergency event.

    Args:
        event: An ``EmergencyEvent`` instance from ``risk.emergency_controls``.

    Returns:
        Markdown string with sections: What Happened, Why It Matters,
        Recommended Actions.  Returns a fallback message when AI is disabled.
    """
    client = get_client()
    if client is None:
        return (
            "_AI explanation unavailable. Set `AI_ENABLED=true` and "
            "`OPENAI_API_KEY` to enable risk alert explanations._"
        )

    event_dict = _event_to_dict(event)
    event_json = json.dumps(event_dict, indent=2, default=str)

    system_prompt = Prompts.RISK_ALERT_EXPLANATION.format(event_json=event_json)

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": "Please explain this emergency event."},
    ]

    try:
        return client.chat(messages, temperature=0.3)
    except RuntimeError as exc:
        logger.error("AI risk alert explanation error: %s", exc)
        return "_Failed to generate AI explanation. Please check logs for details._"


def generate_alert_summary(
    events: List["EmergencyEvent"],  # type: ignore[name-defined]
    window_hours: int = 24,
) -> str:
    """Generate a markdown daily-digest summary of emergency events.

    Args:
        events:       List of ``EmergencyEvent`` instances.
        window_hours: Time window described in the summary heading.

    Returns:
        Markdown digest string.
    """
    client = get_client()
    if client is None:
        return (
            "_AI digest unavailable. Set `AI_ENABLED=true` and "
            "`OPENAI_API_KEY` to enable daily risk summaries._"
        )

    events_dict = [_event_to_dict(e) for e in events]
    events_json = json.dumps(events_dict, indent=2, default=str)

    system_prompt = Prompts.RISK_DAILY_DIGEST.format(
        window_hours=window_hours,
        events_json=events_json,
    )

    messages = [
        {"role": "system", "content": system_prompt},
        {
            "role": "user",
            "content": f"Please generate the {window_hours}-hour risk digest.",
        },
    ]

    try:
        return client.chat(messages, temperature=0.4)
    except RuntimeError as exc:
        logger.error("AI risk digest error: %s", exc)
        return "_Failed to generate AI digest. Please check logs for details._"
