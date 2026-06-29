"""Tests for ORB session manager (autonomous/orb_session_manager.py, #207)."""

import json

import pytest

from autonomous.orb_session_manager import (
    LOCKED_MODES,
    ORBMode,
    ORBSessionManager,
    ORBValidationError,
    validate_strategy,
)


def _ev_ready(tmp_path, symbols=("QQQ",)):
    p = tmp_path / "logs"
    p.mkdir(exist_ok=True)
    f = p / "orb_backtest_evidence_20260601.jsonl"
    f.write_text(json.dumps({
        "symbols": list(symbols),
        "readiness": {"status": "READY_FOR_PAPER"},
    }) + "\n", encoding="utf-8")


def _mgr(tmp_path):
    return ORBSessionManager(config_dir=str(tmp_path / "config"),
                             evidence_dir=str(tmp_path / "logs"))


def test_validate_requires_name_and_symbols():
    with pytest.raises(ORBValidationError):
        validate_strategy({"symbols": []})


def test_validate_rejects_unknown_param():
    with pytest.raises(ORBValidationError):
        validate_strategy({"name": "x", "symbols": ["QQQ"], "parameters": {"bogus": 1}})


def test_validate_model_c_and_short_locked_off():
    rec = validate_strategy({"name": "x", "symbols": ["QQQ"]})
    assert rec["parameters"]["model_c_enabled"] is False
    assert rec["parameters"]["short_enabled"] is False


def test_validate_cutoff_before_flat():
    with pytest.raises(ORBValidationError):
        validate_strategy({"name": "x", "symbols": ["QQQ"],
                           "parameters": {"entry_cutoff_time": "16:00", "force_flat_time": "15:55"}})


def test_persists_across_restart(tmp_path):
    m = _mgr(tmp_path)
    m.upsert_strategy({"name": "ORB1", "symbols": ["QQQ"]})
    m2 = _mgr(tmp_path)
    assert m2.get_strategy("ORB1") is not None


def test_live_modes_cannot_arm(tmp_path):
    m = _mgr(tmp_path)
    m.upsert_strategy({"name": "ORB1", "symbols": ["QQQ"], "mode": "tiny_live_candidate"})
    with pytest.raises(ORBValidationError):
        m.arm("ORB1")
    assert ORBMode.TINY_LIVE_CANDIDATE in LOCKED_MODES


def test_paper_arm_blocked_without_evidence(tmp_path):
    m = _mgr(tmp_path)
    m.upsert_strategy({"name": "ORB1", "symbols": ["QQQ"], "mode": "paper_autonomous"})
    with pytest.raises(ORBValidationError):
        m.arm("ORB1")


def test_paper_arm_ok_with_evidence(tmp_path):
    _ev_ready(tmp_path)
    m = _mgr(tmp_path)
    m.upsert_strategy({"name": "ORB1", "symbols": ["QQQ"], "mode": "paper_autonomous"})
    rec = m.arm("ORB1")
    assert rec["session"]["armed"] is True


def test_recommend_only_arms_with_missing_gates(tmp_path):
    m = _mgr(tmp_path)
    m.upsert_strategy({"name": "ORB1", "symbols": ["QQQ"], "mode": "recommend_only"})
    rec = m.arm("ORB1")
    assert rec["session"]["armed"] is True
    assert "paper_backtest_evidence" in rec["readiness"]["missing"]


def test_disarm_and_disable_today(tmp_path):
    m = _mgr(tmp_path)
    m.upsert_strategy({"name": "ORB1", "symbols": ["QQQ"], "mode": "recommend_only"})
    m.arm("ORB1")
    assert m.disarm("ORB1")["session"] == {}
    rec = m.disable_today("ORB1")
    assert rec["session"]["disabled_today"] is True


def test_emergency_stop_disarms_all(tmp_path):
    m = _mgr(tmp_path)
    m.upsert_strategy({"name": "ORB1", "symbols": ["QQQ"], "mode": "recommend_only"})
    m.arm("ORB1")
    m.emergency_stop()
    assert m.get_strategy("ORB1")["session"] == {}


def test_arm_audit_logged(tmp_path):
    m = _mgr(tmp_path)
    m.upsert_strategy({"name": "ORB1", "symbols": ["QQQ"], "mode": "recommend_only"})
    m.arm("ORB1")
    logs = list((tmp_path / "logs").glob("autonomous_trading_*.jsonl"))
    assert logs
    assert any("orb_session_control" in p.read_text() for p in logs)
