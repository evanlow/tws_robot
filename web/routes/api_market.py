"""Market overview API.

GET  /api/market/overview  — latest index snapshots (cached)
GET  /api/market/outlook   — AI-powered market outlook (cached)
POST /api/market/refresh   — trigger a fresh fetch from yfinance
"""

import logging

from flask import Blueprint, jsonify, request

from web.services import get_services

logger = logging.getLogger(__name__)

bp = Blueprint("api_market", __name__, url_prefix="/api/market")


def _get_service():
    from data.market_overview import get_market_overview_service
    return get_market_overview_service()


@bp.route("/overview", methods=["GET"])
def overview():
    """Return the latest global market overview (from cache or DB).

    The service automatically triggers a background refresh when data is
    stale, so the *next* request will have fresh data.
    """
    svc = _get_service()
    data = svc.get_overview()
    return jsonify(data)


@bp.route("/outlook", methods=["GET"])
def outlook():
    """Return AI-powered market outlook (from cache or freshly generated).

    Combines market overview data with the trader's portfolio to produce
    a structured outlook with session recap, portfolio-relevant insights,
    and recommendations.

    Query parameters:
        refresh=true  — bypass cache and regenerate
    """
    from ai.market_outlook import get_market_outlook_generator

    force = request.args.get("refresh", "false").lower() == "true"
    generator = get_market_outlook_generator()

    # Avoid expensive portfolio analysis when the cache is still fresh
    if not force and not generator.is_stale():
        data = generator.get_outlook()
        return jsonify(data)

    mkt_svc = _get_service()
    market_overview = mkt_svc.get_overview()

    # Gather portfolio context (only when we expect to regenerate)
    svc = get_services()
    positions = svc.get_positions()
    strategy_mix = {}
    account_summary = {}
    try:
        from ai.portfolio_analyzer import PortfolioAnalyzer
        analyzer = PortfolioAnalyzer()
        analysis = analyzer.analyze_portfolio(positions, use_ai=False)
        strategy_mix = analysis.get("strategy_mix", {})
    except Exception:
        logger.debug("Failed to compute strategy mix for outlook", exc_info=True)

    try:
        account_summary = svc.get_account_summary()
        account_summary["equity"] = svc.risk_manager.current_equity
    except Exception:
        logger.debug("Failed to get account summary for outlook", exc_info=True)

    data = generator.get_outlook(
        market_overview=market_overview,
        positions=positions,
        strategy_mix=strategy_mix,
        account_summary=account_summary,
        force_refresh=force,
    )
    return jsonify(data)


@bp.route("/refresh", methods=["POST"])
def refresh():
    """Manually refresh market data from Yahoo Finance.

    This is a synchronous call — it blocks until the fetch completes
    and returns the fresh overview.
    """
    svc = _get_service()
    data = svc.refresh()
    return jsonify(data)
