"""Tests for the ORB Phase 4 live-readiness API endpoint (#213).

Verifies the ``/api/orb/strategies/<name>/live-readiness`` endpoint (built
on ``autonomous.orb_live_readiness``) stays locked by default and only
reports a candidate status when every gate is explicitly satisfied. Never
places an order; never flips a live switch.
"""

import json

import pytest

import web.routes.api_opening_range as api
from web import create_app


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr("web.services.ServiceManager._start_market_events_refresh", lambda self: None)
    api._manager = None
    api._proposal_store = None
    api._executor = None
    api._exit_manager = None
    api._review_store = None
    app = create_app({
        "TESTING": True, "LOGIN_DISABLED": True, "WTF_CSRF_ENABLED": False,
        "orb_config_dir": str(tmp_path / "config"),
        "orb_evidence_dir": str(tmp_path / "logs"),
    })
    yield app.test_client()
    api._manager = None
    api._proposal_store = None
    api._executor = None
    api._exit_manager = None
    api._review_store = None


def _make(client, name="ORB1", symbols=None, mode="recommend_only"):
    return client.post("/api/orb/strategies", json={
        "name": name, "symbols": symbols or ["QQQ"], "mode": mode})


def test_unknown_strategy_404(client):
    res = client.get("/api/orb/strategies/NOPE/live-readiness")
    assert res.status_code == 404


def test_default_locked_no_paper_evidence(client):
    _make(client)
    res = client.get("/api/orb/strategies/ORB1/live-readiness")
    assert res.status_code == 200
    body = res.get_json()
    assert body["overall_status"] == "LOCKED"
    assert body["live_trading_locked"] is True
    # No connection, no live master switch, no operator confirmation, no
    # emergency-stop testing -> multiple gates fail by default.
    assert "live_master_switch_enabled" in body["failing_gates"]
    assert "operator_confirmation" in body["failing_gates"]
    assert "broker_connection_confirmed" in body["failing_gates"]


def test_readiness_audit_logged(client, tmp_path):
    _make(client)
    client.get("/api/orb/strategies/ORB1/live-readiness")
    log_files = list((tmp_path / "logs").glob("autonomous_trading_*.jsonl"))
    assert log_files
    records = [json.loads(l) for l in log_files[0].read_text().splitlines()]
    assert any(r.get("kind") == "orb_live_readiness" and r.get("action") == "evaluate" for r in records)


def test_query_params_do_not_bypass_broker_or_switch(client):
    _make(client)
    res = client.get(
        "/api/orb/strategies/ORB1/live-readiness",
        query_string={
            "confirm_account": "true",
            "confirm_mode": "true",
            "emergency_stop_tested": "true",
        },
    )
    body = res.get_json()
    # Operator confirmations alone never unlock live trading: master switch
    # and broker connection are still unmet in a bare test app.
    assert body["overall_status"] == "LOCKED"
    assert "live_master_switch_enabled" in body["failing_gates"]
    assert "broker_connection_confirmed" in body["failing_gates"]
