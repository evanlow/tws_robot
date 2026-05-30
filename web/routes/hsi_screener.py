"""HSI Screener page route.

GET /stocks/hsi  →  Hong Kong HSI Screener page
"""

from flask import Blueprint, render_template

bp = Blueprint("hsi_screener", __name__, url_prefix="/stocks")


@bp.route("/hsi")
def screener():
    """Render the Hong Kong HSI Screener page."""
    context = {
        "title": "Hong Kong HSI Screener",
        "active_page": "stock_analysis",
    }
    return render_template("stock_analysis/hsi.html", **context)
