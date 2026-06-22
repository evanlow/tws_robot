from datetime import datetime, timedelta, timezone

import pytest

from autonomous.evidence_calibrator import (
    SETUP_STATE_INSUFFICIENT_EVIDENCE,
    SETUP_STATE_LIVE_ELIGIBLE,
    SETUP_STATE_PAPER_ONLY,
    SETUP_STATE_RETIRED,
    SETUP_STATE_STRONG,
    EvidenceCalibrator,
    calibrate_setup_evidence,
)


BASE = datetime(2026, 6, 22, 12, 0, tzinfo=timezone.utc)


def _record(
    r_value,
    *,
    index=0,
    symbol="AAA",
    signal="Confirmed Rebound",
    support_distance_pct=0.02,
    realized=True,
):
    return {
        "schema_version": 3,
        "evidence_type": "autonomous_outcome",
        "timestamp": (BASE + timedelta(minutes=index)).isoformat(),
        "symbol": symbol,
        "strategy_bucket": {
            "signal_label": signal,
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
                "support_distance_pct": support_distance_pct,
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


def _series(values, **kwargs):
    return [_record(value, index=index, **kwargs) for index, value in enumerate(values)]


def test_evidence_calibrator_groups_realized_records_by_setup_id():
    records = (
        _series([1.0] * 12 + [-0.5] * 8 + [0.25] * 5, symbol="AAA")
        + _series([2.0] * 30, symbol="BBB", signal="VWAP Reclaim", support_distance_pct=0.12)
        + [_record(5.0, index=200, symbol="CCC", realized=False)]
    )

    summaries = calibrate_setup_evidence(records)

    assert len(summaries) == 2
    sample_sizes = sorted(summary.sample_size for summary in summaries.values())
    assert sample_sizes == [25, 30]
    first = [summary for summary in summaries.values() if summary.sample_size == 25][0]
    assert first.metrics.trade_count == 25
    assert first.setup_metadata.observation_count == 25
    assert first.setup_metadata.symbols == ["AAA"]


def test_evidence_calibrator_marks_sparse_samples_insufficient():
    summaries = calibrate_setup_evidence(_series([1.0] * 5 + [-0.5] * 4))

    summary = next(iter(summaries.values()))

    assert summary.state == SETUP_STATE_INSUFFICIENT_EVIDENCE
    assert summary.sample_size == 9
    assert summary.evidence_weight < 0.5
    assert summary.confidence < 0.6
    assert "below minimum" in summary.reasons[0]


def test_evidence_calibrator_applies_shrinkage_before_strong_classification():
    records = _series(([1.0, 1.0, 1.0, -0.4, -0.4] * 12))

    summary = next(iter(EvidenceCalibrator().summarize(records).values()))

    assert summary.state == SETUP_STATE_STRONG
    assert summary.metrics.expected_r == pytest.approx(0.44)
    assert summary.posterior_expected_r < summary.metrics.expected_r
    assert summary.posterior_expected_r > 0.20
    assert summary.prior_weight > 0.0


def test_evidence_calibrator_classifies_large_high_quality_sample_live_eligible():
    records = _series(([1.0, 1.0, 1.0, -0.4, -0.4] * 24))

    summary = next(iter(calibrate_setup_evidence(records).values()))

    assert summary.state == SETUP_STATE_LIVE_ELIGIBLE
    assert summary.sample_size == 120
    assert summary.confidence > 0.75
    assert summary.posterior_win_rate == pytest.approx((72 + 10) / 140)


def test_evidence_calibrator_keeps_low_positive_edge_paper_only():
    records = _series(([0.30, -0.25] * 14) + [0.30, 0.30])

    summary = next(iter(calibrate_setup_evidence(records).values()))

    assert summary.state == SETUP_STATE_PAPER_ONLY
    assert summary.posterior_expected_r > 0.0
    assert summary.posterior_expected_r < 0.05


def test_evidence_calibrator_retires_sufficient_negative_evidence():
    records = _series([-0.5] * 35)

    summary = next(iter(calibrate_setup_evidence(records).values()))

    assert summary.state == SETUP_STATE_RETIRED
    assert summary.metrics.trade_count == 35
    assert summary.posterior_expected_r < 0.0
    assert any("retired" in reason for reason in summary.reasons)


def test_evidence_calibrator_serializes_summary_safely():
    summary = next(iter(calibrate_setup_evidence(_series([1.0, 1.0, 1.0, -0.4, -0.4] * 24)).values()))

    data = summary.to_dict()

    assert data["setup_id"] == summary.setup_id
    assert data["state"] == SETUP_STATE_LIVE_ELIGIBLE
    assert data["sample_size"] == 120
    assert data["metrics"]["trade_count"] == 120
    assert data["setup_metadata"]["setup_id"] == summary.setup_id
    assert data["reasons"]
