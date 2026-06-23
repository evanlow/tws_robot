"""Read-only evidence-learning summaries for APIs and dashboards.

This module turns realized autonomous evidence into operator-facing learning
diagnostics. It does not mutate trading configuration, capital levels, broker
state, orders, risk controls, or lifecycle state.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional

from autonomous.capital_promotion import CapitalPromotionEvaluator
from autonomous.evidence_calibrator import (
    SETUP_STATE_INSUFFICIENT_EVIDENCE,
    SETUP_STATE_LIVE_ELIGIBLE,
    SETUP_STATE_PAPER_ONLY,
    SETUP_STATE_RETIRED,
    SETUP_STATE_STRONG,
    SETUP_STATE_WEAK,
    EvidenceCalibrator,
    SetupEvidenceSummary,
)
from autonomous.performance_metrics import calculate_performance_metrics
from autonomous.setup_registry import setup_id_for_record


EVIDENCE_LEARNING_SUMMARY_VERSION = 1

WEAK_SETUP_STATES = {
    SETUP_STATE_INSUFFICIENT_EVIDENCE,
    SETUP_STATE_PAPER_ONLY,
    SETUP_STATE_RETIRED,
    SETUP_STATE_WEAK,
}


def summarize_evidence_learning(
    records: Iterable[Dict[str, Any]],
    *,
    current_level: int = 0,
    setup_limit: int = 50,
    drift_recent_trades: int = 10,
    drift_min_trades: int = 3,
    drift_expected_r_delta: float = 0.25,
    now: Optional[datetime] = None,
) -> Dict[str, Any]:
    """Return EL8 setup, promotion, weak-setup, and drift diagnostics."""

    rows = list(records or [])
    outcome_rows = _outcome_records(rows)
    calibrator = EvidenceCalibrator()
    summaries = calibrator.summarize(outcome_rows)
    grouped = _records_by_setup(outcome_rows)
    promotion = CapitalPromotionEvaluator().evaluate(
        outcome_rows,
        current_level=current_level,
        now=now,
    )
    setup_performance = _setup_performance(
        summaries=summaries,
        grouped=grouped,
        current_level=current_level,
        limit=setup_limit,
    )
    weak_setups = _weak_setups(setup_performance)
    drift = _drift_report(
        grouped=grouped,
        recent_trades=drift_recent_trades,
        min_trades=drift_min_trades,
        expected_r_delta=drift_expected_r_delta,
    )
    return {
        "version": EVIDENCE_LEARNING_SUMMARY_VERSION,
        "generated_at": (now or datetime.now(timezone.utc)).isoformat(),
        "counts": {
            "records": len(rows),
            "outcomes": len(outcome_rows),
            "setups": len(summaries),
            "weak_setups": len(weak_setups),
            "drift_setups": len(drift["setups"]),
        },
        "setup_performance": {
            "count": len(setup_performance),
            "setups": setup_performance,
        },
        "promotion_report": promotion.to_dict(),
        "weak_setups": {
            "count": len(weak_setups),
            "setups": weak_setups,
        },
        "drift_report": drift,
        "safety_notes": {
            "read_only": True,
            "does_not_submit_orders": True,
            "does_not_cancel_orders": True,
            "does_not_flatten_positions": True,
            "does_not_apply_capital_changes": True,
        },
    }


def _setup_performance(
    *,
    summaries: Dict[str, SetupEvidenceSummary],
    grouped: Dict[str, List[Dict[str, Any]]],
    current_level: int,
    limit: int,
) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for setup_id, summary in summaries.items():
        metrics = summary.metrics.to_dict()
        promotion = CapitalPromotionEvaluator().evaluate(
            grouped.get(setup_id, []),
            current_level=current_level,
        )
        rows.append(
            {
                "setup_id": setup_id,
                "status": summary.state,
                "trade_count": summary.sample_size,
                "avg_r": metrics.get("avg_r"),
                "expected_r": summary.posterior_expected_r,
                "raw_expected_r": metrics.get("expected_r"),
                "win_rate": metrics.get("win_rate"),
                "profit_factor": metrics.get("profit_factor"),
                "profit_factor_unbounded": metrics.get("profit_factor_unbounded"),
                "sharpe": metrics.get("sharpe"),
                "rolling_sharpe": metrics.get("rolling_sharpe"),
                "sortino": metrics.get("sortino"),
                "max_drawdown_r": metrics.get("max_drawdown_r"),
                "confidence": summary.confidence,
                "current_allowed_mode": _allowed_mode(summary.state),
                "recommended_capital_level": promotion.recommended_level,
                "promotion_action": promotion.action,
                "reasons": list(summary.reasons),
                "setup_metadata": summary.setup_metadata.to_dict(),
            }
        )

    rows.sort(
        key=lambda item: (
            item.get("expected_r") if item.get("expected_r") is not None else -999.0,
            item.get("confidence") or 0.0,
            item.get("trade_count") or 0,
        ),
        reverse=True,
    )
    return rows[: max(1, int(limit or 50))]


def _weak_setups(setups: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    rows = []
    for setup in setups:
        state = setup.get("status")
        if state not in WEAK_SETUP_STATES:
            continue
        rows.append(
            {
                "setup_id": setup.get("setup_id"),
                "status": state,
                "trade_count": setup.get("trade_count"),
                "expected_r": setup.get("expected_r"),
                "confidence": setup.get("confidence"),
                "current_allowed_mode": setup.get("current_allowed_mode"),
                "recommended_size_state": _size_state(state),
                "reasons": list(setup.get("reasons") or []),
            }
        )
    rows.sort(key=lambda item: (str(item.get("status")), item.get("expected_r") or 0.0))
    return rows


def _drift_report(
    *,
    grouped: Dict[str, List[Dict[str, Any]]],
    recent_trades: int,
    min_trades: int,
    expected_r_delta: float,
) -> Dict[str, Any]:
    recent_n = max(1, int(recent_trades or 10))
    min_n = max(1, int(min_trades or 3))
    threshold = max(0.0, float(expected_r_delta or 0.0))
    rows: List[Dict[str, Any]] = []

    for setup_id, records in grouped.items():
        ordered = sorted(records, key=lambda item: _timestamp_key(item.get("timestamp")))
        if len(ordered) < min_n * 2:
            continue
        recent = ordered[-recent_n:]
        historical = ordered[:-len(recent)]
        if len(recent) < min_n or len(historical) < min_n:
            continue
        recent_metrics = calculate_performance_metrics(recent).to_dict()
        historical_metrics = calculate_performance_metrics(historical).to_dict()
        delta = (recent_metrics["expected_r"] or 0.0) - (historical_metrics["expected_r"] or 0.0)
        if delta <= -threshold:
            direction = "weakening"
        elif delta >= threshold:
            direction = "improving"
        else:
            direction = "stable"
        if direction == "stable":
            continue
        rows.append(
            {
                "setup_id": setup_id,
                "direction": direction,
                "expected_r_delta": round(delta, 6),
                "recent": {
                    "trade_count": recent_metrics["trade_count"],
                    "expected_r": recent_metrics["expected_r"],
                    "win_rate": recent_metrics["win_rate"],
                    "max_drawdown_r": recent_metrics["max_drawdown_r"],
                },
                "historical": {
                    "trade_count": historical_metrics["trade_count"],
                    "expected_r": historical_metrics["expected_r"],
                    "win_rate": historical_metrics["win_rate"],
                    "max_drawdown_r": historical_metrics["max_drawdown_r"],
                },
            }
        )

    rows.sort(key=lambda item: item["expected_r_delta"])
    return {
        "count": len(rows),
        "recent_trades": recent_n,
        "min_trades": min_n,
        "expected_r_delta_threshold": threshold,
        "setups": rows,
    }


def _records_by_setup(records: Iterable[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    grouped: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for record in records:
        grouped[setup_id_for_record(record)].append(record)
    return dict(grouped)


def _outcome_records(records: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [record for record in records if record.get("evidence_type") == "autonomous_outcome"]


def _allowed_mode(state: str) -> str:
    if state in {SETUP_STATE_STRONG, SETUP_STATE_LIVE_ELIGIBLE}:
        return "recommend_paper_or_operator_approved_assisted_live"
    if state == SETUP_STATE_PAPER_ONLY:
        return "recommend_or_paper_only"
    if state == SETUP_STATE_INSUFFICIENT_EVIDENCE:
        return "recommend_or_paper_only_until_more_evidence"
    if state in {SETUP_STATE_RETIRED, SETUP_STATE_WEAK}:
        return "no_new_entries"
    return "recommend_or_paper"


def _size_state(state: str) -> str:
    if state == SETUP_STATE_RETIRED:
        return "RETIRED"
    if state == SETUP_STATE_WEAK:
        return "NO_TRADE"
    if state in {SETUP_STATE_PAPER_ONLY, SETUP_STATE_INSUFFICIENT_EVIDENCE}:
        return "PAPER_ONLY"
    return "NORMAL_CAPPED"


def _timestamp_key(value: Any) -> str:
    return str(value or "")
