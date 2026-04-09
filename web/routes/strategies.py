"""Strategies route — list, start/stop, and tune live strategies.

GET  /strategies          →  strategy list
GET  /strategies/<name>   →  detail / parameter editor
POST /strategies/<name>   →  update parameters
"""

from flask import Blueprint, render_template

bp = Blueprint("strategies", __name__, url_prefix="/strategies")


@bp.route("/")
def index():
    context = {
        "title": "Strategies",
        "active_page": "strategies",
    }
    return render_template("strategies/index.html", **context)


@bp.route("/<name>", methods=["GET", "POST"])
def detail(name: str):
    context = {
        "title": f"Strategy — {name}",
        "active_page": "strategies",
        "strategy_name": name,
    }
    return render_template("strategies/detail.html", **context)
