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
from autonomous.trade_store import AutonomousTrade, EXIT_PENDING, FAILED, OPEN, TradeStore
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
        from autonomous.autonomous_mode import AutonomousModeState, TradingCycle
        store, adapter = _install_runner(app, tmp_path)
        # run-once-paper requires Autonomous Mode ON
        state = AutonomousModeState()
        state.turn_on(TradingCycle.SINGLE_TRADE)
        app.config["autonomous_mode_state"] = state
        resp = client.post("/api/autonomous/runner/run-once-paper", json={})
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["status"] == "executed"
        assert body["trade"]["symbol"] == "AAA"
        assert len(store.list_open()) == 1
        assert len(adapter.calls) == 1

    def test_returns_clear_reason_when_gated(self, app, client, tmp_path):
        from autonomous.autonomous_mode import AutonomousModeState, TradingCycle
        _install_runner(app, tmp_path, runner_enabled=False)
        state = AutonomousModeState()
        state.turn_on(TradingCycle.SINGLE_TRADE)
        app.config["autonomous_mode_state"] = state
        body = client.post("/api/autonomous/runner/run-once-paper", json={}).get_json()
        assert body["status"] == "runner_disabled"
        assert body["rejection_reason"]

    def test_rejects_when_autonomous_mode_off(self, app, client, tmp_path):
        _install_runner(app, tmp_path)
        # Mode is OFF by default
        resp = client.post("/api/autonomous/runner/run-once-paper", json={})
        assert resp.status_code == 409
        body = resp.get_json()
        assert body["status"] == "autonomous_mode_off"
        assert "Autonomous Mode is OFF" in body["rejection_reason"]


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
        assert body["connection"]["running_account_id"] == "DU12345"

    def test_activate_requires_confirm_flag(self, app, client, tmp_path):
        _install_runner(app, tmp_path)
        app.config["services"].set_connected(
            "paper",
            {"host": "127.0.0.1", "port": 7497, "client_id": 1, "account": "DU12345"},
        )
        # Missing confirm flag
        body = client.post(
            "/api/autonomous/mode/activate",
            json={"trading_cycle": "single_trade"},
        ).get_json()
        assert body["status"] == "confirmation_required"
        # confirm=False also rejected
        body = client.post(
            "/api/autonomous/mode/activate",
            json={"trading_cycle": "single_trade", "confirm": False},
        ).get_json()
        assert body["status"] == "confirmation_required"

    def test_activate_single_trade_runs_cycle(self, app, client, tmp_path):
        store, _adapter = _install_runner(app, tmp_path)
        app.config["services"].set_connected(
            "paper",
            {"host": "127.0.0.1", "port": 7497, "client_id": 1, "account": "DU12345"},
        )
        body = client.post(
            "/api/autonomous/mode/activate",
            json={"trading_cycle": "single_trade", "confirm": True},
        ).get_json()
        assert body["status"] == "activated"
        assert body["autonomous_mode"]["mode"]["operating_state"] == "ON"
        assert body["autonomous_mode"]["mode"]["cycles_started"] == 1
        assert len(store.list_open()) == 1

    def test_activate_paper_sets_paper_account_mode(self, app, client, tmp_path):
        """Paper activation should default to PAPER account_mode (backward compat)."""
        _install_runner(app, tmp_path)
        app.config["services"].set_connected(
            "paper",
            {"host": "127.0.0.1", "port": 7497, "client_id": 1, "account": "DU12345"},
        )
        body = client.post(
            "/api/autonomous/mode/activate",
            json={"trading_cycle": "single_trade", "confirm": True},
        ).get_json()
        assert body["status"] == "activated"
        # display_mode comes from to_dict() which derives it from account_mode
        assert body["autonomous_mode"]["mode"].get("account_mode") == "paper"
        assert body["autonomous_mode"]["mode"].get("display_mode") == "PAPER"

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
            json={"trading_cycle": "single_trade", "confirm": True},
        ).get_json()
        assert body["status"] == "halted"
        assert body["autonomous_mode"]["mode"]["operating_state"] == "OFF"
        assert "bearish market" in body["autonomous_mode"]["readiness"]["message"]

    def test_activate_rejected_when_account_unknown(self, app, client, tmp_path):
        """Activation must fail-closed when account type is Unknown."""
        _install_runner(app, tmp_path)
        # Connected but no account id populated yet → Unknown
        app.config["services"].set_connected(
            "paper",
            {"host": "127.0.0.1", "port": 7497, "client_id": 1, "account": ""},
        )
        resp = client.post(
            "/api/autonomous/mode/activate",
            json={"trading_cycle": "single_trade", "confirm": True},
        )
        assert resp.status_code == 409
        body = resp.get_json()
        assert body["status"] == "rejected"
        assert "not verified" in body["error"]

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

    def test_dual_halt_sequence_is_safe_under_ambiguous_context(
        self, app, client, tmp_path
    ):
        """Live then paper halt sequence must be safe and idempotent.

        This mirrors the dashboard's ambiguous-context OFF fallback path,
        where JS attempts both /live/halt and /mode/halt to avoid leaving
        live mode running when account context is temporarily blocked.
        """
        from autonomous.autonomous_mode import (
            AccountMode,
            AutonomousModeState,
            TradingCycle,
        )

        _install_runner(app, tmp_path)

        # Seed both mode states as ON to emulate an ambiguous UI context.
        paper_state = AutonomousModeState()
        paper_state.turn_on(TradingCycle.SINGLE_TRADE)
        live_state = AutonomousModeState()
        live_state.turn_on(TradingCycle.CONTINUOUS, AccountMode.LIVE)
        app.config["autonomous_mode_state"] = paper_state
        app.config["autonomous_live_mode_state"] = live_state

        live_resp = client.post("/api/autonomous/live/halt", json={"reason": "test-ambiguous"})
        assert live_resp.status_code == 200
        live_body = live_resp.get_json()
        assert live_body["status"] == "halted"
        assert live_body["autonomous_live_mode"]["operating_state"] == "OFF"

        paper_resp = client.post("/api/autonomous/mode/halt", json={"reason": "test-ambiguous"})
        assert paper_resp.status_code == 200
        paper_body = paper_resp.get_json()
        assert paper_body["status"] == "halted"
        assert paper_body["autonomous_mode"]["mode"]["operating_state"] == "OFF"

        # Both states must be OFF after the fallback sequence.
        assert app.config["autonomous_live_mode_state"].is_on is False
        assert app.config["autonomous_mode_state"].is_on is False

    def test_status_poll_forces_off_when_runner_disabled_after_activation(
        self, app, client, tmp_path
    ):
        """Mode must turn OFF when the runner is disabled while mode is ON.

        This covers the gap where Autonomous Mode was ON but infrastructure
        readiness gates (runner_enabled, paper_adapter_ready, signal_provider_ready)
        later fail — previously only disconnect/mismatch/emergency-stop caused
        a force-OFF.
        """
        from autonomous.autonomous_mode import AutonomousModeState, TradingCycle

        _install_runner(app, tmp_path, runner_enabled=False)
        app.config["services"].set_connected(
            "paper",
            {"host": "127.0.0.1", "port": 7497, "client_id": 1, "account": "DU12345"},
        )

        # Manually force mode ON to simulate a state where mode was activated
        # before the runner was subsequently disabled.
        state = AutonomousModeState()
        state.turn_on(TradingCycle.SINGLE_TRADE)
        app.config["autonomous_mode_state"] = state

        # A status poll should detect runner_enabled=False and turn mode OFF.
        body = client.get("/api/autonomous/mode/status").get_json()
        assert body["mode"]["operating_state"] == "OFF", (
            "Mode should be forced OFF when the runner gate is no longer passing"
        )
        assert body["mode"]["message"], "A reason message should be set"


class TestEvaluateExits:
    def test_spy_bearish_forces_risk_exit(self, app, client, tmp_path):
        app.config["autonomous_spy_price_provider"] = lambda: {
            "open": 500.0,
            "current": 499.0,
            "source": "test",
        }
        seed = [AutonomousTrade(
            autonomous_trade_id="t_spy",
            symbol="AAA",
            trade_type="buy_shares",
            status=OPEN,
            entry_order_id=1,
            entry_time=datetime.now(timezone.utc),
            entry_limit_price=100.0,
            quantity=10,
            target_price=130.0,
            stop_price=90.0,
            max_holding_days=5,
        )]
        store, _adapter = _install_runner(app, tmp_path, store_seed=seed)

        resp = client.post("/api/autonomous/runner/evaluate-exits", json={})
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["count"] == 1
        d = body["decisions"][0]
        assert d["decision"] == "RISK_EXIT"
        assert "SPY intraday bearish" in d["reason"]
        assert store.get("t_spy").status == EXIT_PENDING

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

    def test_single_trade_lifecycle_turns_off_after_exit(self, app, client, tmp_path):
        """Single Trade: Autonomous Mode turns OFF after all lifecycle trades close."""
        from autonomous.autonomous_mode import AutonomousModeState, TradingCycle
        from autonomous.trade_store import CLOSED as CLOSED_STATUS

        store, adapter = _install_runner(app, tmp_path)
        app.config["services"].set_connected(
            "paper",
            {"host": "127.0.0.1", "port": 7497, "client_id": 1, "account": "DU12345"},
        )

        # Activate in Single Trade mode
        body = client.post(
            "/api/autonomous/mode/activate",
            json={"trading_cycle": "single_trade", "confirm": True},
        ).get_json()
        assert body["status"] == "activated"
        assert len(store.list_open()) == 1
        trade = store.list_open()[0]

        # Simulate trade closing (manually mark as CLOSED)
        store.update_trade(
            trade.autonomous_trade_id,
            status=CLOSED_STATUS,
            exit_reason="TAKE_PROFIT",
            exit_time=datetime.now(timezone.utc),
        )

        # evaluate-exits should detect no active trades and turn mode OFF
        resp = client.post("/api/autonomous/runner/evaluate-exits", json={})
        assert resp.status_code == 200

        # Mode should now be OFF
        mode_body = client.get("/api/autonomous/mode/status").get_json()
        assert mode_body["mode"]["operating_state"] == "OFF"
        assert "completed" in mode_body["mode"]["message"]

    def test_single_trade_turns_off_after_filled_exit_order(
        self, app, client, tmp_path
    ):
        """Single Trade closes from broker fill reconciliation, then turns OFF."""
        store, _adapter = _install_runner(app, tmp_path)
        app.config["services"].set_connected(
            "paper",
            {"host": "127.0.0.1", "port": 7497, "client_id": 1, "account": "DU12345"},
        )

        body = client.post(
            "/api/autonomous/mode/activate",
            json={"trading_cycle": "single_trade", "confirm": True},
        ).get_json()
        assert body["status"] == "activated"
        trade = store.list_open()[0]

        store.update_trade(
            trade.autonomous_trade_id,
            status=EXIT_PENDING,
            exit_order_id=5555,
            exit_reason="TAKE_PROFIT",
        )
        app.config["services"].add_order({
            "broker_order_id": 5555,
            "status": "FILLED",
            "avg_fill_price": 112.5,
            "filled": trade.quantity,
        })

        resp = client.post("/api/autonomous/runner/evaluate-exits", json={})
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["reconciliation"]["before"]["exit_fills"] == 1
        assert store.get(trade.autonomous_trade_id).status == "CLOSED"

        mode_body = client.get("/api/autonomous/mode/status").get_json()
        assert mode_body["mode"]["operating_state"] == "OFF"
        assert "completed" in mode_body["mode"]["message"]

    def test_continuous_retries_scan_when_no_trade_was_opened(
        self, app, client, tmp_path
    ):
        """Continuous mode keeps scanning after a no-candidate/no-trade cycle."""
        from autonomous.autonomous_mode import AutonomousModeState, TradingCycle

        store, _adapter = _install_runner(app, tmp_path)
        state = AutonomousModeState()
        state.turn_on(TradingCycle.CONTINUOUS)
        state.cycles_started = 1
        app.config["autonomous_mode_state"] = state

        resp = client.post("/api/autonomous/runner/evaluate-exits", json={})
        assert resp.status_code == 200

        assert state.is_on is True
        assert state.cycles_started == 2
        assert len(store.list_open()) == 1


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

    def test_dashboard_routes_live_runner_through_account_context(self, app, client):
        html = client.get("/autonomous-trading/").get_data(as_text=True)
        # The dashboard uses one lifecycle panel and lets JS route it to
        # Paper or Live after account verification.
        assert "Autonomous Trade Lifecycle" in html
        assert "Paper" in html and "Live runner" in html
        assert "Run Live Robot" not in html
        assert "Live Robot Runner" not in html

    def test_dashboard_explains_continuous_trading_is_poll_driven(self, app, client):
        """Dashboard must explain that Continuous Trading advances on evaluate-exits calls."""
        html = client.get("/autonomous-trading/").get_data(as_text=True)
        assert "Evaluate Exits Now" in html
        # Help text must clarify the poll-driven design so operators don't
        # assume background looping.
        assert "does not loop in the background" in html


class TestSpyGateFailClosed:
    """SPY gate must fail closed when yfinance is unavailable."""

    def test_spy_price_from_yfinance_returns_zeros_on_import_error(self, monkeypatch):
        """When yfinance cannot be imported, _spy_price_from_yfinance returns zeros.

        Zero prices → engine classifies SPY as Bearish / Not Suitable → trading blocked.
        This test verifies the fail-closed contract without a live network call.
        """
        import builtins
        real_import = builtins.__import__

        def _blocked_import(name, *args, **kwargs):
            if name == "yfinance" or name.startswith("yfinance."):
                raise ImportError(f"No module named '{name}'")
            return real_import(name, *args, **kwargs)

        import web.routes.api_autonomous as mod
        monkeypatch.setattr(builtins, "__import__", _blocked_import)
        # yfinance may already be cached in sys.modules; remove it so the
        # patched importer is exercised on the next lazy import inside the
        # function under test.
        monkeypatch.delitem(__import__("sys").modules, "yfinance", raising=False)

        result = mod._spy_price_from_yfinance()
        assert result["open"] == 0.0, "open must be 0 when yfinance unavailable"
        assert result["current"] == 0.0, "current must be 0 when yfinance unavailable"
        assert "error" in result, "error key should indicate data unavailability"


class TestModeStatusReadiness:
    """Verify /api/autonomous/mode/status returns the correct readiness payload.

    These tests cover the two key UI states that drive whether the dashboard
    activation button is enabled or disabled:
    - Ready: all gates pass, match Verified, no emergency stop → button enabled.
    - Not Ready: a gate fails → readiness.status is Not Ready, reasons present.
    """

    def test_mode_status_ready_when_all_gates_pass(self, app, client, tmp_path):
        """readiness.status must be 'Ready' when all infrastructure gates pass.

        This is the 'button enabled' path: the dashboard reads this field from
        /api/autonomous/mode/status to decide whether to enable #btnAutonomousModeToggle.
        """
        app.config["autonomous_spy_price_provider"] = lambda: {
            "open": 500.0, "current": 510.0,
        }
        _install_runner(app, tmp_path)
        app.config["services"].set_connected(
            "paper",
            {"host": "127.0.0.1", "port": 7497, "client_id": 1, "account": "DU12345"},
        )
        body = client.get("/api/autonomous/mode/status").get_json()
        assert body["readiness"]["status"] == "Ready", (
            "readiness.status must be 'Ready' when all gates pass and match is Verified; "
            "the dashboard uses this to enable the activation button"
        )
        assert body["readiness"]["gates"]["ready"] is True
        assert body["readiness"]["gates"]["reasons"] == []
        assert body["connection"]["paper_live_match_status"] == "Verified"
        assert body["mode"]["operating_state"] == "OFF"

    def test_mode_status_not_ready_when_runner_disabled(self, app, client, tmp_path):
        """readiness.status must be 'Not Ready' and reasons non-empty when a gate fails.

        This is the 'button disabled' path: the dashboard reads reasons from
        readiness.gates.reasons and displays them visibly in #modeGateReasons.
        """
        _install_runner(app, tmp_path, runner_enabled=False)
        app.config["services"].set_connected(
            "paper",
            {"host": "127.0.0.1", "port": 7497, "client_id": 1, "account": "DU12345"},
        )
        body = client.get("/api/autonomous/mode/status").get_json()
        assert body["readiness"]["status"] == "Not Ready", (
            "readiness.status must be 'Not Ready' when runner_enabled=False"
        )
        assert body["readiness"]["gates"]["ready"] is False
        reasons = body["readiness"]["gates"]["reasons"]
        assert len(reasons) > 0, "reasons must be non-empty when a gate fails"
        assert any("Runner disabled in config" in r for r in reasons), (
            "reasons must mention 'Runner disabled in config'"
        )

    def test_mode_status_not_ready_when_not_connected(self, app, client, tmp_path):
        """readiness.status must be 'Not Ready' when IBKR account is not verified.

        The runner factory in tests always reports gates ready; the key verification
        is that an unresolved account (no set_connected call) gives match_status
        'Unknown', which prevents the readiness from advancing to 'Ready'.
        """
        _install_runner(app, tmp_path)
        # No set_connected call → service is disconnected; account type unknown
        body = client.get("/api/autonomous/mode/status").get_json()
        assert body["readiness"]["status"] == "Not Ready"
        assert body["connection"]["paper_live_match_status"] != "Verified", (
            "Unknown account type must not be treated as Verified"
        )
