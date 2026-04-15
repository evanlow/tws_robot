"""Dashboard route — TWS connection status, equity, P&L, active alerts.

GET /  →  renders templates/dashboard/index.html
"""

from flask import Blueprint, render_template

from web.services import get_services

bp = Blueprint("dashboard", __name__, url_prefix="/")


@bp.route("/")
def index():
    """Main dashboard: connection status, equity curve, open positions summary."""
    svc = get_services()
    risk_summary = svc.risk_manager.get_risk_summary()
    positions = svc.get_positions()
    strategies = []
    try:
        strategies = [
            s.get_performance_summary()
            for s in svc.strategy_registry.get_all_strategies()
        ]
    except Exception:
        pass

    context = {
        "title": "Dashboard",
        "active_page": "dashboard",
        "connected": svc.connected,
        "environment": svc.connection_env or "disconnected",
        "risk_summary": risk_summary,
        "positions": positions,
        "strategies": strategies,
        "alerts": svc.get_alerts()[-10:],
        "recent_trades": svc.get_recent_trades()[-10:],
        "system_health": svc.get_system_health(),
    }
    return render_template("dashboard/index.html", **context)
