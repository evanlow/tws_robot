"""STI Screener page route.

GET /stocks/sti  →  Singapore STI Screener page
"""

from flask import Blueprint, render_template

bp = Blueprint("sti_screener", __name__, url_prefix="/stocks")


@bp.route("/sti")
def screener():
    """Render the Singapore STI Screener page."""
    context = {
        "title": "Singapore STI Screener",
        "active_page": "stock_analysis",
    }
    return render_template("stock_analysis/sti.html", **context)
