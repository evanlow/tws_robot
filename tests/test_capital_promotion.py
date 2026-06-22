from datetime import datetime, timedelta, timezone

from autonomous.capital_promotion import (
    PROMOTION_APPROVE,
    PROMOTION_DEMOTE,
    PROMOTION_HOLD,
    CapitalPromotionEvaluator,
    CapitalPromotionThresholds,
)


NOW = datetime(2026, 6, 22, 12, 0, tzinfo=timezone.utc)


def _thresholds(**overrides):
    base = {
        "min_trades_by_level": {1: 2, 2: 5, 3: 6, 4: 8, 5: 10, 6: 12},
        "min_live_trades_by_level": {4: 2, 5: 4, 6: 6},
        "min_avg_r": 0.05,
        "min_expected_r": 0.05,
        "min_win_rate": 0.40,
        "min_profit_factor": 1.10,
        "max_drawdown_r": 2.5,
        "demotion_drawdown_r": 2.5,
        "max_avg_slippage_bps": 20.0,
        "max_partial_fill_rate": 0.25,
        "stale_after_days": 30,
        "consistency_min_trades": 2,
        "max_paper_live_avg_r_delta": 0.40,
        "min_live_avg_r": 0.0,
    }
    base.update(overrides)
    return CapitalPromotionThresholds(**base)


def _outcome(r_value, *, days_ago=0, mode="paper", slippage_pct=0.0005, partial=False):
    when = NOW - timedelta(days=days_ago)
    return {
        "schema_version": 3,
        "evidence_type": "autonomous_outcome",
        "timestamp": when.isoformat(),
        "mode": mode,
        "symbol": "AAA",
        "outcome": {
            "realized": True,
            "realized_r_multiple": r_value,
            "realized_pnl": r_value * 100,
            "entry_slippage_pct": slippage_pct,
            "partial_fill": partial,
        },
    }


def test_capital_promotion_recommends_one_level_with_operator_approval():
    records = [
        _outcome(1.0),
        _outcome(0.7),
        _outcome(-0.2),
        _outcome(0.5),
        _outcome(0.3),
    ]
    evaluator = CapitalPromotionEvaluator(_thresholds())

    report = evaluator.evaluate(records, current_level=1, now=NOW)

    assert report.action == PROMOTION_APPROVE
    assert report.current_level == 1
    assert report.recommended_level == 2
    assert report.operator_approval_required is True
    assert report.automatic_capital_scaling_allowed is False
    assert report.metrics.completed_trade_count == 5
    assert report.metrics.avg_slippage_bps == 5.0


def test_capital_promotion_holds_when_trade_sample_is_too_small():
    evaluator = CapitalPromotionEvaluator(_thresholds())

    report = evaluator.evaluate([_outcome(1.0), _outcome(0.5)], current_level=1, now=NOW)

    assert report.action == PROMOTION_HOLD
    assert report.recommended_level == 1
    assert any("completed_trade_count" in reason for reason in report.rejection_reasons)


def test_capital_promotion_demotes_after_drawdown_breach():
    records = [_outcome(2.0), _outcome(-1.0), _outcome(-1.0), _outcome(-1.0)]
    evaluator = CapitalPromotionEvaluator(_thresholds(demotion_drawdown_r=2.0))

    report = evaluator.evaluate(records, current_level=3, now=NOW)

    assert report.action == PROMOTION_DEMOTE
    assert report.recommended_level == 2
    assert any("max_drawdown_r" in reason for reason in report.demotion_reasons)


def test_capital_promotion_demotes_after_fault_or_stale_evidence():
    evaluator = CapitalPromotionEvaluator(_thresholds(stale_after_days=10))

    stale_report = evaluator.evaluate([_outcome(1.0, days_ago=20)], current_level=2, now=NOW)
    fault_report = evaluator.evaluate(
        [_outcome(1.0)],
        current_level=2,
        operational_events=[{"severity": "fault", "message": "supervisor paused"}],
        now=NOW,
    )

    assert stale_report.action == PROMOTION_DEMOTE
    assert any("stale limit" in reason for reason in stale_report.demotion_reasons)
    assert fault_report.action == PROMOTION_DEMOTE
    assert any("operational_incidents" in reason for reason in fault_report.demotion_reasons)


def test_capital_promotion_blocks_live_level_on_paper_live_inconsistency():
    records = [
        _outcome(1.0, mode="paper"),
        _outcome(0.9, mode="paper"),
        _outcome(0.8, mode="paper"),
        _outcome(0.7, mode="paper"),
        _outcome(0.6, mode="paper"),
        _outcome(0.5, mode="paper"),
        _outcome(-0.4, mode="live"),
        _outcome(-0.3, mode="live"),
    ]
    evaluator = CapitalPromotionEvaluator(_thresholds(min_avg_r=0.0, min_expected_r=0.0))

    report = evaluator.evaluate(records, current_level=3, now=NOW)

    assert report.action == PROMOTION_HOLD
    assert report.recommended_level == 3
    assert report.metrics.paper_live_consistency.evaluated is True
    assert report.metrics.paper_live_consistency.consistent is False
    assert any("paper/live consistency" in reason for reason in report.rejection_reasons)


def test_capital_promotion_report_serializes_required_safety_flags():
    evaluator = CapitalPromotionEvaluator(_thresholds())

    data = evaluator.evaluate([_outcome(1.0), _outcome(0.5)], now=NOW).to_dict()

    assert data["operator_approval_required"] is True
    assert data["automatic_capital_scaling_allowed"] is False
    assert data["metrics"]["completed_trade_count"] == 2
    assert data["metrics"]["profit_factor"] is None
    assert data["metrics"]["profit_factor_unbounded"] is True
    assert "paper_live_consistency" in data["metrics"]
