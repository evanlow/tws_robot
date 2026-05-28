"""Stock Analysis page route — fair value & support/resistance drill-down.

GET /stocks/<ticker>/analysis  →  Stock Price Context page
"""

from flask import Blueprint, render_template

bp = Blueprint("stock_analysis", __name__, url_prefix="/stocks")


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
