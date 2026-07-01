"""Tests for ORB session control API (web/routes/api_opening_range.py, #207)."""

import json
from datetime import datetime, timezone

import pytest

import web.routes.api_opening_range as api
from web import create_app


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr("web.services.ServiceManager._start_market_events_refresh", lambda self: None)
    api._manager = None  # reset singleton between tests
    api._proposal_store = None  # reset proposal store singleton between tests
    api._executor = None  # reset paper executor singleton between tests
    app = create_app({
        "TESTING": True, "LOGIN_DISABLED": True, "WTF_CSRF_ENABLED": False,
        "orb_config_dir": str(tmp_path / "config"),
        "orb_evidence_dir": str(tmp_path / "logs"),
    })
    yield app.test_client()
    api._manager = None
    api._proposal_store = None
    api._executor = None


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
def _seed_proposal(symbol="QQQ", strategy="ORB1", expires_at=None,
                   session_date="2026-06-01"):
    """Build and store a recommend-only proposal in the API singleton store."""
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
        setup, strategy_name=strategy, session_date=session_date,
        orb_state="PROPOSAL_READY", gates=ProposalGates(),
        expires_at=expires_at,
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


def test_proposal_get_auto_expires_past_cutoff(client):
    # A proposal whose entry cutoff has already passed must self-heal to EXPIRED
    # even on a direct single-proposal read, not just via the list endpoint.
    past = datetime(2000, 1, 1, tzinfo=timezone.utc).isoformat()
    with client.application.app_context():
        proposal = _seed_proposal(expires_at=past)
    got = client.get(f"/api/orb/proposals/{proposal.proposal_id}")
    assert got.status_code == 200
    body = got.get_json()
    assert body["status"] == "EXPIRED"
    assert body["expiry_reason"] == "entry_cutoff"


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


# ---- paper-autonomous execution (Phase 2.5, #209) -----------------------
def _seed_paper_evidence(client, symbols):
    """Write a READY_FOR_PAPER backtest evidence file so arming can pass gates."""
    import os

    ev_dir = client.application.config["orb_evidence_dir"]
    os.makedirs(ev_dir, exist_ok=True)
    path = os.path.join(ev_dir, "orb_backtest_evidence_20260601.jsonl")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(json.dumps({
            "symbols": list(symbols),
            "readiness": {"status": "READY_FOR_PAPER"},
        }) + "\n")


def _arm_paper(client, strategy="ORB1", symbols=None):
    """Create, ready, and arm a paper_autonomous strategy for its session.

    Seeds READY_FOR_PAPER evidence, creates the strategy in paper_autonomous
    mode, and arms the ORB session (execution gates on arming, not just mode).
    Returns the armed session date so callers can seed a matching proposal.
    """
    symbols = symbols or ["QQQ"]
    _seed_paper_evidence(client, symbols)
    _make(client, name=strategy, symbols=symbols, mode="paper_autonomous")
    res = client.post(f"/api/orb/strategies/{strategy}/arm", json={"when": "today"})
    assert res.status_code == 200, res.get_json()
    return res.get_json()["session"]["armed_for"]


def test_execute_paper_places_bracket_trade(client):
    armed_for = _arm_paper(client)
    with client.application.app_context():
        proposal = _seed_proposal(strategy="ORB1", session_date=armed_for)
    res = client.post(f"/api/orb/proposals/{proposal.proposal_id}/execute-paper")
    assert res.status_code == 201
    body = res.get_json()
    assert body["protection_status"] == "BRACKET_CONFIRMED"
    assert body["mode"] == "paper_autonomous"
    assert body["entry_order_id"] and body["stop_order_id"] and body["target_order_id"]
    # The trade is retrievable via the trade lookup endpoints.
    assert client.get("/api/orb/trades").get_json()["trades"][0]["trade_id"] == body["trade_id"]
    got = client.get(f"/api/orb/trades/{body['trade_id']}")
    assert got.status_code == 200
    assert got.get_json()["proposal_id"] == proposal.proposal_id


def test_execute_paper_requires_armed_session(client):
    # paper_autonomous mode alone is not enough: an un-armed session is rejected
    # and no paper trade is placed.
    _make(client, mode="paper_autonomous")
    with client.application.app_context():
        proposal = _seed_proposal(strategy="ORB1")
    res = client.post(f"/api/orb/proposals/{proposal.proposal_id}/execute-paper")
    assert res.status_code == 400
    assert res.get_json()["error"] == "orb session not armed"
    assert client.get("/api/orb/trades").get_json()["trades"] == []


def test_execute_paper_rejects_session_date_mismatch(client):
    armed_for = _arm_paper(client)
    # A proposal for a session other than the armed date must be rejected.
    other = "2000-01-02" if armed_for != "2000-01-02" else "2000-01-03"
    with client.application.app_context():
        proposal = _seed_proposal(strategy="ORB1", session_date=other)
    res = client.post(f"/api/orb/proposals/{proposal.proposal_id}/execute-paper")
    assert res.status_code == 400
    assert res.get_json()["error"] == "orb session date mismatch"
    assert client.get("/api/orb/trades").get_json()["trades"] == []


def test_recommend_only_mode_never_executes(client):
    _make(client, mode="recommend_only")
    with client.application.app_context():
        proposal = _seed_proposal(strategy="ORB1")
    res = client.post(f"/api/orb/proposals/{proposal.proposal_id}/execute-paper")
    assert res.status_code == 400
    assert client.get("/api/orb/trades").get_json()["trades"] == []


def test_execute_paper_unknown_proposal_404(client):
    assert client.post("/api/orb/proposals/nope/execute-paper").status_code == 404


def test_execute_paper_is_idempotent(client):
    armed_for = _arm_paper(client)
    with client.application.app_context():
        proposal = _seed_proposal(strategy="ORB1", session_date=armed_for)
    first = client.post(f"/api/orb/proposals/{proposal.proposal_id}/execute-paper")
    second = client.post(f"/api/orb/proposals/{proposal.proposal_id}/execute-paper")
    assert first.status_code == 201 and second.status_code == 201
    assert first.get_json()["trade_id"] == second.get_json()["trade_id"]
    assert len(client.get("/api/orb/trades").get_json()["trades"]) == 1


def test_emergency_stop_blocks_paper_execution(client):
    armed_for = _arm_paper(client)
    with client.application.app_context():
        proposal = _seed_proposal(strategy="ORB1", session_date=armed_for)
    assert client.post("/api/orb/emergency-stop").get_json()["stopped"] is True
    res = client.post(f"/api/orb/proposals/{proposal.proposal_id}/execute-paper")
    assert res.status_code == 409
    assert res.get_json()["reason"] == "emergency_stop"


def test_trade_lookup_missing_404(client):
    assert client.get("/api/orb/trades/nope").status_code == 404
