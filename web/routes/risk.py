"""Risk route — drawdown gauges, correlation heatmap, profile switching.

GET  /risk               →  risk dashboard
POST /risk/profile       →  switch risk profile
GET  /risk/alerts/<id>/ai-explanation  →  AI explanation for a stored alert
GET  /risk/alerts/digest               →  AI daily digest of recent alerts
"""

from flask import Blueprint, jsonify, render_template, request

from risk.ai_alerts import explain_emergency_event, generate_alert_summary
from web.services import get_services

bp = Blueprint("risk", __name__, url_prefix="/risk")

# Cache for AI explanations
_explanation_cache: dict = {}


@bp.route("/")
def index():
    svc = get_services()
    risk_summary = svc.risk_manager.get_risk_summary()
    alerts = svc.get_alerts()

    context = {
        "title": "Risk",
        "active_page": "risk",
        "risk_summary": risk_summary,
        "alerts": alerts[-20:],
        "positions": svc.get_positions(),
    }
    return render_template("risk/index.html", **context)


@bp.route("/alerts/<alert_id>/ai-explanation", methods=["GET"])
def alert_ai_explanation(alert_id: str):
    """Return an AI-generated explanation for a stored alert event."""
    if alert_id in _explanation_cache:
        return jsonify({"explanation": _explanation_cache[alert_id], "cached": True})

    svc = get_services()
    alerts = svc.get_alerts()
    event = next((a for a in alerts if a.get("id") == alert_id), None)
    if event is None:
        return jsonify({"error": "Alert not found"}), 404

    explanation = explain_emergency_event(event)
    _explanation_cache[alert_id] = explanation
    return jsonify({"explanation": explanation, "cached": False})


@bp.route("/alerts/digest", methods=["GET"])
def alert_digest():
    """Return an AI-generated daily digest of recent emergency events."""
    try:
        window_hours = max(1, min(168, int(request.args.get("hours", 24))))
    except (ValueError, TypeError):
        window_hours = 24
    svc = get_services()
    events = svc.get_alerts()
    digest = generate_alert_summary(events, window_hours=window_hours)
    return jsonify({"digest": digest})
