"""Tests for SECRET_KEY production enforcement and centralized order safety gate."""

import os
from datetime import datetime
from unittest.mock import patch, MagicMock

import pytest

from risk.risk_manager import Position
from web import create_app, _DEFAULT_SECRET


# ==============================================================================
# Issue 1: SECRET_KEY enforcement
# ==============================================================================


class TestSecretKeyEnforcement:
    """Verify SECRET_KEY is enforced in production."""

    def test_production_missing_secret_key_raises(self, monkeypatch):
        """Production mode fails fast when SECRET_KEY is missing."""
        # Stub load_dotenv so create_app (non-TESTING) does not load the real
        # .env into os.environ and pollute later tests in the suite.
        monkeypatch.setattr("dotenv.load_dotenv", lambda *a, **kw: False)
        monkeypatch.setattr(
            "web.services.ServiceManager._start_market_events_refresh",
            lambda self: None,
        )
        monkeypatch.setenv("ENVIRONMENT", "production")
        monkeypatch.delenv("SECRET_KEY", raising=False)

        with pytest.raises(RuntimeError, match="SECRET_KEY must be set in production"):
            create_app({"TESTING": False, "SECRET_KEY": ""})

    def test_production_default_secret_key_raises(self, monkeypatch):
        """Production mode fails fast when SECRET_KEY is still the default."""
        monkeypatch.setattr("dotenv.load_dotenv", lambda *a, **kw: False)
        monkeypatch.setattr(
            "web.services.ServiceManager._start_market_events_refresh",
            lambda self: None,
        )
        monkeypatch.setenv("ENVIRONMENT", "production")
        monkeypatch.delenv("SECRET_KEY", raising=False)

        with pytest.raises(RuntimeError, match="Default SECRET_KEY cannot be used"):
            create_app({"TESTING": False, "SECRET_KEY": _DEFAULT_SECRET})

    def test_production_with_secure_key_starts_ok(self, monkeypatch):
        """Production mode starts fine with a secure SECRET_KEY."""
        monkeypatch.setattr("dotenv.load_dotenv", lambda *a, **kw: False)
        monkeypatch.setattr(
            "web.services.ServiceManager._start_market_events_refresh",
            lambda self: None,
        )
        monkeypatch.setenv("ENVIRONMENT", "production")
        monkeypatch.setenv("SECRET_KEY", "super-secure-random-key-12345")

        app = create_app({"TESTING": False, "TWS_ADMIN_PASSWORD": "test-password"})
        assert app is not None

    def test_development_default_secret_key_allowed(self, monkeypatch):
        """Development mode allows the default SECRET_KEY."""
        monkeypatch.setattr(
            "web.services.ServiceManager._start_market_events_refresh",
            lambda self: None,
        )
        monkeypatch.delenv("ENVIRONMENT", raising=False)
        monkeypatch.delenv("SECRET_KEY", raising=False)

        app = create_app({"TESTING": True})
        assert app is not None

    def test_testing_mode_skips_enforcement(self, monkeypatch):
        """TESTING mode always skips SECRET_KEY enforcement."""
        monkeypatch.setattr(
            "web.services.ServiceManager._start_market_events_refresh",
            lambda self: None,
        )
        monkeypatch.setenv("ENVIRONMENT", "production")
        monkeypatch.delenv("SECRET_KEY", raising=False)

        # Even with ENVIRONMENT=production, TESTING=True skips enforcement
        app = create_app({"TESTING": True})
        assert app is not None

    def test_secret_key_loaded_from_env(self, monkeypatch):
        """SECRET_KEY is loaded from environment variable."""
        monkeypatch.setattr(
            "web.services.ServiceManager._start_market_events_refresh",
            lambda self: None,
        )
        monkeypatch.setenv("SECRET_KEY", "my-env-secret")
        monkeypatch.delenv("ENVIRONMENT", raising=False)

        app = create_app({"TESTING": True})
        # config_override doesn't set SECRET_KEY, so the env value is used
        assert app.config["SECRET_KEY"] == "my-env-secret"


# ==============================================================================
# Issue 2: Centralized order safety gate
# ==============================================================================


class TestOrderSafetyGate:
    """Verify web manual orders pass through OrderExecutor safety checks."""

    @pytest.fixture
    def app(self, monkeypatch):
        monkeypatch.setattr(
            "web.services.ServiceManager._start_market_events_refresh",
            lambda self: None,
        )
        return create_app({
            "TESTING": True,
            "LOGIN_DISABLED": True,
            "WTF_CSRF_ENABLED": False,
        })

    @pytest.fixture
    def client(self, app):
        return app.test_client()

    @pytest.fixture
    def services(self, app):
        svc = app.config["services"]
        # Enable order submission by setting trading state
        svc.set_connected("paper", {"host": "127.0.0.1", "port": 7497})
        svc.risk_manager.update(
            equity=100000.0,
            positions={},
            current_date=datetime.now(),
        )
        return svc

    def test_order_blocked_by_emergency_stop(self, client, services):
        """Emergency stop blocks web manual orders through OrderExecutor."""
        with patch.object(
            services.order_executor, "_check_emergency_stop", return_value=True
        ):
            resp = client.post("/api/orders/", json={
                "symbol": "AAPL",
                "action": "BUY",
                "quantity": 10,
            })
        assert resp.status_code == 403
        data = resp.get_json()
        assert "emergency stop" in data["error"].lower()

    def test_order_blocked_by_risk_manager(self, client, services):
        """Risk manager blocks oversized orders through centralized gate."""
        with patch.object(
            services.order_executor.risk_manager,
            "check_trade_risk",
            return_value=(False, "Max position size exceeded"),
        ), patch.object(
            services.order_executor, "_check_emergency_stop", return_value=False
        ):
            resp = client.post("/api/orders/", json={
                "symbol": "AAPL",
                "action": "BUY",
                "quantity": 99999,
            })
        assert resp.status_code == 403
        data = resp.get_json()
        assert "Max position size exceeded" in data["error"]

    def test_order_passes_safety_gate(self, client, services):
        """Valid order passes all safety checks and is recorded."""
        with patch.object(
            services.order_executor,
            "validate_manual_order",
            return_value=(True, ""),
        ):
            resp = client.post("/api/orders/", json={
                "symbol": "AAPL",
                "action": "BUY",
                "quantity": 10,
            })
        assert resp.status_code == 201
        data = resp.get_json()
        assert data["status"] == "recorded"
        assert data["execution_mode"] == "local_only"

    def test_order_uses_equity_and_position_snapshot(self, client, services):
        """Safety gate receives equity and positions in RiskManager format."""
        services.update_position("AAPL", {
            "quantity": 5.0,
            "entry_price": 180.0,
            "current_price": 182.0,
            "side": "LONG",
        })
        services.update_account_summary({"equity": "250000.5"})

        with patch.object(
            services.order_executor,
            "validate_manual_order",
            return_value=(True, ""),
        ) as mock_validate:
            resp = client.post("/api/orders/", json={
                "symbol": "MSFT",
                "action": "BUY",
                "quantity": 3,
            })

        assert resp.status_code == 201
        assert mock_validate.called
        kwargs = mock_validate.call_args.kwargs
        assert kwargs["current_equity"] == pytest.approx(250000.5)
        assert isinstance(kwargs["positions"]["AAPL"], Position)
        assert kwargs["positions"]["AAPL"].quantity == 5

    @pytest.mark.parametrize(
        "payload,error",
        [
            (
                {"symbol": "AAPL", "action": "BUY", "quantity": 1, "order_type": "LIMIT"},
                "limit_price is required",
            ),
            (
                {
                    "symbol": "AAPL",
                    "action": "BUY",
                    "quantity": 1,
                    "order_type": "LIMIT",
                    "limit_price": "abc",
                },
                "limit_price must be a valid number",
            ),
            (
                {
                    "symbol": "AAPL",
                    "action": "BUY",
                    "quantity": 1,
                    "order_type": "LIMIT",
                    "limit_price": 0,
                },
                "limit_price must be > 0",
            ),
        ],
    )
    def test_limit_order_limit_price_validation(self, client, services, payload, error):
        resp = client.post("/api/orders/", json=payload)
        assert resp.status_code == 400
        assert error in resp.get_json()["error"]
