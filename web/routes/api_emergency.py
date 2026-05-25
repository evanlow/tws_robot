"""Emergency controls API.

POST /api/emergency/halt       — immediately halt all trading
POST /api/emergency/close-all  — force-close all positions
POST /api/emergency/resume     — resume trading after halt (requires confirm=true)
GET  /api/emergency/status     — current emergency state
"""

import logging
import os
from datetime import datetime
from pathlib import Path

from flask import Blueprint, jsonify, request

from web.services import get_services
from web.trading_state import TradingState

logger = logging.getLogger(__name__)

bp = Blueprint("api_emergency", __name__, url_prefix="/api/emergency")

# Resolve to an absolute path so the file ends up in a predictable, writable
# location regardless of the process working directory.  Operators can override
# via the EMERGENCY_STOP_FILE env var (e.g. to place it on a shared volume).
EMERGENCY_STOP_FILE = Path(
    os.environ.get(
        "EMERGENCY_STOP_FILE",
        str(Path(__file__).resolve().parent.parent.parent / "EMERGENCY_STOP"),
    )
)


@bp.route("/status", methods=["GET"])
def status():
    """Return current emergency / halt state."""
    svc = get_services()
    risk = svc.risk_manager
    return jsonify({
        "emergency_stop_active": risk.emergency_stop_active,
        "emergency_stop_file_exists": EMERGENCY_STOP_FILE.exists(),
        "trading_state": svc.trading_state.value,
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
    svc.set_trading_state(TradingState.EMERGENCY_STOP)

    # Synchronize file-based emergency stop marker (best-effort: log failures
    # but do not let I/O errors prevent strategy shutdown or alerting).
    try:
        EMERGENCY_STOP_FILE.write_text(
            f"EMERGENCY STOP - {reason}\nTriggered: {datetime.now().isoformat()}\n"
        )
    except OSError as exc:
        logger.error("Failed to write EMERGENCY_STOP file: %s", exc)

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
    svc.set_trading_state(TradingState.EMERGENCY_STOP)

    # Synchronize file-based emergency stop marker (best-effort: log failures
    # but do not let I/O errors prevent position clearing or alerting).
    try:
        EMERGENCY_STOP_FILE.write_text(
            f"EMERGENCY STOP - Close-all from web dashboard\n"
            f"Triggered: {datetime.now().isoformat()}\n"
        )
    except OSError as exc:
        logger.error("Failed to write EMERGENCY_STOP file: %s", exc)

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
    """Resume trading after emergency halt.

    Requires explicit confirmation (confirm=true in request body).
    After resume, trading state is restored to CONNECTED_READ_ONLY
    to prevent accidental live trading without re-arming.
    """
    svc = get_services()
    data = request.get_json(silent=True) or {}
    reason = data.get("reason", "Manual resume from web dashboard")
    confirm = data.get("confirm", False)

    if confirm is not True:
        return jsonify({
            "error": "Explicit confirmation required",
            "message": "Set confirm=true in the request body to acknowledge resuming trading.",
        }), 400

    # Remove file-based emergency stop marker first so that, if this fails,
    # the in-memory flag is left unchanged and the system remains halted.
    if EMERGENCY_STOP_FILE.exists():
        try:
            EMERGENCY_STOP_FILE.unlink()
        except OSError as exc:
            logger.error("Failed to remove EMERGENCY_STOP file: %s", exc)
            return jsonify({
                "error": "Failed to remove emergency stop file",
                "message": str(exc),
            }), 500

    svc.risk_manager.release_emergency_stop(reason)

    # Restore trading state, but never directly into live trading — that
    # requires explicit re-arming even after an emergency resume.
    svc.restore_trading_state_from_connection()
    if svc.trading_state == TradingState.LIVE_TRADING_ARMED:
        svc.set_trading_state(TradingState.CONNECTED_READ_ONLY)

    svc.add_alert({
        "id": f"resume-{datetime.now().timestamp()}",
        "level": "INFO",
        "message": f"Trading resumed: {reason}",
        "timestamp": datetime.now().isoformat(),
    })

    logger.info("Trading resumed from web: %s", reason)
    return jsonify({"status": "resumed", "reason": reason})
