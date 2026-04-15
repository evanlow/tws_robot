"""Backtest route — run configs, equity curve, drawdown, side-by-side comparison.

GET  /backtest         →  backtest home / run form
POST /backtest/run     →  submit new backtest job
GET  /backtest/<id>    →  results for a specific run
POST /backtest/<id>/ai-report  →  generate/return AI narrative report
"""

from flask import Blueprint, jsonify, render_template, request

from backtest.ai_report import cache_report, generate_narrative, get_cached_report
from web.services import get_services

bp = Blueprint("backtest", __name__, url_prefix="/backtest")


@bp.route("/")
def index():
    svc = get_services()
    runs = svc.list_backtest_runs()
    context = {
        "title": "Backtest",
        "active_page": "backtest",
        "runs": runs,
    }
    return render_template("backtest/index.html", **context)


@bp.route("/<run_id>")
def results(run_id: str):
    svc = get_services()
    run = svc.get_backtest_run(run_id)
    context = {
        "title": f"Backtest Results — {run_id}",
        "active_page": "backtest",
        "run_id": run_id,
        "run": run,
    }
    return render_template("backtest/results.html", **context)


@bp.route("/<run_id>/ai-report", methods=["POST"])
def ai_report(run_id: str):
    """Return a cached AI narrative report, or generate one on demand."""
    cached = get_cached_report(run_id)
    if cached:
        return jsonify({"report": cached, "cached": True})

    data = request.get_json(silent=True) or {}
    strategy_name: str = data.get("strategy_name", run_id)
    metrics_dict: dict = data.get("metrics", {})

    report = generate_narrative(metrics_dict, strategy_name)
    cache_report(run_id, report)
    return jsonify({"report": report, "cached": False})
