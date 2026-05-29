"""STI Screener API.

GET /api/stocks/sti/screener
    Returns a compact screener payload listing all STI constituents
    with their Bollinger Bands status (overbought / oversold highlight).

Query parameters
----------------
status : str, optional
    Filter by Bollinger status.  One of:
    ``all`` (default), ``overbought``, ``near_overbought``, ``neutral``,
    ``near_oversold``, ``oversold``, ``insufficient_data``.

sector : str, optional
    Filter by sector name (case-insensitive, partial match allowed).
    Defaults to ``all``.

refresh : str, optional
    Pass ``true`` to bypass the server-side cache and force a fresh scan.
    Defaults to ``false``.
"""

import logging

from flask import Blueprint, jsonify, request

from web.sti_screener_service import sti_screener_service

logger = logging.getLogger(__name__)

bp = Blueprint("api_sti_screener", __name__, url_prefix="/api/stocks")

# Recognised status filter values → the bollinger_status field value they map to.
_STATUS_FILTER_MAP = {
    "overbought": "above_upper_band",
    "near_overbought": "near_upper_band",
    "neutral": "within_bands",
    "near_oversold": "near_lower_band",
    "oversold": "below_lower_band",
    "insufficient_data": "insufficient_data",
}


@bp.route("/sti/screener", methods=["GET"])
def screener():
    """Return the STI screener payload.

    Caches the scan server-side (default TTL: 15 minutes).  Pass
    ``?refresh=true`` to force a fresh scan.
    """
    refresh_param = request.args.get("refresh", "false").lower()
    force_refresh = refresh_param in ("true", "1", "yes")

    try:
        data = sti_screener_service.get_screener_data(refresh=force_refresh)
    except Exception as exc:
        logger.error("STI screener scan failed: %s", exc, exc_info=True)
        return jsonify({"error": "Screener scan could not be completed."}), 500

    rows = data.get("rows", [])

    # --- Status filter ---
    status_filter = request.args.get("status", "all").lower().strip()
    if status_filter != "all" and status_filter in _STATUS_FILTER_MAP:
        target_status = _STATUS_FILTER_MAP[status_filter]
        rows = [r for r in rows if r["bollinger_status"] == target_status]

    # --- Sector filter ---
    sector_filter = request.args.get("sector", "all").strip()
    if sector_filter and sector_filter.lower() != "all":
        sector_lower = sector_filter.lower()
        rows = [r for r in rows if sector_lower in r.get("sector", "").lower()]

    response = {
        "as_of": data.get("as_of"),
        "source": data.get("source"),
        "count": len(rows),
        "summary": data.get("summary", {}),
        "rows": rows,
        "scan_duration_seconds": data.get("scan_duration_seconds"),
    }
    if "error" in data:
        response["error"] = data["error"]

    return jsonify(response)
