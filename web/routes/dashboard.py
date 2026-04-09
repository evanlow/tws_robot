"""Dashboard route — TWS connection status, equity, P&L, active alerts.

GET /  →  renders templates/dashboard/index.html
"""

from flask import Blueprint, render_template

bp = Blueprint("dashboard", __name__, url_prefix="/")


@bp.route("/")
def index():
    """Main dashboard: connection status, equity curve, open positions summary."""
    context = {
        "title": "Dashboard",
        "active_page": "dashboard",
    }
    return render_template("dashboard/index.html", **context)
