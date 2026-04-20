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
from web.services import get_services

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


_MAX_CONTEXT_POSITIONS = 20
_MAX_CONTEXT_STRATEGIES = 10


def _gather_live_context() -> str:
    """Collect live trading state from the ServiceManager and serialise it.

    Returns a JSON string suitable for the LLM system prompt.  If any
    subsystem is unavailable the corresponding field falls back to
    ``None`` / empty list so the prompt is always well-formed.

    Positions are capped at the top ``_MAX_CONTEXT_POSITIONS`` by absolute
    market value and strategies at the top ``_MAX_CONTEXT_STRATEGIES`` to
    keep the prompt within token limits.
    """
    try:
        svc = get_services()
    except Exception:
        # Outside a Flask request context or services not initialised
        return build_trading_context()

    # -- Equity & P&L --------------------------------------------------
    equity = None
    daily_pnl = None
    risk_status = None
    try:
        risk_summary = svc.risk_manager.get_risk_summary()
        equity = risk_summary.get("current_equity")
        risk_status = risk_summary
    except Exception:
        logger.debug("Could not fetch risk summary for AI context", exc_info=True)

    try:
        insights = svc.get_account_insights()
        daily_pnl = insights.get("daily_pnl_dollar")
    except Exception:
        logger.debug("Could not fetch account insights for AI context", exc_info=True)

    # -- Open positions (capped to top N by market value) ---------------
    open_positions = None
    try:
        raw_positions = svc.get_positions()
        all_positions = [
            {
                "symbol": symbol,
                "quantity": pos.get("quantity", 0),
                "entry_price": pos.get("entry_price", 0),
                "current_price": pos.get("current_price", 0),
                "market_value": pos.get("market_value", 0),
                "unrealized_pnl": pos.get("unrealized_pnl", 0),
                "side": pos.get("side", "LONG"),
                "sec_type": pos.get("sec_type", ""),
            }
            for symbol, pos in raw_positions.items()
        ]
        # Sort by absolute market value descending, keep top N
        all_positions.sort(
            key=lambda p: abs(p.get("market_value", 0)), reverse=True,
        )
        open_positions = all_positions[:_MAX_CONTEXT_POSITIONS]
    except Exception:
        logger.debug("Could not fetch positions for AI context", exc_info=True)

    # -- Active strategies (capped) ------------------------------------
    active_strategies = None
    try:
        reg = svc.strategy_registry
        active_strategies = [
            s.get_performance_summary() for s in reg.get_all_strategies()
        ][:_MAX_CONTEXT_STRATEGIES]
    except Exception:
        logger.debug("Could not fetch strategies for AI context", exc_info=True)

    # -- Recent alerts -------------------------------------------------
    recent_alerts = None
    try:
        recent_alerts = svc.get_alerts()[-10:]
    except Exception:
        logger.debug("Could not fetch alerts for AI context", exc_info=True)

    return build_trading_context(
        equity=equity,
        daily_pnl=daily_pnl,
        open_positions=open_positions,
        active_strategies=active_strategies,
        risk_status=risk_status,
        recent_alerts=recent_alerts,
    )


@bp.route("/chat", methods=["GET"])
def chat_page():
    """Render the full-page AI Copilot chat interface."""
    from flask import render_template
    return render_template("ai_chat/index.html", title="AI Copilot", active_page="ai_chat")


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

    # Build live-system context from the ServiceManager
    context_json = _gather_live_context()

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
