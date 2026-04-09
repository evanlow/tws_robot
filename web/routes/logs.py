"""Logs route — live event stream and prime-directive violation log.

GET /logs                →  log viewer page
GET /logs/stream         →  Server-Sent Events stream (event bus)
GET /logs/violations     →  prime_directive_violations.log viewer
"""

from flask import Blueprint, render_template

bp = Blueprint("logs", __name__, url_prefix="/logs")


@bp.route("/")
def index():
    context = {
        "title": "Logs",
        "active_page": "logs",
    }
    return render_template("logs/index.html", **context)
