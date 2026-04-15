"""Emergency controls API.

POST /api/emergency/halt       — immediately halt all trading
POST /api/emergency/close-all  — force-close all positions
POST /api/emergency/resume     — resume trading after halt
GET  /api/emergency/status     — current emergency state
"""

import logging
from datetime import datetime

from flask import Blueprint, jsonify, request

from web.services import get_services

logger = logging.getLogger(__name__)

bp = Blueprint("api_emergency", __name__, url_prefix="/api/emergency")


@bp.route("/status", methods=["GET"])
def status():
    """Return current emergency / halt state."""
    svc = get_services()
    risk = svc.risk_manager
    return jsonify({
        "emergency_stop_active": risk.emergency_stop_active,
        "risk_status": risk.risk_status.value,
        "drawdown_breached": risk.drawdown_breached,
        "daily_limit_breached": risk.daily_limit_breached,
    })


@bp.route("/halt", methods=["POST"])
def halt():
    """Immediately halt all trading via emergency stop."""
    svc = get_services()
    data = request.get_json(silent=True) or {}
    reason = data.get("reason", "Manual halt from web dashboard")

    svc.risk_manager.trigger_emergency_stop(reason)

    # Stop all running strategies
    reg = svc.strategy_registry
    reg.stop_all()

    svc.add_alert({
        "id": f"halt-{datetime.now().timestamp()}",
        "level": "EMERGENCY",
        "message": f"Emergency halt: {reason}",
        "timestamp": datetime.now().isoformat(),
    })

    logger.critical("EMERGENCY HALT triggered from web: %s", reason)
    return jsonify({"status": "halted", "reason": reason})


@bp.route("/close-all", methods=["POST"])
def close_all():
    """Force-close all open positions (placeholder — requires live TWS)."""
    svc = get_services()

    # Trigger emergency stop first
    svc.risk_manager.trigger_emergency_stop("Close-all from web dashboard")

    # Clear tracked positions
    positions = svc.get_positions()
    for symbol in list(positions.keys()):
        svc.remove_position(symbol)

    svc.add_alert({
        "id": f"closeall-{datetime.now().timestamp()}",
        "level": "EMERGENCY",
        "message": "All positions closed (force close-all)",
        "timestamp": datetime.now().isoformat(),
    })

    logger.critical("CLOSE-ALL triggered from web dashboard")
    return jsonify({
        "status": "positions_cleared",
        "positions_closed": len(positions),
    })


@bp.route("/resume", methods=["POST"])
def resume():
    """Resume trading after emergency halt."""
    svc = get_services()
    data = request.get_json(silent=True) or {}
    reason = data.get("reason", "Manual resume from web dashboard")

    svc.risk_manager.release_emergency_stop(reason)

    svc.add_alert({
        "id": f"resume-{datetime.now().timestamp()}",
        "level": "INFO",
        "message": f"Trading resumed: {reason}",
        "timestamp": datetime.now().isoformat(),
    })

    logger.info("Trading resumed from web: %s", reason)
    return jsonify({"status": "resumed", "reason": reason})
