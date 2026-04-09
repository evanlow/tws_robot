"""Positions route — open positions, order history, emergency close.

GET  /positions           →  open positions table
GET  /positions/history   →  order history
POST /positions/close-all →  emergency close all positions
"""

from flask import Blueprint, render_template

bp = Blueprint("positions", __name__, url_prefix="/positions")


@bp.route("/")
def index():
    context = {
        "title": "Positions",
        "active_page": "positions",
    }
    return render_template("positions/index.html", **context)


@bp.route("/history")
def history():
    context = {
        "title": "Order History",
        "active_page": "positions",
    }
    return render_template("positions/history.html", **context)
