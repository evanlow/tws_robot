"""Tests for the /api/autonomous/runner/* endpoints."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from autonomous import (
    AutonomousMode,
    AutonomousTradingConfig,
    AutonomousTradingEngine,
    CandidateScanner,
    CandidateSignal,
    StaticSignalProvider,
)
from autonomous.audit import AuditLogger
from autonomous.autonomous_runner import AutonomousPaperRunner
from autonomous.runner_config import AutonomousRunnerConfig
from autonomous.trade_store import AutonomousTrade, FAILED, OPEN, TradeStore
from data.cash_availability import CashAvailabilityAnalyzer
from web import create_app


@pytest.fixture
def app(monkeypatch):
    monkeypatch.setattr(
        "web.services.ServiceManager._start_market_events_refresh",
        lambda self: None,
    )
    monkeypatch.setattr(
        "web.routes.api_connection.is_accepted", lambda: True
    )
    return create_app(
        {"TESTING": True, "LOGIN_DISABLED": True, "WTF_CSRF_ENABLED": False}
    )


@pytest.fixture
def client(app):
    return app.test_client()


def _signal():
    return CandidateSignal(
        symbol="AAA",
        strength_score=120,
        signal_label="Confirmed Rebound",
        last_price=100.0,
        support_price=95.0,
        resistance_price=110.0,
    )


def _install_runner(app, tmp_path: Path, *, runner_enabled=True, with_signal=True,
                    paper_adapter=None, store_seed=None):
    store_path = tmp_path / "trades.jsonl"
    store = TradeStore(path=str(store_path))
    if store_seed is not None:
        for trade in store_seed:
            store.record_trade(trade)

    cfg = AutonomousRunnerConfig(
        runner_enabled=runner_enabled,
        trade_store_path=str(store_path),
    )

    class _RealProvider:
        pass

    class _ReadyAdapter:
        def __init__(self):
            self.calls = []

        def is_ready(self):
            return True

        def buy(self, **kw):
            self.calls.append(kw)
            return 4242

        def sell(self, **kw):
            self.calls.append(kw)
            return 5555

    adapter = paper_adapter if paper_adapter is not None else _ReadyAdapter()

    signals = [_signal()] if with_signal else []
    scanner = CandidateScanner(
        signal_provider=StaticSignalProvider(signals),
        symbols=[
            {"symbol": s.symbol, "security": s.symbol, "sector": "X", "sub_industry": ""}
            for s in signals
        ],
    )
    engine_cfg = AutonomousTradingConfig(
        mode=AutonomousMode.PAPER_EXECUTE,
        max_trades_per_day=5,
        audit_log_dir=str(tmp_path),
        emergency_stop_file=str(tmp_path / "ESTOP"),
    )
    engine = AutonomousTradingEngine(
        scanner=scanner,
        cash_analyzer=CashAvailabilityAnalyzer(),
        account_provider=lambda: {"cash_balance": 100_000, "equity": 100_000},
        positions_provider=lambda: {"AAA": {"current_price": 112.5}},
        config=engine_cfg,
        paper_adapter=adapter,
        spy_price_provider=app.config.get("autonomous_spy_price_provider"),
        audit_logger=AuditLogger(log_dir=str(tmp_path)),
    )

    def factory():
        return AutonomousPaperRunner(
            engine=engine,
            trade_store=store,
            runner_config=cfg,
            connected_provider=lambda: True,
            connection_env_provider=lambda: "paper",
            paper_adapter_provider=lambda: adapter,
            signal_provider_provider=lambda: _RealProvider(),
            emergency_stop_provider=lambda: False,
        )

    from autonomous.exit_manager import AutonomousExitManager

    def exit_factory():
        return AutonomousExitManager(
            trade_store=store,
            paper_adapter=adapter,
            positions_provider=lambda: {"AAA": {"current_price": 112.5}},
            emergency_stop_file=str(tmp_path / "ESTOP"),
        )

    app.config["autonomous_runner_factory"] = factory
    app.config["autonomous_exit_manager_factory"] = exit_factory
    app.config["autonomous_trade_store"] = store
    app.config["autonomous_runner_config"] = cfg
    return store, adapter


class TestRunnerStatus:
    def test_status_reports_gates(self, app, client, tmp_path):
        _install_runner(app, tmp_path)
        resp = client.get("/api/autonomous/runner/status")
        assert resp.status_code == 200
        body = resp.get_json()
        assert "gates" in body
        assert body["gates"]["paper_mode"] is True
        assert body["gates"]["runner_enabled"] is True
        assert body["gates"]["ready"] is True
        assert body["runner_config"]["paper_only"] is True
        assert body["runner_config"]["buy_shares_only"] is True

    def test_status_reports_disabled_when_runner_off(self, app, client, tmp_path):
        _install_runner(app, tmp_path, runner_enabled=False)
        body = client.get("/api/autonomous/runner/status").get_json()
        assert body["gates"]["runner_enabled"] is False
        assert body["gates"]["ready"] is False
        # Disabled reason must be actionable: tell the operator exactly
        # which env var / config flag enables the runner.
        joined = " ".join(body["gates"]["reasons"])
        assert "AUTONOMOUS_RUNNER_ENABLED" in joined
        assert "autonomous_runner_config.runner_enabled" in joined

    def test_runner_config_reads_env_flag(self, monkeypatch):
        """``AUTONOMOUS_RUNNER_ENABLED`` is the documented opt-in path."""
        monkeypatch.delenv("AUTONOMOUS_RUNNER_ENABLED", raising=False)
        assert AutonomousRunnerConfig.from_env().runner_enabled is False
        monkeypatch.setenv("AUTONOMOUS_RUNNER_ENABLED", "true")
        assert AutonomousRunnerConfig.from_env().runner_enabled is True
        monkeypatch.setenv("AUTONOMOUS_RUNNER_ENABLED", "false")
        assert AutonomousRunnerConfig.from_env().runner_enabled is False
        monkeypatch.setenv("AUTONOMOUS_RUNNER_ENABLED", "1")
        assert AutonomousRunnerConfig.from_env().runner_enabled is True


class TestRunOncePaper:
    def test_executes_when_ready(self, app, client, tmp_path):
        store, adapter = _install_runner(app, tmp_path)
        resp = client.post("/api/autonomous/runner/run-once-paper", json={})
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["status"] == "executed"
        assert body["trade"]["symbol"] == "AAA"
        assert len(store.list_open()) == 1
        assert len(adapter.calls) == 1

    def test_returns_clear_reason_when_gated(self, app, client, tmp_path):
        _install_runner(app, tmp_path, runner_enabled=False)
        body = client.post("/api/autonomous/runner/run-once-paper", json={}).get_json()
        assert body["status"] == "runner_disabled"
        assert body["rejection_reason"]


class TestAutonomousMode:
    def test_mode_status_defaults_off(self, app, client, tmp_path):
        _install_runner(app, tmp_path)
        app.config["services"].set_connected(
            "paper",
            {"host": "127.0.0.1", "port": 7497, "client_id": 1, "account": "DU12345"},
        )
        body = client.get("/api/autonomous/mode/status").get_json()
        assert body["mode"]["operating_state"] == "OFF"
        assert body["mode"]["trading_cycle"] == "single_trade"
        assert body["connection"]["paper_live_match_status"] == "Verified"

    def test_activate_single_trade_runs_cycle(self, app, client, tmp_path):
        store, _adapter = _install_runner(app, tmp_path)
        app.config["services"].set_connected(
            "paper",
            {"host": "127.0.0.1", "port": 7497, "client_id": 1, "account": "DU12345"},
        )
        body = client.post(
            "/api/autonomous/mode/activate",
            json={"trading_cycle": "single_trade"},
        ).get_json()
        assert body["status"] == "activated"
        assert body["autonomous_mode"]["mode"]["operating_state"] == "ON"
        assert len(store.list_open()) == 1

    def test_activate_halts_on_bearish_spy_gate(self, app, client, tmp_path):
        app.config["autonomous_spy_price_provider"] = lambda: {
            "open": 500.0,
            "current": 499.0,
        }
        _install_runner(app, tmp_path)
        app.config["services"].set_connected(
            "paper",
            {"host": "127.0.0.1", "port": 7497, "client_id": 1, "account": "DU12345"},
        )
        body = client.post(
            "/api/autonomous/mode/activate",
            json={"trading_cycle": "single_trade"},
        ).get_json()
        assert body["status"] == "halted"
        assert body["autonomous_mode"]["mode"]["operating_state"] == "OFF"
        assert "bearish market" in body["autonomous_mode"]["readiness"]["message"]

    def test_halt_turns_mode_off_without_closing_trades(self, app, client, tmp_path):
        seed = [AutonomousTrade(
            autonomous_trade_id="open1", symbol="AAA",
            trade_type="buy_shares", status=OPEN, entry_order_id=1,
            entry_time=datetime.now(timezone.utc),
            entry_limit_price=100.0, quantity=10,
        )]
        store, _ = _install_runner(app, tmp_path, store_seed=seed)
        app.config["services"].set_connected(
            "paper",
            {"host": "127.0.0.1", "port": 7497, "client_id": 1, "account": "DU12345"},
        )
        body = client.post("/api/autonomous/mode/halt", json={"reason": "test"}).get_json()
        assert body["status"] == "halted"
        assert body["autonomous_mode"]["mode"]["operating_state"] == "OFF"
        assert store.get("open1").status == OPEN


class TestEvaluateExits:
    def test_take_profit_evaluation(self, app, client, tmp_path):
        seed = [AutonomousTrade(
            autonomous_trade_id="t1",
            symbol="AAA",
            trade_type="buy_shares",
            status=OPEN,
            entry_order_id=1,
            entry_time=datetime.now(timezone.utc),
            entry_limit_price=100.0,
            quantity=10,
            target_price=110.0,
            stop_price=95.0,
            max_holding_days=5,
        )]
        store, adapter = _install_runner(app, tmp_path, store_seed=seed)
        resp = client.post("/api/autonomous/runner/evaluate-exits", json={})
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["count"] == 1
        d = body["decisions"][0]
        assert d["decision"] == "TAKE_PROFIT"
        # Trade is now EXIT_PENDING (no fake fill).
        assert store.get("t1").status == "EXIT_PENDING"


class TestTrades:
    def test_lists_open_and_closed(self, app, client, tmp_path):
        seed = [
            AutonomousTrade(
                autonomous_trade_id="open1", symbol="AAA",
                trade_type="buy_shares", status=OPEN, entry_order_id=1,
                entry_time=datetime.now(timezone.utc),
                entry_limit_price=100.0, quantity=10,
            ),
        ]
        store, _ = _install_runner(app, tmp_path, store_seed=seed)
        body = client.get("/api/autonomous/runner/trades").get_json()
        assert body["counts"]["open"] == 1
        assert body["open"][0]["symbol"] == "AAA"


class TestCancelEntry:
    def test_cancel_entry_forwards_and_marks_failed(self, app, client, tmp_path):
        seed = [AutonomousTrade(
            autonomous_trade_id="open1",
            symbol="AAA",
            trade_type="buy_shares",
            status=OPEN,
            entry_order_id=4242,
            entry_time=datetime.now(timezone.utc),
            entry_limit_price=100.0,
            quantity=10,
        )]
        store, _ = _install_runner(app, tmp_path, store_seed=seed)
        app.config["autonomous_cancel_order"] = lambda order_id: order_id == 4242

        resp = client.post(
            "/api/autonomous/runner/cancel-entry",
            json={"autonomous_trade_id": "open1"},
        )
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["status"] == "cancel_requested"
        assert body["entry_order_id"] == 4242

        trade = store.get("open1")
        assert trade is not None
        assert trade.status == FAILED
        assert trade.exit_reason == "ENTRY_CANCELLED"

    def test_cancel_entry_rejects_non_open_trade(self, app, client, tmp_path):
        seed = [AutonomousTrade(
            autonomous_trade_id="closed1",
            symbol="AAA",
            trade_type="buy_shares",
            status=FAILED,
            entry_order_id=4242,
            entry_time=datetime.now(timezone.utc),
            entry_limit_price=100.0,
            quantity=10,
            exit_reason="ENTRY_CANCELLED",
        )]
        _install_runner(app, tmp_path, store_seed=seed)

        resp = client.post(
            "/api/autonomous/runner/cancel-entry",
            json={"autonomous_trade_id": "closed1"},
        )
        assert resp.status_code == 409

    def test_cancel_entry_keeps_open_when_forward_fails(self, app, client, tmp_path):
        seed = [AutonomousTrade(
            autonomous_trade_id="open2",
            symbol="AAA",
            trade_type="buy_shares",
            status=OPEN,
            entry_order_id=9898,
            entry_time=datetime.now(timezone.utc),
            entry_limit_price=100.0,
            quantity=10,
        )]
        store, _ = _install_runner(app, tmp_path, store_seed=seed)
        app.config["autonomous_cancel_order"] = lambda order_id: False

        resp = client.post(
            "/api/autonomous/runner/cancel-entry",
            json={"autonomous_trade_id": "open2"},
        )
        assert resp.status_code == 503
        body = resp.get_json()
        assert body["status"] == "cancel_not_forwarded"

        trade = store.get("open2")
        assert trade is not None
        assert trade.status == OPEN


class TestDashboardSafety:
    def test_dashboard_includes_runner_section(self, app, client):
        resp = client.get("/autonomous-trading/")
        assert resp.status_code == 200
        html = resp.get_data(as_text=True)
        assert "Autonomous Trade Lifecycle" in html
        assert "Run One Decision Cycle" in html
        assert "Evaluate Exits Now" in html

    def test_dashboard_does_not_expose_live_runner(self, app, client):
        html = client.get("/autonomous-trading/").get_data(as_text=True)
        # The dashboard must never expose a live autonomous runner control.
        assert "Run Live Robot" not in html
        assert "Live Robot Runner" not in html
