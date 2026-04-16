"""Settings route — TWS host/port/client-ID, paper↔live toggle, rate limits.

GET  /settings      →  settings form
POST /settings      →  save settings
"""

import os

from flask import Blueprint, render_template

from ai.client import is_ai_enabled
from web.services import get_services

bp = Blueprint("settings", __name__, url_prefix="/settings")


@bp.route("/", methods=["GET"])
def index():
    svc = get_services()
    risk_summary = svc.risk_manager.get_risk_summary()

    context = {
        "title": "Settings",
        "active_page": "settings",
        "openai_model": os.getenv("OPENAI_MODEL", "gpt-4o"),
        "ai_enabled": is_ai_enabled(),
        "has_env_key": bool(os.getenv("OPENAI_API_KEY", "").strip()),
        "message": None,
        "connected": svc.connected,
        "environment": svc.connection_env,
        "connection_info": svc.connection_info,
        "risk_limits": risk_summary.get("limits", {}),
    }
    return render_template("settings/index.html", **context)
