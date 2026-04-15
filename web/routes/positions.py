"""Positions route — open positions, order history, emergency close.

GET  /positions           →  open positions table
GET  /positions/history   →  order history
POST /positions/close-all →  emergency close all positions
"""

from flask import Blueprint, render_template

from web.services import get_services

bp = Blueprint("positions", __name__, url_prefix="/positions")


@bp.route("/")
def index():
    svc = get_services()
    positions = svc.get_positions()
    risk_summary = svc.risk_manager.get_risk_summary()

    context = {
        "title": "Positions",
        "active_page": "positions",
        "positions": positions,
        "risk_summary": risk_summary,
        "emergency_stop": svc.risk_manager.emergency_stop_active,
    }
    return render_template("positions/index.html", **context)


@bp.route("/history")
def history():
    svc = get_services()
    context = {
        "title": "Order History",
        "active_page": "positions",
        "orders": svc.get_orders(),
        "trades": svc.get_recent_trades(),
    }
    return render_template("positions/history.html", **context)
