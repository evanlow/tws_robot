"""Read-only API for autonomous trading evidence records."""

from __future__ import annotations

from flask import Blueprint, current_app, jsonify, request

from autonomous import AutonomousTradingConfig
from autonomous.evidence_store import TradeEvidenceStore
from autonomous.evidence_learning_summary import summarize_evidence_learning

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


@bp.route("/learning-status", methods=["GET"])
def evidence_learning_status():
    """Return the complete read-only EL8 evidence-learning dashboard payload."""

    summary = _learning_summary_from_request()
    return jsonify(summary)


@bp.route("/setup-performance", methods=["GET"])
def setup_performance():
    """Return setup-level realized performance and eligibility diagnostics."""

    summary = _learning_summary_from_request()
    return jsonify(summary["setup_performance"])


@bp.route("/promotion-report", methods=["GET"])
def promotion_report():
    """Return the advisory capital promotion report without applying changes."""

    summary = _learning_summary_from_request()
    return jsonify(summary["promotion_report"])


@bp.route("/weak-setups", methods=["GET"])
def weak_setups():
    """Return setups that should remain paper-only, reduced, or retired."""

    summary = _learning_summary_from_request()
    return jsonify(summary["weak_setups"])


@bp.route("/drift-report", methods=["GET"])
def drift_report():
    """Return setup families whose recent evidence diverges from history."""

    summary = _learning_summary_from_request()
    return jsonify(summary["drift_report"])


def _learning_summary_from_request() -> dict:
    limit = _int_arg("limit", 1000, minimum=1, maximum=1000)
    setup_limit = _int_arg("setup_limit", 50, minimum=1, maximum=250)
    current_level = _int_arg("current_level", 0, minimum=0, maximum=6)
    drift_recent_trades = _int_arg("recent_trades", 10, minimum=1, maximum=100)
    drift_min_trades = _int_arg("min_trades", 3, minimum=1, maximum=100)
    drift_delta = _float_arg("expected_r_delta", 0.25, minimum=0.0, maximum=10.0)
    return summarize_evidence_learning(
        _evidence_store().recent(limit=limit),
        current_level=current_level,
        setup_limit=setup_limit,
        drift_recent_trades=drift_recent_trades,
        drift_min_trades=drift_min_trades,
        drift_expected_r_delta=drift_delta,
    )


def _int_arg(name: str, default: int, *, minimum: int, maximum: int) -> int:
    try:
        value = int(request.args.get(name, default))
    except (TypeError, ValueError):
        value = default
    return max(minimum, min(maximum, value))


def _float_arg(name: str, default: float, *, minimum: float, maximum: float) -> float:
    try:
        value = float(request.args.get(name, default))
    except (TypeError, ValueError):
        value = default
    return max(minimum, min(maximum, value))
