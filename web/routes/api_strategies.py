"""Strategy management API.

GET  /api/strategies                    — list all strategies with status
POST /api/strategies/<name>/start       — start a strategy
POST /api/strategies/<name>/stop        — stop a running strategy
GET  /api/strategies/<name>/metrics     — live metrics
PUT  /api/strategies/<name>/config      — update strategy parameters
GET  /api/strategies/classes            — list registered strategy classes
POST /api/strategies/create             — create a strategy instance
"""

import logging
from datetime import datetime

from flask import Blueprint, jsonify, request

from web.services import get_services

logger = logging.getLogger(__name__)

bp = Blueprint("api_strategies", __name__, url_prefix="/api/strategies")


@bp.route("/", methods=["GET"])
def list_strategies():
    """Return all registered strategy instances with their status."""
    svc = get_services()
    reg = svc.strategy_registry
    result = []
    for strategy in reg.get_all_strategies():
        result.append(strategy.get_performance_summary())
    return jsonify({
        "strategies": result,
        "summary": reg.get_overall_summary(),
    })


@bp.route("/classes", methods=["GET"])
def list_classes():
    """Return registered strategy class names (types that can be instantiated)."""
    svc = get_services()
    return jsonify({
        "classes": svc.strategy_registry.get_registered_classes(),
    })


@bp.route("/create", methods=["POST"])
def create_strategy():
    """Create a new strategy instance.

    Body::

        {
            "strategy_type": "BollingerBands",
            "name": "BB_AAPL",
            "symbols": ["AAPL"],
            "parameters": { "period": 20, "std_dev": 2.0 }
        }
    """
    svc = get_services()
    data = request.get_json(silent=True) or {}
    strategy_type = data.get("strategy_type", "")
    name = data.get("name", "")
    symbols = data.get("symbols", [])
    parameters = data.get("parameters", {})

    if not strategy_type or not name or not symbols:
        return jsonify({
            "error": "strategy_type, name, and symbols are required",
        }), 400

    try:
        from strategies.base_strategy import StrategyConfig
        config = StrategyConfig(name=name, symbols=symbols, parameters=parameters)
        strategy = svc.strategy_registry.create_strategy(strategy_type, config)
        return jsonify({
            "status": "created",
            "strategy": strategy.get_performance_summary(),
        })
    except Exception as exc:
        return jsonify({"error": str(exc)}), 400


@bp.route("/<name>/start", methods=["POST"])
def start_strategy(name: str):
    """Start a specific strategy."""
    svc = get_services()
    strategy = svc.strategy_registry.get_strategy(name)
    if not strategy:
        return jsonify({"error": f"Strategy '{name}' not found"}), 404

    svc.strategy_registry.start_strategy(name)
    return jsonify({
        "status": "started",
        "strategy": strategy.get_performance_summary(),
    })


@bp.route("/<name>/stop", methods=["POST"])
def stop_strategy(name: str):
    """Stop a specific strategy."""
    svc = get_services()
    strategy = svc.strategy_registry.get_strategy(name)
    if not strategy:
        return jsonify({"error": f"Strategy '{name}' not found"}), 404

    svc.strategy_registry.stop_strategy(name)
    return jsonify({
        "status": "stopped",
        "strategy": strategy.get_performance_summary(),
    })


@bp.route("/<name>/metrics", methods=["GET"])
def strategy_metrics(name: str):
    """Return live metrics for a strategy."""
    svc = get_services()
    strategy = svc.strategy_registry.get_strategy(name)
    if not strategy:
        return jsonify({"error": f"Strategy '{name}' not found"}), 404

    return jsonify(strategy.get_performance_summary())


@bp.route("/<name>/config", methods=["PUT"])
def update_config(name: str):
    """Update strategy parameters (hot-reload).

    Body::

        {
            "symbols": ["AAPL", "MSFT"],
            "parameters": { "period": 25 }
        }
    """
    svc = get_services()
    strategy = svc.strategy_registry.get_strategy(name)
    if not strategy:
        return jsonify({"error": f"Strategy '{name}' not found"}), 404

    data = request.get_json(silent=True) or {}
    try:
        from strategies.base_strategy import StrategyConfig
        new_config = StrategyConfig(
            name=name,
            symbols=data.get("symbols", strategy.config.symbols),
            parameters=data.get("parameters", strategy.config.parameters),
            risk_limits=data.get("risk_limits", strategy.config.risk_limits),
            enabled=data.get("enabled", strategy.config.enabled),
        )
        svc.strategy_registry.reload_config(name, new_config)
        return jsonify({"status": "updated", "config": new_config.__dict__})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 400
