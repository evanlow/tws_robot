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
    account = svc.get_account_summary()
    strategies = []
    try:
        strategies = [
            s.get_performance_summary()
            for s in svc.strategy_registry.get_all_strategies()
        ]
    except Exception:
        pass

    # Compute total unrealized P&L across all open positions
    total_unrealized_pnl = sum(
        pos.get("unrealized_pnl", 0) for pos in positions.values()
    )

    # Daily P&L in dollar amount
    equity = risk_summary.get("current_equity", 0)
    daily_pnl_pct = risk_summary.get("daily_pnl_pct", 0)
    daily_start = risk_summary.get("daily_start_equity", equity)
    daily_pnl_dollar = equity - daily_start if daily_start else 0

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
        "total_unrealized_pnl": total_unrealized_pnl,
        "daily_pnl_dollar": daily_pnl_dollar,
        "buying_power": account.get("buying_power", 0),
    }
    return render_template("dashboard/index.html", **context)
