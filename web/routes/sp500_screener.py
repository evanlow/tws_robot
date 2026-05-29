"""S&P 500 Screener page route.

GET /stocks/sp500  →  S&P 500 Screener page
"""

from flask import Blueprint, render_template

bp = Blueprint("sp500_screener", __name__, url_prefix="/stocks")


@bp.route("/sp500")
def screener():
    """Render the S&P 500 Screener page."""
    context = {
        "title": "S&P 500 Screener",
        "active_page": "stock_analysis",
    }
    return render_template("stock_analysis/sp500.html", **context)
