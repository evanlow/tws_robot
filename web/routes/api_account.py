"""Account data API.

GET /api/account/summary      — equity, buying power, cash balance, P&L
GET /api/account/positions    — all open positions with real-time P&L
GET /api/account/symbol-names — resolve ticker symbols to company names
"""

import logging
import re

from flask import Blueprint, jsonify, request

from web.services import get_services

logger = logging.getLogger(__name__)

# Simple ticker regex: 1-10 uppercase letters, optionally with dots (BRK.B)
_TICKER_RE = re.compile(r"^[A-Z]{1,10}(\.[A-Z]{1,5})?$")

# Maximum number of symbols accepted per request
_MAX_SYMBOLS = 50

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
        "stock_drawdown_pct": risk.get("stock_drawdown_pct", 0),
        "premium_retention_pct": risk.get("premium_retention_pct", 1.0),
        "short_options_premium_collected": risk.get("short_options_premium_collected", 0),
        "short_options_current_liability": risk.get("short_options_current_liability", 0),
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


@bp.route("/symbol-names", methods=["GET"])
def symbol_names():
    """Resolve ticker symbols to human-readable company names.

    Query parameters
    ----------------
    symbols : str, optional
        Comma-separated list of symbols to resolve.  When omitted the
        endpoint resolves all symbols currently in the portfolio.

    Returns
    -------
    JSON ``{"names": {"AAPL": "Apple Inc.", ...}}``
    """
    svc = get_services()

    raw_symbols = request.args.get("symbols", "")
    if raw_symbols:
        symbols = [s.strip().upper() for s in raw_symbols.split(",") if s.strip()]
    else:
        # Default to portfolio — filter to stock tickers only
        positions = svc.get_positions()
        symbols = [
            sym for sym, pos in positions.items()
            if pos.get("sec_type", "STK") in ("STK", "")
            and _TICKER_RE.match(sym)
        ]

    if not symbols:
        return jsonify({"names": {}})

    if len(symbols) > _MAX_SYMBOLS:
        return jsonify({"error": f"Too many symbols (max {_MAX_SYMBOLS})"}), 400

    names: dict[str, str] = {}
    from data.fundamentals import get_fundamentals
    for sym in symbols:
        try:
            data = get_fundamentals(sym, use_cache=True)
            name = data.get("name")
            if name and name != sym:
                names[sym] = name
        except Exception as exc:
            logger.debug("Could not resolve name for %s: %s", sym, exc)

    return jsonify({"names": names})


@bp.route("/portfolio-analysis", methods=["GET"])
def portfolio_analysis():
    """Return aggregate portfolio analysis (concentration, attribution, drawdown)."""
    svc = get_services()
    analysis = svc.get_portfolio_analysis()
    return jsonify(analysis)
