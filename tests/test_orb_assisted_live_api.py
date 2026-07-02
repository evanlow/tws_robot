"""Tests for the ORB Phase 5 assisted-live rehearsal API (#227).

Verifies the ``POST .../assisted-live/rehearse``,
``GET .../assisted-live/rehearsals``, and
``GET /api/orb/assisted-live/rehearsals/<id>`` endpoints stay locked by
default and only build a rehearsal package when every safety gate is
explicitly satisfied. Never places an order.
"""

from datetime import datetime, timezone

import pytest

import web.routes.api_opening_range as api
from autonomous.orb_live_readiness import ASSISTED_LIVE_CANDIDATE
from web import create_app


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


def _rehearse(client, name="ORB1", proposal_id=None, **payload):
    body = dict(payload)
    if proposal_id is not None:
        body["proposal_id"] = proposal_id
    return client.post(f"/api/orb/strategies/{name}/assisted-live/rehearse", json=body)


# ---- 404 / 400 request shape -----------------------------------------------

def test_unknown_strategy_404(client):
    res = _rehearse(client, name="NOPE", proposal_id="whatever")
    assert res.status_code == 404


def test_missing_proposal_id_400(client):
    _make(client)
    res = _rehearse(client)
    assert res.status_code == 400


def test_non_object_json_body_400(client):
    _make(client)
    res = client.post(
        "/api/orb/strategies/ORB1/assisted-live/rehearse",
        json=["proposal-1"],
    )
    assert res.status_code == 400
    assert res.get_json()["error"] == "request body must be a JSON object"


def test_unknown_proposal_404(client):
    _make(client)
    res = _rehearse(client, proposal_id="does-not-exist")
    assert res.status_code == 404


def test_proposal_belongs_to_different_strategy_400(client):
    _make(client, name="ORB1")
    _make(client, name="ORB2")
    with client.application.app_context():
        proposal = _seed_proposal(strategy="ORB2")
    res = _rehearse(client, name="ORB1", proposal_id=proposal.proposal_id)
    assert res.status_code == 400


# ---- fail closed: readiness not passed by default --------------------------

def test_readiness_not_passed_refused_by_default(client, tmp_path):
    _make(client)
    with client.application.app_context():
        proposal = _seed_proposal()
    res = _rehearse(client, proposal_id=proposal.proposal_id)
    assert res.status_code == 409
    body = res.get_json()
    assert body["reason"] == "readiness_not_passed"
    assert body["readiness"]["overall_status"] != ASSISTED_LIVE_CANDIDATE

    # No order is ever placed and no rehearsal package is stored on refusal.
    listing = client.get("/api/orb/strategies/ORB1/assisted-live/rehearsals").get_json()
    assert listing["rehearsals"] == []


# ---- success path (readiness computation monkeypatched to a full pass) ----

def _patch_full_pass(monkeypatch, *, account_id="DU12345"):
    """Simulate every Phase 4 gate + master switch + operator confirmation
    passing, without needing to fabricate 50+ paper trades of evidence end
    to end. The gate-by-gate readiness evaluation itself is already fully
    covered by tests/test_orb_live_readiness.py and
    tests/test_orb_live_readiness_api.py; this isolates the rehearsal
    endpoint's own wiring/refusal behavior.
    """
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
        log_dir = current_app.config.get("orb_evidence_dir", "logs")
        return result, account_id, account_id, True, live_config, log_dir

    monkeypatch.setattr(api, "_compute_orb_live_readiness", _fake_compute)


def test_successful_rehearsal_build_and_lookup(client, tmp_path, monkeypatch):
    _make(client)
    with client.application.app_context():
        proposal = _seed_proposal()
    _patch_full_pass(monkeypatch)

    res = _rehearse(
        client, proposal_id=proposal.proposal_id,
        evidence_id="rev-2026-06-01-ORB1", time_in_force="DAY",
    )
    assert res.status_code == 201
    body = res.get_json()
    assert body["strategy_name"] == "ORB1"
    assert body["symbol"] == "QQQ"
    assert body["account_id"] == "DU12345"
    assert body["proposal_id"] == proposal.proposal_id
    assert body["entry_model"] == "MODEL_A_DISPLACEMENT_GAP"
    assert body["direction"] == "LONG"
    assert body["entry_order_type"] == "LIMIT"
    assert body["stop_price"] == proposal.stop_price
    assert body["target_price"] == proposal.target_price
    assert body["bracket"]["entry_order_type"] == "LIMIT"
    assert body["bracket"]["stop_order_type"] == "STOP"
    assert body["evidence_id"] == "rev-2026-06-01-ORB1"
    assert body["mode"] == "REHEARSAL"
    assert body["status"] == "DRY_RUN_ONLY"
    rehearsal_id = body["rehearsal_id"]

    listing = client.get("/api/orb/strategies/ORB1/assisted-live/rehearsals").get_json()
    assert len(listing["rehearsals"]) == 1
    assert listing["rehearsals"][0]["rehearsal_id"] == rehearsal_id

    got = client.get(f"/api/orb/assisted-live/rehearsals/{rehearsal_id}")
    assert got.status_code == 200
    assert got.get_json()["rehearsal_id"] == rehearsal_id

    # Audit logged.
    log_files = list((tmp_path / "logs").glob("autonomous_trading_*.jsonl"))
    assert log_files
    import json
    records = [json.loads(l) for l in log_files[0].read_text().splitlines()]
    assert any(
        r.get("kind") == "orb_assisted_live_rehearsal" and r.get("action") == "rehearsal_created"
        for r in records
    )


def test_rehearsal_missing_404(client):
    _make(client)
    res = client.get("/api/orb/assisted-live/rehearsals/does-not-exist")
    assert res.status_code == 404


def test_account_mismatch_refused(client, monkeypatch):
    _make(client)
    with client.application.app_context():
        proposal = _seed_proposal()
    _patch_full_pass(monkeypatch, account_id="DU12345")

    def _fake_compute(name, rec, requested_mode, args):
        from flask import current_app
        result = {"overall_status": ASSISTED_LIVE_CANDIDATE, "live_trading_locked": False}
        live_config = api._live_runner_config_for_readiness()
        live_config.live_enabled = True
        log_dir = current_app.config.get("orb_evidence_dir", "logs")
        return result, "DU99999", "DU12345", True, live_config, log_dir

    monkeypatch.setattr(api, "_compute_orb_live_readiness", _fake_compute)
    res = _rehearse(client, proposal_id=proposal.proposal_id)
    assert res.status_code == 409
    assert res.get_json()["reason"] == "account_mismatch"


def test_market_data_source_query_override_cannot_mask_unsafe_config(client):
    """Regression for review feedback: the rehearsal endpoint's readiness
    gate (``_compute_orb_live_readiness``) must always evaluate the real
    ``AutonomousLiveRunnerConfig.live_market_data_provider`` value, never a
    ``market_data_source`` query-string value, so a request cannot mask an
    unsafe actual live-runner data source (e.g. "yahoo") behind an
    acceptable-looking query parameter (e.g. "ibkr").
    """
    from autonomous.runner_config import AutonomousLiveRunnerConfig

    _make(client)
    with client.application.app_context():
        proposal = _seed_proposal()
    live_config = AutonomousLiveRunnerConfig()
    live_config.live_market_data_provider = "yahoo"  # unsafe actual config
    client.application.config["autonomous_live_runner_config"] = live_config

    res = client.post(
        f"/api/orb/strategies/ORB1/assisted-live/rehearse?market_data_source=ibkr",
        json={"proposal_id": proposal.proposal_id},
    )
    assert res.status_code == 409
    body = res.get_json()
    assert body["reason"] == "readiness_not_passed"
    assert "market_data_source_acceptable" in body["readiness"]["failing_gates"]
