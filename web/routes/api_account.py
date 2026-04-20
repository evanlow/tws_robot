"""Account data API.

GET /api/account/summary      — equity, buying power, cash balance, P&L
GET /api/account/positions    — all open positions with real-time P&L
GET /api/account/symbol-names — resolve ticker symbols to company names
"""

import logging
import re

from flask import Blueprint, jsonify, request

from web.services import get_services
from data.fundamentals import get_fundamentals

logger = logging.getLogger(__name__)

# Ticker regex: uppercase letters and/or digits, optionally with dots (BRK.B, 1211)
_TICKER_RE = re.compile(r"^[A-Z0-9]{1,10}(\.[A-Z]{1,5})?$")

# Maximum number of symbols accepted per request
_MAX_SYMBOLS = 50

# Mapping from IB exchange names to yfinance ticker suffixes.
# Numeric-only symbols (e.g. HK stocks) and other international tickers
# need a suffix for yfinance to resolve them correctly.
_IB_EXCHANGE_TO_YF_SUFFIX: dict[str, str] = {
    "SEHK": ".HK",
    "HKFE": ".HK",
    "TSE": ".T",
    "JPX": ".T",
    "LSE": ".L",
    "ASX": ".AX",
    "SGX": ".SI",
    "KSE": ".KS",
    "KOSDAQ": ".KQ",
    "TWSE": ".TW",
    "OTC": ".TWO",
    "SFB": ".ST",
    "IBIS": ".DE",
    "FWB": ".F",
    "AEB": ".AS",
    "SBF": ".PA",
    "BM": ".MC",
    "BVME": ".MI",
    "EBS": ".SW",
    "VSE": ".VI",
    "NSE": ".NS",
    "BSE": ".BO",
    "JSE": ".JO",
    "BOVESPA": ".SA",
    "MEXI": ".MX",
    "MOEX": ".ME",
    "ENEXT.BE": ".BR",
    "BVL": ".LS",
    "WSE": ".WA",
    "HEX": ".HE",
    "KFB": ".CO",
    "OSE": ".OL",
    "ICEEX": ".IC",
    "NZE": ".NZ",
}

bp = Blueprint("api_account", __name__, url_prefix="/api/account")

# Currency → yfinance suffix fallback (when exchange is not available).
_CURRENCY_TO_YF_SUFFIX: dict[str, str] = {
    "HKD": ".HK",
    "JPY": ".T",
    "GBP": ".L",
    "AUD": ".AX",
    "SGD": ".SI",
    "KRW": ".KS",
    "TWD": ".TW",
    "SEK": ".ST",
    "EUR": "",       # Multiple European exchanges — don't guess
    "INR": ".NS",
    "BRL": ".SA",
    "MXN": ".MX",
    "NZD": ".NZ",
}


def _to_yfinance_symbol(ib_symbol: str, pos_data: dict) -> str:
    """Convert an IB symbol to its yfinance equivalent.

    Uses exchange and currency information stored in position data to
    determine the correct yfinance suffix for international tickers.
    US tickers (no suffix needed) are returned unchanged.
    """
    exchange = pos_data.get("exchange", "")
    currency = pos_data.get("currency", "")

    # If the symbol contains any dot, don't append an exchange/currency
    # suffix; keep the .OLD special-case so it can still be normalized.
    if "." in ib_symbol and not ib_symbol.endswith(".OLD"):
        return ib_symbol

    # Try exchange-based mapping first
    if exchange:
        suffix = _IB_EXCHANGE_TO_YF_SUFFIX.get(exchange, "")
        if suffix:
            return ib_symbol + suffix

    # Fallback to currency-based mapping for numeric-only symbols
    # (e.g. HK stocks: 1211, 2331) or when exchange info is missing
    if currency and currency != "USD":
        suffix = _CURRENCY_TO_YF_SUFFIX.get(currency, "")
        if suffix:
            return ib_symbol + suffix

    return ib_symbol


@bp.route("/summary", methods=["GET"])
def summary():
    """Return account summary (equity, P&L, risk status)."""
    svc = get_services()

    risk = svc.risk_manager.get_risk_summary()
    account = svc.get_account_summary()
    insights = svc.get_account_insights()

    equity_initialized = risk.get("equity_initialized", False)

    return jsonify({
        "connected": svc.connected,
        "environment": svc.connection_env,
        "equity": risk.get("current_equity", 0) if equity_initialized else None,
        "peak_equity": risk.get("peak_equity", 0) if equity_initialized else None,
        "daily_pnl_pct": risk.get("daily_pnl_pct", 0),
        "daily_pnl_dollar": insights["daily_pnl_dollar"],
        "drawdown_pct": risk.get("drawdown_pct", 0) if equity_initialized else None,
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
    positions = svc.get_positions()

    raw_symbols = request.args.get("symbols", "")
    if raw_symbols:
        all_symbols = [s.strip().upper() for s in raw_symbols.split(",") if s.strip()]
        # Filter to valid ticker symbols instead of rejecting the whole request.
        # The frontend may send option symbols (e.g. "MRNA 261218P00025000")
        # alongside stock tickers; silently skipping invalid ones allows the
        # valid tickers to still be resolved.
        # De-duplicate after filtering so repeated symbols do not trigger
        # redundant lookups or count multiple times toward _MAX_SYMBOLS.
        symbols = list(dict.fromkeys(
            s for s in all_symbols if _TICKER_RE.match(s)
        ))
    else:
        # Default to portfolio — filter to stock tickers only
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
    for sym in symbols:
        try:
            yf_sym = _to_yfinance_symbol(sym, positions.get(sym, {}))
            data = get_fundamentals(yf_sym, use_cache=True)
            name = data.get("name")
            if name and name != yf_sym and name != sym:
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
