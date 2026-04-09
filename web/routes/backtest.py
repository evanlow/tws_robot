"""Backtest route — run configs, equity curve, drawdown, side-by-side comparison.

GET  /backtest         →  backtest home / run form
POST /backtest/run     →  submit new backtest job
GET  /backtest/<id>    →  results for a specific run
"""

from flask import Blueprint, render_template

bp = Blueprint("backtest", __name__, url_prefix="/backtest")


@bp.route("/")
def index():
    context = {
        "title": "Backtest",
        "active_page": "backtest",
    }
    return render_template("backtest/index.html", **context)


@bp.route("/<run_id>")
def results(run_id: str):
    context = {
        "title": f"Backtest Results — {run_id}",
        "active_page": "backtest",
        "run_id": run_id,
    }
    return render_template("backtest/results.html", **context)
