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
    raw_strategies = []
    classes = []
    try:
        raw_strategies = list(svc.strategy_registry.get_all_strategies())
        classes = svc.strategy_registry.get_registered_classes()
    except Exception:
        pass

    # Auto-detected strategies from current positions
    inferred = []
    try:
        inferred = svc.get_inferred_strategies()
    except Exception:
        pass

    all_positions = {}
    try:
        all_positions = svc.get_positions()
    except Exception:
        pass

    # Pre-compute per-strategy live positions using the strategy's configured
    # symbols list so templates don't need fragile substring matching.
    strategies = []
    for s in raw_strategies:
        perf = s.get_performance_summary()
        symbols = s.config.symbols or []
        perf["live_positions"] = {
            sym: all_positions[sym]
            for sym in symbols
            if sym in all_positions
        }
        strategies.append(perf)

    context = {
        "title": "Strategies",
        "active_page": "strategies",
        "strategies": strategies,
        "strategy_classes": classes,
        "summary": svc.strategy_registry.get_overall_summary() if strategies else {},
        "inferred_strategies": inferred,
    }
    return render_template("strategies/index.html", **context)


@bp.route("/<name>", methods=["GET", "POST"])
def detail(name: str):
    svc = get_services()
    strategy = svc.strategy_registry.get_strategy(name)
    perf = strategy.get_performance_summary() if strategy else {}
    config_dict = strategy.config.__dict__ if strategy else {}

    # Enrich with live positions matching this strategy's symbols
    all_positions = {}
    try:
        all_positions = svc.get_positions()
    except Exception:
        pass
    symbols = config_dict.get("symbols", [])
    strategy_positions = {s: all_positions[s] for s in symbols if s in all_positions}

    context = {
        "title": f"Strategy — {name}",
        "active_page": "strategies",
        "strategy_name": name,
        "strategy": perf,
        "config": config_dict,
        "strategy_positions": strategy_positions,
    }
    return render_template("strategies/detail.html", **context)
