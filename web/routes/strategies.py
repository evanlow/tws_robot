"""Strategies route — list, start/stop, and tune live strategies.

GET  /strategies          →  strategy list
GET  /strategies/<name>   →  detail / parameter editor
POST /strategies/<name>   →  update parameters
"""

from flask import Blueprint, render_template

from ai.client import is_ai_enabled
from web.position_analyzer import _parse_option_symbol, _underlying_for
from web.services import get_services


def _positions_for_symbols(all_positions, symbols):
    """Return positions whose symbol or option-underlying matches ``symbols``.

    Option contracts are keyed by their OCC localSymbol, so a plain ``sym in
    all_positions`` lookup misses covered-call legs and similar option positions.
    Each returned entry includes a parsed ``option_contract`` dict when the key
    is an option, so callers (templates, AI prompts) can render the leg details.
    """
    symbol_set = set(symbols or [])
    out = {}
    for sym, pos in all_positions.items():
        underlying = _underlying_for(sym, pos)
        if sym in symbol_set or underlying in symbol_set:
            entry = dict(pos)
            parsed = _parse_option_symbol(sym)
            if parsed:
                entry["option_contract"] = parsed
            out[sym] = entry
    return out

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
        perf["live_positions"] = _positions_for_symbols(all_positions, symbols)
        # Expose config parameters so the template can render adoption metadata
        # (targets, description, confidence, strategy_type) stored at adopt-time.
        perf["config_parameters"] = dict(s.config.parameters)
        strategies.append(perf)

    context = {
        "title": "Strategies",
        "active_page": "strategies",
        "strategies": strategies,
        "strategy_classes": classes,
        "summary": svc.strategy_registry.get_overall_summary() if strategies else {},
        "inferred_strategies": inferred,
        "ai_enabled": is_ai_enabled(),
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
    strategy_positions = _positions_for_symbols(all_positions, symbols)

    context = {
        "title": f"Strategy — {name}",
        "active_page": "strategies",
        "strategy_name": name,
        "strategy": perf,
        "config": config_dict,
        "strategy_positions": strategy_positions,
    }
    return render_template("strategies/detail.html", **context)
