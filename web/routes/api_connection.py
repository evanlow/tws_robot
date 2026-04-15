"""Connection management API.

POST /api/connection/connect     — connect to TWS (paper or live)
POST /api/connection/disconnect  — disconnect
GET  /api/connection/status      — connection state, client ID, environment
"""

import logging

from flask import Blueprint, jsonify, request

from web.services import get_services

logger = logging.getLogger(__name__)

bp = Blueprint("api_connection", __name__, url_prefix="/api/connection")


@bp.route("/status", methods=["GET"])
def status():
    """Return current TWS connection state."""
    svc = get_services()
    return jsonify({
        "connected": svc.connected,
        "environment": svc.connection_env,
        "info": svc.connection_info,
    })


@bp.route("/connect", methods=["POST"])
def connect():
    """Initiate a connection to TWS.

    Body (optional)::

        { "environment": "paper" | "live" }
    """
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
        return jsonify({"error": str(exc)}), 400

    # Record connection in service manager (actual TWS socket connection
    # requires the IB Gateway/TWS to be running — we store intent here).
    svc.set_connected(env, {
        "host": cfg["host"],
        "port": cfg["port"],
        "client_id": cfg["client_id"],
        "account": cfg.get("account", ""),
    })

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

    svc.set_disconnected()
    logger.info("Disconnected from TWS")
    return jsonify({"status": "disconnected"})
