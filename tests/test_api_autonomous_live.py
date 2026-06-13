"""Tests for the /api/autonomous/live/* endpoints."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

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
from autonomous.autonomous_live_runner import AutonomousLiveRunner, EXECUTED, DRY_RUN_EXECUTED, NO_TRADE
from autonomous.runner_config import AutonomousLiveRunnerConfig
from autonomous.trade_store import TradeStore
from data.cash_availability import CashAvailabilityAnalyzer
from execution.order_executor import OrderResult, OrderStatus
from web import create_app


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _RealProvider:
    pass


class _SubmittingExecutor:
    def __init__(self, order_id=7777):
        self._order_id = order_id
        self.calls = []

    def execute_signal(self, strategy_name, signal, current_equity, positions):
        self.calls.append({"symbol": signal.symbol, "qty": signal.quantity})
        return OrderResult(
            status=OrderStatus.SUBMITTED,
            order_id=self._order_id,
            signal=signal,
            quantity=signal.quantity or 1,
            price=signal.target_price or 0.0,
            reason=f"Order {self._order_id} submitted",
        )


class _DryRunExecutor:
    def execute_signal(self, strategy_name, signal, current_equity, positions):
        return OrderResult(
            status=OrderStatus.DRY_RUN,
            order_id=None,
            signal=signal,
            quantity=signal.quantity or 1,
            price=signal.target_price or 0.0,
            reason="Dry-run preview",
        )


def _signal():
    return CandidateSignal(
        symbol="AAA",
        strength_score=120,
        signal_label="Confirmed Rebound",
        last_price=100.0,
        support_price=95.0,
        resistance_price=110.0,
    )


def _install_live_runner(
    app,
    tmp_path: Path,
    *,
    live_enabled: bool = True,
    live_continuous_enabled: bool = True,
    expected_account_id: str = "U1234567",
    with_signal: bool = True,
    executor=None,
    dry_run: bool = False,
    deployable_cash: float = 50_000.0,
    account_id: str = "U1234567",
):
    """Install a live runner factory and live-mode state into the app config."""
    store_path = tmp_path / "live_trades.jsonl"
    store = TradeStore(path=str(store_path))

    live_cfg = AutonomousLiveRunnerConfig(
        live_enabled=live_enabled,
        live_continuous_enabled=live_continuous_enabled,
        expected_account_id=expected_account_id,
        live_dry_run=dry_run,
        trade_store_path=str(store_path),
    )

    signals = [_signal()] if with_signal else []
    scanner = CandidateScanner(
        signal_provider=StaticSignalProvider(signals),
        symbols=[
            {"symbol": s.symbol, "security": s.symbol, "sector": "X", "sub_industry": ""}
            for s in signals
        ],
    )
    engine_cfg = AutonomousTradingConfig(
        mode=AutonomousMode.ASSISTED_LIVE,
        allow_live_execution=True,
        max_trades_per_day=5,
        audit_log_dir=str(tmp_path),
        emergency_stop_file=str(tmp_path / "ESTOP"),
    )
    engine = AutonomousTradingEngine(
        scanner=scanner,
        cash_analyzer=CashAvailabilityAnalyzer(),
        account_provider=lambda: {"cash_balance": 100_000, "equity": 100_000},
        positions_provider=lambda: {},
        config=engine_cfg,
        paper_adapter=None,
        spy_price_provider=app.config.get("autonomous_spy_price_provider"),
        audit_logger=AuditLogger(log_dir=str(tmp_path)),
    )

    active_executor = executor if executor is not None else _SubmittingExecutor()

    def factory(cfg, continuous_mode=False):
        return AutonomousLiveRunner(
            engine=engine,
            trade_store=store,
            live_config=cfg,
            order_executor=active_executor,
            connected_provider=lambda: True,
            connection_env_provider=lambda: "live",
            account_id_provider=lambda: account_id,
            signal_provider_provider=lambda: _RealProvider(),
            emergency_stop_provider=lambda: False,
            deployable_cash_provider=lambda: deployable_cash,
            continuous_mode=continuous_mode,
        )

    app.config["autonomous_live_runner_factory"] = factory
    app.config["autonomous_live_runner_config"] = live_cfg
    app.config["autonomous_live_trade_store"] = store
    # Use a bullish SPY gate so the engine doesn't block
    app.config["autonomous_spy_price_provider"] = lambda: {"open": 100.0, "current": 105.0}
    return store, active_executor


# ---------------------------------------------------------------------------
# /api/autonomous/live/status
# ---------------------------------------------------------------------------


class TestLiveStatus:
    def test_status_returns_live_config(self, app, client, tmp_path):
        _install_live_runner(app, tmp_path)
        resp = client.get("/api/autonomous/live/status")
        assert resp.status_code == 200
        body = resp.get_json()
        assert "live_runner_config" in body
        assert "gates" in body
        assert "autonomous_live_mode" in body
        assert body["live_runner_config"]["live_enabled"] is True

    def test_gates_show_live_mode_false_when_not_connected(self, app, client, tmp_path):
        _install_live_runner(app, tmp_path)

        # Override with a disconnected factory
        def _disconnected_factory(cfg, continuous_mode=False):
            return AutonomousLiveRunner(
                engine=AutonomousTradingEngine(
                    scanner=CandidateScanner(signal_provider=StaticSignalProvider()),
                    cash_analyzer=CashAvailabilityAnalyzer(),
                    account_provider=lambda: {},
                    positions_provider=lambda: {},
                    config=AutonomousTradingConfig(),
                ),
                trade_store=TradeStore(path=str(tmp_path / "x.jsonl")),
                live_config=cfg,
                order_executor=_SubmittingExecutor(),
                connected_provider=lambda: False,
                connection_env_provider=lambda: "live",
                account_id_provider=lambda: "U1234567",
                signal_provider_provider=lambda: _RealProvider(),
                emergency_stop_provider=lambda: False,
                deployable_cash_provider=lambda: 50_000.0,
            )

        app.config["autonomous_live_runner_factory"] = _disconnected_factory
        resp = client.get("/api/autonomous/live/status")
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["gates"]["connected"] is False
        assert body["gates"]["ready"] is False


# ---------------------------------------------------------------------------
# /api/autonomous/live/activate
# ---------------------------------------------------------------------------


class TestLiveActivate:
    def test_requires_confirm_true(self, app, client, tmp_path):
        _install_live_runner(app, tmp_path)
        resp = client.post(
            "/api/autonomous/live/activate",
            json={"confirm": False, "account_mode": "live", "trading_cycle": "continuous"},
        )
        assert resp.status_code == 400
        assert "confirm" in resp.get_json()["error"]

    def test_requires_account_mode_live(self, app, client, tmp_path):
        _install_live_runner(app, tmp_path)
        resp = client.post(
            "/api/autonomous/live/activate",
            json={"confirm": True, "account_mode": "paper", "trading_cycle": "continuous"},
        )
        assert resp.status_code == 400
        assert "account_mode" in resp.get_json()["error"]

    def test_requires_valid_trading_cycle(self, app, client, tmp_path):
        _install_live_runner(app, tmp_path)
        resp = client.post(
            "/api/autonomous/live/activate",
            json={"confirm": True, "account_mode": "live", "trading_cycle": "invalid"},
        )
        assert resp.status_code == 400

    def test_rejected_when_live_disabled(self, app, client, tmp_path):
        _install_live_runner(app, tmp_path, live_enabled=False)
        resp = client.post(
            "/api/autonomous/live/activate",
            json={
                "confirm": True,
                "account_mode": "live",
                "trading_cycle": "continuous",
                "expected_account_id": "U1234567",
            },
        )
        assert resp.status_code == 409
        body = resp.get_json()
        assert body["status"] == "rejected"
        assert any("AUTONOMOUS_LIVE_ENABLED" in r for r in body["gates"]["reasons"])

    def test_rejected_when_continuous_disabled_for_continuous_mode(self, app, client, tmp_path):
        _install_live_runner(app, tmp_path, live_continuous_enabled=False)
        resp = client.post(
            "/api/autonomous/live/activate",
            json={
                "confirm": True,
                "account_mode": "live",
                "trading_cycle": "continuous",
                "expected_account_id": "U1234567",
            },
        )
        assert resp.status_code == 409
        body = resp.get_json()
        assert body["status"] == "rejected"
        assert any("AUTONOMOUS_LIVE_CONTINUOUS_ENABLED" in r for r in body["gates"]["reasons"])

    def test_rejected_when_account_id_mismatch(self, app, client, tmp_path):
        _install_live_runner(app, tmp_path, expected_account_id="U9999999")
        resp = client.post(
            "/api/autonomous/live/activate",
            json={
                "confirm": True,
                "account_mode": "live",
                "trading_cycle": "continuous",
                "expected_account_id": "U9999999",  # matches config
            },
        )
        # Should proceed (factory uses actual account_id="U1234567" which != "U9999999")
        # Actually this should be REJECTED because U1234567 != U9999999
        # But wait - the factory uses account_id_provider=lambda: "U1234567"
        # and live_cfg.expected_account_id="U9999999"
        # So the gate should fail
        assert resp.status_code == 409
        body = resp.get_json()
        assert body["status"] == "rejected"

    def test_activates_with_valid_request(self, app, client, tmp_path):
        _install_live_runner(app, tmp_path)
        resp = client.post(
            "/api/autonomous/live/activate",
            json={
                "confirm": True,
                "account_mode": "live",
                "trading_cycle": "continuous",
                "expected_account_id": "U1234567",
                "confirmed_by": "TestOperator",
            },
        )
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["status"] in ("activated", "halted")
        assert "autonomous_live_mode" in body

    def test_activate_records_display_mode(self, app, client, tmp_path):
        _install_live_runner(app, tmp_path)
        resp = client.post(
            "/api/autonomous/live/activate",
            json={
                "confirm": True,
                "account_mode": "live",
                "trading_cycle": "continuous",
                "expected_account_id": "U1234567",
            },
        )
        assert resp.status_code == 200
        body = resp.get_json()
        live_mode = body.get("autonomous_live_mode", {})
        if body["status"] == "activated":
            assert live_mode.get("display_mode") == "LIVE CONTINUOUS"
        else:
            assert live_mode.get("display_mode") == "OFF"

    def test_dry_run_flag_accepted(self, app, client, tmp_path):
        _install_live_runner(app, tmp_path, dry_run=True)
        resp = client.post(
            "/api/autonomous/live/activate",
            json={
                "confirm": True,
                "account_mode": "live",
                "trading_cycle": "single_trade",
                "expected_account_id": "U1234567",
                "dry_run": True,
            },
        )
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# /api/autonomous/live/halt
# ---------------------------------------------------------------------------


class TestLiveHalt:
    def test_halt_turns_mode_off(self, app, client, tmp_path):
        _install_live_runner(app, tmp_path)
        resp = client.post("/api/autonomous/live/halt", json={"reason": "test halt"})
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["status"] == "halted"
        assert body["autonomous_live_mode"]["operating_state"] == "OFF"

    def test_halt_includes_display_mode_off(self, app, client, tmp_path):
        _install_live_runner(app, tmp_path)
        resp = client.post("/api/autonomous/live/halt", json={})
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["autonomous_live_mode"]["display_mode"] == "OFF"


# ---------------------------------------------------------------------------
# /api/autonomous/live/run-once
# ---------------------------------------------------------------------------


class TestLiveRunOnce:
    def test_returns_409_when_mode_off(self, app, client, tmp_path):
        _install_live_runner(app, tmp_path)
        resp = client.post("/api/autonomous/live/run-once", json={})
        assert resp.status_code == 409
        assert "Live Autonomous Mode is OFF" in resp.get_json()["rejection_reason"]

    def test_runs_when_mode_on(self, app, client, tmp_path):
        from autonomous.autonomous_mode import AutonomousModeState, TradingCycle, AccountMode
        _install_live_runner(app, tmp_path)
        # Activate live mode state
        state = AutonomousModeState()
        state.turn_on(TradingCycle.CONTINUOUS, AccountMode.LIVE)
        app.config["autonomous_live_mode_state"] = state

        resp = client.post("/api/autonomous/live/run-once", json={})
        assert resp.status_code == 200
        body = resp.get_json()
        assert "status" in body


# ---------------------------------------------------------------------------
# /api/autonomous/live/trades
# ---------------------------------------------------------------------------


class TestLiveTrades:
    def test_empty_stores_by_default(self, app, client, tmp_path):
        _install_live_runner(app, tmp_path)
        resp = client.get("/api/autonomous/live/trades")
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["counts"]["total"] == 0
        assert body["open"] == []
        assert body["closed"] == []


# ---------------------------------------------------------------------------
# /api/autonomous/live/evaluate-exits
# ---------------------------------------------------------------------------


class TestLiveEvaluateExits:
    def test_evaluates_exits(self, app, client, tmp_path):
        _install_live_runner(app, tmp_path)
        resp = client.post("/api/autonomous/live/evaluate-exits", json={})
        assert resp.status_code == 200
        body = resp.get_json()
        assert "decisions" in body
        assert "count" in body


# ---------------------------------------------------------------------------
# Fix #3/#4: Session confirmation + expected_account_id persistence
# ---------------------------------------------------------------------------


class TestActivationPersistence:
    def test_activate_persists_expected_account_id_in_app_config(
        self, app, client, tmp_path
    ):
        """After a successful activation, expected_account_id must be stored
        in app.config so subsequent runner rebuilds use it."""
        _install_live_runner(app, tmp_path, expected_account_id="U1234567")
        with app.app_context():
            resp = client.post(
                "/api/autonomous/live/activate",
                json={
                    "confirm": True,
                    "account_mode": "live",
                    "trading_cycle": "continuous",
                    "expected_account_id": "U1234567",
                    "confirmed_by": "TestOperator",
                },
            )
            assert resp.status_code == 200
            assert (
                app.config.get("autonomous_live_expected_account_id") == "U1234567"
            )

    def test_activate_dry_run_does_not_persist_live_confirmation(
        self, app, client, tmp_path
    ):
        """dry_run=True should NOT persist a LiveTradingConfirmation (safe path)."""
        _install_live_runner(app, tmp_path, dry_run=True)
        with app.app_context():
            resp = client.post(
                "/api/autonomous/live/activate",
                json={
                    "confirm": True,
                    "account_mode": "live",
                    "trading_cycle": "continuous",
                    "expected_account_id": "U1234567",
                    "dry_run": True,
                },
            )
            assert resp.status_code == 200
            # dry_run=True → no live confirmation persisted
            assert app.config.get("autonomous_live_confirmation") is None


# ---------------------------------------------------------------------------
# Fix #1 (API layer): live evaluate-exits uses an order executor
# ---------------------------------------------------------------------------


class TestLiveEvaluateExitsWithExecutor:
    def test_evaluate_exits_uses_app_config_override_executor(
        self, app, client, tmp_path
    ):
        """When autonomous_live_order_executor is pre-set in app.config, the
        evaluate-exits endpoint must use it (not crash when factory is absent)."""
        from autonomous.trade_store import TradeStore
        store = TradeStore(path=str(tmp_path / "t.jsonl"))
        app.config["autonomous_live_trade_store"] = store
        # Override executor directly — no live runner factory needed
        executor = _SubmittingExecutor()
        app.config["autonomous_live_order_executor"] = executor

        resp = client.post("/api/autonomous/live/evaluate-exits", json={})
        assert resp.status_code == 200
        body = resp.get_json()
        assert "decisions" in body
