"""Strategies route — list, start/stop, and tune live strategies.

GET  /strategies          →  strategy list
GET  /strategies/<name>   →  detail / parameter editor
POST /strategies/<name>   →  update parameters
"""

from flask import Blueprint, render_template

from web.services import get_services

bp = Blueprint("strategies", __name__, url_prefix="/strategies")


@bp.route("/")
def index():
    svc = get_services()
    strategies = []
    classes = []
    try:
        strategies = [
            s.get_performance_summary()
            for s in svc.strategy_registry.get_all_strategies()
        ]
        classes = svc.strategy_registry.get_registered_classes()
    except Exception:
        pass

    # Auto-detected strategies from current positions
    inferred = []
    try:
        inferred = svc.get_inferred_strategies()
    except Exception:
        pass

    summary = {}
    if strategies:
        try:
            summary = svc.strategy_registry.get_overall_summary()
        except Exception:
            pass

    context = {
        "title": "Strategies",
        "active_page": "strategies",
        "strategies": strategies,
        "strategy_classes": classes,
        "summary": summary,
        "inferred_strategies": inferred,
    }
    return render_template("strategies/index.html", **context)


@bp.route("/<name>", methods=["GET", "POST"])
def detail(name: str):
    svc = get_services()
    strategy = svc.strategy_registry.get_strategy(name)
    perf = strategy.get_performance_summary() if strategy else {}
    config_dict = strategy.config.__dict__ if strategy else {}

    context = {
        "title": f"Strategy — {name}",
        "active_page": "strategies",
        "strategy_name": name,
        "strategy": perf,
        "config": config_dict,
    }
    return render_template("strategies/detail.html", **context)
