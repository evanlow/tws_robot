"""Tests for ORB session control API (web/routes/api_opening_range.py, #207)."""

import json

import pytest

import web.routes.api_opening_range as api
from web import create_app


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr("web.services.ServiceManager._start_market_events_refresh", lambda self: None)
    api._manager = None  # reset singleton between tests
    app = create_app({
        "TESTING": True, "LOGIN_DISABLED": True, "WTF_CSRF_ENABLED": False,
        "orb_config_dir": str(tmp_path / "config"),
        "orb_evidence_dir": str(tmp_path / "logs"),
    })
    yield app.test_client()
    api._manager = None


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
