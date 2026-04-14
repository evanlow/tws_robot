"""AI Strategy route — Enhancement 2.

Endpoints
---------
POST /ai/strategy/suggest-params
    Body: { "strategy_name": "...", "current_params": {...},
            "backtest_metrics": {...} }
    Returns: { "suggestions": { ..., "_reasoning": "..." } }

POST /ai/strategy/create
    Body: { "description": "Buy when RSI < 30 on daily bars..." }
    Returns: { "config": { StrategyConfig-compatible JSON } }

POST /ai/strategy/explain-signal
    Body: { "signal": { ...signal dict... } }
    Returns: { "explanation": "..." }
"""

import json
import logging

from flask import Blueprint, jsonify, request

from ai.client import get_client
from ai.prompts import Prompts

logger = logging.getLogger(__name__)

bp = Blueprint("ai_strategy", __name__, url_prefix="/ai/strategy")


def _ai_unavailable_response():
    return jsonify({
        "error": "AI features are not enabled. "
                 "Set AI_ENABLED=true and OPENAI_API_KEY to activate."
    }), 503


@bp.route("/suggest-params", methods=["POST"])
def suggest_params():
    """Suggest improved strategy parameters based on backtest performance."""
    client = get_client()
    if client is None:
        return _ai_unavailable_response()

    data = request.get_json(silent=True) or {}
    strategy_name: str = data.get("strategy_name", "Unknown Strategy")
    current_params = data.get("current_params", {})
    backtest_metrics = data.get("backtest_metrics", {})

    system_prompt = Prompts.STRATEGY_PARAM_SUGGESTION.format(
        strategy_name=strategy_name,
        current_params_json=json.dumps(current_params, indent=2),
        metrics_json=json.dumps(backtest_metrics, indent=2),
    )

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": "Please suggest improved parameter values."},
    ]

    try:
        raw = client.chat(messages, temperature=0.2)
    except RuntimeError as exc:
        logger.error("AI suggest-params error: %s", exc)
        return jsonify({"error": "AI request failed. Please try again."}), 502

    # Parse JSON response
    try:
        suggestions = json.loads(raw)
    except json.JSONDecodeError:
        # Return raw text under a dedicated key if JSON parse fails
        suggestions = {"_raw": raw}

    return jsonify({"suggestions": suggestions})


@bp.route("/create", methods=["POST"])
def create_strategy():
    """Generate a StrategyConfig JSON object from a plain-English description."""
    client = get_client()
    if client is None:
        return _ai_unavailable_response()

    data = request.get_json(silent=True) or {}
    description: str = (data.get("description") or "").strip()
    if not description:
        return jsonify({"error": "description field is required"}), 400

    system_prompt = Prompts.STRATEGY_CREATE.format(description=description)

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": description},
    ]

    try:
        raw = client.chat(messages, temperature=0.3)
    except RuntimeError as exc:
        logger.error("AI create-strategy error: %s", exc)
        return jsonify({"error": "AI request failed. Please try again."}), 502

    try:
        config = json.loads(raw)
    except json.JSONDecodeError:
        config = {"_raw": raw}

    return jsonify({"config": config})


@bp.route("/explain-signal", methods=["POST"])
def explain_signal():
    """Return a plain-English explanation of a trade signal."""
    client = get_client()
    if client is None:
        return _ai_unavailable_response()

    data = request.get_json(silent=True) or {}
    signal = data.get("signal", {})
    if not signal:
        return jsonify({"error": "signal field is required"}), 400

    system_prompt = Prompts.SIGNAL_EXPLANATION.format(
        signal_json=json.dumps(signal, indent=2, default=str)
    )

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": "Please explain this signal."},
    ]

    try:
        explanation = client.chat(messages, temperature=0.4)
    except RuntimeError as exc:
        logger.error("AI explain-signal error: %s", exc)
        return jsonify({"error": "AI request failed. Please try again."}), 502

    return jsonify({"explanation": explanation})
