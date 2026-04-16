"""Market overview API.

GET  /api/market/overview  — latest index snapshots (cached)
POST /api/market/refresh   — trigger a fresh fetch from yfinance
"""

import logging

from flask import Blueprint, jsonify

logger = logging.getLogger(__name__)

bp = Blueprint("api_market", __name__, url_prefix="/api/market")


def _get_service():
    from data.market_overview import get_market_overview_service
    return get_market_overview_service()


@bp.route("/overview", methods=["GET"])
def overview():
    """Return the latest global market overview (from cache or DB).

    If data is stale a background refresh is automatically triggered
    so the *next* request will have fresh data.
    """
    svc = _get_service()
    data = svc.get_overview()

    # Kick off a background refresh when stale
    if svc.is_stale():
        svc.refresh_async()

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
