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
from autonomous.trade_store import AutonomousTrade, TradeStore
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
    max_live_trades_per_day: int = 1,
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
        max_live_trades_per_day=max_live_trades_per_day,
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
        assert "continuous_supervisor" in body
        assert body["live_runner_config"]["live_enabled"] is True
        assert body["continuous_supervisor"]["state"] == "IDLE"
        assert body["continuous_supervisor"]["paused"] is False

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

    def test_dry_run_path_returns_outcome_label(self, app, client, tmp_path):
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
        body = resp.get_json()
        run_payload = body.get("run") or {}
        assert run_payload.get("outcome") == "LIVE_DRY_RUN_PREVIEW_ONLY"


# ---------------------------------------------------------------------------
# /api/autonomous/live/actual-live/activate
# ---------------------------------------------------------------------------


class TestActualLiveActivate:
    """Tests for the Actual Live Trading activation endpoint."""

    VALID_PAYLOAD = {
        "confirm": True,
        "account_mode": "live",
        "trading_cycle": "single_trade",
        "expected_account_id": "U1234567",
        "confirmed_by": "test-operator",
        "confirmation_phrase": "ENABLE ACTUAL LIVE TRADING",
        "acknowledge_real_money_risk": True,
    }

    def test_rejects_missing_confirm(self, app, client, tmp_path):
        _install_live_runner(app, tmp_path)
        payload = {**self.VALID_PAYLOAD, "confirm": False}
        resp = client.post("/api/autonomous/live/actual-live/activate", json=payload)
        assert resp.status_code == 400
        assert resp.get_json()["outcome"] == "LIVE_ORDER_REJECTED"

    def test_rejects_wrong_account_mode(self, app, client, tmp_path):
        _install_live_runner(app, tmp_path)
        payload = {**self.VALID_PAYLOAD, "account_mode": "paper"}
        resp = client.post("/api/autonomous/live/actual-live/activate", json=payload)
        assert resp.status_code == 400
        assert "account_mode" in resp.get_json()["error"]

    def test_accepts_continuous_cycle(self, app, client, tmp_path):
        """Continuous mode is permitted when max_live_trades_per_day > 1 and
        bracket-at-entry attaches target+stop child orders at TWS, so exits
        don't depend on the runner staying ON between cycles."""
        _install_live_runner(app, tmp_path, max_live_trades_per_day=3)
        payload = {**self.VALID_PAYLOAD, "trading_cycle": "continuous"}
        resp = client.post("/api/autonomous/live/actual-live/activate", json=payload)
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["status"] in ("activated", "halted")

    def test_single_trade_activation_does_not_mutate_shared_daily_cap(
        self, app, client, tmp_path
    ):
        _install_live_runner(app, tmp_path, max_live_trades_per_day=3)
        resp = client.post("/api/autonomous/live/actual-live/activate", json=self.VALID_PAYLOAD)
        assert resp.status_code == 200
        with app.app_context():
            cfg = app.config.get("autonomous_live_runner_config")
            assert cfg is not None
            assert cfg.max_live_trades_per_day == 3

    def test_rejects_continuous_when_daily_cap_is_one(self, app, client, tmp_path):
        """Actual-live continuous activation must be rejected when the configured
        max_live_trades_per_day is still at the default of 1, because continuous
        mode cannot make progress with a cap of one."""
        _install_live_runner(app, tmp_path, max_live_trades_per_day=1)
        payload = {**self.VALID_PAYLOAD, "trading_cycle": "continuous"}
        resp = client.post("/api/autonomous/live/actual-live/activate", json=payload)
        assert resp.status_code == 400
        body = resp.get_json()
        assert body["outcome"] == "LIVE_ORDER_REJECTED"
        assert "continuous_cap_too_low" in body["rejection_reason"]

    def test_passes_continuous_mode_into_actual_live_runner(self, app, client, tmp_path):
        _install_live_runner(app, tmp_path, max_live_trades_per_day=3)
        base_factory = app.config["autonomous_live_runner_factory"]
        seen = {"continuous_mode": None}

        def tracking_factory(cfg, continuous_mode=False):
            seen["continuous_mode"] = continuous_mode
            return base_factory(cfg, continuous_mode=continuous_mode)

        app.config["autonomous_live_runner_factory"] = tracking_factory

        payload = {**self.VALID_PAYLOAD, "trading_cycle": "continuous"}
        resp = client.post("/api/autonomous/live/actual-live/activate", json=payload)
        assert resp.status_code == 200
        assert seen["continuous_mode"] is True

    def test_rejects_missing_expected_account_id(self, app, client, tmp_path):
        _install_live_runner(app, tmp_path)
        payload = {**self.VALID_PAYLOAD, "expected_account_id": ""}
        resp = client.post("/api/autonomous/live/actual-live/activate", json=payload)
        assert resp.status_code == 400
        assert "expected_account_id" in resp.get_json()["error"]

    def test_rejects_missing_confirmed_by(self, app, client, tmp_path):
        _install_live_runner(app, tmp_path)
        payload = {**self.VALID_PAYLOAD, "confirmed_by": ""}
        resp = client.post("/api/autonomous/live/actual-live/activate", json=payload)
        assert resp.status_code == 400
        assert "confirmed_by" in resp.get_json()["error"]

    def test_rejects_wrong_confirmation_phrase(self, app, client, tmp_path):
        _install_live_runner(app, tmp_path)
        payload = {**self.VALID_PAYLOAD, "confirmation_phrase": "WRONG"}
        resp = client.post("/api/autonomous/live/actual-live/activate", json=payload)
        assert resp.status_code == 400
        assert "confirmation_phrase" in resp.get_json()["error"]

    def test_rejects_no_risk_acknowledgement(self, app, client, tmp_path):
        _install_live_runner(app, tmp_path)
        payload = {**self.VALID_PAYLOAD, "acknowledge_real_money_risk": False}
        resp = client.post("/api/autonomous/live/actual-live/activate", json=payload)
        assert resp.status_code == 400
        assert "acknowledge_real_money_risk" in resp.get_json()["error"]

    def test_successful_activation_submits_order(self, app, client, tmp_path):
        """When all confirmations pass, the order is submitted and returns order ID."""
        store, executor = _install_live_runner(app, tmp_path)
        resp = client.post(
            "/api/autonomous/live/actual-live/activate", json=self.VALID_PAYLOAD
        )
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["status"] in ("activated", "halted")
        run_payload = body.get("run") or {}
        # The _SubmittingExecutor returns order 7777
        assert run_payload.get("outcome") == "LIVE_ORDER_SUBMITTED"
        # Verify the executor was actually called
        assert len(executor.calls) == 1

    def test_rejected_when_account_id_mismatch(self, app, client, tmp_path):
        """Rejects when expected_account_id does not match detected."""
        _install_live_runner(app, tmp_path, account_id="DU999999")
        payload = {**self.VALID_PAYLOAD, "expected_account_id": "U1234567"}
        resp = client.post(
            "/api/autonomous/live/actual-live/activate", json=payload
        )
        # Gates will reject because account_id doesn't match expected
        assert resp.status_code == 409
        body = resp.get_json()
        assert body["outcome"] == "LIVE_ORDER_REJECTED"

    def test_rejected_when_live_disabled(self, app, client, tmp_path):
        """Rejects when AUTONOMOUS_LIVE_ENABLED=false."""
        _install_live_runner(app, tmp_path, live_enabled=False)
        resp = client.post(
            "/api/autonomous/live/actual-live/activate", json=self.VALID_PAYLOAD
        )
        assert resp.status_code == 409
        body = resp.get_json()
        assert body["outcome"] == "LIVE_ORDER_REJECTED"

    def test_rejected_when_emergency_stop_active(self, app, client, tmp_path):
        """Rejects when emergency stop is active."""
        store_path = tmp_path / "live_trades.jsonl"
        store = TradeStore(path=str(store_path))
        live_cfg = AutonomousLiveRunnerConfig(
            live_enabled=True,
            live_continuous_enabled=True,
            expected_account_id="U1234567",
            trade_store_path=str(store_path),
        )
        signals = [_signal()]
        scanner = CandidateScanner(
            signal_provider=StaticSignalProvider(signals),
            symbols=[{"symbol": "AAA", "security": "AAA", "sector": "X", "sub_industry": ""}],
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

        def factory(cfg, continuous_mode=False):
            return AutonomousLiveRunner(
                engine=engine,
                trade_store=store,
                live_config=cfg,
                order_executor=_SubmittingExecutor(),
                connected_provider=lambda: True,
                connection_env_provider=lambda: "live",
                account_id_provider=lambda: "U1234567",
                signal_provider_provider=lambda: _RealProvider(),
                emergency_stop_provider=lambda: True,  # ESTOP active
                deployable_cash_provider=lambda: 50_000.0,
                continuous_mode=continuous_mode,
            )

        app.config["autonomous_live_runner_factory"] = factory
        app.config["autonomous_live_runner_config"] = live_cfg
        app.config["autonomous_spy_price_provider"] = lambda: {"open": 100.0, "current": 105.0}

        resp = client.post(
            "/api/autonomous/live/actual-live/activate", json=self.VALID_PAYLOAD
        )
        assert resp.status_code == 409
        body = resp.get_json()
        assert body["outcome"] == "LIVE_ORDER_REJECTED"

    def test_no_trade_when_no_signals(self, app, client, tmp_path):
        """Returns NO_TRADE when no qualifying candidates."""
        _install_live_runner(app, tmp_path, with_signal=False)
        resp = client.post(
            "/api/autonomous/live/actual-live/activate", json=self.VALID_PAYLOAD
        )
        assert resp.status_code == 200
        body = resp.get_json()
        run_payload = body.get("run") or {}
        assert run_payload.get("outcome") == "NO_TRADE"

    def test_dry_run_false_in_config(self, app, client, tmp_path):
        """Verifies the actual-live path sets dry_run=False in runner config."""
        _install_live_runner(app, tmp_path)
        resp = client.post(
            "/api/autonomous/live/actual-live/activate", json=self.VALID_PAYLOAD
        )
        assert resp.status_code == 200
        # Verify the persisted dry_run flag is False
        with app.app_context():
            assert app.config.get("autonomous_live_dry_run") is False

    def test_persists_confirmation_and_account_id_for_continuous_cycles(
        self, app, client, tmp_path
    ):
        """After actual-live activation the app config holds the confirmation
        and expected_account_id so that subsequent continuous cycles can rebuild
        a verified actual-live executor."""
        _install_live_runner(app, tmp_path, max_live_trades_per_day=3)
        payload = {**self.VALID_PAYLOAD, "trading_cycle": "continuous"}
        resp = client.post("/api/autonomous/live/actual-live/activate", json=payload)
        assert resp.status_code == 200
        with app.app_context():
            assert app.config.get("autonomous_live_expected_account_id") == "U1234567"
            assert app.config.get("autonomous_live_confirmation") is not None
            assert app.config.get("autonomous_live_dry_run") is False


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


class TestAutonomousEmergencyStop:
    def test_stop_pauses_supervisor_and_reports_visibility(self, app, client, tmp_path):
        _install_live_runner(app, tmp_path)

        from autonomous.autonomous_mode import (
            AccountMode,
            AutonomousModeState,
            TradingCycle,
        )

        state = AutonomousModeState()
        state.turn_on(TradingCycle.CONTINUOUS, AccountMode.LIVE, dry_run=True)
        app.config["autonomous_live_mode_state"] = state

        resp = client.post(
            "/api/autonomous/emergency-stop",
            json={"reason": "operator stop"},
        )

        assert resp.status_code == 200
        body = resp.get_json()
        assert body["status"] == "halted"
        assert body["emergency_stop"]["active"] is True
        assert body["emergency_stop"]["manual_reset_required"] is True
        assert body["emergency_stop"]["panic_flatten_available"] is False
        assert body["continuous_supervisor"]["paused"] is True
        assert body["continuous_supervisor"]["pause_reason"] == "emergency_stop_active"
        assert body["autonomous_live_mode"]["operating_state"] == "OFF"

        live_status = client.get("/api/autonomous/live/status")
        assert live_status.status_code == 200
        assert live_status.get_json()["emergency_stop"]["active"] is True

    def test_stop_optionally_cancels_only_pending_entry_orders(
        self, app, client, tmp_path
    ):
        _install_live_runner(app, tmp_path)
        cancelled = []

        def cancel_order(order_id):
            cancelled.append(order_id)
            return True

        app.config["autonomous_cancel_order"] = cancel_order

        with app.app_context():
            store = app.config["autonomous_live_trade_store"]
            store.record_trade(
                AutonomousTrade(
                    autonomous_trade_id="pending-entry",
                    symbol="AAPL",
                    trade_type="BUY_SHARES",
                    status="OPEN",
                    entry_order_id=777,
                    entry_time=datetime.now(timezone.utc),
                    entry_limit_price=150.0,
                    quantity=10,
                    target_order_id=778,
                    stop_order_id=779,
                    notes=["recorded by AutonomousLiveRunner", "dry_run=False"],
                )
            )

        resp = client.post(
            "/api/autonomous/emergency-stop",
            json={
                "reason": "cancel pending entries",
                "cancel_pending_entries": True,
            },
        )

        assert resp.status_code == 200
        body = resp.get_json()
        cleanup = body["pending_entry_cleanup"]
        assert cleanup["requested"] is True
        assert cleanup["pending_entry_order_count"] == 1
        assert cleanup["cancel_forwarded_count"] == 1
        assert cancelled == [777]
        assert cleanup["protective_exit_order_count"] == 2
        preserved_ids = {
            item["order_id"]
            for item in cleanup["protective_exit_orders_preserved"]
        }
        assert preserved_ids == {778, 779}
        assert 778 not in cancelled
        assert 779 not in cancelled

        with app.app_context():
            trade = app.config["autonomous_live_trade_store"].get("pending-entry")
            assert trade.status == "OPEN"

    def test_stop_does_not_cancel_entries_unless_requested(
        self, app, client, tmp_path
    ):
        _install_live_runner(app, tmp_path)
        cancelled = []

        def cancel_order(order_id):
            cancelled.append(order_id)
            return True

        app.config["autonomous_cancel_order"] = cancel_order

        with app.app_context():
            store = app.config["autonomous_live_trade_store"]
            store.record_trade(
                AutonomousTrade(
                    autonomous_trade_id="pending-entry",
                    symbol="MSFT",
                    trade_type="BUY_SHARES",
                    status="OPEN",
                    entry_order_id=880,
                    entry_time=datetime.now(timezone.utc),
                    entry_limit_price=300.0,
                    quantity=5,
                )
            )

        resp = client.post(
            "/api/autonomous/emergency-stop",
            json={"reason": "plain stop"},
        )

        assert resp.status_code == 200
        cleanup = resp.get_json()["pending_entry_cleanup"]
        assert cleanup["requested"] is False
        assert cleanup["pending_entry_order_count"] == 1
        assert cleanup["cancel_forwarded_count"] == 0
        assert cancelled == []

    def test_reset_requires_confirmation_and_is_audited(
        self, app, client, tmp_path
    ):
        _install_live_runner(app, tmp_path)
        app.config["autonomous_audit_log_dir"] = str(tmp_path / "audit")

        stop = client.post(
            "/api/autonomous/emergency-stop",
            json={"reason": "reset test"},
        )
        assert stop.status_code == 200

        rejected = client.post(
            "/api/autonomous/emergency-reset",
            json={"reason": "missing confirm"},
        )
        assert rejected.status_code == 400
        assert rejected.get_json()["status"] == "confirmation_required"

        reset = client.post(
            "/api/autonomous/emergency-reset",
            json={"reason": "operator reviewed", "confirm": True},
        )
        assert reset.status_code == 200
        body = reset.get_json()
        assert body["status"] == "reset"
        assert body["emergency_stop"]["active"] is False
        assert body["autonomous_live_mode"]["operating_state"] == "OFF"
        assert body["continuous_supervisor"]["paused"] is False

        audit_files = list((tmp_path / "audit").glob("autonomous_trading_*.jsonl"))
        assert audit_files
        audit_text = audit_files[0].read_text(encoding="utf-8")
        assert '"event": "emergency_reset"' in audit_text
        assert '"mode_remains_off": true' in audit_text


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
        # Activate live mode state in dry-run (the default) so the executor
        # build succeeds through the test runner factory without a real TWS
        # connection.
        state = AutonomousModeState()
        state.turn_on(TradingCycle.CONTINUOUS, AccountMode.LIVE, dry_run=True)
        app.config["autonomous_live_mode_state"] = state

        resp = client.post("/api/autonomous/live/run-once", json={})
        assert resp.status_code == 200
        body = resp.get_json()
        assert "status" in body

    def test_actual_live_run_once_rejected_without_confirmation(
        self, app, client, tmp_path, monkeypatch
    ):
        """When mode is ON with dry_run=False (actual-live) and no valid
        LiveTradingConfirmation is stored, run-once must fail closed."""
        from autonomous.autonomous_mode import AutonomousModeState, TradingCycle, AccountMode
        _install_live_runner(app, tmp_path)
        state = AutonomousModeState()
        state.turn_on(TradingCycle.SINGLE_TRADE, AccountMode.LIVE, dry_run=False)

        # Monkeypatch services so the connectivity checks pass and we reach
        # the confirmation validation step.
        monkeypatch.setattr("web.services.ServiceManager.connected", True)
        monkeypatch.setattr("web.services.ServiceManager.connection_env", "live")
        monkeypatch.setattr(
            "web.services.ServiceManager.connection_info",
            {"account": "U1234567", "port": 7496, "host": "127.0.0.1"},
        )

        class _ConnectedBridge:
            is_connected = True

        monkeypatch.setattr("web.services.ServiceManager.tws_bridge", _ConnectedBridge())

        with app.app_context():
            app.config["autonomous_live_mode_state"] = state
            app.config["autonomous_live_expected_account_id"] = "U1234567"
            app.config["autonomous_live_confirmation"] = None  # no confirmation

        resp = client.post("/api/autonomous/live/run-once", json={})
        assert resp.status_code == 400
        body = resp.get_json()
        assert body.get("rejection_reason") == "confirmation_missing"


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

    def test_activate_persists_dry_run_flag_in_app_config(
        self, app, client, tmp_path
    ):
        """Activation should persist dry-run intent for subsequent lifecycle calls."""
        _install_live_runner(app, tmp_path, dry_run=False)
        with app.app_context():
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
            assert app.config.get("autonomous_live_dry_run") is True

    def test_run_once_uses_persisted_dry_run_when_config_rebuilds(
        self, app, client, monkeypatch
    ):
        """run-once must use activation-time dry-run state even without fixed app config."""

        seen_dry_run: list[bool] = []

        class _ReadyGates:
            ready = True

            def reasons(self):
                return []

            def to_dict(self):
                return {
                    "ready": True,
                    "reasons": [],
                    "live_mode": True,
                    "live_enabled": True,
                    "account_id_verified": True,
                    "signal_provider_ready": True,
                    "emergency_stop_active": False,
                    "connected": True,
                }

        class _Result:
            status = DRY_RUN_EXECUTED
            decision = {}

            def to_dict(self):
                return {"status": DRY_RUN_EXECUTED, "decision": {}}

        class _Runner:
            def __init__(self, cfg):
                self._cfg = cfg

            def evaluate_gates(self):
                return _ReadyGates()

            def run_once(self):
                seen_dry_run.append(bool(self._cfg.live_dry_run))
                return _Result()

        def _factory(cfg, continuous_mode=False):
            return _Runner(cfg)

        app.config["autonomous_live_runner_factory"] = _factory
        app.config["autonomous_spy_price_provider"] = lambda: {
            "open": 100.0,
            "current": 105.0,
        }
        app.config.pop("autonomous_live_runner_config", None)
        app.config.pop("autonomous_live_dry_run", None)

        monkeypatch.setenv("AUTONOMOUS_LIVE_DRY_RUN", "false")

        with app.app_context():
            activate = client.post(
                "/api/autonomous/live/activate",
                json={
                    "confirm": True,
                    "account_mode": "live",
                    "trading_cycle": "single_trade",
                    "expected_account_id": "U1234567",
                    "dry_run": True,
                },
            )
            assert activate.status_code == 200
            assert app.config.get("autonomous_live_dry_run") is True

            run_once = client.post("/api/autonomous/live/run-once", json={})
            assert run_once.status_code == 200

        # First run is from activation; second is explicit /live/run-once.
        assert seen_dry_run[:2] == [True, True]


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


# ---------------------------------------------------------------------------
# Regression tests for review issues #1, #2, #3, #4, #6
# These tests exercise the actual endpoint flow without relying solely on
# runner factory overrides.
# ---------------------------------------------------------------------------


class _RejectingExecutor:
    """Executor that simulates an execution_failed / engine_rejected status."""

    def __init__(self, status=OrderStatus.REJECTED, reason="engine_rejected"):
        self._status = status
        self._reason = reason
        self.calls = []

    def execute_signal(self, strategy_name, signal, current_equity, positions):
        self.calls.append({"symbol": signal.symbol})
        return OrderResult(
            status=self._status,
            order_id=None,
            signal=signal,
            quantity=signal.quantity or 1,
            price=signal.target_price or 0.0,
            reason=self._reason,
        )


class TestActualLiveExecutorOrdering:
    """Regression tests ensuring executor is wired BEFORE runner.run_once()."""

    VALID_PAYLOAD = {
        "confirm": True,
        "account_mode": "live",
        "trading_cycle": "single_trade",
        "expected_account_id": "U1234567",
        "confirmed_by": "test-operator",
        "confirmation_phrase": "ENABLE ACTUAL LIVE TRADING",
        "acknowledge_real_money_risk": True,
    }

    def test_runner_receives_executor_at_construction_time(self, app, client, tmp_path):
        """The factory receives config so the runner is built with the correct
        executor at construction time, not after."""
        captured_executors = []

        def factory(cfg, continuous_mode=False):
            store_path = tmp_path / "live_trades.jsonl"
            store = TradeStore(path=str(store_path))
            signals = [_signal()]
            scanner = CandidateScanner(
                signal_provider=StaticSignalProvider(signals),
                symbols=[{"symbol": "AAA", "security": "AAA", "sector": "X", "sub_industry": ""}],
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
            executor = _SubmittingExecutor()
            captured_executors.append(executor)
            runner = AutonomousLiveRunner(
                engine=engine,
                trade_store=store,
                live_config=cfg,
                order_executor=executor,
                connected_provider=lambda: True,
                connection_env_provider=lambda: "live",
                account_id_provider=lambda: "U1234567",
                signal_provider_provider=lambda: _RealProvider(),
                emergency_stop_provider=lambda: False,
                deployable_cash_provider=lambda: 50_000.0,
                continuous_mode=continuous_mode,
            )
            # Verify: executor is already attached at construction
            assert runner.order_executor is executor
            return runner

        app.config["autonomous_live_runner_factory"] = factory
        app.config["autonomous_spy_price_provider"] = lambda: {"open": 100.0, "current": 105.0}
        app.config["autonomous_live_runner_config"] = AutonomousLiveRunnerConfig(
            live_enabled=True,
            live_continuous_enabled=True,
            expected_account_id="U1234567",
            trade_store_path=str(tmp_path / "live_trades.jsonl"),
        )

        resp = client.post(
            "/api/autonomous/live/actual-live/activate", json=self.VALID_PAYLOAD
        )
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["run"]["outcome"] == "LIVE_ORDER_SUBMITTED"
        # Verify that the factory was called (not bypassed)
        assert len(captured_executors) == 1
        assert len(captured_executors[0].calls) == 1


class TestActualLiveAdapterConnection:
    """Regression tests ensuring adapter connectivity is verified."""

    VALID_PAYLOAD = {
        "confirm": True,
        "account_mode": "live",
        "trading_cycle": "single_trade",
        "expected_account_id": "U1234567",
        "confirmed_by": "test-operator",
        "confirmation_phrase": "ENABLE ACTUAL LIVE TRADING",
        "acknowledge_real_money_risk": True,
    }

    def test_returns_503_when_adapter_not_connected(self, app, client, tmp_path, monkeypatch):
        """Without a factory override, the production path reuses the
        persistent TWSBridge as the OrderExecutor adapter.  If the bridge
        is not connected (or absent), the endpoint must return 503."""
        # Do NOT install a runner factory — exercise the production code path
        app.config["autonomous_spy_price_provider"] = lambda: {"open": 100.0, "current": 105.0}
        # Mock service as connected with live environment so we reach the
        # bridge check.  No tws_bridge is set, so the bridge-not-connected
        # branch fires.
        monkeypatch.setattr(
            "web.services.ServiceManager.connected", True
        )
        monkeypatch.setattr(
            "web.services.ServiceManager.connection_env", "live"
        )
        monkeypatch.setattr(
            "web.services.ServiceManager.connection_info",
            {"account": "U1234567", "port": 7496, "host": "127.0.0.1"},
        )
        # Explicitly assert there is no bridge so the production path hits
        # the bridge_not_connected guard rather than any cached adapter.
        monkeypatch.setattr(
            "web.services.ServiceManager.tws_bridge", None
        )

        resp = client.post(
            "/api/autonomous/live/actual-live/activate", json=self.VALID_PAYLOAD
        )
        assert resp.status_code == 503
        body = resp.get_json()
        assert body["outcome"] == "LIVE_ORDER_REJECTED"
        assert body["rejection_reason"] == "tws_not_connected"

    def test_returns_400_when_detected_account_missing(self, app, client, tmp_path, monkeypatch):
        """When the service is connected/live but the detected account ID has not
        been populated yet, the endpoint must reject before building an adapter."""
        app.config["autonomous_spy_price_provider"] = lambda: {"open": 100.0, "current": 105.0}
        monkeypatch.setattr("web.services.ServiceManager.connected", True)
        monkeypatch.setattr("web.services.ServiceManager.connection_env", "live")
        # account is empty — not yet populated
        monkeypatch.setattr(
            "web.services.ServiceManager.connection_info",
            {"account": "", "port": 7496, "host": "127.0.0.1"},
        )

        resp = client.post(
            "/api/autonomous/live/actual-live/activate", json=self.VALID_PAYLOAD
        )
        assert resp.status_code == 400
        body = resp.get_json()
        assert body["outcome"] == "LIVE_ORDER_REJECTED"
        assert body["rejection_reason"] == "account_id_unavailable"


class TestDryRunBleedThroughPrevention:
    """Regression tests ensuring dry-run cannot reuse an actual-live executor."""

    VALID_PAYLOAD = {
        "confirm": True,
        "account_mode": "live",
        "trading_cycle": "single_trade",
        "expected_account_id": "U1234567",
        "confirmed_by": "test-operator",
        "confirmation_phrase": "ENABLE ACTUAL LIVE TRADING",
        "acknowledge_real_money_risk": True,
    }

    def test_dry_run_after_actual_live_cannot_submit_real_orders(
        self, app, client, tmp_path
    ):
        """After an actual-live activation, the _build_live_runner default path
        builds a fresh executor (no bleed-through from the actual-live executor).
        The executor's dry_run flag follows live_config.live_dry_run."""
        # Step 1: Perform an actual-live activation
        store, executor = _install_live_runner(app, tmp_path)
        resp = client.post(
            "/api/autonomous/live/actual-live/activate", json=self.VALID_PAYLOAD
        )
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["run"]["outcome"] == "LIVE_ORDER_SUBMITTED"

        # Step 2: Verify the default _build_live_runner path (no executor_override)
        # builds a fresh executor whose dry_run follows live_config.live_dry_run.
        from web.routes.api_autonomous import _build_live_runner

        with app.app_context():
            # Remove the factory to exercise the real default path
            saved_factory = app.config.pop("autonomous_live_runner_factory", None)
            try:
                # With live_dry_run=True the executor must be dry-run.
                live_config_dry = AutonomousLiveRunnerConfig(
                    live_enabled=True,
                    live_continuous_enabled=True,
                    expected_account_id="U1234567",
                    live_dry_run=True,
                    trade_store_path=str(tmp_path / "t.jsonl"),
                )
                runner_dry = _build_live_runner(live_config_dry, continuous_mode=False)
                assert runner_dry.order_executor is not None
                assert runner_dry.order_executor.dry_run is True

                # With live_dry_run=False the executor must NOT be dry-run,
                # keeping runner config and executor in sync.
                live_config_live = AutonomousLiveRunnerConfig(
                    live_enabled=True,
                    live_continuous_enabled=True,
                    expected_account_id="U1234567",
                    live_dry_run=False,
                    trade_store_path=str(tmp_path / "t2.jsonl"),
                )
                runner_live = _build_live_runner(live_config_live, continuous_mode=False)
                assert runner_live.order_executor is not None
                assert runner_live.order_executor.dry_run is False
            finally:
                if saved_factory:
                    app.config["autonomous_live_runner_factory"] = saved_factory

    def test_build_live_runner_default_executor_follows_live_dry_run(
        self, app, client, tmp_path
    ):
        """_build_live_runner without executor_override builds an executor whose
        dry_run flag mirrors live_config.live_dry_run (tws_adapter is always None)."""
        from web.routes.api_autonomous import _build_live_runner
        from autonomous.runner_config import AutonomousLiveRunnerConfig

        app.config["autonomous_spy_price_provider"] = lambda: {"open": 100.0, "current": 105.0}
        # Ensure no factory override
        app.config.pop("autonomous_live_runner_factory", None)

        with app.app_context():
            # dry_run=True when live_dry_run=True
            live_config_dry = AutonomousLiveRunnerConfig(
                live_enabled=True,
                live_continuous_enabled=True,
                expected_account_id="U1234567",
                live_dry_run=True,
                trade_store_path=str(tmp_path / "t.jsonl"),
            )
            runner_dry = _build_live_runner(live_config_dry, continuous_mode=False)
            assert runner_dry.order_executor is not None
            assert runner_dry.order_executor.dry_run is True

            # dry_run=False when live_dry_run=False
            live_config_live = AutonomousLiveRunnerConfig(
                live_enabled=True,
                live_continuous_enabled=True,
                expected_account_id="U1234567",
                live_dry_run=False,
                trade_store_path=str(tmp_path / "t2.jsonl"),
            )
            runner_live = _build_live_runner(live_config_live, continuous_mode=False)
            assert runner_live.order_executor is not None
            assert runner_live.order_executor.dry_run is False


class TestActualLiveAllStatusesTurnOff:
    """Regression: all non-executed statuses turn mode OFF in v1."""

    VALID_PAYLOAD = {
        "confirm": True,
        "account_mode": "live",
        "trading_cycle": "single_trade",
        "expected_account_id": "U1234567",
        "confirmed_by": "test-operator",
        "confirmation_phrase": "ENABLE ACTUAL LIVE TRADING",
        "acknowledge_real_money_risk": True,
    }

    def _install_with_executor(self, app, tmp_path, executor):
        """Install a runner factory with a custom executor."""
        store_path = tmp_path / "live_trades.jsonl"
        store = TradeStore(path=str(store_path))
        signals = [_signal()]
        scanner = CandidateScanner(
            signal_provider=StaticSignalProvider(signals),
            symbols=[{"symbol": "AAA", "security": "AAA", "sector": "X", "sub_industry": ""}],
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

        def factory(cfg, continuous_mode=False):
            return AutonomousLiveRunner(
                engine=engine,
                trade_store=store,
                live_config=cfg,
                order_executor=executor,
                connected_provider=lambda: True,
                connection_env_provider=lambda: "live",
                account_id_provider=lambda: "U1234567",
                signal_provider_provider=lambda: _RealProvider(),
                emergency_stop_provider=lambda: False,
                deployable_cash_provider=lambda: 50_000.0,
                continuous_mode=continuous_mode,
            )

        app.config["autonomous_live_runner_factory"] = factory
        app.config["autonomous_spy_price_provider"] = lambda: {"open": 100.0, "current": 105.0}
        app.config["autonomous_live_runner_config"] = AutonomousLiveRunnerConfig(
            live_enabled=True,
            live_continuous_enabled=True,
            expected_account_id="U1234567",
            trade_store_path=str(store_path),
        )

    def test_execution_failed_turns_mode_off(self, app, client, tmp_path):
        """execution_failed status turns mode OFF."""
        executor = _RejectingExecutor(
            status=OrderStatus.REJECTED, reason="execution_failed"
        )
        self._install_with_executor(app, tmp_path, executor)
        resp = client.post(
            "/api/autonomous/live/actual-live/activate", json=self.VALID_PAYLOAD
        )
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["status"] == "halted"
        assert body["run"]["outcome"] == "LIVE_ORDER_REJECTED"

    def test_engine_rejected_turns_mode_off(self, app, client, tmp_path):
        """engine_rejected status turns mode OFF."""
        executor = _RejectingExecutor(
            status=OrderStatus.REJECTED, reason="engine_rejected"
        )
        self._install_with_executor(app, tmp_path, executor)
        resp = client.post(
            "/api/autonomous/live/actual-live/activate", json=self.VALID_PAYLOAD
        )
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["status"] == "halted"
        assert body["run"]["outcome"] == "LIVE_ORDER_REJECTED"

    def test_no_trade_turns_mode_off(self, app, client, tmp_path):
        """no_trade status turns mode OFF."""
        _install_live_runner(app, tmp_path, with_signal=False)
        resp = client.post(
            "/api/autonomous/live/actual-live/activate", json=self.VALID_PAYLOAD
        )
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["status"] == "halted"

    def test_executed_turns_mode_off_v1_entry_only(self, app, client, tmp_path):
        """v1 entry-only: 'executed' also turns mode OFF after entry submission."""
        _install_live_runner(app, tmp_path)
        resp = client.post(
            "/api/autonomous/live/actual-live/activate", json=self.VALID_PAYLOAD
        )
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["run"]["outcome"] == "LIVE_ORDER_SUBMITTED"
        # v1 entry-only: mode turns OFF even on success
        assert body["status"] == "halted"
        state = body["autonomous_live_mode"]
        assert state["operating_state"] == "OFF"


# ---------------------------------------------------------------------------
# Regression: actual-live post-entry exit lifecycle
# ---------------------------------------------------------------------------


class TestActualLivePostEntryExitBehavior:
    """Regression tests ensuring that after a successful actual-live entry,
    the exit endpoint fails closed and cannot silently dry-run actual-live
    trades.

    These tests verify:
    1. Actual-live entry succeeds and turns mode OFF (v1 entry-only).
    2. /live/evaluate-exits rejects when actual-live mode is ON with no real
       executor (fail-closed guard).
    3. A dry-run executor cannot mark an actual-live trade EXIT_PENDING.
    """

    VALID_PAYLOAD = {
        "confirm": True,
        "account_mode": "live",
        "trading_cycle": "single_trade",
        "expected_account_id": "U1234567",
        "confirmed_by": "test-operator",
        "confirmation_phrase": "ENABLE ACTUAL LIVE TRADING",
        "acknowledge_real_money_risk": True,
    }

    def test_actual_live_entry_turns_mode_off(self, app, client, tmp_path):
        """After successful actual-live entry, mode is OFF (v1 entry-only)."""
        _install_live_runner(app, tmp_path)
        resp = client.post(
            "/api/autonomous/live/actual-live/activate", json=self.VALID_PAYLOAD
        )
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["run"]["outcome"] == "LIVE_ORDER_SUBMITTED"
        # Mode turned OFF — exit management is manual for v1
        assert body["status"] == "halted"
        assert body["autonomous_live_mode"]["operating_state"] == "OFF"

    def test_exit_rejects_when_actual_live_mode_on_no_executor(
        self, app, client, tmp_path
    ):
        """If actual-live mode is somehow ON without a real executor,
        /live/evaluate-exits must fail closed (400) instead of silently
        using a dry-run executor."""
        _install_live_runner(app, tmp_path)
        # Manually force mode ON with dry_run=False to simulate the scenario
        # where mode was left ON (shouldn't happen in v1, but tests the guard)
        from autonomous.autonomous_mode import (
            AccountMode,
            AutonomousModeState,
            AutonomousOperatingState,
            TradingCycle,
        )

        with app.app_context():
            state = AutonomousModeState()
            state.turn_on(TradingCycle.SINGLE_TRADE, AccountMode.LIVE, dry_run=False)
            app.config["autonomous_live_mode_state"] = state
            # Ensure no global executor is stored
            app.config.pop("autonomous_live_order_executor", None)

        resp = client.post("/api/autonomous/live/evaluate-exits", json={})
        assert resp.status_code == 400
        body = resp.get_json()
        assert body["outcome"] == "NO_EXIT"
        assert "manual" in body["reason"].lower()

    def test_exit_rejects_dry_run_executor_for_actual_live_trades(
        self, app, client, tmp_path
    ):
        """If a dry-run executor is stored globally while mode is actual-live,
        the exit endpoint must reject rather than allow the dry-run executor
        to mark actual-live trades EXIT_PENDING."""
        _install_live_runner(app, tmp_path)
        from autonomous.autonomous_mode import (
            AccountMode,
            AutonomousModeState,
            AutonomousOperatingState,
            TradingCycle,
        )

        with app.app_context():
            state = AutonomousModeState()
            state.turn_on(TradingCycle.SINGLE_TRADE, AccountMode.LIVE, dry_run=False)
            app.config["autonomous_live_mode_state"] = state
            # Store a dry-run executor globally (simulates bleed-through risk)
            dry_executor = _DryRunExecutor()
            dry_executor.dry_run = True
            app.config["autonomous_live_order_executor"] = dry_executor

        resp = client.post("/api/autonomous/live/evaluate-exits", json={})
        assert resp.status_code == 400
        body = resp.get_json()
        assert body["outcome"] == "NO_EXIT"
        assert "dry-run" in body["reason"].lower()

    def test_exit_allowed_for_dry_run_mode(self, app, client, tmp_path):
        """When mode is dry-run (dry_run=True), exit evaluation works normally
        even with a dry-run executor — no false rejection."""
        _install_live_runner(app, tmp_path)
        from autonomous.autonomous_mode import (
            AccountMode,
            AutonomousModeState,
            TradingCycle,
        )

        with app.app_context():
            state = AutonomousModeState()
            state.turn_on(TradingCycle.SINGLE_TRADE, AccountMode.LIVE, dry_run=True)
            app.config["autonomous_live_mode_state"] = state

        resp = client.post("/api/autonomous/live/evaluate-exits", json={})
        assert resp.status_code == 200
        body = resp.get_json()
        assert "decisions" in body

    def test_exit_allowed_when_mode_off_no_actual_live_trades(self, app, client, tmp_path):
        """When mode is OFF and no actual-live trades are open in the store,
        exit evaluation proceeds normally with a dry-run executor."""
        _install_live_runner(app, tmp_path)
        resp = client.post("/api/autonomous/live/evaluate-exits", json={})
        assert resp.status_code == 200
        body = resp.get_json()
        assert "decisions" in body

    def test_exit_rejects_when_mode_off_but_actual_live_trades_open(
        self, app, client, tmp_path
    ):
        """After v1 entry-only (mode OFF), if the store still has open
        actual-live trades (dry_run=False in notes), the exit endpoint must
        fail closed — a dry-run executor must NOT mark these EXIT_PENDING."""
        _install_live_runner(app, tmp_path)
        from autonomous.trade_store import AutonomousTrade
        from datetime import datetime, timezone

        with app.app_context():
            store = app.config["autonomous_live_trade_store"]
            # Record an open actual-live trade (like the runner would)
            trade = AutonomousTrade(
                autonomous_trade_id="actual-live-123",
                symbol="AAPL",
                trade_type="BUY_SHARES",
                status="OPEN",
                entry_order_id=42,
                entry_time=datetime.now(timezone.utc),
                entry_limit_price=150.0,
                quantity=10,
                notes=["recorded by AutonomousLiveRunner", "dry_run=False"],
            )
            store.record_trade(trade)

        resp = client.post("/api/autonomous/live/evaluate-exits", json={})
        assert resp.status_code == 400
        body = resp.get_json()
        assert body["outcome"] == "NO_EXIT"
        assert "manual" in body["reason"].lower()

    def test_exit_rejects_partially_persisted_bracket_trade(
        self, app, client, tmp_path
    ):
        """A trade with only one bracket child ID must still be guarded as
        needing client-side exit management."""
        _install_live_runner(app, tmp_path)
        from autonomous.trade_store import AutonomousTrade
        from datetime import datetime, timezone

        with app.app_context():
            store = app.config["autonomous_live_trade_store"]
            trade = AutonomousTrade(
                autonomous_trade_id="actual-live-partial-bracket",
                symbol="AAPL",
                trade_type="BUY_SHARES",
                status="OPEN",
                entry_order_id=777,
                entry_time=datetime.now(timezone.utc),
                entry_limit_price=150.0,
                quantity=10,
                target_order_id=778,
                stop_order_id=None,
                notes=["recorded by AutonomousLiveRunner", "dry_run=False"],
            )
            store.record_trade(trade)

        resp = client.post("/api/autonomous/live/evaluate-exits", json={})
        assert resp.status_code == 400
        body = resp.get_json()
        assert body["outcome"] == "NO_EXIT"
        assert "manual" in body["reason"].lower()

    def test_exit_rejects_dry_run_executor_when_actual_live_trades_open(
        self, app, client, tmp_path
    ):
        """Even if a dry-run executor is globally stored, the exit endpoint
        must reject when there are open actual-live trades in the store."""
        _install_live_runner(app, tmp_path)
        from autonomous.trade_store import AutonomousTrade
        from datetime import datetime, timezone

        with app.app_context():
            store = app.config["autonomous_live_trade_store"]
            trade = AutonomousTrade(
                autonomous_trade_id="actual-live-456",
                symbol="MSFT",
                trade_type="BUY_SHARES",
                status="OPEN",
                entry_order_id=99,
                entry_time=datetime.now(timezone.utc),
                entry_limit_price=300.0,
                quantity=5,
                notes=["recorded by AutonomousLiveRunner", "dry_run=False"],
            )
            store.record_trade(trade)
            # Store a dry-run executor globally
            dry_executor = _DryRunExecutor()
            dry_executor.dry_run = True
            app.config["autonomous_live_order_executor"] = dry_executor

        resp = client.post("/api/autonomous/live/evaluate-exits", json={})
        assert resp.status_code == 400
        body = resp.get_json()
        assert body["outcome"] == "NO_EXIT"
        assert "dry-run" in body["reason"].lower()

    def test_exit_allowed_when_mode_off_only_dry_run_trades_open(
        self, app, client, tmp_path
    ):
        """When mode is OFF and only dry-run trades are open in the store
        (dry_run=True in notes), exit evaluation works normally — no false
        rejection for dry-run lifecycle trades."""
        _install_live_runner(app, tmp_path)
        from autonomous.trade_store import AutonomousTrade
        from datetime import datetime, timezone

        with app.app_context():
            store = app.config["autonomous_live_trade_store"]
            # Record an open dry-run trade (safe to exit with dry-run executor)
            trade = AutonomousTrade(
                autonomous_trade_id="dry-run-789",
                symbol="TSLA",
                trade_type="BUY_SHARES",
                status="OPEN",
                entry_order_id=0,
                entry_time=datetime.now(timezone.utc),
                entry_limit_price=200.0,
                quantity=3,
                notes=["recorded by AutonomousLiveRunner", "dry_run=True"],
            )
            store.record_trade(trade)

        resp = client.post("/api/autonomous/live/evaluate-exits", json={})
        assert resp.status_code == 200
        body = resp.get_json()
        assert "decisions" in body


class TestActualLiveFullLifecycleE2E:
    """End-to-end test: actual-live entry → mode OFF → exit evaluation fails
    closed for the actual-live trade in the store."""

    VALID_PAYLOAD = {
        "confirm": True,
        "account_mode": "live",
        "trading_cycle": "single_trade",
        "expected_account_id": "U1234567",
        "confirmed_by": "test-operator",
        "confirmation_phrase": "ENABLE ACTUAL LIVE TRADING",
        "acknowledge_real_money_risk": True,
    }

    def test_entry_then_exit_fails_closed_for_actual_live_trade(
        self, app, client, tmp_path
    ):
        """Full lifecycle: actual-live entry submits → mode OFF → evaluate-exits
        detects open actual-live trade in store → returns fail-closed 400.

        This prevents a dry-run executor from marking an actual-live trade
        EXIT_PENDING when no real exit order was submitted.
        """
        _install_live_runner(app, tmp_path)

        # Step 1: Submit actual-live entry
        resp = client.post(
            "/api/autonomous/live/actual-live/activate", json=self.VALID_PAYLOAD
        )
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["run"]["outcome"] == "LIVE_ORDER_SUBMITTED"
        # Mode is OFF (v1 entry-only)
        assert body["autonomous_live_mode"]["operating_state"] == "OFF"

        # Verify the trade is recorded in the store with dry_run=False
        with app.app_context():
            store = app.config["autonomous_live_trade_store"]
            open_trades = store.list_open()
            assert len(open_trades) >= 1
            actual_live_trade = open_trades[0]
            assert "dry_run=False" in actual_live_trade.notes

        # Step 2: Call evaluate-exits — should fail closed
        resp = client.post("/api/autonomous/live/evaluate-exits", json={})
        assert resp.status_code == 400
        body = resp.get_json()
        assert body["outcome"] == "NO_EXIT"
        assert "manual" in body["reason"].lower()


class TestActualLiveContinuousLifecycle:
    """Tests for actual-live continuous lifecycle advancement.

    When mode is actual-live (dry_run=False) and cycle is continuous,
    _maybe_advance_live_lifecycle() must rebuild a verified actual-live
    executor for the next cycle and fail closed if it cannot.
    """

    VALID_PAYLOAD = {
        "confirm": True,
        "account_mode": "live",
        "trading_cycle": "continuous",
        "expected_account_id": "U1234567",
        "confirmed_by": "test-operator",
        "confirmation_phrase": "ENABLE ACTUAL LIVE TRADING",
        "acknowledge_real_money_risk": True,
    }

    def test_continuous_actual_live_activation_persists_context(
        self, app, client, tmp_path
    ):
        """After actual-live continuous activation, expected_account_id,
        confirmation, and dry_run=False are persisted for subsequent cycles."""
        _install_live_runner(app, tmp_path, max_live_trades_per_day=3)
        resp = client.post(
            "/api/autonomous/live/actual-live/activate", json=self.VALID_PAYLOAD
        )
        assert resp.status_code == 200
        with app.app_context():
            assert app.config.get("autonomous_live_expected_account_id") == "U1234567"
            assert app.config.get("autonomous_live_dry_run") is False
            assert app.config.get("autonomous_live_confirmation") is not None

    def test_lifecycle_fails_closed_when_executor_build_fails(
        self, app, client, tmp_path
    ):
        """When _maybe_advance_live_lifecycle cannot build an actual-live
        executor (no live bridge in test service), mode must turn OFF rather
        than fall back to a dry-run executor.

        For the lifecycle to attempt advancement, a previous actual-live trade
        must have been started (since_activation non-empty) and all such trades
        must now be CLOSED (still_active empty).
        """
        import datetime as _dt
        from autonomous.autonomous_mode import (
            AccountMode,
            AutonomousModeState,
            TradingCycle,
        )
        from autonomous.trade_store import AutonomousTrade, TradeStore

        _install_live_runner(app, tmp_path, max_live_trades_per_day=3)

        activation_time = _dt.datetime.now(_dt.timezone.utc)

        with app.app_context():
            # Set up actual-live continuous mode as ON
            state = AutonomousModeState()
            state.turn_on(TradingCycle.CONTINUOUS, AccountMode.LIVE, dry_run=False)
            state.cycles_started = 1
            state.activated_at = activation_time.isoformat()
            app.config["autonomous_live_mode_state"] = state
            app.config["autonomous_live_dry_run"] = False
            app.config["autonomous_live_expected_account_id"] = "U1234567"
            app.config["autonomous_live_confirmation"] = None

            # Seed a CLOSED trade dated after activation so lifecycle
            # sees `since_activation` non-empty and `still_active` empty,
            # triggering the advancement path.
            store_path = str(tmp_path / "live2.jsonl")
            store = TradeStore(path=store_path)
            closed_trade = AutonomousTrade(
                autonomous_trade_id="alc-closed-001",
                symbol="AAPL",
                trade_type="BUY_SHARES",
                status="CLOSED",
                entry_order_id=1001,
                entry_time=activation_time,
                entry_limit_price=150.0,
                quantity=5,
                notes=["dry_run=False"],
            )
            store.record_trade(closed_trade)
            app.config["autonomous_live_trade_store"] = store

        # Status poll triggers _maybe_advance_live_lifecycle() automatically.
        # The lifecycle will attempt to build an actual-live executor via
        # _build_actual_live_executor(), which will fail because the test
        # service has no real TWS connection.  Fail-closed: mode turns OFF.
        resp = client.get("/api/autonomous/live/status")
        assert resp.status_code == 200

        with app.app_context():
            final_state = app.config.get("autonomous_live_mode_state")
            assert final_state is not None
            assert final_state.operating_state.value == "OFF"

    def test_lifecycle_turns_off_on_daily_cap_exhausted(
        self, app, client, tmp_path, monkeypatch
    ):
        """When actual-live continuous lifecycle fires and run_once() returns
        daily_live_trade_limit_reached, Autonomous Mode must turn OFF rather
        than stay ON and keep polling.
        """
        import datetime as _dt
        from autonomous.autonomous_mode import (
            AccountMode,
            AutonomousModeState,
            TradingCycle,
        )
        from autonomous.trade_store import AutonomousTrade, TradeStore
        from execution.order_executor import LiveTradingConfirmation

        activation_time = _dt.datetime.now(_dt.timezone.utc)

        # Build a store pre-seeded with two closed trades so:
        #   - lifecycle sees since_activation non-empty and still_active empty
        #     (advances past the "wait for fills" guard)
        #   - runner's own store also reports two trades today (>= cap of 1)
        store_path = str(tmp_path / "live_cap.jsonl")
        store = TradeStore(path=str(store_path))
        for i, oid in enumerate([2001, 2002], start=1):
            store.record_trade(AutonomousTrade(
                autonomous_trade_id=f"alc-cap-00{i}",
                symbol="AAPL",
                trade_type="BUY_SHARES",
                status="CLOSED",
                entry_order_id=oid,
                entry_time=activation_time,
                entry_limit_price=150.0 + i,
                quantity=5,
                notes=["dry_run=False"],
            ))

        # Monkeypatch services so _build_actual_live_executor() passes all
        # connectivity and account checks.
        class _ConnectedBridge:
            is_connected = True
            environment = "live"
            port = 7496

        monkeypatch.setattr("web.services.ServiceManager.connected", True)
        monkeypatch.setattr("web.services.ServiceManager.connection_env", "live")
        monkeypatch.setattr(
            "web.services.ServiceManager.connection_info",
            {"account": "U1234567", "port": 7496, "host": "127.0.0.1"},
        )
        monkeypatch.setattr("web.services.ServiceManager.tws_bridge", _ConnectedBridge())

        confirmation = LiveTradingConfirmation(
            environment="live",
            account_id="U1234567",
            port=7496,
            confirmed_by="test-operator",
        )

        # Install the base runner (for engine/config) then override the
        # factory to share the cap-exhausted store, ensuring both the
        # lifecycle guard and runner.evaluate_gates() see the same data.
        _, _ = _install_live_runner(app, tmp_path, max_live_trades_per_day=1)

        with app.app_context():
            base_cfg = app.config.get("autonomous_live_runner_config")

            # Rebuild factory with the shared cap-exhausted store.
            signals = [_signal()]
            scanner = CandidateScanner(
                signal_provider=StaticSignalProvider(signals),
                symbols=[{"symbol": "AAA", "security": "AAA", "sector": "X", "sub_industry": ""}],
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

            def cap_factory(cfg, continuous_mode=False):
                return AutonomousLiveRunner(
                    engine=engine,
                    trade_store=store,  # cap-exhausted store
                    live_config=cfg,
                    order_executor=_SubmittingExecutor(),
                    connected_provider=lambda: True,
                    connection_env_provider=lambda: "live",
                    account_id_provider=lambda: "U1234567",
                    signal_provider_provider=lambda: _RealProvider(),
                    emergency_stop_provider=lambda: False,
                    deployable_cash_provider=lambda: 50_000.0,
                    continuous_mode=continuous_mode,
                )

            app.config["autonomous_live_runner_factory"] = cap_factory
            app.config["autonomous_live_trade_store"] = store

            state = AutonomousModeState()
            state.turn_on(TradingCycle.CONTINUOUS, AccountMode.LIVE, dry_run=False)
            state.cycles_started = 1
            state.activated_at = activation_time.isoformat()
            app.config["autonomous_live_mode_state"] = state
            app.config["autonomous_live_dry_run"] = False
            app.config["autonomous_live_expected_account_id"] = "U1234567"
            app.config["autonomous_live_confirmation"] = confirmation

        resp = client.get("/api/autonomous/live/status")
        assert resp.status_code == 200

        with app.app_context():
            final_state = app.config.get("autonomous_live_mode_state")
            assert final_state is not None
            assert final_state.operating_state.value == "OFF"

    def test_lifecycle_turns_off_when_failed_trade_detected(
        self, app, client, tmp_path
    ):
        import datetime as _dt
        from autonomous.autonomous_mode import (
            AccountMode,
            AutonomousModeState,
            TradingCycle,
        )
        from autonomous.trade_store import AutonomousTrade, TradeStore

        activation_time = _dt.datetime.now(_dt.timezone.utc)
        store = TradeStore(path=str(tmp_path / "live_failed.jsonl"))
        store.record_trade(AutonomousTrade(
            autonomous_trade_id="alc-failed-001",
            symbol="AAPL",
            trade_type="BUY_SHARES",
            status="FAILED",
            entry_order_id=3001,
            entry_time=activation_time,
            entry_limit_price=150.0,
            quantity=5,
            notes=["dry_run=False"],
        ))
        _install_live_runner(app, tmp_path, max_live_trades_per_day=3)

        with app.app_context():
            state = AutonomousModeState()
            state.turn_on(TradingCycle.CONTINUOUS, AccountMode.LIVE, dry_run=False)
            state.cycles_started = 1
            state.activated_at = activation_time.isoformat()
            app.config["autonomous_live_mode_state"] = state
            app.config["autonomous_live_dry_run"] = False
            app.config["autonomous_live_trade_store"] = store

        resp = client.get("/api/autonomous/live/status")
        assert resp.status_code == 200
        with app.app_context():
            final_state = app.config.get("autonomous_live_mode_state")
            assert final_state is not None
            assert final_state.operating_state.value == "OFF"


# ---------------------------------------------------------------------------
# _live_runner_config() reads env on every call
# ---------------------------------------------------------------------------


class TestLiveRunnerConfigEnvReread:
    """Operator-edited .env values should take effect on the next call
    without restarting the web server."""

    def test_env_change_visible_on_next_call(self, app, monkeypatch):
        from web.routes.api_autonomous import _live_runner_config

        # Ensure no preset config short-circuits the env-read path.
        app.config.pop("autonomous_live_runner_config", None)

        monkeypatch.setenv("AUTONOMOUS_MAX_OPEN_LIVE_TRADES", "1")
        with app.app_context():
            cfg1 = _live_runner_config()
        assert cfg1.max_open_live_trades == 1

        # Operator edits the env (simulates editing .env between clicks).
        monkeypatch.setenv("AUTONOMOUS_MAX_OPEN_LIVE_TRADES", "5")
        with app.app_context():
            cfg2 = _live_runner_config()
        assert cfg2.max_open_live_trades == 5

    def test_preset_config_overrides_env(self, app, tmp_path):
        """When the operator/test registers an explicit config, the
        env-reread path is bypassed and the registered config wins."""
        from web.routes.api_autonomous import _live_runner_config

        preset = AutonomousLiveRunnerConfig(
            live_enabled=True,
            max_open_live_trades=3,
            trade_store_path=str(tmp_path / "live.jsonl"),
        )
        app.config["autonomous_live_runner_config"] = preset
        with app.app_context():
            cfg = _live_runner_config()
        assert cfg is preset
        assert cfg.max_open_live_trades == 3


class TestLiveLifecycleTick:
    def test_live_lifecycle_tick_drains_runner_gates(self, app, monkeypatch):
        from web.routes import api_autonomous

        calls = {"gate_drains": 0, "exit_eval": 0}

        class _Runner:
            def evaluate_gates(self):
                calls["gate_drains"] += 1

        monkeypatch.setattr(api_autonomous, "_live_mode_state", lambda: type("S", (), {"is_on": True})())
        monkeypatch.setattr(api_autonomous, "_live_runner_config", lambda: object())
        monkeypatch.setattr(api_autonomous, "_build_live_runner", lambda *args, **kwargs: _Runner())
        monkeypatch.setattr(api_autonomous, "_reconcile_live_trades", lambda: None)
        monkeypatch.setattr(
            api_autonomous,
            "_build_live_exit_manager",
            lambda: type("M", (), {"evaluate_open_trades": lambda self: calls.__setitem__("exit_eval", calls["exit_eval"] + 1)})(),
        )
        monkeypatch.setattr(api_autonomous, "_maybe_advance_live_lifecycle", lambda: None)

        with app.app_context():
            api_autonomous._live_lifecycle_tick()

        assert calls["gate_drains"] == 1
        assert calls["exit_eval"] == 1

    def test_live_lifecycle_tick_continues_when_gate_drain_fails(self, app, monkeypatch):
        from web.routes import api_autonomous

        calls = {"exit_eval": 0}

        class _Runner:
            def evaluate_gates(self):
                raise RuntimeError("boom")

        monkeypatch.setattr(api_autonomous, "_live_mode_state", lambda: type("S", (), {"is_on": True})())
        monkeypatch.setattr(api_autonomous, "_live_runner_config", lambda: object())
        monkeypatch.setattr(api_autonomous, "_build_live_runner", lambda *args, **kwargs: _Runner())
        monkeypatch.setattr(api_autonomous, "_reconcile_live_trades", lambda: None)
        monkeypatch.setattr(
            api_autonomous,
            "_build_live_exit_manager",
            lambda: type("M", (), {"evaluate_open_trades": lambda self: calls.__setitem__("exit_eval", calls["exit_eval"] + 1)})(),
        )
        monkeypatch.setattr(api_autonomous, "_maybe_advance_live_lifecycle", lambda: None)

        with app.app_context():
            api_autonomous._live_lifecycle_tick()

        assert calls["exit_eval"] == 1
