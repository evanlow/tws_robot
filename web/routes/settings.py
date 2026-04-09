"""Settings route — TWS host/port/client-ID, paper↔live toggle, rate limits.

GET  /settings      →  settings form
POST /settings      →  save settings
"""

from flask import Blueprint, render_template

bp = Blueprint("settings", __name__, url_prefix="/settings")


@bp.route("/", methods=["GET", "POST"])
def index():
    context = {
        "title": "Settings",
        "active_page": "settings",
    }
    return render_template("settings/index.html", **context)
