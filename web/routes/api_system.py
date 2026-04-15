"""System health, diagnostics, and market status API.

GET  /api/system/health          — system health summary
POST /api/system/init-db         — initialise database tables
POST /api/diagnostics/test-connection — test TWS socket reachability
GET  /api/diagnostics/market-status   — US market open/closed
"""

import logging
import socket
from datetime import datetime

from flask import Blueprint, jsonify, request

from web.services import get_services

logger = logging.getLogger(__name__)

bp = Blueprint("api_system", __name__, url_prefix="/api")


# ------------------------------------------------------------------
# System health
# ------------------------------------------------------------------

@bp.route("/system/health", methods=["GET"])
def health():
    """Return system-wide health snapshot."""
    svc = get_services()
    return jsonify(svc.get_system_health())


# ------------------------------------------------------------------
# Diagnostics
# ------------------------------------------------------------------

@bp.route("/diagnostics/test-connection", methods=["POST"])
def test_connection():
    """Test TCP reachability of TWS/Gateway.

    Body (optional)::

        { "host": "127.0.0.1", "port": 7497 }
    """
    data = request.get_json(silent=True) or {}
    host = data.get("host", "127.0.0.1")
    port = int(data.get("port", 7497))
    timeout = float(data.get("timeout", 3))

    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        result = sock.connect_ex((host, port))
        sock.close()
        reachable = result == 0
    except Exception as exc:
        reachable = False
        logger.debug("Connection test failed: %s", exc)

    return jsonify({
        "host": host,
        "port": port,
        "reachable": reachable,
        "tested_at": datetime.now().isoformat(),
    })


@bp.route("/diagnostics/market-status", methods=["GET"])
def market_status():
    """Return whether US stock markets are currently open."""
    try:
        from scripts.market_status import MarketStatusChecker
        checker = MarketStatusChecker()
        status = checker.get_market_status()
        return jsonify(status)
    except Exception as exc:
        # Fallback: minimal time-based check
        logger.debug("MarketStatusChecker not available: %s", exc)
        import pytz
        ny_tz = pytz.timezone("America/New_York")
        now_ny = datetime.now(ny_tz)
        weekday = now_ny.weekday()
        hour = now_ny.hour
        minute = now_ny.minute

        is_weekday = weekday < 5
        market_open = is_weekday and (
            (hour == 9 and minute >= 30) or (10 <= hour < 16)
        )

        return jsonify({
            "market_open": market_open,
            "current_time_ny": now_ny.strftime("%Y-%m-%d %H:%M:%S %Z"),
            "is_weekday": is_weekday,
            "source": "fallback",
        })


# ------------------------------------------------------------------
# Database initialisation
# ------------------------------------------------------------------

@bp.route("/system/init-db", methods=["POST"])
def init_db():
    """Initialise database tables (first-time setup).

    This is a no-op if tables already exist.
    """
    try:
        from data.database import init_database
        init_database()
        return jsonify({"status": "ok", "message": "Database initialized"})
    except ImportError:
        return jsonify({
            "status": "skipped",
            "message": "Database module not configured",
        })
    except Exception as exc:
        logger.error("Database init failed: %s", exc)
        return jsonify({"status": "error", "message": "Database initialization failed. Check logs for details."}), 500
