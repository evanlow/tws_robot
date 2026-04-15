"""Logs route — live event stream and prime-directive violation log.

GET /logs                →  log viewer page
GET /logs/stream         →  Server-Sent Events stream (event bus)
GET /logs/violations     →  prime_directive_violations.log viewer
"""

from pathlib import Path

from flask import Blueprint, jsonify, render_template

from web.services import get_services

bp = Blueprint("logs", __name__, url_prefix="/logs")


@bp.route("/")
def index():
    svc = get_services()
    # Recent events from EventBus
    events = svc.event_bus.get_history(limit=50)
    event_list = []
    for e in events:
        event_list.append({
            "type": e.event_type.name,
            "data": str(e.data)[:200] if e.data else "",
            "source": e.source or "",
            "timestamp": e.timestamp.isoformat() if e.timestamp else "",
        })

    context = {
        "title": "Logs & Events",
        "active_page": "logs",
        "events": event_list,
        "event_stats": svc.event_bus.get_stats(),
    }
    return render_template("logs/index.html", **context)


@bp.route("/violations", methods=["GET"])
def violations():
    """Return prime_directive_violations.log contents."""
    log_path = Path(__file__).resolve().parent.parent.parent / "prime_directive_violations.log"
    lines = []
    if log_path.exists():
        lines = log_path.read_text().strip().split("\n")[-100:]
    return jsonify({"lines": lines, "count": len(lines)})
