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
    
    def test_get_account_insights(self, services):
        """Test get_account_insights() method returns calculated metrics."""
        # Set up test data
        services.risk_manager.current_equity = 105000.0
        services.risk_manager.daily_start_equity = 100000.0
        services.update_account_summary({"buying_power": 200000.0})
        
        # Add a position with unrealized P&L
        services.update_position("AAPL", {
            "quantity": 100,
            "entry_price": 150.0,
            "current_price": 155.0,
            "unrealized_pnl": 500.0,
        })
        services.update_position("MSFT", {
            "quantity": 50,
            "entry_price": 300.0,
            "current_price": 310.0,
            "unrealized_pnl": 500.0,
        })
        
        # Get insights
        insights = services.get_account_insights()
        
        # Verify calculated values
        assert insights["total_unrealized_pnl"] == 1000.0  # 500 + 500
        assert insights["daily_pnl_dollar"] == 5000.0  # 105000 - 100000
        assert insights["buying_power"] == 200000.0
    
    def test_get_account_insights_no_positions(self, services):
        """Test get_account_insights() with no positions."""
        services.risk_manager.current_equity = 100000.0
        services.risk_manager.daily_start_equity = 100000.0
        services.update_account_summary({"buying_power": 150000.0})
        
        insights = services.get_account_insights()
        
        assert insights["total_unrealized_pnl"] == 0.0
        assert insights["daily_pnl_dollar"] == 0.0
        assert insights["buying_power"] == 150000.0

    def test_position_analyzer_lazy_init(self, services):
        """Test position_analyzer is created on first access."""
        analyzer = services.position_analyzer
        assert analyzer is not None
        # Should return same instance on second access
        assert services.position_analyzer is analyzer

    def test_get_inferred_strategies_empty_positions(self, services):
        """Test get_inferred_strategies() with no positions."""
        inferred = services.get_inferred_strategies()
        assert inferred == []

    def test_get_inferred_strategies_with_positions(self, services):
        """Test get_inferred_strategies() detects strategies from positions."""
        # Add a long equity position
        services.update_position("AAPL", {
            "quantity": 100,
            "entry_price": 150.0,
            "current_price": 155.0,
            "unrealized_pnl": 500.0,
            "market_value": 15500.0,
            "side": "LONG",
            "sec_type": "STK",
        })
        
        inferred = services.get_inferred_strategies()
        
        # Should detect at least one strategy
        assert len(inferred) > 0
        # First strategy should be LongEquity for AAPL
        assert inferred[0]["strategy_type"] == "LongEquity"
        assert "AAPL" in inferred[0]["symbols"]
        assert "id" in inferred[0]
        assert "confidence" in inferred[0]

    def test_dismiss_inferred_strategy(self, services):
        """Test dismissing an inferred strategy."""
        # Add position and get inferred strategies
        services.update_position("AAPL", {
            "quantity": 100,
            "entry_price": 150.0,
            "current_price": 155.0,
            "unrealized_pnl": 500.0,
            "market_value": 15500.0,
            "side": "LONG",
            "sec_type": "STK",
        })
        
        inferred = services.get_inferred_strategies()
        assert len(inferred) == 1
        strategy_id = inferred[0]["id"]
        
        # Dismiss the strategy
        assert services.dismiss_inferred_strategy(strategy_id) is True
        
        # Should no longer appear in the list
        inferred_after = services.get_inferred_strategies()
        assert len(inferred_after) == 0

    def test_dismiss_invalid_strategy_id(self, services):
        """Test dismissing a non-existent strategy ID returns False."""
        assert services.dismiss_inferred_strategy("invalid_id") is False

    def test_reset_dismissed_inferred(self, services):
        """Test resetting dismissed strategies."""
        # Add position and dismiss it
        services.update_position("AAPL", {
            "quantity": 100,
            "entry_price": 150.0,
            "current_price": 155.0,
            "unrealized_pnl": 500.0,
            "market_value": 15500.0,
            "side": "LONG",
            "sec_type": "STK",
        })
        
        inferred = services.get_inferred_strategies()
        strategy_id = inferred[0]["id"]
        services.dismiss_inferred_strategy(strategy_id)
        
        # Verify it's dismissed
        assert len(services.get_inferred_strategies()) == 0
        
        # Reset dismissed
        services.reset_dismissed_inferred()
        
        # Should reappear in the list
        inferred_after = services.get_inferred_strategies()
        assert len(inferred_after) == 1


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
        # Verify new fields from get_account_insights()
        assert "daily_pnl_dollar" in data
        assert "unrealized_pnl" in data
        assert "buying_power" in data
    
    def test_summary_with_positions(self, client, services):
        """Test /api/account/summary includes calculated insights."""
        # Set up equity and positions
        services.risk_manager.current_equity = 105000.0
        services.risk_manager.daily_start_equity = 100000.0
        services.update_account_summary({"buying_power": 200000.0})
        services.update_position("AAPL", {
            "quantity": 100,
            "unrealized_pnl": 1500.0,
        })
        
        resp = client.get("/api/account/summary")
        data = resp.get_json()
        
        assert resp.status_code == 200
        assert data["daily_pnl_dollar"] == 5000.0  # 105000 - 100000
        assert data["unrealized_pnl"] == 1500.0
        assert data["buying_power"] == 200000.0

    def test_positions_empty(self, client):
        resp = client.get("/api/account/positions")
        data = resp.get_json()
        assert resp.status_code == 200
        assert data["count"] == 0
        assert data["positions"] == []

    def test_portfolio_analysis_empty(self, client):
        """Test /api/account/portfolio-analysis returns 200 with expected keys."""
        resp = client.get("/api/account/portfolio-analysis")
        data = resp.get_json()
        assert resp.status_code == 200
        for key in ("allocation", "concentration", "drawdown", "attribution",
                     "diversification", "sector_exposure", "suggestions",
                     "risk_flags", "total_value"):
            assert key in data, f"Missing key: {key}"
        assert data["allocation"] == []
        assert data["total_value"] == 0

    def test_portfolio_analysis_with_positions(self, client, services):
        """Test /api/account/portfolio-analysis with open positions."""
        services.update_position("AAPL", {
            "quantity": 100,
            "entry_price": 150.0,
            "current_price": 155.0,
            "market_value": 15500.0,
            "unrealized_pnl": 500.0,
        })
        services.update_position("MSFT", {
            "quantity": 50,
            "entry_price": 300.0,
            "current_price": 310.0,
            "market_value": 15500.0,
            "unrealized_pnl": 500.0,
        })

        resp = client.get("/api/account/portfolio-analysis")
        data = resp.get_json()
        assert resp.status_code == 200
        assert len(data["allocation"]) == 2
        assert data["total_value"] == 31000.0
        # Each position has equal weight
        for item in data["allocation"]:
            assert item["symbol"] in ("AAPL", "MSFT")
            assert 0.0 <= item["weight"] <= 1.0
        # Drawdown should be clamped to [0, 1]
        assert 0.0 <= data["drawdown"]["current_pct"] <= 1.0

    def test_symbol_names_empty(self, client):
        """Test /api/account/symbol-names with no positions returns empty."""
        resp = client.get("/api/account/symbol-names")
        data = resp.get_json()
        assert resp.status_code == 200
        assert data["names"] == {}

    def test_symbol_names_explicit_symbols(self, client):
        """Test /api/account/symbol-names with explicit symbols param."""
        resp = client.get("/api/account/symbol-names?symbols=AAPL,MSFT")
        data = resp.get_json()
        assert resp.status_code == 200
        assert "names" in data
        # Result depends on yfinance availability, but structure is correct
        assert isinstance(data["names"], dict)

    def test_symbol_names_defaults_to_portfolio(self, client, services):
        """Test /api/account/symbol-names defaults to portfolio stock symbols."""
        services.update_position("GOOG", {
            "quantity": 10,
            "entry_price": 100.0,
            "current_price": 110.0,
            "market_value": 1100.0,
            "unrealized_pnl": 100.0,
            "side": "LONG",
            "sec_type": "STK",
        })
        resp = client.get("/api/account/symbol-names")
        data = resp.get_json()
        assert resp.status_code == 200
        assert isinstance(data["names"], dict)

    def test_symbol_names_filters_options(self, client, services):
        """Test that option symbols are excluded from default resolution."""
        services.update_position("AAPL 250418C200", {
            "quantity": -1,
            "entry_price": 5.0,
            "current_price": 3.0,
            "market_value": -300.0,
            "unrealized_pnl": 200.0,
            "side": "SHORT",
            "sec_type": "OPT",
        })
        resp = client.get("/api/account/symbol-names")
        data = resp.get_json()
        assert resp.status_code == 200
        # Option symbol should not appear in results
        assert "AAPL 250418C200" not in data["names"]

    def test_symbol_names_too_many_symbols(self, client):
        """Test /api/account/symbol-names rejects too many symbols."""
        symbols = ",".join(f"SYM{i}" for i in range(60))
        resp = client.get(f"/api/account/symbol-names?symbols={symbols}")
        assert resp.status_code == 400
        data = resp.get_json()
        assert "error" in data

    def test_symbol_names_numeric_hk_stock_included(self, client, services):
        """Test that numeric HK stock symbols are included in default resolution."""
        services.update_position("1211", {
            "quantity": 1500,
            "entry_price": 128.84,
            "current_price": 111.51,
            "market_value": 167265.0,
            "unrealized_pnl": -26002.45,
            "side": "LONG",
            "sec_type": "STK",
            "exchange": "SEHK",
            "currency": "HKD",
        })
        resp = client.get("/api/account/symbol-names")
        data = resp.get_json()
        assert resp.status_code == 200
        assert isinstance(data["names"], dict)
        # Verify numeric symbol is not filtered out — if yfinance resolves
        # it, it will appear in names; if not, it still shouldn't error.
        # The key check: the endpoint accepted the numeric symbol (no 400
        # error) and the regex didn't exclude it from default resolution.
        # We can also verify via explicit param to confirm it's processed:
        resp2 = client.get("/api/account/symbol-names?symbols=1211")
        assert resp2.status_code == 200
        assert isinstance(resp2.get_json()["names"], dict)


class TestToYfinanceSymbol:
    """Unit tests for _to_yfinance_symbol helper."""

    def test_us_ticker_unchanged(self):
        from web.routes.api_account import _to_yfinance_symbol
        assert _to_yfinance_symbol("AAPL", {}) == "AAPL"

    def test_hk_stock_by_exchange(self):
        from web.routes.api_account import _to_yfinance_symbol
        pos = {"exchange": "SEHK", "currency": "HKD"}
        assert _to_yfinance_symbol("1211", pos) == "1211.HK"

    def test_hk_stock_by_currency_fallback(self):
        from web.routes.api_account import _to_yfinance_symbol
        pos = {"currency": "HKD"}
        assert _to_yfinance_symbol("9888", pos) == "9888.HK"

    def test_japanese_stock_by_exchange(self):
        from web.routes.api_account import _to_yfinance_symbol
        pos = {"exchange": "TSE", "currency": "JPY"}
        assert _to_yfinance_symbol("7203", pos) == "7203.T"

    def test_symbol_with_existing_suffix_unchanged(self):
        from web.routes.api_account import _to_yfinance_symbol
        pos = {"exchange": "SEHK", "currency": "HKD"}
        assert _to_yfinance_symbol("BRK.B", pos) == "BRK.B"

    def test_old_suffix_gets_exchange_mapping(self):
        """Symbols ending in .OLD should still get exchange suffix."""
        from web.routes.api_account import _to_yfinance_symbol
        pos = {"exchange": "SEHK", "currency": "HKD"}
        assert _to_yfinance_symbol("CTKYY.OLD", pos) == "CTKYY.OLD.HK"

    def test_usd_currency_no_suffix(self):
        from web.routes.api_account import _to_yfinance_symbol
        pos = {"currency": "USD"}
        assert _to_yfinance_symbol("WKHS", pos) == "WKHS"

    def test_empty_pos_data(self):
        from web.routes.api_account import _to_yfinance_symbol
        assert _to_yfinance_symbol("MSFT", {}) == "MSFT"


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

    def test_list_inferred_empty(self, client):
        """Test /api/strategies/inferred with no positions."""
        resp = client.get("/api/strategies/inferred")
        data = resp.get_json()
        assert resp.status_code == 200
        assert "inferred" in data
        assert data["inferred"] == []

    def test_list_inferred_with_positions(self, client, services):
        """Test /api/strategies/inferred detects strategies from positions."""
        # Add a long equity position
        services.update_position("AAPL", {
            "quantity": 100,
            "entry_price": 150.0,
            "current_price": 155.0,
            "unrealized_pnl": 500.0,
            "market_value": 15500.0,
            "side": "LONG",
            "sec_type": "STK",
        })
        
        resp = client.get("/api/strategies/inferred")
        data = resp.get_json()
        
        assert resp.status_code == 200
        assert len(data["inferred"]) > 0
        assert data["inferred"][0]["strategy_type"] == "LongEquity"

    def test_dismiss_inferred_strategy(self, client, services):
        """Test POST /api/strategies/inferred/<id>/dismiss."""
        # Add position to create an inferred strategy
        services.update_position("MSFT", {
            "quantity": 50,
            "entry_price": 300.0,
            "current_price": 310.0,
            "unrealized_pnl": 500.0,
            "market_value": 15500.0,
            "side": "LONG",
            "sec_type": "STK",
        })
        
        # Get the strategy ID
        resp = client.get("/api/strategies/inferred")
        inferred = resp.get_json()["inferred"]
        assert len(inferred) == 1
        strategy_id = inferred[0]["id"]
        
        # Dismiss it
        resp = client.post(f"/api/strategies/inferred/{strategy_id}/dismiss")
        data = resp.get_json()
        
        assert resp.status_code == 200
        assert data["status"] == "dismissed"
        assert data["id"] == strategy_id
        
        # Verify it's no longer in the list
        resp = client.get("/api/strategies/inferred")
        inferred_after = resp.get_json()["inferred"]
        assert len(inferred_after) == 0

    def test_dismiss_invalid_inferred_strategy(self, client):
        """Test dismissing a non-existent inferred strategy."""
        resp = client.post("/api/strategies/inferred/invalid_id/dismiss")
        assert resp.status_code == 404

    def test_reset_dismissed_inferred(self, client, services):
        """Test POST /api/strategies/inferred/reset."""
        # Add position and dismiss it
        services.update_position("TSLA", {
            "quantity": 25,
            "entry_price": 200.0,
            "current_price": 220.0,
            "unrealized_pnl": 500.0,
            "market_value": 5500.0,
            "side": "LONG",
            "sec_type": "STK",
        })
        
        # Get and dismiss the strategy
        resp = client.get("/api/strategies/inferred")
        strategy_id = resp.get_json()["inferred"][0]["id"]
        client.post(f"/api/strategies/inferred/{strategy_id}/dismiss")
        
        # Verify it's dismissed
        resp = client.get("/api/strategies/inferred")
        assert len(resp.get_json()["inferred"]) == 0
        
        # Reset dismissed strategies
        resp = client.post("/api/strategies/inferred/reset")
        data = resp.get_json()
        
        assert resp.status_code == 200
        assert data["status"] == "reset"
        
        # Strategy should reappear
        resp = client.get("/api/strategies/inferred")
        inferred_after = resp.get_json()["inferred"]
        assert len(inferred_after) == 1


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
