"""Read-only API for autonomous trading evidence records."""

from __future__ import annotations

from flask import Blueprint, current_app, jsonify, request

from autonomous import AutonomousTradingConfig
from autonomous.evidence_store import TradeEvidenceStore

bp = Blueprint(
    "api_autonomous_evidence",
    __name__,
    url_prefix="/api/autonomous/evidence",
)


def _evidence_store() -> TradeEvidenceStore:
    log_dir = (
        current_app.config.get("autonomous_audit_log_dir")
        or AutonomousTradingConfig().audit_log_dir
    )
    return TradeEvidenceStore(log_dir)


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
