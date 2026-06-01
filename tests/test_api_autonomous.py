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
    def test_status_warns_when_using_default_provider(self, client):
        resp = client.get("/api/autonomous/status")
        assert resp.status_code == 200
        body = resp.get_json()
        assert "warning" in body
        assert "StaticSignalProvider" in body["warning"]
        assert body["paper_adapter_configured"] is False

    def test_status_omits_warning_when_factory_registered(self, app, client, tmp_path):
        _install_factory(app, tmp_path)
        resp = client.get("/api/autonomous/status")
        body = resp.get_json()
        # When a factory is installed we trust the operator wired a real
        # provider and suppress the stub warning.
        assert "warning" not in body


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
