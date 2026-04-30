"""Market Events API.

GET  /api/market-events/upcoming?days=14   — upcoming events (from DB cache)
POST /api/market-events/refresh            — trigger a fresh fetch from external sources
"""

import logging

from flask import Blueprint, jsonify, request

from web.services import get_services

logger = logging.getLogger(__name__)

bp = Blueprint("api_market_events", __name__, url_prefix="/api/market-events")


def _get_event_service():
    from data.market_events import get_market_events_service
    return get_market_events_service()


@bp.route("/upcoming", methods=["GET"])
def upcoming():
    """Return upcoming market events sorted chronologically.

    Query parameters:
        days  (int, default 14) — how many calendar days ahead to look
    """
    try:
        days = max(1, min(int(request.args.get("days", 14)), 90))
    except (TypeError, ValueError):
        days = 14

    svc = _get_event_service()
    app_svc = get_services()

    # Collect portfolio symbols from active positions + strategies
    portfolio_symbols = _get_portfolio_symbols(app_svc)

    events = svc.get_upcoming_events(
        days_ahead=days,
        portfolio_symbols=portfolio_symbols,
    )

    return jsonify({
        "events": events,
        "count": len(events),
        "days_ahead": days,
        "portfolio_symbols": sorted(portfolio_symbols),
    })


@bp.route("/refresh", methods=["POST"])
def refresh():
    """Trigger a background refresh of market events from external sources.

    Forces a re-fetch regardless of TTL.
    """
    app_svc = get_services()
    portfolio_symbols = _get_portfolio_symbols(app_svc)

    svc = _get_event_service()
    svc.refresh_async(portfolio_symbols=list(portfolio_symbols), force=True)

    return jsonify({
        "status": "refresh_started",
        "portfolio_symbols": sorted(portfolio_symbols),
    })


# ── helpers ───────────────────────────────────────────────────────────────────

def _get_portfolio_symbols(app_svc) -> set:
    """Collect unique symbols from open positions and active strategies."""
    symbols: set = set()
    try:
        for sym in app_svc.get_positions():
            symbols.add(sym.upper())
    except Exception:
        pass
    try:
        for s in app_svc.strategy_registry.get_all_strategies():
            for sym in (s.config.symbols or []):
                symbols.add(sym.upper())
    except Exception:
        pass
    return symbols
