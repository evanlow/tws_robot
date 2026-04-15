"""Backtest execution API.

POST /api/backtest/run                    — run a backtest (returns run_id)
GET  /api/backtest/<run_id>/status        — check if running/complete
GET  /api/backtest/<run_id>/results       — full results (metrics, equity)
GET  /api/backtest/runs                   — list all backtest runs
GET  /api/backtest/compare                — side-by-side comparison
"""

import logging
import threading
import uuid
from datetime import datetime

from flask import Blueprint, jsonify, request

from web.services import get_services

logger = logging.getLogger(__name__)

bp = Blueprint("api_backtest", __name__, url_prefix="/api/backtest")


@bp.route("/runs", methods=["GET"])
def list_runs():
    """Return all stored backtest runs."""
    svc = get_services()
    return jsonify({"runs": svc.list_backtest_runs()})


@bp.route("/run", methods=["POST"])
def run_backtest():
    """Submit a new backtest job (runs in background thread).

    Body::

        {
            "strategy": "MovingAverageCross",
            "symbols": ["AAPL"],
            "start_date": "2024-01-01",
            "end_date": "2024-12-31",
            "initial_capital": 100000
        }
    """
    svc = get_services()
    data = request.get_json(silent=True) or {}

    strategy_name = data.get("strategy", "")
    symbols = data.get("symbols", [])
    start_date = data.get("start_date", "")
    end_date = data.get("end_date", "")
    initial_capital = float(data.get("initial_capital", 100000))

    if not strategy_name or not symbols or not start_date or not end_date:
        return jsonify({
            "error": "strategy, symbols, start_date, end_date are required",
        }), 400

    run_id = str(uuid.uuid4())[:8]

    svc.store_backtest_run(run_id, {
        "status": "running",
        "strategy_name": strategy_name,
        "symbols": symbols,
        "start_date": start_date,
        "end_date": end_date,
        "initial_capital": initial_capital,
        "created": datetime.now().isoformat(),
        "results": None,
    })

    # Run backtest in background
    thread = threading.Thread(
        target=_run_backtest_thread,
        args=(svc, run_id, strategy_name, symbols, start_date, end_date, initial_capital),
        daemon=True,
    )
    thread.start()

    return jsonify({"run_id": run_id, "status": "running"}), 202


@bp.route("/<run_id>/status", methods=["GET"])
def backtest_status(run_id: str):
    """Check status of a backtest run."""
    svc = get_services()
    run = svc.get_backtest_run(run_id)
    if not run:
        return jsonify({"error": f"Run '{run_id}' not found"}), 404
    return jsonify({
        "run_id": run_id,
        "status": run.get("status", "unknown"),
        "strategy_name": run.get("strategy_name", ""),
    })


@bp.route("/<run_id>/results", methods=["GET"])
def backtest_results(run_id: str):
    """Return full backtest results if complete."""
    svc = get_services()
    run = svc.get_backtest_run(run_id)
    if not run:
        return jsonify({"error": f"Run '{run_id}' not found"}), 404

    if run.get("status") == "running":
        return jsonify({"run_id": run_id, "status": "running"}), 202

    return jsonify({
        "run_id": run_id,
        "status": run.get("status"),
        "results": run.get("results"),
    })


@bp.route("/compare", methods=["GET"])
def compare_runs():
    """Compare multiple backtest runs side-by-side.

    Query: ?runs=id1,id2,id3
    """
    svc = get_services()
    run_ids = request.args.get("runs", "").split(",")
    run_ids = [r.strip() for r in run_ids if r.strip()]

    if not run_ids:
        return jsonify({"error": "Provide ?runs=id1,id2,..."}), 400

    comparisons = []
    for rid in run_ids:
        run = svc.get_backtest_run(rid)
        if run and run.get("results"):
            comparisons.append({
                "run_id": rid,
                "strategy": run.get("strategy_name", ""),
                "metrics": run["results"].get("metrics", {}),
            })

    return jsonify({"comparisons": comparisons})


def _run_backtest_thread(svc, run_id, strategy_name, symbols, start_date, end_date, initial_capital):
    """Execute backtest in background thread and store results."""
    try:
        from backtest.data_manager import HistoricalDataManager
        from backtest.engine import BacktestConfig, BacktestEngine
        from backtest.strategy import StrategyConfig

        config = BacktestConfig(
            start_date=datetime.strptime(start_date, "%Y-%m-%d"),
            end_date=datetime.strptime(end_date, "%Y-%m-%d"),
            initial_capital=initial_capital,
        )

        data_manager = HistoricalDataManager()
        engine = BacktestEngine(config, data_manager)

        strategy_config = StrategyConfig(name=strategy_name, symbols=symbols)

        # Try to import the named strategy
        from backtest.strategy_templates import get_strategy_class
        strategy_class = get_strategy_class(strategy_name)
        strategy = strategy_class(strategy_config)

        engine.set_strategy(strategy)
        result = engine.run()

        # Serialise results
        results_dict = {
            "metrics": {
                "total_return": result.total_return,
                "total_pnl": result.total_pnl,
                "final_equity": result.final_equity,
                "total_trades": result.total_trades,
                "winning_trades": result.winning_trades,
                "losing_trades": result.losing_trades,
                "win_rate": result.win_rate,
                "max_drawdown": result.max_drawdown,
                "max_drawdown_pct": result.max_drawdown_pct,
            },
            "equity_curve": [
                {
                    "timestamp": ep.timestamp.isoformat(),
                    "equity": ep.equity,
                    "drawdown": ep.drawdown,
                }
                for ep in result.equity_curve[::max(1, len(result.equity_curve) // 500)]
            ],
        }

        run = svc.get_backtest_run(run_id) or {}
        run["status"] = "complete"
        run["results"] = results_dict
        svc.store_backtest_run(run_id, run)

        logger.info("Backtest %s completed: return=%.2f%%", run_id, result.total_return * 100)

    except Exception as exc:
        logger.error("Backtest %s failed: %s", run_id, exc)
        run = svc.get_backtest_run(run_id) or {}
        run["status"] = "failed"
        run["error"] = str(exc)
        svc.store_backtest_run(run_id, run)
