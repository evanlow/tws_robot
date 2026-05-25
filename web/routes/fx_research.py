"""FX Research Dashboard route — research-only SGD FX signal monitoring.

GET /fx  →  FX Research Dashboard (read-only, no order execution)
"""

from flask import Blueprint, render_template

from web.fx_signal_service import get_fx_dashboard_data

bp = Blueprint("fx_research", __name__, url_prefix="/fx")


@bp.route("/")
def index():
    """Render the FX Research Dashboard with mock data."""
    data = get_fx_dashboard_data()
    context = {
        "title": "FX Research",
        "active_page": "fx_research",
        **data,
    }
    return render_template("fx_research/index.html", **context)
