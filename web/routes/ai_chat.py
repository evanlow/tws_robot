"""AI Copilot Chat route — Enhancement 1.

Endpoints
---------
POST /ai/chat
    Body: { "message": "..." }
    Returns: { "reply": "...", "context_timestamp": "..." }

GET /ai/chat/history
    Returns: { "history": [ {"role": "...", "content": "..."}, ... ] }

DELETE /ai/chat/history
    Clears the in-memory chat history for the current session.
"""

import logging
from collections import deque
from datetime import datetime, timezone
from typing import Deque, Dict, List

from flask import Blueprint, jsonify, request

from ai.client import get_client
from ai.context_builder import build_trading_context
from ai.prompts import Prompts

logger = logging.getLogger(__name__)

bp = Blueprint("ai_chat", __name__, url_prefix="/ai")

# In-memory chat history: a circular buffer of the last 50 messages.
# In a multi-user deployment this should be moved to a session store.
_MAX_HISTORY = 50
_history: Deque[Dict[str, str]] = deque(maxlen=_MAX_HISTORY)


def _ai_unavailable_response():
    return jsonify({
        "error": "AI features are not enabled. "
                 "Set AI_ENABLED=true and OPENAI_API_KEY to activate."
    }), 503


@bp.route("/chat", methods=["POST"])
def chat():
    """Accept a user message, call OpenAI, return the assistant reply."""
    client = get_client()
    if client is None:
        return _ai_unavailable_response()

    data = request.get_json(silent=True) or {}
    user_message: str = (data.get("message") or "").strip()
    if not user_message:
        return jsonify({"error": "message field is required"}), 400

    # Build live-system context (empty stubs when no live data available)
    context_json = build_trading_context()

    system_prompt = Prompts.TRADING_ASSISTANT.format(context_json=context_json)

    # Assemble message list: system + full history + new user turn
    messages: List[Dict[str, str]] = [{"role": "system", "content": system_prompt}]
    messages.extend(list(_history))
    messages.append({"role": "user", "content": user_message})

    try:
        reply = client.chat(messages)
    except RuntimeError as exc:
        logger.error("AI chat error: %s", exc)
        return jsonify({"error": "AI request failed. Please try again."}), 502

    # Persist to history
    _history.append({"role": "user", "content": user_message})
    _history.append({"role": "assistant", "content": reply})

    return jsonify({
        "reply": reply,
        "context_timestamp": datetime.now(timezone.utc).isoformat(),
    })


@bp.route("/chat/history", methods=["GET"])
def history():
    """Return the current in-memory chat history."""
    return jsonify({"history": list(_history)})


@bp.route("/chat/history", methods=["DELETE"])
def clear_history():
    """Clear the in-memory chat history."""
    _history.clear()
    return jsonify({"status": "cleared"})
