"""Tests for ORB session control API (web/routes/api_opening_range.py, #207)."""

import json

import pytest

import web.routes.api_opening_range as api
from web import create_app


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr("web.services.ServiceManager._start_market_events_refresh", lambda self: None)
    api._manager = None  # reset singleton between tests
    api._proposal_store = None  # reset proposal store singleton between tests
    app = create_app({
        "TESTING": True, "LOGIN_DISABLED": True, "WTF_CSRF_ENABLED": False,
        "orb_config_dir": str(tmp_path / "config"),
        "orb_evidence_dir": str(tmp_path / "logs"),
    })
    yield app.test_client()
    api._manager = None
    api._proposal_store = None


def _make(client, name="ORB1", symbols=None, mode="recommend_only"):
    return client.post("/api/orb/strategies", json={
        "name": name, "symbols": symbols or ["QQQ"], "mode": mode})


def test_session_page_loads(client):
    assert client.get("/opening-range/").status_code == 200


def test_create_list_get_update(client):
    assert _make(client).status_code == 201
    assert client.get("/api/orb/strategies").get_json()["strategies"][0]["name"] == "ORB1"
    assert client.get("/api/orb/strategies/ORB1").status_code == 200
    res = client.put("/api/orb/strategies/ORB1", json={"symbols": ["SPY"], "mode": "off"})
    assert res.get_json()["symbols"] == ["SPY"]


def test_invalid_config_rejected(client):
    res = client.post("/api/orb/strategies", json={"name": "", "symbols": []})
    assert res.status_code == 400
    assert res.get_json()["messages"]


def test_live_mode_arm_locked(client):
    _make(client, mode="assisted_live")
    assert client.post("/api/orb/strategies/ORB1/arm", json={}).status_code == 400


def test_recommend_arm_disarm(client):
    _make(client)
    assert client.post("/api/orb/strategies/ORB1/arm", json={"when": "today"}).status_code == 200
    assert client.post("/api/orb/strategies/ORB1/disarm").status_code == 200


def test_disable_today_and_emergency(client):
    _make(client)
    assert client.post("/api/orb/strategies/ORB1/disable-today").status_code == 200
    assert client.post("/api/orb/emergency-stop").get_json()["stopped"] is True


def test_status_lists_locked_modes(client):
    data = client.get("/api/orb/status").get_json()
    assert "tiny_live_candidate" in data["locked_modes"]


# ---- recommend-only proposals (Phase 2.4, #208) -------------------------
def _seed_proposal(symbol="QQQ", strategy="ORB1"):
    """Build and store a recommend-only proposal in the API singleton store."""
    from datetime import datetime, timezone

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
    rng = OpeningRange(symbol, "2026-06-01", start, start, 102.0, 100.0, c5)
    conf = BreakoutConfirmation(symbol, ORBDirection.LONG, c5, 102.0, 100.0, start)
    setup = ORBSetup(
        symbol=symbol, direction=ORBDirection.LONG,
        model=ORBEntryModel.MODEL_A_DISPLACEMENT_GAP, detected_at=start,
        entry_price=104.0, stop_price=103.0, target_price=106.0,
        risk_per_share=1.0, reward_per_share=2.0, rr_ratio=2.0,
        opening_range=rng, confirmation=conf, evidence={},
    )
    return api.get_proposal_store().create_from_setup(
        setup, strategy_name=strategy, session_date="2026-06-01",
        orb_state="PROPOSAL_READY", gates=ProposalGates(),
    )


def test_proposals_list_and_get(client):
    with client.application.app_context():
        proposal = _seed_proposal()
    listing = client.get("/api/orb/proposals").get_json()["proposals"]
    assert len(listing) == 1
    assert listing[0]["order_type"] == "LIMIT"
    assert listing[0]["recommend_only"] is True
    got = client.get(f"/api/orb/proposals/{proposal.proposal_id}")
    assert got.status_code == 200
    assert got.get_json()["stop_price"] < got.get_json()["target_price"]


def test_proposal_get_missing_404(client):
    assert client.get("/api/orb/proposals/nope").status_code == 404


def test_proposal_skip_endpoint(client):
    with client.application.app_context():
        proposal = _seed_proposal()
    res = client.post(f"/api/orb/proposals/{proposal.proposal_id}/skip",
                      json={"reason": "spread too wide"})
    assert res.status_code == 200
    body = res.get_json()
    assert body["status"] == "SKIPPED"
    assert body["skip_reason"] == "spread too wide"


def test_proposal_expire_endpoint(client):
    with client.application.app_context():
        proposal = _seed_proposal()
    res = client.post(f"/api/orb/proposals/{proposal.proposal_id}/expire",
                      json={"reason": "invalidation"})
    assert res.status_code == 200
    assert res.get_json()["status"] == "EXPIRED"
    assert res.get_json()["expiry_reason"] == "invalidation"


def test_proposal_skip_missing_404(client):
    assert client.post("/api/orb/proposals/nope/skip", json={}).status_code == 404
