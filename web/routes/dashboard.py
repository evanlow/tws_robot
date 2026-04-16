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
    insights = svc.get_account_insights()
    strategies = []
    try:
        strategies = [
            s.get_performance_summary()
            for s in svc.strategy_registry.get_all_strategies()
        ]
    except Exception:
        pass

    # Market overview (cached / DB — auto-refreshes in the background when stale)
    market_overview = {"regions": [], "market_status": {}, "last_updated": None, "snapshots": []}
    try:
        from data.market_overview import get_market_overview_service
        mkt_svc = get_market_overview_service()
        market_overview = mkt_svc.get_overview()
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
        "total_unrealized_pnl": insights["total_unrealized_pnl"],
        "daily_pnl_dollar": insights["daily_pnl_dollar"],
        "buying_power": insights["buying_power"],
        "market_overview": market_overview,
    }
    return render_template("dashboard/index.html", **context)
