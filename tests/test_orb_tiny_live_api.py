"""Tests for the ORB Phase 6 human-confirmed tiny-live assisted execution
API (#229).

Verifies ``POST .../assisted-live/rehearsals/<id>/submit-tiny-live``,
``GET /api/orb/tiny-live/orders``, ``GET /api/orb/tiny-live/orders/<id>``,
and ``POST /api/orb/tiny-live/orders/<id>/cancel-if-pending`` stay locked by
default, re-check every safety gate immediately before submit, and only ever
call the narrow fake broker adapter once every gate has passed. Never calls a
real broker.
"""

from datetime import datetime, timezone

import pytest

import web.routes.api_opening_range as api
from autonomous.orb_live_order_adapter import FakeORBLiveOrderAdapter
from autonomous.orb_live_readiness import ASSISTED_LIVE_CANDIDATE, LOCKED
from web import create_app

ACCOUNT_ID = "DU12345"


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr("web.services.ServiceManager._start_market_events_refresh", lambda self: None)
    api._manager = None
    api._proposal_store = None
    api._executor = None
    api._exit_manager = None
    api._review_store = None
    api._live_readiness_confirmations = None
    api._assisted_live_rehearsals = None
    api._tiny_live_orders = None
    api._live_order_adapter = None
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
    api._live_readiness_confirmations = None
    api._assisted_live_rehearsals = None
    api._tiny_live_orders = None
    api._live_order_adapter = None


def _make(client, name="ORB1", symbols=None, mode="recommend_only"):
    return client.post("/api/orb/strategies", json={
        "name": name, "symbols": symbols or ["QQQ"], "mode": mode})


def _seed_proposal(symbol="QQQ", strategy="ORB1", session_date="2026-06-01"):
    from autonomous.opening_range import (
        BreakoutConfirmation,
        Candle,
        ORBDirection,
        ORBEntryModel,
        ORBSetup,
        OpeningRange,
    )
    from autonomous.orb_proposals import ProposalGates

    start = datetime(2026, 6, 1, 9, 45, tzinfo=timezone.utc)
    c5 = Candle(symbol, "5m", start, start, 103.0, 103.5, 102.8, 103.4, 1000.0)
    rng = OpeningRange(symbol, session_date, start, start, 102.0, 100.0, c5)
    conf = BreakoutConfirmation(symbol, ORBDirection.LONG, c5, 102.0, 100.0, start)
    setup = ORBSetup(
        symbol=symbol, direction=ORBDirection.LONG,
        model=ORBEntryModel.MODEL_A_DISPLACEMENT_GAP, detected_at=start,
        entry_price=104.0, stop_price=103.0, target_price=106.0,
        risk_per_share=1.0, reward_per_share=2.0, rr_ratio=2.0,
        opening_range=rng, confirmation=conf, evidence={},
    )
    return api.get_proposal_store().create_from_setup(
        setup, strategy_name=strategy, session_date=session_date,
        orb_state="PROPOSAL_READY", gates=ProposalGates(),
    )


def _patch_full_pass(monkeypatch, *, account_id=ACCOUNT_ID, market_data_provider="ibkr"):
    def _fake_compute(name, rec, requested_mode, args):
        from flask import current_app
        result = {
            "strategy_name": name,
            "requested_mode": requested_mode,
            "overall_status": ASSISTED_LIVE_CANDIDATE,
            "live_trading_locked": False,
            "checklist": [],
            "failing_gates": [],
        }
        live_config = api._live_runner_config_for_readiness()
        live_config.live_enabled = True
        live_config.live_market_data_provider = market_data_provider
        live_config.max_live_trades_per_day = 1
        live_config.max_deployable_cash_pct = 0.01
        log_dir = current_app.config.get("orb_evidence_dir", "logs")
        return result, account_id, account_id, True, live_config, log_dir

    monkeypatch.setattr(api, "_compute_orb_live_readiness", _fake_compute)

    class _FakeConnectedServices:
        connected = True

    monkeypatch.setattr(
        "web.services.get_services", lambda: _FakeConnectedServices(),
    )
    monkeypatch.setattr(api, "_tiny_live_account_equity", lambda: 5_000_000.0)


def _rehearse(client, name="ORB1", proposal_id=None, **payload):
    body = dict(payload)
    if proposal_id is not None:
        body["proposal_id"] = proposal_id
    return client.post(f"/api/orb/strategies/{name}/assisted-live/rehearse", json=body)


def _submit_tiny_live(client, rehearsal_id, **payload):
    body = dict(
        confirm_live_order=True,
        expected_account_id=ACCOUNT_ID,
        operator="alice",
        notes="I confirm this tiny-live ORB trade",
    )
    body.update(payload)
    return client.post(
        f"/api/orb/assisted-live/rehearsals/{rehearsal_id}/submit-tiny-live", json=body,
    )


def _build_rehearsal(client, monkeypatch, adapter=None):
    _make(client)
    with client.application.app_context():
        proposal = _seed_proposal()
    _patch_full_pass(monkeypatch)
    if adapter is not None:
        client.application.config["orb_live_order_adapter"] = adapter
    res = _rehearse(client, proposal_id=proposal.proposal_id)
    assert res.status_code == 201, res.get_json()
    return res.get_json()["rehearsal_id"], proposal


# ---- 404 -----------------------------------------------------------------

def test_unknown_rehearsal_404(client):
    res = _submit_tiny_live(client, "does-not-exist")
    assert res.status_code == 404


# ---- successful submit ----------------------------------------------------

def test_successful_submit_records_order_group_and_broker_ids(client, monkeypatch, tmp_path):
    adapter = FakeORBLiveOrderAdapter()
    rehearsal_id, proposal = _build_rehearsal(client, monkeypatch, adapter=adapter)

    res = _submit_tiny_live(client, rehearsal_id)
    assert res.status_code == 201, res.get_json()
    body = res.get_json()
    assert body["rehearsal_id"] == rehearsal_id
    assert body["proposal_id"] == proposal.proposal_id
    assert body["account_id"] == ACCOUNT_ID
    assert body["status"] == "SUBMITTED"
    assert body["protection_broker_visible"] is True
    assert body["entry_broker_order_id"]
    assert body["stop_broker_order_id"]
    assert body["target_broker_order_id"]
    assert adapter.submit_calls == 1

    # The order group is retrievable via list/get endpoints.
    got = client.get(f"/api/orb/tiny-live/orders/{body['order_group_id']}")
    assert got.status_code == 200
    assert got.get_json()["order_group_id"] == body["order_group_id"]

    listing = client.get("/api/orb/tiny-live/orders").get_json()
    assert len(listing["orders"]) == 1

    # Audit logged.
    import json
    log_files = list((tmp_path / "logs").glob("autonomous_trading_*.jsonl"))
    assert log_files
    records = [json.loads(l) for f in log_files for l in f.read_text().splitlines()]
    assert any(
        r.get("kind") == "orb_tiny_live_execution" and r.get("action") == "tiny_live_order_submitted"
        for r in records
    )


def test_second_submit_of_same_rehearsal_refused_no_second_broker_call(client, monkeypatch):
    adapter = FakeORBLiveOrderAdapter()
    rehearsal_id, _proposal = _build_rehearsal(client, monkeypatch, adapter=adapter)

    first = _submit_tiny_live(client, rehearsal_id)
    assert first.status_code == 201

    second = _submit_tiny_live(client, rehearsal_id)
    assert second.status_code == 409
    assert second.get_json()["reason"] == "rehearsal_already_submitted"
    assert adapter.submit_calls == 1


def test_daily_cap_blocks_second_live_trade(client, monkeypatch):
    adapter = FakeORBLiveOrderAdapter()
    _make(client)
    _patch_full_pass(monkeypatch)
    client.application.config["orb_live_order_adapter"] = adapter

    with client.application.app_context():
        proposal_1 = _seed_proposal(session_date="2026-06-01")
    res1 = _rehearse(client, proposal_id=proposal_1.proposal_id)
    rehearsal_id_1 = res1.get_json()["rehearsal_id"]
    submit1 = _submit_tiny_live(client, rehearsal_id_1)
    assert submit1.status_code == 201

    with client.application.app_context():
        proposal_2 = _seed_proposal(symbol="QQQ", session_date="2026-06-01")
    res2 = _rehearse(client, proposal_id=proposal_2.proposal_id)
    # Second proposal for the same session may itself be refused by the
    # session cap upstream; regardless, submit-tiny-live must never place a
    # second live order for the same strategy/session once the daily cap of
    # 1 is consumed.
    if res2.status_code == 201:
        rehearsal_id_2 = res2.get_json()["rehearsal_id"]
        submit2 = _submit_tiny_live(client, rehearsal_id_2)
        assert submit2.status_code == 409
        assert submit2.get_json()["reason"] == "daily_cap_reached"
    assert adapter.submit_calls == 1


# ---- fail-closed gates -----------------------------------------------------

def test_account_mismatch_refused(client, monkeypatch):
    adapter = FakeORBLiveOrderAdapter()
    rehearsal_id, _proposal = _build_rehearsal(client, monkeypatch, adapter=adapter)

    res = _submit_tiny_live(client, rehearsal_id, expected_account_id="DU00000")
    assert res.status_code == 409
    assert res.get_json()["reason"] == "account_mismatch"
    assert adapter.submit_calls == 0


def test_missing_operator_confirmation_refused(client, monkeypatch):
    adapter = FakeORBLiveOrderAdapter()
    rehearsal_id, _proposal = _build_rehearsal(client, monkeypatch, adapter=adapter)

    res = _submit_tiny_live(client, rehearsal_id, confirm_live_order=False)
    assert res.status_code == 409
    assert res.get_json()["reason"] == "operator_confirmation_missing"
    assert adapter.submit_calls == 0


def test_live_master_switch_disabled_blocks_submit(client, monkeypatch):
    adapter = FakeORBLiveOrderAdapter()
    rehearsal_id, _proposal = _build_rehearsal(client, monkeypatch, adapter=adapter)

    def _fake_compute(name, rec, requested_mode, args):
        from flask import current_app
        result = {"overall_status": ASSISTED_LIVE_CANDIDATE}
        live_config = api._live_runner_config_for_readiness()
        live_config.live_enabled = False  # disabled!
        log_dir = current_app.config.get("orb_evidence_dir", "logs")
        return result, ACCOUNT_ID, ACCOUNT_ID, True, live_config, log_dir

    monkeypatch.setattr(api, "_compute_orb_live_readiness", _fake_compute)
    res = _submit_tiny_live(client, rehearsal_id)
    assert res.status_code == 409
    assert res.get_json()["reason"] == "live_master_switch_disabled"
    assert adapter.submit_calls == 0


def test_readiness_no_longer_passing_blocks_submit(client, monkeypatch):
    adapter = FakeORBLiveOrderAdapter()
    rehearsal_id, _proposal = _build_rehearsal(client, monkeypatch, adapter=adapter)

    def _fake_compute(name, rec, requested_mode, args):
        from flask import current_app
        result = {"overall_status": LOCKED}
        live_config = api._live_runner_config_for_readiness()
        live_config.live_enabled = True
        log_dir = current_app.config.get("orb_evidence_dir", "logs")
        return result, ACCOUNT_ID, ACCOUNT_ID, True, live_config, log_dir

    monkeypatch.setattr(api, "_compute_orb_live_readiness", _fake_compute)
    res = _submit_tiny_live(client, rehearsal_id)
    assert res.status_code == 409
    assert res.get_json()["reason"] == "readiness_not_passed"
    assert adapter.submit_calls == 0


def test_emergency_stop_blocks_submit(client, monkeypatch):
    adapter = FakeORBLiveOrderAdapter()
    rehearsal_id, _proposal = _build_rehearsal(client, monkeypatch, adapter=adapter)

    from web.routes.api_autonomous import EMERGENCY_STOP_FILE
    EMERGENCY_STOP_FILE.parent.mkdir(parents=True, exist_ok=True)
    EMERGENCY_STOP_FILE.write_text("stop")
    try:
        res = _submit_tiny_live(client, rehearsal_id)
        assert res.status_code == 409
        assert res.get_json()["reason"] == "emergency_stop_active"
        assert adapter.submit_calls == 0
    finally:
        EMERGENCY_STOP_FILE.unlink(missing_ok=True)


def test_unhealthy_market_data_source_blocks_submit(client, monkeypatch):
    adapter = FakeORBLiveOrderAdapter()
    _make(client)
    with client.application.app_context():
        proposal = _seed_proposal()
    _patch_full_pass(monkeypatch, market_data_provider="yahoo")
    client.application.config["orb_live_order_adapter"] = adapter
    res = _rehearse(client, proposal_id=proposal.proposal_id)
    # Rehearsal itself is not market-data gated, so it should still build.
    assert res.status_code == 201
    rehearsal_id = res.get_json()["rehearsal_id"]

    submit_res = _submit_tiny_live(client, rehearsal_id)
    assert submit_res.status_code == 409
    assert submit_res.get_json()["reason"] == "market_data_unacceptable"
    assert adapter.submit_calls == 0


def test_missing_account_equity_blocks_submit(client, monkeypatch):
    adapter = FakeORBLiveOrderAdapter()
    rehearsal_id, _proposal = _build_rehearsal(client, monkeypatch, adapter=adapter)
    monkeypatch.setattr(api, "_tiny_live_account_equity", lambda: None)

    res = _submit_tiny_live(client, rehearsal_id)
    assert res.status_code == 409
    assert res.get_json()["reason"] == "risk_cap_unverifiable"
    assert adapter.submit_calls == 0


def test_protection_not_broker_visible_fails_closed(client, monkeypatch):
    adapter = FakeORBLiveOrderAdapter(protection_broker_visible=False)
    rehearsal_id, _proposal = _build_rehearsal(client, monkeypatch, adapter=adapter)

    res = _submit_tiny_live(client, rehearsal_id)
    assert res.status_code == 409
    assert res.get_json()["reason"] == "protection_not_broker_visible"
    assert adapter.submit_calls == 1
    assert adapter.cancel_calls == 1


def test_default_adapter_refuses_when_none_configured(client, monkeypatch):
    """Production default (no fake adapter wired in) must fail closed."""
    _make(client)
    with client.application.app_context():
        proposal = _seed_proposal()
    _patch_full_pass(monkeypatch)
    res = _rehearse(client, proposal_id=proposal.proposal_id)
    assert res.status_code == 201
    rehearsal_id = res.get_json()["rehearsal_id"]

    submit_res = _submit_tiny_live(client, rehearsal_id)
    assert submit_res.status_code == 409
    assert submit_res.get_json()["reason"] == "broker_submit_failed"


# ---- cancel-if-pending ------------------------------------------------

def test_cancel_if_pending_unknown_order_404(client):
    res = client.post("/api/orb/tiny-live/orders/does-not-exist/cancel-if-pending")
    assert res.status_code == 404


def test_cancel_if_pending_cancels_submitted_order(client, monkeypatch):
    adapter = FakeORBLiveOrderAdapter()
    rehearsal_id, _proposal = _build_rehearsal(client, monkeypatch, adapter=adapter)
    submit_res = _submit_tiny_live(client, rehearsal_id)
    order_group_id = submit_res.get_json()["order_group_id"]

    res = client.post(f"/api/orb/tiny-live/orders/{order_group_id}/cancel-if-pending")
    assert res.status_code == 200
    assert res.get_json()["status"] == "CANCELLED"
    assert adapter.cancel_calls == 1

    # Idempotent: cancelling again does not error and does not re-cancel at
    # the broker (status is no longer SUBMITTED).
    res2 = client.post(f"/api/orb/tiny-live/orders/{order_group_id}/cancel-if-pending")
    assert res2.status_code == 200
    assert res2.get_json()["status"] == "CANCELLED"
    assert adapter.cancel_calls == 1
