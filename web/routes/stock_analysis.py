"""Stock Analysis page routes — dashboard and per-ticker drill-down.

GET /stocks/analysis           →  Stock Analysis dashboard (ticker search + portfolio shortcuts)
GET /stocks/<ticker>/analysis  →  Stock Price Context page
"""

import re
from typing import Optional

from flask import Blueprint, render_template

from web.services import get_services

bp = Blueprint("stock_analysis", __name__, url_prefix="/stocks")

# Pattern for option symbols: TICKER [optional space] DIGITS[C|P]DIGITS
# e.g. "GOOG 260821C00415000", "BIDU 2605P00121000", "SPX250620C05500000"
_OPTION_RE = re.compile(
    r"^([A-Z]{1,6})\s*\d{4,6}[CP]\d+$"
)


def parse_underlying_symbol(instrument_symbol: Optional[str]) -> Optional[str]:
    """Extract the underlying stock ticker from an option or equity symbol.

    Examples:
        - "GOOG" -> "GOOG"
        - "GOOG 260821C00415000" -> "GOOG"
        - "BIDU 2605P00121000" -> "BIDU"
        - "SPX  250620C05500000" -> "SPX"
        - "" -> None
        - None -> None

    Returns None if the symbol cannot be parsed into a recognisable equity/underlying.
    """
    if not instrument_symbol or not isinstance(instrument_symbol, str):
        return None

    symbol = instrument_symbol.strip()
    if not symbol:
        return None

    # Check if it looks like an option symbol
    m = _OPTION_RE.match(symbol)
    if m:
        return m.group(1)

    # Plain equity ticker (letters, digits, dots — e.g. BRK.B)
    if re.match(r"^[A-Z0-9]{1,10}(\.[A-Z]{1,5})?$", symbol):
        return symbol

    return None


@bp.route("/analysis")
def dashboard():
    """Stock Analysis dashboard — ticker search with portfolio position shortcuts."""
    svc = get_services()
    positions = svc.get_positions()

    # Build analysis links for positions
    position_links = []
    for symbol, pos in positions.items():
        underlying = parse_underlying_symbol(symbol)
        position_links.append({
            "symbol": symbol,
            "underlying": underlying,
            "quantity": pos.get("quantity", 0),
            "entry_price": pos.get("entry_price", 0),
            "current_price": pos.get("current_price", 0),
            "unrealized_pnl_pct": pos.get("unrealized_pnl_pct", 0),
            "sec_type": pos.get("sec_type", "STK"),
            "analyzable": underlying is not None,
        })

    context = {
        "title": "Stock Analysis",
        "active_page": "stock_analysis",
        "position_links": position_links,
    }
    return render_template("stock_analysis/dashboard.html", **context)


@bp.route("/<ticker>/analysis")
def index(ticker: str):
    """Render the stock analysis drill-down page."""
    ticker = ticker.upper()
    context = {
        "title": f"Stock Price Context — {ticker}",
        "active_page": "stock_analysis",
        "ticker": ticker,
    }
    return render_template("stock_analysis/index.html", **context)
