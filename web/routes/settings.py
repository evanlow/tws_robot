"""Settings route — TWS host/port/client-ID, paper↔live toggle, rate limits.

GET  /settings      →  settings form
POST /settings      →  save settings
"""

import os

from flask import Blueprint, render_template, request

bp = Blueprint("settings", __name__, url_prefix="/settings")


@bp.route("/", methods=["GET", "POST"])
def index():
    message = None
    if request.method == "POST":
        # In a real implementation these would be persisted to a config store.
        # For now we update the current process environment as a demonstration.
        ai_key = request.form.get("openai_api_key", "").strip()
        ai_model = request.form.get("openai_model", "gpt-4o").strip()
        ai_enabled = request.form.get("ai_enabled") == "on"

        if ai_key:
            os.environ["OPENAI_API_KEY"] = ai_key
        if ai_model:
            os.environ["OPENAI_MODEL"] = ai_model
        os.environ["AI_ENABLED"] = "true" if ai_enabled else "false"

        # Reset the cached client so it picks up new settings
        import ai.client as _ai_client
        _ai_client._client_instance = None
        _ai_client._AI_ENABLED = None

        message = "Settings saved."

    context = {
        "title": "Settings",
        "active_page": "settings",
        "openai_model": os.getenv("OPENAI_MODEL", "gpt-4o"),
        "ai_enabled": os.getenv("AI_ENABLED", "false").lower() == "true",
        "message": message,
    }
    return render_template("settings/index.html", **context)
