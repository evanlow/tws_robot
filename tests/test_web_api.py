"""Tests for the web API routes and ServiceManager.

Tests the new Super Dashboard API endpoints using the Flask test client.
"""

import json
import pytest

from web import create_app
from web.services import ServiceManager


@pytest.fixture
def app():
    """Create Flask app with test configuration."""
    app = create_app({"TESTING": True})
    return app


@pytest.fixture
def client(app):
    """Flask test client."""
    return app.test_client()


@pytest.fixture
def services(app):
    """Access the ServiceManager from app config."""
    return app.config["services"]


# ==============================================================================
# ServiceManager
# ==============================================================================


class TestServiceManager:
    """Tests for the ServiceManager singleton."""

    def test_initial_state(self, services):
        assert isinstance(services, ServiceManager)
        assert services.connected is False
        assert services.connection_env is None
        assert services.get_positions() == {}
        assert services.get_orders() == []

    def test_connection_state(self, services):
        services.set_connected("paper", {"host": "127.0.0.1", "port": 7497})
        assert services.connected is True
        assert services.connection_env == "paper"
        assert services.connection_info["host"] == "127.0.0.1"

        services.set_disconnected()
        assert services.connected is False
        assert services.connection_env is None

    def test_positions(self, services):
        services.update_position("AAPL", {
            "quantity": 100,
            "entry_price": 150.0,
            "current_price": 155.0,
            "unrealized_pnl": 500.0,
        })
        positions = services.get_positions()
        assert "AAPL" in positions
        assert positions["AAPL"]["quantity"] == 100

        services.remove_position("AAPL")
        assert "AAPL" not in services.get_positions()

    def test_orders(self, services):
        services.add_order({"id": "1", "symbol": "AAPL", "status": "SUBMITTED"})
        orders = services.get_orders()
        assert len(orders) == 1
        assert orders[0]["symbol"] == "AAPL"

    def test_alerts(self, services):
        services.add_alert({"id": "a1", "level": "WARNING", "message": "Test"})
        alerts = services.get_alerts()
        assert len(alerts) == 1

        assert services.dismiss_alert("a1") is True
        assert len(services.get_alerts()) == 0

    def test_system_health(self, services):
        health = services.get_system_health()
        assert health["status"] == "ok"
        assert "uptime_seconds" in health
        assert health["connected"] is False

    def test_backtest_runs(self, services):
        services.store_backtest_run("r1", {
            "status": "complete",
            "strategy_name": "Test",
            "created": "2024-01-01",
        })
        runs = services.list_backtest_runs()
        assert len(runs) == 1
        assert runs[0]["run_id"] == "r1"

        run = services.get_backtest_run("r1")
        assert run["status"] == "complete"

    def test_risk_manager_lazy_init(self, services):
        rm = services.risk_manager
        assert rm is not None
        summary = rm.get_risk_summary()
        assert "risk_status" in summary


# ==============================================================================
# Connection API
# ==============================================================================


class TestConnectionAPI:
    """Tests for /api/connection/* endpoints."""

    def test_status_disconnected(self, client):
        resp = client.get("/api/connection/status")
        data = resp.get_json()
        assert resp.status_code == 200
        assert data["connected"] is False

    def test_connect(self, client):
        resp = client.post("/api/connection/connect",
                           json={"environment": "paper"})
        data = resp.get_json()
        assert resp.status_code == 200
        assert data["status"] == "connected"
        assert data["environment"] == "paper"

    def test_connect_already_connected(self, client):
        client.post("/api/connection/connect", json={"environment": "paper"})
        resp = client.post("/api/connection/connect",
                           json={"environment": "paper"})
        assert resp.status_code == 409

    def test_disconnect(self, client):
        client.post("/api/connection/connect", json={"environment": "paper"})
        resp = client.post("/api/connection/disconnect")
        data = resp.get_json()
        assert resp.status_code == 200
        assert data["status"] == "disconnected"

    def test_disconnect_not_connected(self, client):
        resp = client.post("/api/connection/disconnect")
        assert resp.status_code == 409

    def test_invalid_environment(self, client):
        resp = client.post("/api/connection/connect",
                           json={"environment": "invalid"})
        assert resp.status_code == 400


# ==============================================================================
# Account API
# ==============================================================================


class TestAccountAPI:
    """Tests for /api/account/* endpoints."""

    def test_summary(self, client):
        resp = client.get("/api/account/summary")
        data = resp.get_json()
        assert resp.status_code == 200
        assert "equity" in data
        assert "risk_status" in data

    def test_positions_empty(self, client):
        resp = client.get("/api/account/positions")
        data = resp.get_json()
        assert resp.status_code == 200
        assert data["count"] == 0
        assert data["positions"] == []


# ==============================================================================
# Emergency API
# ==============================================================================


class TestEmergencyAPI:
    """Tests for /api/emergency/* endpoints."""

    def test_status(self, client):
        resp = client.get("/api/emergency/status")
        data = resp.get_json()
        assert resp.status_code == 200
        assert data["emergency_stop_active"] is False

    def test_halt_and_resume(self, client):
        # Halt
        resp = client.post("/api/emergency/halt",
                           json={"reason": "Test halt"})
        data = resp.get_json()
        assert resp.status_code == 200
        assert data["status"] == "halted"

        # Check status
        resp = client.get("/api/emergency/status")
        assert resp.get_json()["emergency_stop_active"] is True

        # Resume
        resp = client.post("/api/emergency/resume",
                           json={"reason": "Test resume"})
        data = resp.get_json()
        assert resp.status_code == 200
        assert data["status"] == "resumed"

    def test_close_all(self, client, services):
        services.update_position("AAPL", {"quantity": 100})
        resp = client.post("/api/emergency/close-all")
        data = resp.get_json()
        assert resp.status_code == 200
        assert data["positions_closed"] == 1


# ==============================================================================
# Orders API
# ==============================================================================


class TestOrdersAPI:
    """Tests for /api/orders/* endpoints."""

    def test_list_empty(self, client):
        resp = client.get("/api/orders/")
        data = resp.get_json()
        assert resp.status_code == 200
        assert data["count"] == 0

    def test_submit_order(self, client):
        resp = client.post("/api/orders/", json={
            "symbol": "AAPL",
            "action": "BUY",
            "quantity": 100,
            "order_type": "MARKET",
        })
        data = resp.get_json()
        assert resp.status_code == 201
        assert data["status"] == "submitted"
        assert data["order"]["symbol"] == "AAPL"

    def test_submit_order_validation(self, client):
        resp = client.post("/api/orders/", json={
            "symbol": "",
            "action": "HOLD",
            "quantity": 0,
        })
        assert resp.status_code == 400

    def test_submit_order_during_emergency(self, client):
        client.post("/api/emergency/halt", json={})
        resp = client.post("/api/orders/", json={
            "symbol": "AAPL",
            "action": "BUY",
            "quantity": 100,
        })
        assert resp.status_code == 403
        # Cleanup
        client.post("/api/emergency/resume", json={})

    def test_cancel_order(self, client):
        # Submit first
        resp = client.post("/api/orders/", json={
            "symbol": "MSFT",
            "action": "SELL",
            "quantity": 50,
        })
        order_id = resp.get_json()["order"]["id"]

        # Cancel
        resp = client.delete(f"/api/orders/{order_id}")
        assert resp.status_code == 200

    def test_cancel_nonexistent(self, client):
        resp = client.delete("/api/orders/nonexistent-id")
        assert resp.status_code == 404


# ==============================================================================
# System Health API
# ==============================================================================


class TestSystemAPI:
    """Tests for /api/system/* endpoints."""

    def test_health(self, client):
        resp = client.get("/api/system/health")
        data = resp.get_json()
        assert resp.status_code == 200
        assert data["status"] == "ok"
        assert "uptime_seconds" in data

    def test_test_connection(self, client):
        resp = client.post("/api/diagnostics/test-connection",
                           json={"host": "127.0.0.1", "port": 99999})
        data = resp.get_json()
        assert resp.status_code == 200
        assert "reachable" in data
        # Port 99999 should not be reachable
        assert data["reachable"] is False

    def test_market_status(self, client):
        resp = client.get("/api/diagnostics/market-status")
        data = resp.get_json()
        assert resp.status_code == 200
        assert "market_open" in data


# ==============================================================================
# Backtest API
# ==============================================================================


class TestBacktestAPI:
    """Tests for /api/backtest/* endpoints."""

    def test_list_runs_empty(self, client):
        resp = client.get("/api/backtest/runs")
        data = resp.get_json()
        assert resp.status_code == 200
        assert data["runs"] == [] or isinstance(data["runs"], list)

    def test_run_backtest_validation(self, client):
        resp = client.post("/api/backtest/run", json={})
        assert resp.status_code == 400

    def test_status_not_found(self, client):
        resp = client.get("/api/backtest/nonexistent/status")
        assert resp.status_code == 404

    def test_results_not_found(self, client):
        resp = client.get("/api/backtest/nonexistent/results")
        assert resp.status_code == 404

    def test_compare_no_runs(self, client):
        resp = client.get("/api/backtest/compare?runs=")
        assert resp.status_code == 400


# ==============================================================================
# Data API
# ==============================================================================


class TestDataAPI:
    """Tests for /api/data/* endpoints."""

    def test_list_symbols(self, client):
        resp = client.get("/api/data/symbols")
        data = resp.get_json()
        assert resp.status_code == 200
        assert "symbols" in data

    def test_data_status(self, client):
        resp = client.get("/api/data/status")
        data = resp.get_json()
        assert resp.status_code == 200
        assert "files" in data

    def test_download_no_symbols(self, client):
        resp = client.post("/api/data/download", json={})
        assert resp.status_code == 400


# ==============================================================================
# Strategy API
# ==============================================================================


class TestStrategyAPI:
    """Tests for /api/strategies/* endpoints."""

    def test_list_strategies(self, client):
        resp = client.get("/api/strategies/")
        data = resp.get_json()
        assert resp.status_code == 200
        assert "strategies" in data

    def test_list_classes(self, client):
        resp = client.get("/api/strategies/classes")
        data = resp.get_json()
        assert resp.status_code == 200
        assert "classes" in data

    def test_start_nonexistent(self, client):
        resp = client.post("/api/strategies/nonexistent/start")
        assert resp.status_code == 404

    def test_stop_nonexistent(self, client):
        resp = client.post("/api/strategies/nonexistent/stop")
        assert resp.status_code == 404

    def test_metrics_nonexistent(self, client):
        resp = client.get("/api/strategies/nonexistent/metrics")
        assert resp.status_code == 404


# ==============================================================================
# Event API
# ==============================================================================


class TestEventAPI:
    """Tests for /api/events/* endpoints."""

    def test_event_history(self, client):
        resp = client.get("/api/events/history")
        data = resp.get_json()
        assert resp.status_code == 200
        assert "events" in data

    def test_event_history_with_limit(self, client):
        resp = client.get("/api/events/history?limit=5")
        assert resp.status_code == 200

    def test_event_history_invalid_type(self, client):
        resp = client.get("/api/events/history?type=INVALID_TYPE")
        assert resp.status_code == 400


# ==============================================================================
# Page routes (smoke tests)
# ==============================================================================


class TestPageRoutes:
    """Smoke tests for all HTML page routes."""

    def test_dashboard(self, client):
        resp = client.get("/")
        assert resp.status_code == 200
        assert b"Dashboard" in resp.data

    def test_strategies(self, client):
        resp = client.get("/strategies/", follow_redirects=True)
        assert resp.status_code == 200
        assert b"Strategies" in resp.data

    def test_backtest(self, client):
        resp = client.get("/backtest/", follow_redirects=True)
        assert resp.status_code == 200
        assert b"Backtest" in resp.data

    def test_positions(self, client):
        resp = client.get("/positions/", follow_redirects=True)
        assert resp.status_code == 200
        assert b"Positions" in resp.data

    def test_positions_history(self, client):
        resp = client.get("/positions/history", follow_redirects=True)
        assert resp.status_code == 200

    def test_risk(self, client):
        resp = client.get("/risk/", follow_redirects=True)
        assert resp.status_code == 200
        assert b"Risk" in resp.data

    def test_logs(self, client):
        resp = client.get("/logs/", follow_redirects=True)
        assert resp.status_code == 200

    def test_settings(self, client):
        resp = client.get("/settings/", follow_redirects=True)
        assert resp.status_code == 200
        assert b"Settings" in resp.data
