"""Risk route — drawdown gauges, correlation heatmap, profile switching.

GET  /risk               →  risk dashboard
POST /risk/profile       →  switch risk profile
"""

from flask import Blueprint, render_template

bp = Blueprint("risk", __name__, url_prefix="/risk")


@bp.route("/")
def index():
    context = {
        "title": "Risk",
        "active_page": "risk",
    }
    return render_template("risk/index.html", **context)
