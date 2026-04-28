"""Dashboard route — TWS connection status, equity, P&L, active alerts.

GET /  →  renders templates/dashboard/index.html
"""

import logging

from flask import Blueprint, render_template

from web.services import get_services

logger = logging.getLogger(__name__)

bp = Blueprint("dashboard", __name__, url_prefix="/")


@bp.route("/")
def index():
    """Main dashboard: connection status, equity curve, open positions summary."""
    svc = get_services()
    risk_summary = svc.risk_manager.get_risk_summary()
    positions = svc.get_positions()
    insights = svc.get_account_insights()
    raw_strategies = []
    try:
        raw_strategies = list(svc.strategy_registry.get_all_strategies())
    except Exception:
        pass

    # Pre-compute per-strategy live positions using the strategy's configured
    # symbols list so the template can display precise P&L per strategy.
    strategies = []
    for s in raw_strategies:
        perf = s.get_performance_summary()
        syms = s.config.symbols or []
        perf["live_positions"] = {sym: positions[sym] for sym in syms if sym in positions}
        strategies.append(perf)

    # Market overview (cached / DB — auto-refreshes in the background when stale)
    market_overview = {"regions": [], "market_status": {}, "last_updated": None, "snapshots": []}
    try:
        from data.market_overview import get_market_overview_service
        mkt_svc = get_market_overview_service()
        market_overview = mkt_svc.get_overview()
    except Exception:
        pass

    # Portfolio analysis (concentration, allocation, drawdown, attribution)
    portfolio_analysis = {
        "drawdown": {"current_pct": 0, "peak_equity": 0, "current_equity": 0, "has_real_data": False},
        "allocation": [],
        "concentration": {},
        "diversification": {},
        "sector_exposure": {},
        "risk_flags": {},
        "attribution": {"by_symbol": [], "by_strategy": [], "win_rate": 0, "total_pnl": 0},
        "suggestions": [],
        "total_value": 0,
    }
    try:
        portfolio_analysis = svc.get_portfolio_analysis()
    except Exception:
        logger.exception("Failed to compute portfolio analysis")

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
        "portfolio_analysis": portfolio_analysis,
    }
    return render_template("dashboard/index.html", **context)
