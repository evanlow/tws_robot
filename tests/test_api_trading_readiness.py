from autonomous.runner_config import AutonomousLiveRunnerConfig
from web import create_app


class _RealProvider:
    pass


class _Bridge:
    is_connected = True


class _DisconnectedBridge:
    is_connected = False


def _make_app(monkeypatch):
    monkeypatch.setattr(
        "web.services.ServiceManager._start_market_events_refresh",
        lambda self: None,
    )
    monkeypatch.setattr(
        "web.routes.api_connection.is_accepted",
        lambda: True,
    )
    return create_app(
        {"TESTING": True, "LOGIN_DISABLED": True, "WTF_CSRF_ENABLED": False}
    )


def _arm_live_services(app, *, deployable_cash=50_000.0, bridge_connected=True):
    svc = app.config["services"]
    svc.set_connected("live", {"account": "U1234567", "port": 7496})
    svc.update_account_summary(
        {
            "cash_balance": deployable_cash,
            "available_funds": deployable_cash,
            "buying_power": deployable_cash,
            "equity": deployable_cash,
        }
    )
    rm = svc.risk_manager
    rm.current_equity = deployable_cash
    rm.peak_equity = deployable_cash
    rm.daily_start_equity = deployable_cash
    rm._equity_initialized = True
    svc._tws_bridge = _Bridge() if bridge_connected else _DisconnectedBridge()


def test_status_blocks_meaningful_capital_by_default(monkeypatch):
    app = _make_app(monkeypatch)
    client = app.test_client()

    resp = client.get("/api/trading-readiness/status")

    assert resp.status_code == 200
    body = resp.get_json()
    assert body["overall_fit"] is False
    assert body["criteria"]["recommend_only"]["status"] == "YES"
    assert body["criteria"]["capital_growth_50k"]["status"] == "BLOCKED"
    assert body["criteria"]["actual_live_continuous"]["status"] == "BLOCKED"


def test_status_allows_small_single_trade_live_experiment_when_gates_pass(monkeypatch):
    app = _make_app(monkeypatch)
    app.config["autonomous_signal_provider"] = _RealProvider()
    app.config["autonomous_live_runner_config"] = AutonomousLiveRunnerConfig(
        live_enabled=True,
        expected_account_id="U1234567",
        max_deployable_cash_pct=0.005,
        max_open_live_trades=1,
        max_live_trades_per_day=1,
    )
    _arm_live_services(app, deployable_cash=50_000.0)
    client = app.test_client()

    resp = client.get("/api/trading-readiness/status")

    assert resp.status_code == 200
    body = resp.get_json()
    assert body["overall_status"] == "FIT_FOR_SMALL_LIVE_EXPERIMENT"
    assert body["overall_fit"] is True
    assert body["criteria"]["live_dry_run"]["status"] == "YES"
    assert body["criteria"]["actual_live_single_trade"]["status"] == "YES"
    assert body["criteria"]["capital_growth_50k"]["status"] == "BLOCKED"


def test_status_blocks_single_trade_when_trade_value_cap_is_too_high(monkeypatch):
    app = _make_app(monkeypatch)
    app.config["autonomous_signal_provider"] = _RealProvider()
    app.config["autonomous_live_runner_config"] = AutonomousLiveRunnerConfig(
        live_enabled=True,
        expected_account_id="U1234567",
        max_deployable_cash_pct=0.10,
        max_open_live_trades=1,
        max_live_trades_per_day=1,
    )
    _arm_live_services(app, deployable_cash=50_000.0)
    client = app.test_client()

    resp = client.get("/api/trading-readiness/status")

    assert resp.status_code == 200
    body = resp.get_json()
    assert body["overall_fit"] is False
    single = body["criteria"]["actual_live_single_trade"]
    assert single["status"] == "NO"
    assert any("exceeds first-live cap" in r for r in single["reasons"])
