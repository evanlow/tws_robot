"""Tests for ORB Phase 4 tiny-live / assisted-live readiness gates (#213).

Covers pass/fail evidence thresholds, missing protection, account
mismatch, live disabled, and emergency stop, plus the audit trail
written for every readiness evaluation. Never places an order.
"""

import json

import pytest

from autonomous.audit import AuditLogger
from autonomous.orb_live_readiness import (
    ASSISTED_LIVE_CANDIDATE,
    ASSISTED_LIVE_MODE,
    LOCKED,
    TINY_LIVE_CANDIDATE,
    TINY_LIVE_CANDIDATE_MODE,
    ORBLiveReadinessCriteria,
    ORBLiveReadinessInput,
    TinyLiveRiskCaps,
    compute_r_stats,
    evaluate_orb_live_readiness,
    log_operator_decision,
)


@pytest.fixture
def audit(tmp_path):
    return AuditLogger(str(tmp_path))


def _strategy_config(**overrides):
    cfg = {
        "name": "ORB1",
        "symbols": ["QQQ"],
        "require_stop": True,
        "require_target": True,
        "require_bracket": True,
        "parameters": {
            "short_enabled": False,
            "model_c_enabled": False,
            "max_total_orb_trades_per_session": 3,
        },
    }
    cfg.update(overrides)
    return cfg


def _good_paper_summary(**overrides):
    summary = {
        "total_trades": 60,
        "closed_trades": 60,
        "failed_trades": 0,
        "avg_realized_r": 0.3,
    }
    summary.update(overrides)
    return summary


def _fully_ready_input(**overrides) -> ORBLiveReadinessInput:
    data = ORBLiveReadinessInput(
        strategy_name="ORB1",
        strategy_config=_strategy_config(),
        paper_summary=_good_paper_summary(),
        requested_mode=TINY_LIVE_CANDIDATE_MODE,
        max_drawdown_r=1.0,
        max_consecutive_losses=2,
        avg_entry_slippage_bps=5.0,
        unresolved_protection_failures=0,
        data_quality_failures=0,
        emergency_stop_incidents_from_orb=0,
        market_data_provider_healthy=True,
        market_data_source="ibkr",
        broker_connected=True,
        broker_account_id="DU12345",
        expected_account_id="DU12345",
        live_master_switch_enabled=True,
        emergency_stop_available=True,
        emergency_stop_tested=True,
        operator_confirmed_account=True,
        operator_confirmed_mode=True,
        paper_max_trades_per_session=3,
    )
    for k, v in overrides.items():
        setattr(data, k, v)
    return data


# ---------------------------------------------------------------------------
# compute_r_stats
# ---------------------------------------------------------------------------

def test_compute_r_stats_empty():
    assert compute_r_stats([]) == {"max_drawdown_r": 0.0, "max_consecutive_losses": 0}


def test_compute_r_stats_drawdown_and_streak():
    # peak reaches 2.0 after two wins, drawdown to -1.0 (peak - running = 3.0)
    values = [1.0, 1.0, -1.0, -1.0, -1.0, 0.5]
    stats = compute_r_stats(values)
    assert stats["max_drawdown_r"] == 3.0
    assert stats["max_consecutive_losses"] == 3


def test_compute_r_stats_ignores_none():
    assert compute_r_stats([1.0, None, -0.5])["max_consecutive_losses"] == 1


# ---------------------------------------------------------------------------
# Full pass
# ---------------------------------------------------------------------------

def test_fully_ready_tiny_live_candidate(tmp_path, audit):
    result = evaluate_orb_live_readiness(_fully_ready_input(), audit=audit)
    assert result["overall_status"] == TINY_LIVE_CANDIDATE
    assert not result["live_trading_locked"]
    assert result["failing_gates"] == []
    assert result["paper_evidence_status"] == "TINY_LIVE_CANDIDATE"

    # Audit log written.
    files = list(tmp_path.glob("autonomous_trading_*.jsonl"))
    assert files
    lines = files[0].read_text().splitlines()
    records = [json.loads(l) for l in lines]
    assert any(r["kind"] == "orb_live_readiness" and r["action"] == "evaluate" for r in records)


def test_assisted_live_candidate_requires_session_confirmation(audit):
    data = _fully_ready_input(requested_mode=ASSISTED_LIVE_MODE)
    result = evaluate_orb_live_readiness(data, audit=audit)
    assert result["overall_status"] == ASSISTED_LIVE_CANDIDATE

    # Without an expected_account_id, assisted-live must lock even though every
    # other gate passes.
    data2 = _fully_ready_input(requested_mode=ASSISTED_LIVE_MODE, expected_account_id=None)
    result2 = evaluate_orb_live_readiness(data2, audit=audit)
    assert result2["overall_status"] == LOCKED
    assert "assisted_live_session_confirmed" in result2["failing_gates"]


def test_tiny_live_does_not_require_expected_account_id(audit):
    # Unlike assisted-live, tiny-live candidacy does not require an explicit
    # expected_account_id session confirmation (just a connected/confirmed
    # broker account).
    data = _fully_ready_input(requested_mode=TINY_LIVE_CANDIDATE_MODE, expected_account_id=None)
    result = evaluate_orb_live_readiness(data, audit=audit)
    assert result["overall_status"] == TINY_LIVE_CANDIDATE
    assert result["failing_gates"] == []


# ---------------------------------------------------------------------------
# Individual gate failures -> LOCKED
# ---------------------------------------------------------------------------

def test_live_master_switch_disabled_locks(audit):
    data = _fully_ready_input(live_master_switch_enabled=False)
    result = evaluate_orb_live_readiness(data, audit=audit)
    assert result["overall_status"] == LOCKED
    assert "live_master_switch_enabled" in result["failing_gates"]


def test_emergency_stop_not_available_locks(audit):
    data = _fully_ready_input(emergency_stop_available=False)
    result = evaluate_orb_live_readiness(data, audit=audit)
    assert result["overall_status"] == LOCKED
    assert "emergency_stop_tested_available" in result["failing_gates"]


def test_emergency_stop_not_tested_locks(audit):
    data = _fully_ready_input(emergency_stop_tested=False)
    result = evaluate_orb_live_readiness(data, audit=audit)
    assert result["overall_status"] == LOCKED
    assert "emergency_stop_tested_available" in result["failing_gates"]


def test_emergency_stop_currently_active_locks(audit):
    data = _fully_ready_input(emergency_stop_currently_active=True)
    result = evaluate_orb_live_readiness(data, audit=audit)
    assert result["overall_status"] == LOCKED
    assert "emergency_stop_not_currently_active" in result["failing_gates"]


def test_account_mismatch_locks(audit):
    data = _fully_ready_input(broker_account_id="DU99999")
    result = evaluate_orb_live_readiness(data, audit=audit)
    assert result["overall_status"] == LOCKED
    assert "broker_connection_confirmed" in result["failing_gates"]


def test_broker_not_connected_locks(audit):
    data = _fully_ready_input(broker_connected=False)
    result = evaluate_orb_live_readiness(data, audit=audit)
    assert result["overall_status"] == LOCKED
    assert "broker_connection_confirmed" in result["failing_gates"]


def test_missing_protection_locks(audit):
    data = _fully_ready_input(
        strategy_config=_strategy_config(require_bracket=False),
    )
    result = evaluate_orb_live_readiness(data, audit=audit)
    assert result["overall_status"] == LOCKED
    assert "protection_mandatory" in result["failing_gates"]


def test_unresolved_protection_failures_locks(audit):
    data = _fully_ready_input(unresolved_protection_failures=2)
    result = evaluate_orb_live_readiness(data, audit=audit)
    assert result["overall_status"] == LOCKED
    assert "no_unresolved_protection_failures" in result["failing_gates"]


def test_data_quality_failures_locks(audit):
    data = _fully_ready_input(data_quality_failures=1)
    result = evaluate_orb_live_readiness(data, audit=audit)
    assert result["overall_status"] == LOCKED
    assert "no_repeated_data_quality_failures" in result["failing_gates"]


def test_emergency_stop_incidents_from_orb_locks(audit):
    data = _fully_ready_input(emergency_stop_incidents_from_orb=1)
    result = evaluate_orb_live_readiness(data, audit=audit)
    assert result["overall_status"] == LOCKED
    assert "no_emergency_stop_incidents" in result["failing_gates"]


def test_market_data_source_not_acceptable_locks(audit):
    data = _fully_ready_input(market_data_source="yahoo")
    result = evaluate_orb_live_readiness(data, audit=audit)
    assert result["overall_status"] == LOCKED
    assert "market_data_source_acceptable" in result["failing_gates"]


def test_market_data_unhealthy_locks(audit):
    data = _fully_ready_input(market_data_provider_healthy=False)
    result = evaluate_orb_live_readiness(data, audit=audit)
    assert result["overall_status"] == LOCKED
    assert "data_provider_healthy" in result["failing_gates"]


def test_operator_confirmation_missing_locks(audit):
    data = _fully_ready_input(operator_confirmed_account=False)
    result = evaluate_orb_live_readiness(data, audit=audit)
    assert result["overall_status"] == LOCKED
    assert "operator_confirmation" in result["failing_gates"]

    data2 = _fully_ready_input(operator_confirmed_mode=False)
    result2 = evaluate_orb_live_readiness(data2, audit=audit)
    assert result2["overall_status"] == LOCKED
    assert "operator_confirmation" in result2["failing_gates"]


def test_short_enabled_locks(audit):
    cfg = _strategy_config()
    cfg["parameters"]["short_enabled"] = True
    data = _fully_ready_input(strategy_config=cfg)
    result = evaluate_orb_live_readiness(data, audit=audit)
    assert result["overall_status"] == LOCKED
    assert "long_only" in result["failing_gates"]


def test_model_c_enabled_locks(audit):
    cfg = _strategy_config()
    cfg["parameters"]["model_c_enabled"] = True
    data = _fully_ready_input(strategy_config=cfg)
    result = evaluate_orb_live_readiness(data, audit=audit)
    assert result["overall_status"] == LOCKED
    assert "model_c_disabled" in result["failing_gates"]


def test_unsupported_mode_locks(audit):
    data = _fully_ready_input(requested_mode="full_live")
    result = evaluate_orb_live_readiness(data, audit=audit)
    assert result["overall_status"] == LOCKED
    assert "requested_mode_supported" in result["failing_gates"]


def test_config_missing_locks(audit):
    data = _fully_ready_input(strategy_config={})
    result = evaluate_orb_live_readiness(data, audit=audit)
    assert result["overall_status"] == LOCKED
    assert "config_valid_and_persisted" in result["failing_gates"]


# ---------------------------------------------------------------------------
# Evidence thresholds
# ---------------------------------------------------------------------------

def test_insufficient_paper_trades_locks(audit):
    data = _fully_ready_input(paper_summary=_good_paper_summary(closed_trades=5, total_trades=5))
    result = evaluate_orb_live_readiness(data, audit=audit)
    assert result["overall_status"] == LOCKED
    assert "paper_evidence_meets_thresholds" in result["failing_gates"]
    assert result["paper_evidence_status"] == "NEEDS_MORE_DATA"


def test_negative_avg_r_locks(audit):
    data = _fully_ready_input(paper_summary=_good_paper_summary(avg_realized_r=-0.2))
    result = evaluate_orb_live_readiness(data, audit=audit)
    assert result["overall_status"] == LOCKED
    assert "paper_evidence_meets_thresholds" in result["failing_gates"]
    assert result["paper_evidence_status"] == "DO_NOT_TRADE"


def test_excess_drawdown_locks(audit):
    data = _fully_ready_input(max_drawdown_r=999.0)
    result = evaluate_orb_live_readiness(data, audit=audit)
    assert result["overall_status"] == LOCKED
    assert "paper_evidence_meets_thresholds" in result["failing_gates"]


def test_excess_consecutive_losses_locks(audit):
    data = _fully_ready_input(max_consecutive_losses=999)
    result = evaluate_orb_live_readiness(data, audit=audit)
    assert result["overall_status"] == LOCKED
    assert "paper_evidence_meets_thresholds" in result["failing_gates"]


def test_excess_entry_slippage_locks(audit):
    data = _fully_ready_input(avg_entry_slippage_bps=999.0)
    result = evaluate_orb_live_readiness(data, audit=audit)
    assert result["overall_status"] == LOCKED
    assert "paper_evidence_meets_thresholds" in result["failing_gates"]


def test_custom_criteria_applied(audit):
    criteria = ORBLiveReadinessCriteria(
        min_paper_trades_diagnostic=5, min_paper_trades_tiny_live=5, min_avg_r_after_costs=0.05,
    )
    data = _fully_ready_input(paper_summary=_good_paper_summary(closed_trades=5, total_trades=5, avg_realized_r=0.06))
    result = evaluate_orb_live_readiness(data, criteria=criteria, audit=audit)
    assert result["overall_status"] == TINY_LIVE_CANDIDATE


# ---------------------------------------------------------------------------
# Tiny-live caps must be stricter than paper caps
# ---------------------------------------------------------------------------

def test_tiny_live_caps_too_large_locks(audit):
    data = _fully_ready_input(
        tiny_live_caps=TinyLiveRiskCaps(max_deployable_cash_pct=0.05, max_live_orb_trades_per_day=1),
    )
    result = evaluate_orb_live_readiness(data, audit=audit)
    assert result["overall_status"] == LOCKED
    assert "tiny_live_caps_valid" in result["failing_gates"]


def test_tiny_live_trades_per_day_exceeds_default_locks(audit):
    data = _fully_ready_input(
        tiny_live_caps=TinyLiveRiskCaps(max_deployable_cash_pct=0.005, max_live_orb_trades_per_day=2),
    )
    result = evaluate_orb_live_readiness(data, audit=audit)
    assert result["overall_status"] == LOCKED
    assert "tiny_live_caps_valid" in result["failing_gates"]


def test_tiny_live_trades_per_day_exceeds_paper_cap_locks(audit):
    data = _fully_ready_input(paper_max_trades_per_session=0)
    result = evaluate_orb_live_readiness(data, audit=audit)
    assert result["overall_status"] == LOCKED
    assert "tiny_live_caps_valid" in result["failing_gates"]


# ---------------------------------------------------------------------------
# Operator decision audit logging
# ---------------------------------------------------------------------------

def test_log_operator_decision_writes_audit(tmp_path, audit):
    log_operator_decision(
        "ORB1", "acknowledged", requested_mode=TINY_LIVE_CANDIDATE_MODE,
        operator="trader1", notes="reviewed evidence", audit=audit,
    )
    files = list(tmp_path.glob("autonomous_trading_*.jsonl"))
    assert files
    records = [json.loads(l) for l in files[0].read_text().splitlines()]
    decision_records = [r for r in records if r["action"] == "operator_decision"]
    assert decision_records
    assert decision_records[0]["decision"] == "acknowledged"
    assert decision_records[0]["operator"] == "trader1"
