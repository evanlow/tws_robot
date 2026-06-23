import pytest

from autonomous.autonomous_config import AutonomousTradingConfig
from autonomous.candidate_scanner import CandidateSignal
from autonomous.evidence_aware_sizer import (
    EVIDENCE_SIZE_NORMAL_CAPPED,
    EVIDENCE_SIZE_REDUCED_SIZE,
    EVIDENCE_SIZE_RETIRED,
)
from autonomous.trade_planner import TradePlanner


def _candidate(**kwargs):
    extras = {
        "edge_observed_trades": 120,
        "edge_estimate": {
            "expected_r": 0.35,
            "confidence": 0.80,
            "sample_size": 120,
            "rolling_sharpe": 1.2,
            "max_drawdown_r": 3.0,
        },
        "setup_eligibility": {
            "action": "ALLOW",
            "setup_id": "AAA:rebound:v1",
            "setup_state": "LIVE_ELIGIBLE",
            "sample_size": 120,
            "expected_r": 0.35,
            "confidence": 0.80,
            "diagnostics": {
                "rolling_sharpe": 1.2,
                "max_drawdown_r": 3.0,
            },
        },
    }
    data = {
        "symbol": "AAA",
        "strength_score": 100,
        "signal_label": "Confirmed Rebound",
        "last_price": 100.0,
        "support_price": 95.0,
        "resistance_price": 115.0,
        "extras": extras,
    }
    data.update(kwargs)
    return CandidateSignal(**data)


def _config(**kwargs):
    data = {
        "risk_per_trade_sizing_enabled": False,
        "volatility_sizing_enabled": False,
        "drawdown_governor_enabled": False,
        "evidence_aware_sizing_enabled": True,
        "max_new_position_pct": 0.10,
    }
    data.update(kwargs)
    return AutonomousTradingConfig(**data)


def test_trade_planner_evidence_sizing_blocks_rejected_setup():
    cfg = _config()
    planner = TradePlanner(cfg)
    reasons = []
    candidate = _candidate(
        extras={
            "edge_observed_trades": 120,
            "setup_eligibility": {
                "action": "REJECT",
                "setup_state": "RETIRED",
                "sample_size": 120,
                "expected_r": -0.20,
                "confidence": 0.90,
                "diagnostics": {"max_drawdown_r": 12.5},
            },
        }
    )

    plan = planner.plan(candidate, deployable_cash=100_000.0, equity=100_000.0, reasons=reasons)

    assert plan is None
    assert any("binding_cap=evidence_aware_cap" in reason for reason in reasons)


def test_trade_planner_evidence_sizing_reduces_low_confidence_setup():
    cfg = _config(evidence_aware_reduced_size_multiplier=0.25)
    planner = TradePlanner(cfg)
    candidate = _candidate()
    candidate.extras["setup_eligibility"]["confidence"] = 0.40

    plan = planner.plan(candidate, deployable_cash=100_000.0, equity=100_000.0)

    assert plan is not None
    assert plan.quantity == 25
    assert plan.sizing["binding_cap"] == "evidence_aware_cap"
    assert plan.sizing["caps"]["evidence_aware"]["state"] == EVIDENCE_SIZE_REDUCED_SIZE


def test_trade_planner_evidence_sizing_keeps_strong_evidence_hard_capped():
    cfg = _config()
    planner = TradePlanner(cfg)

    plan = planner.plan(_candidate(), deployable_cash=100_000.0, equity=100_000.0)

    assert plan is not None
    assert plan.quantity == 100
    assert plan.sizing["binding_cap"] == "cash_equity_cap"
    assert plan.sizing["caps"]["evidence_aware"]["state"] == EVIDENCE_SIZE_NORMAL_CAPPED
    assert plan.sizing["caps"]["evidence_aware"]["applied"] is False


def test_trade_planner_records_evidence_state_in_risk_notes():
    cfg = _config()
    planner = TradePlanner(cfg)
    candidate = _candidate()
    candidate.extras["setup_eligibility"]["action"] = "REJECT"
    candidate.extras["setup_eligibility"]["setup_state"] = "RETIRED"

    plan = planner.plan(candidate, deployable_cash=100_000.0, equity=100_000.0)

    assert plan is None
    sizing = planner.sizer.size_buy_shares(
        symbol="AAA",
        entry_price=100.0,
        stop_price=95.0,
        base_cap_value=10_000.0,
        equity=100_000.0,
        setup_eligibility=candidate.extras["setup_eligibility"],
    )
    assert sizing.caps["evidence_aware"]["state"] == EVIDENCE_SIZE_RETIRED
    assert any("evidence_aware" in note for note in sizing.notes)


def test_config_rejects_invalid_evidence_sizing_thresholds():
    with pytest.raises(ValueError, match="evidence_aware_min_trades_for_normal"):
        AutonomousTradingConfig(
            evidence_aware_min_trades_for_tiny_live=20,
            evidence_aware_min_trades_for_normal=10,
        )
