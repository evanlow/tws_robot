"""Tests for the ORB backtest lab API (web/routes/api_opening_range.py)."""

from datetime import datetime, timedelta

import pytest

from web import create_app


def _inline_candles(symbol="QQQ", day=datetime(2026, 6, 1)):
    rows = []
    t = day.replace(hour=9, minute=30)
    def add(o, h, low, c):
        rows.append({"symbol": symbol, "start": t.isoformat(), "open": o, "high": h, "low": low, "close": c, "volume": 1000})
    for _ in range(15):
        add(101, 102, 100, 101); t += timedelta(minutes=1)
    for _ in range(5):
        add(103, 103.3, 102.8, 103); t += timedelta(minutes=1)
    add(103.1, 103.3, 103.0, 103.2); t += timedelta(minutes=1)
    add(103.6, 105.0, 103.5, 104.9); t += timedelta(minutes=1)
    for _ in range(20):
        add(105, 110, 105, 110); t += timedelta(minutes=1)
    return rows


def _raise_boom(*_args, **_kwargs):
    raise Exception("boom")


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr("web.services.ServiceManager._start_market_events_refresh", lambda self: None)
    app = create_app({"TESTING": True, "LOGIN_DISABLED": True, "WTF_CSRF_ENABLED": False})
    return app.test_client()


def test_backtest_page_loads(client):
    assert client.get("/opening-range/backtest").status_code == 200


def test_run_endpoint(client):
    res = client.post("/api/opening-range/backtest/run", json={"candles": _inline_candles()})
    assert res.status_code == 200
    data = res.get_json()
    assert data["report"]["total_trades"] == 1
    assert data["readiness"]["status"] in ("READY_FOR_PAPER", "NEEDS_MORE_DATA", "DO_NOT_TRADE")


def test_sweep_endpoint(client):
    res = client.post("/api/opening-range/backtest/sweep", json={
        "candles": _inline_candles(),
        "sweep": {"entry_cutoff_time": ["10:30", "11:30"], "continuation_rr": [1.5, 2.0]},
    })
    assert res.status_code == 200
    assert res.get_json()["count"] == 4


def test_run_endpoint_accepts_z_timestamps(client):
    candles = _inline_candles()
    for row in candles:
        row["start"] = f'{row["start"]}Z'
    res = client.post("/api/opening-range/backtest/run", json={"candles": candles})
    assert res.status_code == 200


def test_run_endpoint_coerces_numeric_strings(client):
    res = client.post(
        "/api/opening-range/backtest/run",
        json={
            "candles": _inline_candles(),
            "continuation_rr": "2.0",
            "retest_tolerance_bps": "8",
            "max_entry_slippage_bps": "12",
            "risk_per_trade_equity_pct": "0.01",
            "max_total_orb_trades_per_session": "2",
            "commission_per_share": "0.005",
            "criteria": {
                "min_trade_count": "1",
                "min_avg_r": "-1",
                "max_drawdown_r": "10",
                "max_slippage_sensitivity_r": "5",
                "max_no_data_failures": "2",
            },
        },
    )
    assert res.status_code == 200


def test_run_endpoint_invalid_payload_returns_400(client):
    res = client.post(
        "/api/opening-range/backtest/run",
        json={"candles": _inline_candles(), "continuation_rr": "abc"},
    )
    assert res.status_code == 400
    assert res.get_json()["error"] == "Invalid request payload"


def test_run_endpoint_unexpected_error_sanitized(client, monkeypatch):
    monkeypatch.setattr("web.routes.api_opening_range.run_backtest", _raise_boom)
    res = client.post("/api/opening-range/backtest/run", json={"candles": _inline_candles()})
    assert res.status_code == 400
    assert res.get_json()["error"] == "Backtest run failed"


def test_sweep_endpoint_unexpected_error_sanitized(client, monkeypatch):
    monkeypatch.setattr("web.routes.api_opening_range.run_sweep", _raise_boom)
    res = client.post(
        "/api/opening-range/backtest/sweep",
        json={"candles": _inline_candles(), "sweep": {"entry_cutoff_time": ["10:30"]}},
    )
    assert res.status_code == 400
    assert res.get_json()["error"] == "Backtest sweep failed"


def test_save_evidence_endpoint(client, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    run = client.post("/api/opening-range/backtest/run", json={"candles": _inline_candles()}).get_json()
    res = client.post("/api/opening-range/backtest/save-evidence",
                      json={"report": run["report"], "readiness": run["readiness"], "symbols": ["QQQ"]})
    assert res.status_code == 200 and res.get_json()["saved"] is True
