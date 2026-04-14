"""Settings route — TWS host/port/client-ID, paper↔live toggle, rate limits.

GET  /settings      →  settings form
POST /settings      →  save settings
"""

import os

from flask import Blueprint, render_template

bp = Blueprint("settings", __name__, url_prefix="/settings")


@bp.route("/", methods=["GET"])
def index():
    context = {
        "title": "Settings",
        "active_page": "settings",
        "openai_model": os.getenv("OPENAI_MODEL", "gpt-4o"),
        "ai_enabled": os.getenv("AI_ENABLED", "false").lower() == "true",
        "message": None,
    }
    return render_template("settings/index.html", **context)
