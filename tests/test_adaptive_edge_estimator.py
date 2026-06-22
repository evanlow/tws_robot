from datetime import datetime, timedelta, timezone

import pytest

from autonomous.adaptive_edge_estimator import AdaptiveEdgeEstimator
from autonomous.edge_estimator import EdgeEstimate
from autonomous.evidence_calibrator import (
    SETUP_STATE_INSUFFICIENT_EVIDENCE,
    SETUP_STATE_LIVE_ELIGIBLE,
    SETUP_STATE_RETIRED,
    calibrate_setup_evidence,
)
from autonomous.evidence_store import SCHEMA_VERSION


BASE = datetime(2026, 6, 22, 12, 0, tzinfo=timezone.utc)


def _prior():
    return EdgeEstimate(
        p_win=0.55,
        avg_win_r=1.20,
        avg_loss_r=1.00,
        expected_r=(0.55 * 1.20) - (0.45 * 1.00),
        confidence=0.40,
        source="rule_based_bootstrap",
        reasons=["bootstrap rule-based estimate"],
    )


def _record(r_value, *, index=0, symbol="AAA", realized=True):
    return {
        "schema_version": SCHEMA_VERSION,
        "evidence_type": "autonomous_outcome",
        "timestamp": (BASE + timedelta(minutes=index)).isoformat(),
        "symbol": symbol,
        "strategy_bucket": {
            "signal_label": "Confirmed Rebound",
            "quality_label": "Strong",
            "momentum_label": "Confirmed Rebound",
            "market_classification": "Bullish / Volatility Acceptable",
            "vix_level_regime": "normal",
            "vix_direction_regime": "falling",
            "sector": "Technology",
        },
        "selected": {
            "features": {
                "sector_regime": "sector_supportive",
                "time_of_day_regime": "regular_session",
                "support_distance_pct": 0.02,
                "resistance_room_pct": 0.12,
                "adr_pct": 0.035,
            },
        },
        "trade_plan": {"symbol": symbol, "trade_type": "BUY_SHARES"},
        "outcome": {
            "realized": realized,
            "realized_r_multiple": r_value,
            "realized_pnl": r_value * 100 if isinstance(r_value, (int, float)) else None,
        },
    }


def _summary(values):
    records = [_record(value, index=index) for index, value in enumerate(values)]
    return next(iter(calibrate_setup_evidence(records).values()))


def test_adaptive_edge_estimator_returns_prior_when_setup_evidence_missing():
    estimate = AdaptiveEdgeEstimator().estimate(_prior(), None)

    assert estimate.source == "adaptive_prior_only"
    assert estimate.p_win == pytest.approx(0.55)
    assert estimate.expected_r == pytest.approx(_prior().expected_r)
    assert estimate.prior_weight == pytest.approx(1.0)
    assert estimate.evidence_weight == pytest.approx(0.0)
    assert estimate.sample_size == 0
    assert "setup evidence unavailable" in estimate.reasons[-1]


def test_adaptive_edge_estimator_keeps_sparse_evidence_low_weight():
    evidence = _summary([1.0] * 5 + [-0.5] * 4)

    estimate = AdaptiveEdgeEstimator().estimate(_prior(), evidence)

    assert evidence.state == SETUP_STATE_INSUFFICIENT_EVIDENCE
    assert estimate.source == "adaptive_evidence_blend"
    assert estimate.setup_id == evidence.setup_id
    assert estimate.sample_size == 9
    assert estimate.evidence_weight < 0.20
    assert estimate.prior_weight > 0.80
    assert estimate.expected_r == pytest.approx(_prior().expected_r, abs=0.10)


def test_adaptive_edge_estimator_lets_mature_evidence_dominate():
    evidence = _summary([1.0, 1.0, 1.0, -0.4, -0.4] * 24)

    estimate = AdaptiveEdgeEstimator().estimate(_prior(), evidence)

    assert evidence.state == SETUP_STATE_LIVE_ELIGIBLE
    assert estimate.evidence_weight == pytest.approx(0.85)
    assert estimate.prior_weight == pytest.approx(0.15)
    assert estimate.p_win == pytest.approx(
        (_prior().p_win * 0.15) + (evidence.posterior_win_rate * 0.85)
    )
    assert estimate.expected_r > _prior().expected_r
    assert estimate.confidence > _prior().confidence
    data = estimate.to_dict()
    assert data["setup_id"] == evidence.setup_id
    assert data["sample_size"] == 120
    assert data["setup_state"] == SETUP_STATE_LIVE_ELIGIBLE


def test_adaptive_edge_estimator_uses_negative_evidence_to_reduce_edge():
    evidence = _summary([-0.5] * 35)

    estimate = AdaptiveEdgeEstimator().estimate(_prior(), evidence)

    assert evidence.state == SETUP_STATE_RETIRED
    assert estimate.evidence_weight >= 0.75
    assert estimate.expected_r < 0.0
    assert estimate.setup_state == SETUP_STATE_RETIRED
    assert any("state=RETIRED" in reason for reason in estimate.reasons)


def test_adaptive_edge_estimator_uses_positive_loss_magnitude_convention():
    evidence = _summary([1.0, 1.0, 1.0, -0.4, -0.4] * 24)

    estimate = AdaptiveEdgeEstimator().estimate(_prior(), evidence)

    assert evidence.posterior_avg_loss_r < 0.0
    assert estimate.avg_loss_r > 0.0
    assert estimate.expected_r == pytest.approx(
        (estimate.p_win * estimate.avg_win_r)
        - ((1.0 - estimate.p_win) * estimate.avg_loss_r)
    )
