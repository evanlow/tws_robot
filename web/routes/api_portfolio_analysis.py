"""Portfolio Analysis API — enhanced portfolio insights & stock deep-dive.

Endpoints
---------
GET  /api/account/portfolio-insights
    Returns enhanced portfolio analysis with strategy deductions,
    allocation intelligence, and optional AI narrative.

GET  /api/account/stock-deep-dive/<symbol>
    Returns on-demand deep-dive analysis for a specific portfolio holding.

POST /api/account/portfolio-snapshot
    Saves the current portfolio state as a snapshot for historical tracking.

GET  /api/account/portfolio-snapshots
    Returns recent portfolio snapshot history.

GET  /api/account/stock-analysis-history/<symbol>
    Returns historical deep-dive analyses for a symbol.
"""

import logging
from datetime import datetime, timezone

from flask import Blueprint, jsonify, request

from web.services import get_services

logger = logging.getLogger(__name__)

bp = Blueprint("api_portfolio_analysis", __name__, url_prefix="/api/account")


@bp.route("/portfolio-insights", methods=["GET"])
def portfolio_insights():
    """Return enhanced portfolio analysis with strategy deductions."""
    svc = get_services()
    positions = svc.get_positions()

    if not positions:
        return jsonify({
            "positions_enriched": [],
            "strategy_mix": {},
            "ai_narrative": None,
            "ai_recommendations": [],
            "ai_risk_assessment": None,
            "total_value": 0,
            "position_count": 0,
        })

    from ai.portfolio_analyzer import PortfolioAnalyzer

    use_ai = request.args.get("ai", "true").lower() == "true"
    analyzer = PortfolioAnalyzer()
    account_summary = svc.get_account_summary()
    # Add equity from risk manager
    account_summary["equity"] = svc.risk_manager.current_equity

    result = analyzer.analyze_portfolio(
        positions,
        account_summary=account_summary,
        use_ai=use_ai,
    )

    total_value = sum(
        abs(pos.get("market_value", 0)) for pos in positions.values()
    )

    return jsonify({
        "positions_enriched": result["positions_enriched"],
        "strategy_mix": result["strategy_mix"],
        "ai_narrative": result.get("ai_narrative"),
        "ai_recommendations": result.get("ai_recommendations", []),
        "ai_risk_assessment": result.get("ai_risk_assessment"),
        "ai_strategy_mix": result.get("ai_strategy_mix"),
        "total_value": total_value,
        "position_count": len(positions),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })


@bp.route("/stock-deep-dive/<symbol>", methods=["GET"])
def stock_deep_dive(symbol: str):
    """Return on-demand deep-dive analysis for a portfolio holding."""
    symbol = symbol.upper()
    svc = get_services()
    positions = svc.get_positions()

    # Check if the symbol is in the portfolio
    position = positions.get(symbol)
    if position is None:
        return jsonify({
            "error": f"{symbol} is not in the current portfolio",
            "available_symbols": list(positions.keys()),
        }), 404

    use_ai = request.args.get("ai", "true").lower() == "true"
    use_cache = request.args.get("cache", "true").lower() == "true"

    # Check for cached analysis first
    if use_cache:
        try:
            from data.portfolio_persistence import get_latest_stock_analysis
            cached = get_latest_stock_analysis(symbol)
            if cached is not None:
                cached["from_cache"] = True
                return jsonify(cached)
        except Exception:
            logger.debug("Cache lookup failed for %s", symbol)

    # Fetch fundamentals
    try:
        from data.fundamentals import get_fundamentals
        fundamentals = get_fundamentals(symbol, use_cache=use_cache)
    except Exception:
        logger.warning("Fundamentals fetch failed for %s", symbol)
        fundamentals = {}

    # Compute technical context
    technical_context = {}
    try:
        from data.fundamentals import fetch_price_history
        from ai.stock_analyzer import compute_technical_context

        current_price = position.get("current_price", 0)
        history = fetch_price_history(symbol, period="1y", interval="1d")
        if history and current_price > 0:
            technical_context = compute_technical_context(current_price, history)
    except Exception:
        logger.warning("Technical context computation failed for %s", symbol)

    # Enrich position data
    enriched_position = dict(position)
    enriched_position["symbol"] = symbol
    total_value = sum(
        abs(p.get("market_value", 0)) for p in positions.values()
    )
    mv = abs(position.get("market_value", 0))
    enriched_position["portfolio_weight"] = mv / total_value if total_value > 0 else 0

    # Run the deep-dive analysis
    from ai.stock_analyzer import StockAnalyzer

    analyzer = StockAnalyzer()
    result = analyzer.analyze_stock(
        symbol=symbol,
        position=enriched_position,
        fundamentals=fundamentals,
        technical_context=technical_context,
        use_ai=use_ai,
    )

    # Persist the analysis
    try:
        from data.portfolio_persistence import save_stock_analysis
        verdict = None
        if result.get("ai_analysis"):
            verdict = result["ai_analysis"].get("verdict")
        save_stock_analysis(
            symbol=symbol,
            fundamentals=fundamentals,
            technical=technical_context,
            ai_analysis=result.get("ai_analysis"),
            verdict=verdict,
        )
    except Exception:
        logger.debug("Failed to persist analysis for %s", symbol)

    result["from_cache"] = False
    # Sanitize: remove any internal keys that shouldn't be exposed
    safe_result = {
        "symbol": result.get("symbol"),
        "position": result.get("position"),
        "fundamentals": result.get("fundamentals"),
        "technicals": result.get("technicals"),
        "ai_analysis": result.get("ai_analysis"),
        "timestamp": result.get("timestamp"),
        "from_cache": False,
    }
    return jsonify(safe_result)


@bp.route("/portfolio-snapshot", methods=["POST"])
def save_snapshot():
    """Save the current portfolio state as a snapshot."""
    svc = get_services()
    positions = svc.get_positions()
    account = svc.get_account_summary()
    equity = svc.risk_manager.current_equity
    cash = account.get("cash_balance", 0)

    # Compute strategy mix
    from ai.portfolio_analyzer import PortfolioAnalyzer
    analyzer = PortfolioAnalyzer()
    analysis = analyzer.analyze_portfolio(positions, account_summary=account, use_ai=False)

    positions_list = []
    for symbol, pos in positions.items():
        positions_list.append({
            "symbol": symbol,
            "quantity": pos.get("quantity", 0),
            "entry_price": pos.get("entry_price", 0),
            "current_price": pos.get("current_price", 0),
            "market_value": pos.get("market_value", 0),
            "unrealized_pnl": pos.get("unrealized_pnl", 0),
        })

    try:
        from data.portfolio_persistence import save_portfolio_snapshot
        row_id = save_portfolio_snapshot(
            total_equity=equity,
            cash=cash,
            positions=positions_list,
            strategy_mix=analysis.get("strategy_mix"),
            analysis={"deductions": analysis.get("deductions")},
        )
        return jsonify({"status": "saved", "snapshot_id": row_id})
    except Exception as exc:
        logger.error("Failed to save portfolio snapshot: %s", exc)
        return jsonify({"error": "Failed to save snapshot"}), 500


@bp.route("/portfolio-snapshots", methods=["GET"])
def list_snapshots():
    """Return recent portfolio snapshot history."""
    limit = request.args.get("limit", 30, type=int)
    limit = min(max(1, limit), 100)

    try:
        from data.portfolio_persistence import get_snapshot_history
        snapshots = get_snapshot_history(limit=limit)
        return jsonify({"snapshots": snapshots, "count": len(snapshots)})
    except Exception as exc:
        logger.error("Failed to retrieve snapshots: %s", exc)
        return jsonify({"error": "Failed to retrieve snapshots"}), 500


@bp.route("/stock-analysis-history/<symbol>", methods=["GET"])
def stock_analysis_history(symbol: str):
    """Return historical deep-dive analyses for a symbol."""
    symbol = symbol.upper()
    limit = request.args.get("limit", 10, type=int)
    limit = min(max(1, limit), 50)

    try:
        from data.portfolio_persistence import get_stock_analysis_history
        analyses = get_stock_analysis_history(symbol=symbol, limit=limit)
        return jsonify({"symbol": symbol, "analyses": analyses, "count": len(analyses)})
    except Exception as exc:
        logger.error("Failed to retrieve analyses for %s: %s", symbol, exc)
        return jsonify({"error": "Failed to retrieve analyses"}), 500
