"""Tests for the /api/autonomous/* HTTP routes.

These tests use the Flask test client to drive the endpoints end-to-end.
The engine itself is exercised via ``autonomous_engine_factory`` so we
can inject a tiny in-memory engine with a mocked paper adapter without
needing real broker plumbing.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from autonomous import (
    AutonomousTradingConfig,
    AutonomousTradingEngine,
    CandidateScanner,
    CandidateSignal,
    StaticSignalProvider,
)
from autonomous.audit import AuditLogger
from data.cash_availability import CashAvailabilityAnalyzer
from web import create_app
from web.routes.api_autonomous import _sanitize_config_overrides


def _signal(symbol="AAA"):
    return CandidateSignal(
        symbol=symbol,
        strength_score=120,
        signal_label="Confirmed Rebound",
        last_price=100.0,
        support_price=95.0,
        resistance_price=110.0,
    )


@pytest.fixture
def app(monkeypatch):
    monkeypatch.setattr(
        "web.services.ServiceManager._start_market_events_refresh",
        lambda self: None,
    )
    monkeypatch.setattr(
        "web.routes.api_connection.is_accepted", lambda: True
    )
    app = create_app(
        {"TESTING": True, "LOGIN_DISABLED": True, "WTF_CSRF_ENABLED": False}
    )
    return app


@pytest.fixture
def client(app):
    return app.test_client()


def _install_factory(
    app,
    tmp_path: Path,
    *,
    signals=None,
    paper_adapter=None,
    account=None,
    positions=None,
    config_kwargs=None,
):
    """Register an ``autonomous_engine_factory`` that builds a tiny engine."""
    audit = AuditLogger(log_dir=str(tmp_path))

    def factory(overrides):
        provider = StaticSignalProvider(signals or [])
        scanner = CandidateScanner(
            signal_provider=provider,
            symbols=[
                {"symbol": s.symbol, "security": s.symbol, "sector": "X", "sub_industry": ""}
                for s in (signals or [])
            ],
        )
        base_kwargs = dict(config_kwargs or {})
        base_kwargs.setdefault(
            "emergency_stop_file", str(tmp_path / "EMERGENCY_STOP")
        )
        base_kwargs.setdefault("audit_log_dir", str(tmp_path))
        # Apply whitelisted overrides from the HTTP body so tests still
        # exercise mode switching through the API.
        for k in (
            "mode",
            "allow_live_execution",
            "require_user_confirmation",
            "max_trades_per_day",
        ):
            if k in overrides:
                base_kwargs[k] = overrides[k]
        cfg = AutonomousTradingConfig(**base_kwargs)
        return AutonomousTradingEngine(
            scanner=scanner,
            cash_analyzer=CashAvailabilityAnalyzer(),
            account_provider=lambda: account
            or {"cash_balance": 100_000, "equity": 100_000},
            positions_provider=lambda: positions or {},
            config=cfg,
            paper_adapter=paper_adapter,
            audit_logger=audit,
        )

    app.config["autonomous_engine_factory"] = factory


class _RecordingAdapter:
    def __init__(self):
        self.calls = []

    def buy(self, **kw):
        self.calls.append(kw)
        return 11


class TestStatus:
    def test_status_reports_real_provider_by_default(self, client):
        resp = client.get("/api/autonomous/status")
        assert resp.status_code == 200
        body = resp.get_json()
        # Production wiring: the real TechnicalAnalysisSignalProvider is
        # used by default, so /status must advertise it as ready and
        # must *not* surface the StaticSignalProvider warning.
        assert body["signal_provider"] == "TechnicalAnalysisSignalProvider"
        assert body["signal_provider_ready"] is True
        assert "warning" not in body
        # No paper adapter wired by default (service manager is not
        # connected to a paper TWS in the test client).
        assert body["paper_adapter_configured"] is False
        assert "paper_adapter_reason" in body

    def test_status_falls_back_to_static_when_provider_construction_fails(
        self, app, client, monkeypatch
    ):
        monkeypatch.setattr(
            "web.routes.api_autonomous.TechnicalAnalysisSignalProvider.try_build",
            classmethod(lambda cls, **kw: None),
        )
        body = client.get("/api/autonomous/status").get_json()
        assert body["signal_provider"] == "StaticSignalProvider"
        assert body["signal_provider_ready"] is False
        assert "warning" in body
        assert "StaticSignalProvider" in body["warning"]

    def test_status_omits_warning_when_factory_registered(self, app, client, tmp_path):
        _install_factory(app, tmp_path)
        resp = client.get("/api/autonomous/status")
        body = resp.get_json()
        # When a factory is installed we trust the operator wired a real
        # provider and suppress the stub warning.
        assert "warning" not in body

    def test_status_reports_paper_adapter_when_connected_to_paper(
        self, app, client, monkeypatch
    ):
        """When the service manager is connected to paper TWS the adapter
        must be advertised as configured so the dashboard renders
        ``PAPER ADAPTER READY``.
        """
        with app.app_context():
            from web.services import get_services
            svc = get_services()
        monkeypatch.setattr(type(svc), "connected", property(lambda self: True))
        monkeypatch.setattr(
            type(svc), "connection_env", property(lambda self: "paper")
        )

        class _FakeBridge:
            is_connected = True
            _app = object()

        monkeypatch.setattr(svc, "_tws_bridge", _FakeBridge(), raising=False)
        body = client.get("/api/autonomous/status").get_json()
        assert body["paper_adapter_configured"] is True
        assert body["connection_env"] == "paper"

    def test_status_blocks_paper_adapter_when_connected_to_live(
        self, app, client, monkeypatch
    ):
        with app.app_context():
            from web.services import get_services
            svc = get_services()
        monkeypatch.setattr(type(svc), "connected", property(lambda self: True))
        monkeypatch.setattr(
            type(svc), "connection_env", property(lambda self: "live")
        )

        class _FakeBridge:
            is_connected = True
            _app = object()

        monkeypatch.setattr(svc, "_tws_bridge", _FakeBridge(), raising=False)
        body = client.get("/api/autonomous/status").get_json()
        # Even when connected, live mode must never expose paper exec.
        assert body["paper_adapter_configured"] is False
        assert "live" in (body.get("paper_adapter_reason") or "")


class TestExecutePaper:
    def test_confirm_false_blocks_execution(self, app, client, tmp_path):
        adapter = _RecordingAdapter()
        _install_factory(
            app, tmp_path, signals=[_signal()], paper_adapter=adapter
        )
        resp = client.post(
            "/api/autonomous/execute-paper", json={"confirm": False}
        )
        body = resp.get_json()
        assert body["status"] == "confirmation_required"
        assert adapter.calls == []

    def test_confirm_true_executes_via_paper_adapter_with_limit(
        self, app, client, tmp_path
    ):
        adapter = _RecordingAdapter()
        _install_factory(
            app, tmp_path, signals=[_signal()], paper_adapter=adapter
        )
        resp = client.post(
            "/api/autonomous/execute-paper", json={"confirm": True}
        )
        body = resp.get_json()
        assert body["status"] == "paper_executed"
        assert body["order_id"] == 11
        assert len(adapter.calls) == 1
        call = adapter.calls[0]
        assert call["order_type"] == "LIMIT"
        assert call["limit_price"] == body["trade_plan"]["limit_price"]
        assert call["symbol"] == "AAA"

    def test_confirm_true_without_paper_adapter_fails_safely(
        self, app, client, tmp_path
    ):
        _install_factory(app, tmp_path, signals=[_signal()], paper_adapter=None)
        resp = client.post(
            "/api/autonomous/execute-paper", json={"confirm": True}
        )
        body = resp.get_json()
        assert body["status"] == "execution_failed"
        assert "no paper_adapter" in body["rejection_reason"]

    def test_string_confirm_does_not_bypass_confirmation(
        self, app, client, tmp_path
    ):
        adapter = _RecordingAdapter()
        _install_factory(
            app, tmp_path, signals=[_signal()], paper_adapter=adapter
        )
        resp = client.post(
            "/api/autonomous/execute-paper", json={"confirm": "false"}
        )
        body = resp.get_json()
        assert body["status"] == "confirmation_required"
        assert adapter.calls == []


class TestDailyLimit:
    def test_second_same_day_execution_is_blocked(self, app, client, tmp_path):
        adapter = _RecordingAdapter()
        _install_factory(
            app,
            tmp_path,
            signals=[_signal()],
            paper_adapter=adapter,
            config_kwargs={"max_trades_per_day": 1},
        )
        first = client.post(
            "/api/autonomous/execute-paper", json={"confirm": True}
        ).get_json()
        assert first["status"] == "paper_executed"

        second = client.post(
            "/api/autonomous/execute-paper", json={"confirm": True}
        ).get_json()
        assert second["status"] == "daily_limit_reached"
        # Adapter must not have been called a second time.
        assert len(adapter.calls) == 1


class TestLiveBlocked:
    def test_no_api_endpoint_exposes_live_execution(self, client):
        """There is no ``/api/autonomous/execute-live`` endpoint in the MVP.

        Live execution is intentionally not reachable from HTTP; the only
        way to attempt it is to call the engine directly, and even then
        the engine returns ``live_blocked`` (covered by
        ``tests/test_autonomous_engine.py``).
        """
        resp = client.post("/api/autonomous/execute-live", json={"confirm": True})
        assert resp.status_code == 404


class TestConfigOverrideValidation:
    def test_non_boolean_live_flag_is_ignored(self):
        cleaned = _sanitize_config_overrides({"allow_live_execution": "false"})
        assert "allow_live_execution" not in cleaned

    def test_non_boolean_confirmation_flag_is_ignored(self):
        cleaned = _sanitize_config_overrides({"require_user_confirmation": "false"})
        assert "require_user_confirmation" not in cleaned

    def test_exit_target_mode_accepted(self):
        cleaned = _sanitize_config_overrides({"exit_target_mode": "adr_intraday"})
        assert cleaned["exit_target_mode"] == "adr_intraday"

    def test_invalid_exit_target_mode_rejected(self):
        cleaned = _sanitize_config_overrides({"exit_target_mode": "bad_mode"})
        assert "exit_target_mode" not in cleaned

    def test_adr_numeric_overrides_accepted(self):
        cleaned = _sanitize_config_overrides({
            "take_profit_pct": 0.05,
            "adr_lookback_days": 20,
            "adr_target_fraction": 0.60,
            "adr_max_target_pct": 0.04,
            "adr_min_target_pct": 0.003,
        })
        assert cleaned["take_profit_pct"] == 0.05
        assert cleaned["adr_lookback_days"] == 20
        assert cleaned["adr_target_fraction"] == 0.60
        assert cleaned["adr_max_target_pct"] == 0.04
        assert cleaned["adr_min_target_pct"] == 0.003

    def test_adr_zero_or_negative_pct_rejected(self):
        cleaned = _sanitize_config_overrides({
            "take_profit_pct": 0.0,
            "adr_target_fraction": -0.1,
        })
        assert "take_profit_pct" not in cleaned
        assert "adr_target_fraction" not in cleaned

    def test_adr_respect_resistance_cap_boolean(self):
        cleaned = _sanitize_config_overrides({"adr_respect_resistance_cap": True})
        assert cleaned["adr_respect_resistance_cap"] is True
        cleaned = _sanitize_config_overrides({"adr_respect_resistance_cap": "yes"})
        assert "adr_respect_resistance_cap" not in cleaned


class TestADREnvConfig:
    """Tests proving env vars affect the built engine config."""

    def test_env_vars_applied_to_engine_config(self, monkeypatch, app):
        """AUTONOMOUS_* env vars should flow into the engine config."""
        monkeypatch.setenv("AUTONOMOUS_EXIT_TARGET_MODE", "adr_intraday")
        monkeypatch.setenv("AUTONOMOUS_TAKE_PROFIT_PCT", "0.06")
        monkeypatch.setenv("AUTONOMOUS_ADR_LOOKBACK_DAYS", "20")
        monkeypatch.setenv("AUTONOMOUS_ADR_TARGET_FRACTION", "0.60")
        monkeypatch.setenv("AUTONOMOUS_ADR_MAX_TARGET_PCT", "0.04")
        monkeypatch.setenv("AUTONOMOUS_ADR_MIN_TARGET_PCT", "0.003")
        monkeypatch.setenv("AUTONOMOUS_ADR_RESPECT_RESISTANCE_CAP", "false")

        from web.routes.api_autonomous import _build_engine
        with app.app_context():
            engine = _build_engine()
        cfg = engine.config
        assert cfg.exit_target_mode == "adr_intraday"
        assert cfg.take_profit_pct == 0.06
        assert cfg.adr_lookback_days == 20
        assert cfg.adr_target_fraction == 0.60
        assert cfg.adr_max_target_pct == 0.04
        assert cfg.adr_min_target_pct == 0.003
        assert cfg.adr_respect_resistance_cap is False

    def test_invalid_env_vars_use_defaults(self, monkeypatch, app):
        """Invalid env values should not crash — defaults apply."""
        monkeypatch.setenv("AUTONOMOUS_EXIT_TARGET_MODE", "bad_mode")
        monkeypatch.setenv("AUTONOMOUS_TAKE_PROFIT_PCT", "not_a_number")
        monkeypatch.setenv("AUTONOMOUS_ADR_LOOKBACK_DAYS", "-5")

        from web.routes.api_autonomous import _build_engine
        with app.app_context():
            engine = _build_engine()
        cfg = engine.config
        # Invalid mode not applied — default
        assert cfg.exit_target_mode == "resistance"
        # Invalid float not applied — default
        assert cfg.take_profit_pct == 0.08
        # Negative int not applied — default
        assert cfg.adr_lookback_days == 14

    def test_api_override_changes_target_mode(self, monkeypatch, app):
        """HTTP config override for exit_target_mode flows through."""
        from web.routes.api_autonomous import _build_engine
        with app.app_context():
            engine = _build_engine({"exit_target_mode": "percent"})
        assert engine.config.exit_target_mode == "percent"
