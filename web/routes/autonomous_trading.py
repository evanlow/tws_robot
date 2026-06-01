"""Autonomous Trading dashboard page.

Server-rendered control-tower page that drives the
``/api/autonomous/*`` endpoints from the browser.

GET /autonomous-trading  →  renders templates/autonomous_trading/index.html
"""

from flask import Blueprint, render_template

bp = Blueprint("autonomous_trading", __name__, url_prefix="/autonomous-trading")


@bp.route("/")
def index():
    """Render the Autonomous Trading dashboard page."""
    context = {
        "title": "Autonomous Trading",
        "active_page": "autonomous_trading",
    }
    return render_template("autonomous_trading/index.html", **context)
