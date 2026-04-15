"""Account data API.

GET /api/account/summary    — equity, buying power, cash balance, P&L
GET /api/account/positions  — all open positions with real-time P&L
"""

from flask import Blueprint, jsonify

from web.services import get_services

bp = Blueprint("api_account", __name__, url_prefix="/api/account")


@bp.route("/summary", methods=["GET"])
def summary():
    """Return account summary (equity, P&L, risk status)."""
    svc = get_services()

    risk = svc.risk_manager.get_risk_summary()
    account = svc.get_account_summary()
    insights = svc.get_account_insights()

    return jsonify({
        "connected": svc.connected,
        "environment": svc.connection_env,
        "equity": risk.get("current_equity", 0),
        "peak_equity": risk.get("peak_equity", 0),
        "daily_pnl_pct": risk.get("daily_pnl_pct", 0),
        "daily_pnl_dollar": insights["daily_pnl_dollar"],
        "drawdown_pct": risk.get("drawdown_pct", 0),
        "risk_status": risk.get("risk_status", "NORMAL"),
        "emergency_stop": risk.get("emergency_stop_active", False),
        "buying_power": insights["buying_power"],
        "cash_balance": account.get("cash_balance", 0),
        "unrealized_pnl": insights["total_unrealized_pnl"],
        "limits": risk.get("limits", {}),
    })


@bp.route("/positions", methods=["GET"])
def positions():
    """Return all open positions with P&L."""
    svc = get_services()
    raw = svc.get_positions()

    positions_list = []
    for symbol, pos in raw.items():
        positions_list.append({
            "symbol": symbol,
            "quantity": pos.get("quantity", 0),
            "entry_price": pos.get("entry_price", 0),
            "current_price": pos.get("current_price", 0),
            "market_value": pos.get("market_value", 0),
            "unrealized_pnl": pos.get("unrealized_pnl", 0),
            "unrealized_pnl_pct": pos.get("unrealized_pnl_pct", 0),
            "side": pos.get("side", "LONG"),
            "sec_type": pos.get("sec_type", ""),
        })

    return jsonify({"positions": positions_list, "count": len(positions_list)})
