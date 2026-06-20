"""Read-only API for autonomous trading evidence records."""

from __future__ import annotations

from flask import Blueprint, jsonify, request

from autonomous.evidence_store import TradeEvidenceStore
from web.routes.api_autonomous import EMERGENCY_STOP_FILE

bp = Blueprint(
    "api_autonomous_evidence",
    __name__,
    url_prefix="/api/autonomous/evidence",
)


def _evidence_store() -> TradeEvidenceStore:
    # Use the same default root as the autonomous engine/audit logger.  The
    # emergency-stop path is anchored in the repository root, so parent is a
    # stable fallback when the process working directory changes.
    default_log_dir = str(EMERGENCY_STOP_FILE.parent / "logs")
    return TradeEvidenceStore(default_log_dir)


@bp.route("", methods=["GET"])
def recent_evidence():
    """Return recent autonomous evidence records, newest first."""

    raw_limit = request.args.get("limit", "100")
    try:
        limit = int(raw_limit)
    except (TypeError, ValueError):
        limit = 100
    records = _evidence_store().recent(limit=limit)
    return jsonify({
        "count": len(records),
        "records": records,
    })
