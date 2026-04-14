"""Risk route — drawdown gauges, correlation heatmap, profile switching.

GET  /risk               →  risk dashboard
POST /risk/profile       →  switch risk profile
GET  /risk/alerts/<id>/ai-explanation  →  AI explanation for a stored alert
GET  /risk/alerts/digest               →  AI daily digest of recent alerts
"""

from flask import Blueprint, jsonify, render_template, request

from risk.ai_alerts import explain_emergency_event, generate_alert_summary

bp = Blueprint("risk", __name__, url_prefix="/risk")

# In-memory store for demo purposes.
# Keys are string IDs; values are dicts with at minimum "event" key.
_alert_store: dict = {}
_explanation_cache: dict = {}


@bp.route("/")
def index():
    context = {
        "title": "Risk",
        "active_page": "risk",
    }
    return render_template("risk/index.html", **context)


@bp.route("/alerts/<alert_id>/ai-explanation", methods=["GET"])
def alert_ai_explanation(alert_id: str):
    """Return an AI-generated explanation for a stored alert event."""
    if alert_id in _explanation_cache:
        return jsonify({"explanation": _explanation_cache[alert_id], "cached": True})

    event = _alert_store.get(alert_id)
    if event is None:
        return jsonify({"error": "Alert not found"}), 404

    explanation = explain_emergency_event(event)
    _explanation_cache[alert_id] = explanation
    return jsonify({"explanation": explanation, "cached": False})


@bp.route("/alerts/digest", methods=["GET"])
def alert_digest():
    """Return an AI-generated daily digest of recent emergency events."""
    window_hours = int(request.args.get("hours", 24))
    events = list(_alert_store.values())
    digest = generate_alert_summary(events, window_hours=window_hours)
    return jsonify({"digest": digest})
