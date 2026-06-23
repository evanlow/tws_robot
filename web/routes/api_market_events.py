"""Market Events API.

GET  /api/market-events/upcoming?days=14   — upcoming events (from DB cache)
POST /api/market-events/refresh            — trigger a fresh fetch from external sources
GET  /api/market-events/sync-log           — provider sync status history
GET  /api/market-events/ticker             — compact rolling ticker payload
GET  /api/market-events/reminders          — popup reminder payload
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

    event_types = _csv_arg("event_type")
    symbols = _csv_arg("symbol")
    statuses = _csv_arg("status")

    svc = _get_event_service()
    portfolio_symbols = _get_portfolio_symbols(get_services())
    events = svc.get_upcoming_events(
        days_ahead=days,
        portfolio_symbols=portfolio_symbols,
        event_types=event_types,
        symbols=symbols,
        statuses=statuses,
    )

    return jsonify({
        "events": events,
        "count": len(events),
        "days_ahead": days,
        "portfolio_symbols": sorted(portfolio_symbols),
        "filters": {
            "event_type": event_types,
            "symbol": symbols,
            "status": statuses,
        },
    })


@bp.route("/refresh", methods=["POST"])
def refresh():
    """Trigger a background refresh of market events from external sources.

    Forces a re-fetch regardless of TTL.
    """
    app_svc = get_services()
    portfolio_symbols = _get_portfolio_symbols(app_svc)

    try:
        days = max(1, min(int(request.args.get("days", 28)), 90))
    except (TypeError, ValueError):
        days = 28

    svc = _get_event_service()
    svc.refresh_async(
        portfolio_symbols=list(portfolio_symbols),
        force=True,
        days_ahead=days,
    )
    return jsonify({
        "status": "refresh_started",
        "days_ahead": days,
        "portfolio_symbols": sorted(portfolio_symbols),
    })


@bp.route("/sync-log", methods=["GET"])
def sync_log():
    """Return recent market-event provider sync attempts."""
    try:
        limit = max(1, min(int(request.args.get("limit", 20)), 100))
    except (TypeError, ValueError):
        limit = 20
    svc = _get_event_service()
    logs = svc.get_sync_logs(limit=limit)
    return jsonify({
        "logs": logs,
        "count": len(logs),
        "last_sync_summary": svc.get_last_sync_summary(),
    })


@bp.route("/ticker", methods=["GET"])
def ticker():
    """Return compact upcoming-event items for a dashboard strip."""
    try:
        days = max(1, min(int(request.args.get("days", 28)), 90))
    except (TypeError, ValueError):
        days = 28
    try:
        limit = max(1, min(int(request.args.get("limit", 8)), 20))
    except (TypeError, ValueError):
        limit = 8
    portfolio_symbols = _get_portfolio_symbols(get_services())
    svc = _get_event_service()
    items = svc.get_ticker_items(
        days_ahead=days,
        portfolio_symbols=list(portfolio_symbols),
        limit=limit,
    )
    return jsonify({
        "items": items,
        "count": len(items),
        "days_ahead": days,
        "portfolio_symbols": sorted(portfolio_symbols),
    })


@bp.route("/reminders", methods=["GET"])
def reminders():
    """Return popup reminder candidates for medium/high/critical events."""
    try:
        days = max(1, min(int(request.args.get("days", 7)), 30))
    except (TypeError, ValueError):
        days = 7
    mode = (request.args.get("mode") or "high_only").strip().lower()
    if mode not in {"off", "high_only", "medium_high", "all"}:
        mode = "high_only"
    portfolio_symbols = _get_portfolio_symbols(get_services())
    svc = _get_event_service()
    items = svc.get_reminders(
        days_ahead=days,
        portfolio_symbols=list(portfolio_symbols),
        mode=mode,
    )
    return jsonify({
        "reminders": items,
        "count": len(items),
        "days_ahead": days,
        "mode": mode,
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


def _csv_arg(name: str) -> list:
    values = []
    for raw in request.args.getlist(name):
        for part in str(raw).split(","):
            item = part.strip().upper()
            if item:
                values.append(item)
    return values
