"""Safety regression tests for TWS Robot.

These tests verify critical safety behaviors that must never regress:
- Connection state accuracy
- Order submission gating
- Emergency stop enforcement
- Cancellation labelling correctness
- Production secret-key enforcement
- Account data readiness checks
"""

from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from web import create_app, _DEFAULT_SECRET
from web.trading_state import TradingState


# ==============================================================================
# Fixtures
# ==============================================================================


@pytest.fixture
def app(monkeypatch):
    """Create Flask app with test configuration."""
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
def client(app):
    return app.test_client()


@pytest.fixture
def services(app):
    return app.config["services"]


def _mark_account_data_ready(services, equity: float = 100000.0) -> None:
    services.risk_manager.update(
        equity=equity,
        positions={},
        current_date=datetime.now(),
    )


# ==============================================================================
# 1. Failed TWS connection does not show connected
# ==============================================================================


class TestConnectionStateAccuracy:
    """Failed connections must never report 'connected'."""

    def test_failed_connection_not_shown_as_connected(self, client, services):
        """A failed TWS connection attempt must not report connected status."""
        # Simulate a connection failure by directly setting state
        services.set_trading_state(TradingState.CONNECTION_FAILED)

        resp = client.get("/api/connection/status")
        data = resp.get_json()
        assert data["connected"] is False
        assert data["trading_state"] == "CONNECTION_FAILED"

    def test_initial_state_is_disconnected(self, client):
        """Fresh app starts disconnected, not connected."""
        resp = client.get("/api/connection/status")
        data = resp.get_json()
        assert data["connected"] is False
        assert data["trading_state"] == "DISCONNECTED"

    def test_connect_tws_failure_stays_disconnected(self, services):
        """When connect_tws fails, ServiceManager stays disconnected."""
        with patch("core.tws_bridge.TWSBridge.connect", return_value=False):
            result = services.connect_tws("paper", {
                "host": "127.0.0.1",
                "port": 7497,
                "client_id": 1,
                "account": "DU12345",
            })
        assert result is False
        assert services.connected is False
        assert services.trading_state == TradingState.CONNECTION_FAILED


# ==============================================================================
# 2. Disconnected app cannot submit executable order
# ==============================================================================


class TestDisconnectedOrderBlocking:
    """Orders must be rejected when the app is not in a trading-ready state."""

    def test_order_rejected_when_disconnected(self, client):
        """POST /api/orders/ must fail when disconnected."""
        resp = client.post("/api/orders/", json={
            "symbol": "AAPL",
            "action": "BUY",
            "quantity": 10,
        })
        assert resp.status_code == 403
        assert "not allowed" in resp.get_json()["error"].lower()

    def test_order_rejected_in_connection_failed_state(self, client, services):
        """Orders blocked when state is CONNECTION_FAILED."""
        services.set_trading_state(TradingState.CONNECTION_FAILED)
        resp = client.post("/api/orders/", json={
            "symbol": "AAPL",
            "action": "BUY",
            "quantity": 10,
        })
        assert resp.status_code == 403

    def test_order_rejected_in_read_only_state(self, client, services):
        """Orders blocked when state is CONNECTED_READ_ONLY."""
        services.set_trading_state(TradingState.CONNECTED_READ_ONLY)
        resp = client.post("/api/orders/", json={
            "symbol": "AAPL",
            "action": "BUY",
            "quantity": 10,
        })
        assert resp.status_code == 403


# ==============================================================================
# 3. Manual order is not labelled submitted unless actually executed
# ==============================================================================


class TestOrderLabelAccuracy:
    """Manual orders must use 'recorded' status, never 'submitted'."""

    def test_manual_order_status_is_recorded_not_submitted(self, client, services):
        """POST /api/orders/ records locally — status must be RECORDED."""
        services.set_connected("paper", {"host": "127.0.0.1", "port": 7497})
        _mark_account_data_ready(services)

        resp = client.post("/api/orders/", json={
            "symbol": "AAPL",
            "action": "BUY",
            "quantity": 10,
        })
        data = resp.get_json()
        assert resp.status_code == 201
        assert data["status"] == "recorded"
        assert data["execution_mode"] == "local_only"
        assert data["order"]["status"] == "RECORDED"
        # Must NOT have submitted_at timestamp
        assert "submitted_at" not in data["order"]
        services.set_disconnected()

    def test_manual_order_message_says_not_submitted(self, client, services):
        """Response message must clarify the order was NOT sent to broker."""
        services.set_connected("paper", {"host": "127.0.0.1", "port": 7497})
        _mark_account_data_ready(services)

        resp = client.post("/api/orders/", json={
            "symbol": "MSFT",
            "action": "SELL",
            "quantity": 5,
        })
        data = resp.get_json()
        assert "not submitted to a broker" in data["message"]
        services.set_disconnected()


# ==============================================================================
# 4. Emergency stop blocks orders
# ==============================================================================


class TestEmergencyStopBlocksOrders:
    """Emergency stop must block all order submission."""

    def test_halt_blocks_new_orders(self, client, services):
        """After /api/emergency/halt, orders must be rejected."""
        services.set_connected("paper", {"host": "127.0.0.1", "port": 7497})
        _mark_account_data_ready(services)

        # Halt trading
        client.post("/api/emergency/halt", json={"reason": "safety test"})

        # Attempt order
        resp = client.post("/api/orders/", json={
            "symbol": "AAPL",
            "action": "BUY",
            "quantity": 10,
        })
        assert resp.status_code == 403

        # Cleanup
        client.post("/api/emergency/resume", json={"confirm": True})
        services.set_disconnected()

    def test_emergency_stop_state_blocks_orders(self, client, services):
        """EMERGENCY_STOP trading state blocks orders."""
        services.set_trading_state(TradingState.EMERGENCY_STOP)
        resp = client.post("/api/orders/", json={
            "symbol": "AAPL",
            "action": "BUY",
            "quantity": 10,
        })
        assert resp.status_code == 403

    def test_order_executor_emergency_stop_rejects(self, tmp_path):
        """OrderExecutor rejects when emergency stop file exists."""
        from pathlib import Path
        from unittest.mock import Mock
        from execution.order_executor import OrderExecutor, OrderStatus
        from execution.order_executor import RejectionReason, Signal, SignalType
        from risk.risk_manager import RiskManager

        emergency_file = tmp_path / "EMERGENCY_STOP"
        emergency_file.touch()

        mock_adapter = Mock()
        risk_mgr = RiskManager(initial_capital=100000.0)

        executor = OrderExecutor(
            tws_adapter=mock_adapter,
            risk_manager=risk_mgr,
            is_live_mode=False,
            emergency_stop_file=str(emergency_file),
        )

        from strategies.signal import SignalStrength
        signal = Signal(
            signal_type=SignalType.BUY,
            symbol="AAPL",
            quantity=10,
            strength=SignalStrength.STRONG,
            timestamp=datetime.now(),
        )
        result = executor.execute_signal(
            strategy_name="TestStrategy",
            signal=signal,
            current_equity=100000.0,
            positions={},
        )
        assert result.status == OrderStatus.REJECTED
        assert RejectionReason.EMERGENCY_STOP_ACTIVE.value in result.reason


# ==============================================================================
# 5. Cancellation is not mislabelled as broker cancellation
# ==============================================================================


class TestCancellationLabelling:
    """Local-only cancellations must not claim broker involvement."""

    def test_local_cancel_not_labelled_as_broker(self, client, services):
        """Cancelling a local_only order must not say 'forwarded_to_broker'."""
        services.set_connected("paper", {"host": "127.0.0.1", "port": 7497})
        _mark_account_data_ready(services)

        # Create order
        resp = client.post("/api/orders/", json={
            "symbol": "AAPL",
            "action": "BUY",
            "quantity": 10,
        })
        order_id = resp.get_json()["order"]["id"]

        # Cancel it
        resp = client.delete(f"/api/orders/{order_id}")
        data = resp.get_json()
        assert resp.status_code == 200
        assert data["status"] == "cancelled"
        assert data["execution_mode"] == "local_only"
        # Must include warning about broker, and NOT claim forwarded
        assert "warning" in data
        assert data.get("forwarded_to_broker") is not True
        services.set_disconnected()

    def test_broker_cancel_correctly_labelled(self, client, services):
        """Broker-forwarded cancellation must include forwarded_to_broker=True."""
        mock_bridge = MagicMock()
        mock_bridge.is_connected = True
        mock_bridge.cancel_order = MagicMock()
        services._tws_bridge = mock_bridge

        order = {
            "id": "safety-broker-1",
            "symbol": "AAPL",
            "action": "BUY",
            "quantity": 100,
            "status": "SUBMITTED",
            "execution_mode": "broker",
            "broker_order_id": 99,
        }
        services.add_order(order)

        resp = client.delete("/api/orders/safety-broker-1")
        data = resp.get_json()
        assert resp.status_code == 200
        assert data["status"] == "cancel_requested"
        assert data["forwarded_to_broker"] is True
        assert data["execution_mode"] == "broker"

        services._tws_bridge = None


# ==============================================================================
# 6. Production mode rejects default SECRET_KEY
# ==============================================================================


class TestProductionSecretKey:
    """Production mode must reject insecure SECRET_KEY values."""

    def test_production_rejects_default_secret(self, monkeypatch):
        """App must refuse to start in production with default SECRET_KEY."""
        monkeypatch.setattr(
            "web.services.ServiceManager._start_market_events_refresh",
            lambda self: None,
        )
        monkeypatch.setenv("ENVIRONMENT", "production")
        monkeypatch.delenv("SECRET_KEY", raising=False)

        with pytest.raises(RuntimeError, match="Default SECRET_KEY cannot be used"):
            create_app({"TESTING": False, "SECRET_KEY": _DEFAULT_SECRET})

    def test_production_rejects_empty_secret(self, monkeypatch):
        """App must refuse to start in production with empty SECRET_KEY."""
        monkeypatch.setattr(
            "web.services.ServiceManager._start_market_events_refresh",
            lambda self: None,
        )
        monkeypatch.setenv("ENVIRONMENT", "production")
        monkeypatch.delenv("SECRET_KEY", raising=False)

        with pytest.raises(RuntimeError, match="SECRET_KEY must be set"):
            create_app({"TESTING": False, "SECRET_KEY": ""})

    def test_production_accepts_secure_key(self, monkeypatch):
        """App starts normally in production with a proper SECRET_KEY."""
        monkeypatch.setattr(
            "web.services.ServiceManager._start_market_events_refresh",
            lambda self: None,
        )
        monkeypatch.setenv("ENVIRONMENT", "production")
        monkeypatch.setenv("SECRET_KEY", "a-properly-secure-random-key-xyz")

        app = create_app({"TESTING": False, "TWS_ADMIN_PASSWORD": "test-pw"})
        assert app is not None


# ==============================================================================
# 7. Account data readiness required before order execution
# ==============================================================================


class TestAccountDataReadiness:
    """Orders must be blocked until account data (equity) is loaded."""

    def test_order_blocked_before_account_data(self, client, services):
        """Connected but equity not received → 503."""
        services.set_connected("paper", {"host": "127.0.0.1", "port": 7497})
        assert not services.account_data_ready

        resp = client.post("/api/orders/", json={
            "symbol": "AAPL",
            "action": "BUY",
            "quantity": 10,
        })
        assert resp.status_code == 503
        assert "account data" in resp.get_json()["error"].lower()
        services.set_disconnected()

    def test_order_allowed_after_account_data(self, client, services):
        """Connected and equity received → order accepted."""
        services.set_connected("paper", {"host": "127.0.0.1", "port": 7497})
        _mark_account_data_ready(services)

        resp = client.post("/api/orders/", json={
            "symbol": "AAPL",
            "action": "BUY",
            "quantity": 10,
        })
        assert resp.status_code == 201
        services.set_disconnected()

    def test_account_data_ready_flag_resets_on_reconnect(self, services):
        """Reconnecting must reset account_data_ready until new data arrives."""
        services.set_connected("paper", {"host": "127.0.0.1", "port": 7497})
        _mark_account_data_ready(services)
        assert services.account_data_ready

        # Disconnect and reconnect
        services.set_disconnected()
        services.set_connected("paper", {"host": "127.0.0.1", "port": 7497})
        assert not services.account_data_ready
        services.set_disconnected()
