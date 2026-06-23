import pytest

from autonomous.evidence_aware_sizer import (
    EVIDENCE_SIZE_NORMAL_CAPPED,
    EVIDENCE_SIZE_NO_TRADE,
    EVIDENCE_SIZE_PAPER_ONLY,
    EVIDENCE_SIZE_REDUCED_SIZE,
    EVIDENCE_SIZE_RETIRED,
    EVIDENCE_SIZE_TINY_LIVE,
    EvidenceAwareSizer,
    EvidenceAwareSizingConfig,
)


def _sizer(**kwargs):
    return EvidenceAwareSizer(EvidenceAwareSizingConfig(enabled=True, **kwargs))


def _eligibility(**kwargs):
    data = {
        "action": "ALLOW",
        "setup_id": "AAA:rebound:v1",
        "setup_state": "LIVE_ELIGIBLE",
        "sample_size": 120,
        "expected_r": 0.35,
        "confidence": 0.80,
        "diagnostics": {
            "rolling_sharpe": 1.4,
            "max_drawdown_r": 3.0,
        },
    }
    data.update(kwargs)
    return data


def test_evidence_aware_sizer_disabled_is_diagnostic_only():
    decision = EvidenceAwareSizer().evaluate(
        equity=100_000.0,
        current_cap_value=10_000.0,
        edge_estimate={"expected_r": 0.40, "confidence": 0.90},
        observed_trades=120,
    )

    assert decision.enabled is False
    assert decision.applied is False
    assert decision.cap_value is None


def test_evidence_aware_sizer_retires_rejected_setup():
    decision = _sizer().evaluate(
        equity=100_000.0,
        current_cap_value=10_000.0,
        setup_eligibility=_eligibility(action="REJECT", setup_state="RETIRED"),
    )

    assert decision.applied is True
    assert decision.state == EVIDENCE_SIZE_RETIRED
    assert decision.cap_value == 0.0


def test_evidence_aware_sizer_keeps_small_samples_paper_only():
    decision = _sizer(min_trades_for_tiny_live=20, min_trades_for_normal=100).evaluate(
        equity=100_000.0,
        current_cap_value=10_000.0,
        setup_eligibility=_eligibility(setup_state="INSUFFICIENT_EVIDENCE", sample_size=8),
    )

    assert decision.applied is True
    assert decision.state == EVIDENCE_SIZE_PAPER_ONLY
    assert decision.cap_value == 0.0


def test_evidence_aware_sizer_limits_immature_evidence_to_tiny_cap():
    decision = _sizer(
        min_trades_for_tiny_live=20,
        min_trades_for_normal=100,
        tiny_live_max_position_pct=0.001,
    ).evaluate(
        equity=100_000.0,
        current_cap_value=10_000.0,
        setup_eligibility=_eligibility(setup_state="INSUFFICIENT_EVIDENCE", sample_size=30),
    )

    assert decision.applied is True
    assert decision.state == EVIDENCE_SIZE_TINY_LIVE
    assert decision.cap_value == pytest.approx(100.0)


def test_evidence_aware_sizer_never_widens_existing_cap_for_tiny_state():
    decision = _sizer(
        min_trades_for_tiny_live=20,
        min_trades_for_normal=100,
        tiny_live_max_position_pct=0.01,
    ).evaluate(
        equity=100_000.0,
        current_cap_value=50.0,
        setup_eligibility=_eligibility(setup_state="PAPER_ONLY", sample_size=30),
    )

    assert decision.state == EVIDENCE_SIZE_TINY_LIVE
    assert decision.cap_value == pytest.approx(50.0)


def test_evidence_aware_sizer_reduces_weak_mature_evidence():
    decision = _sizer(reduced_size_multiplier=0.25).evaluate(
        equity=100_000.0,
        current_cap_value=10_000.0,
        setup_eligibility=_eligibility(confidence=0.40),
    )

    assert decision.applied is True
    assert decision.state == EVIDENCE_SIZE_REDUCED_SIZE
    assert decision.cap_value == pytest.approx(2_500.0)


def test_evidence_aware_sizer_blocks_non_positive_expected_r():
    decision = _sizer().evaluate(
        equity=100_000.0,
        current_cap_value=10_000.0,
        setup_eligibility=_eligibility(sample_size=120, expected_r=0.0),
    )

    assert decision.state == EVIDENCE_SIZE_NO_TRADE
    assert decision.cap_value == 0.0


def test_evidence_aware_sizer_holds_normal_capped_strong_evidence():
    decision = _sizer().evaluate(
        equity=100_000.0,
        current_cap_value=10_000.0,
        setup_eligibility=_eligibility(),
    )

    assert decision.applied is False
    assert decision.state == EVIDENCE_SIZE_NORMAL_CAPPED
    assert decision.cap_value is None
    assert decision.evidence_score > 0


def test_evidence_aware_sizer_does_not_reduce_for_drawdown_below_governor_floor():
    decision = _sizer().evaluate(
        equity=100_000.0,
        current_cap_value=10_000.0,
        setup_eligibility=_eligibility(),
        strategy_drawdown_pct=0.01,
    )

    assert decision.applied is False
    assert decision.state == EVIDENCE_SIZE_NORMAL_CAPPED
