"""Connection management API.

POST /api/connection/connect     — connect to TWS (paper or live)
POST /api/connection/disconnect  — disconnect
GET  /api/connection/status      — connection state, client ID, environment
"""

import logging

from flask import Blueprint, jsonify, request

from web.disclaimer import RISK_DISCLAIMER_VERSION, is_accepted
from web.services import get_services
from autonomous.autonomous_mode import infer_account_type, mismatch_message

logger = logging.getLogger(__name__)

bp = Blueprint("api_connection", __name__, url_prefix="/api/connection")


@bp.route("/status", methods=["GET"])
def status():
    """Return current TWS connection state."""
    svc = get_services()
    return jsonify({
        "connected": svc.connected,
        "environment": svc.connection_env,
        "trading_state": svc.trading_state.value,
        "account_data_ready": svc.account_data_ready,
        "info": svc.connection_info,
    })


@bp.route("/connect", methods=["POST"])
def connect():
    """Initiate a connection to TWS.

    Body (optional)::

        { "environment": "paper" | "live" }

    Requires the Risk & Liability Disclaimer to have been accepted before
    any connection (paper or live) is permitted.
    """
    # Gate: disclaimer must be accepted before connecting.
    if not is_accepted():
        return jsonify(
            {
                "error": "Risk disclaimer not accepted",
                "disclaimer_required": True,
                "required_version": RISK_DISCLAIMER_VERSION,
            }
        ), 403

    svc = get_services()
    if svc.connected:
        return jsonify({"error": "Already connected", "connected": True}), 409

    data = request.get_json(silent=True) or {}
    env = data.get("environment", "paper").lower()
    if env not in ("paper", "live"):
        return jsonify({"error": "environment must be 'paper' or 'live'"}), 400

    try:
        from config.env_config import get_config
        cfg = get_config(env)
    except Exception as exc:
        return jsonify({"error": "Configuration error for the requested environment"}), 400

    # Attempt a real TWS API connection via the bridge.
    ok = svc.connect_tws(env, cfg, timeout=10)

    if not ok:
        error = (
            "TWS or IB Gateway is not reachable. Please check that it is "
            "running and API access is enabled."
        )
        logger.warning("TWS not reachable for %s", env)
        return jsonify({
            "status": "connection_failed",
            "connected": False,
            "environment": env,
            "host": cfg["host"],
            "port": cfg["port"],
            "error": error,
            "message": error,  # Backward compatibility for existing clients.
        }), 503

    actual = infer_account_type(getattr(svc, "connection_info", {}).get("account"))
    if actual is not None and actual != env:
        error = mismatch_message(env, actual)
        svc.disconnect_tws()
        try:
            from web.routes.api_autonomous import force_autonomous_mode_off

            force_autonomous_mode_off(message=error, status="Error")
        except Exception:  # pragma: no cover - best-effort safety notification
            pass
        logger.warning("Connection rejected: selected=%s actual=%s", env, actual)
        return jsonify({
            "status": "connection_rejected",
            "connected": False,
            "environment": env,
            "actual_environment": actual,
            "error": error,
            "message": error,
        }), 409

    logger.info("Connection initiated: env=%s host=%s port=%s",
                env, cfg["host"], cfg["port"])
    return jsonify({
        "status": "connected",
        "environment": env,
        "host": cfg["host"],
        "port": cfg["port"],
    })


@bp.route("/disconnect", methods=["POST"])
def disconnect():
    """Disconnect from TWS."""
    svc = get_services()
    if not svc.connected:
        return jsonify({"error": "Not connected"}), 409

    svc.disconnect_tws()
    try:
        from web.routes.api_autonomous import force_autonomous_mode_off

        force_autonomous_mode_off(
            message="TWS disconnected. Autonomous Mode has been turned OFF.",
            status="Not Ready",
        )
    except Exception:  # pragma: no cover - best-effort safety notification
        pass
    logger.info("Disconnected from TWS")
    return jsonify({"status": "disconnected"})
