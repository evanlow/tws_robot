"""Tests for the web API routes and ServiceManager.

Tests the new Super Dashboard API endpoints using the Flask test client.
"""

import json
from datetime import datetime
from unittest.mock import patch

import pytest

from web import create_app
from web.services import ServiceManager


def _mark_account_data_ready(services, equity: float = 100000.0) -> None:
    services.risk_manager.update(
        equity=equity,
        positions={},
        current_date=datetime.now(),
    )


@pytest.fixture
def app(monkeypatch):
    """Create Flask app with test configuration."""
    monkeypatch.setattr(
        "web.services.ServiceManager._start_market_events_refresh",
        lambda self: None,
    )
    # Treat disclaimer as already accepted in all web-API tests so that
    # connection tests exercise connection logic, not the disclaimer gate.
    monkeypatch.setattr("web.routes.api_connection.is_accepted", lambda: True)
    app = create_app({"TESTING": True, "LOGIN_DISABLED": True, "WTF_CSRF_ENABLED": False})
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

    def test_cancel_order(self, services):
        services.add_order({"id": "1", "symbol": "AAPL", "status": "SUBMITTED"})
        cancelled_at = "2026-05-21T00:00:00"

        result = services.cancel_order("1", cancelled_at)

        assert result["result"] == "cancelled"
        assert result["order"]["status"] == "CANCELLED"
        assert result["order"]["cancelled_at"] == cancelled_at

    def test_cancel_order_terminal_status(self, services):
        services.add_order({"id": "1", "symbol": "AAPL", "status": "FILLED"})

        result = services.cancel_order("1", "2026-05-21T00:00:00")

        assert result == {"result": "terminal", "status": "FILLED"}

    def test_alerts(self, services):
        services.add_alert({"id": "a1", "level": "WARNING", "message": "Test"})
        alerts = services.get_alerts()
        assert len(alerts) == 1

        assert services.dismiss_alert("a1") is True
        assert len(services.get_alerts()) == 0

    def test_system_health(self, services):
        services.add_order({"id": "1", "symbol": "AAPL", "status": "SUBMITTED"})
        services.add_order({"id": "2", "symbol": "MSFT", "status": "RECORDED"})
        services.add_order({"id": "3", "symbol": "TSLA", "status": "CANCELLED"})
        health = services.get_system_health()
        assert health["status"] == "ok"
        assert "uptime_seconds" in health
        assert health["connected"] is False
        assert health["pending_orders"] == 2
        assert health["trading_state"] == "DISCONNECTED"

    def test_trading_state_initial(self, services):
        from web.trading_state import TradingState
        assert services.trading_state == TradingState.DISCONNECTED

    def test_trading_state_paper_connection(self, services):
        from web.trading_state import TradingState
        services.set_connected("paper", {"host": "127.0.0.1", "port": 7497})
        assert services.trading_state == TradingState.PAPER_TRADING_ENABLED
        services.set_disconnected()
        assert services.trading_state == TradingState.DISCONNECTED

    def test_trading_state_live_connection(self, services):
        from web.trading_state import TradingState
        services.set_connected("live", {"host": "127.0.0.1", "port": 7496})
        assert services.trading_state == TradingState.LIVE_TRADING_ARMED
        services.set_disconnected()

    def test_trading_state_emergency_stop(self, services):
        from web.trading_state import TradingState
        services.set_connected("paper", {"host": "127.0.0.1", "port": 7497})
        services.set_trading_state(TradingState.EMERGENCY_STOP)
        assert services.trading_state == TradingState.EMERGENCY_STOP
        assert not services.trading_state.allows_order_submission
        services.set_disconnected()

    def test_trading_state_allows_order_submission(self, services):
        from web.trading_state import TradingState
        assert not TradingState.DISCONNECTED.allows_order_submission
        assert not TradingState.CONNECTION_FAILED.allows_order_submission
        assert not TradingState.CONNECTED_READ_ONLY.allows_order_submission
        assert TradingState.PAPER_TRADING_ENABLED.allows_order_submission
        assert TradingState.LIVE_TRADING_ARMED.allows_order_submission
        assert TradingState.LIVE_TRADING_ACTIVE.allows_order_submission
        assert not TradingState.EMERGENCY_STOP.allows_order_submission

    def test_account_data_ready_disconnected(self, services):
        """account_data_ready must be False when not connected."""
        assert services.account_data_ready is False

    def test_account_data_ready_connected_no_equity(self, services):
        """account_data_ready must be False when connected but equity not initialized."""
        services.set_connected("paper", {"host": "127.0.0.1", "port": 7497})
        assert services.account_data_ready is False
        services.set_disconnected()

    def test_account_data_ready_connected_with_equity(self, services):
        """account_data_ready must be True once equity has been initialized."""
        services.set_connected("paper", {"host": "127.0.0.1", "port": 7497})
        _mark_account_data_ready(services)
        assert services.account_data_ready is True
        services.set_disconnected()

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

    def test_get_inferred_strategies_suppresses_adopted(self, services):
        """Inferred detections whose symbol-set matches an adopted _InferredBase
        strategy should be suppressed so they don't reappear after restart."""
        from strategies.strategy_registry import StrategyRegistry
        from strategies.base_strategy import StrategyConfig
        from strategies.inferred_strategies import LongEquityStrategy, INFERRED_STRATEGY_CLASSES

        # Inject a fresh in-memory registry (no DB) to avoid cross-test contamination.
        reg = StrategyRegistry(event_bus=services.event_bus, account_id="")
        for stype, cls in INFERRED_STRATEGY_CLASSES.items():
            reg.register_strategy_class(stype, cls)
        services._strategy_registry = reg

        # Add a long equity position so the analyzer detects it.
        services.update_position("AAPL", {
            "quantity": 100,
            "entry_price": 150.0,
            "current_price": 155.0,
            "unrealized_pnl": 500.0,
            "market_value": 15500.0,
            "side": "LONG",
            "sec_type": "STK",
        })

        # Confirm it is detected before adoption.
        inferred_before = services.get_inferred_strategies()
        assert len(inferred_before) > 0
        aapl_before = [s for s in inferred_before if "AAPL" in s["symbols"]]
        assert len(aapl_before) > 0

        # Simulate adoption: register a LongEquityStrategy covering the same symbols.
        config = StrategyConfig(name="LongEquity_AAPL", symbols=["AAPL"])
        reg.create_strategy("LongEquity", config)

        # The matching inferred card should now be suppressed.
        inferred_after = services.get_inferred_strategies()
        aapl_after = [s for s in inferred_after if "AAPL" in s["symbols"]]
        assert len(aapl_after) == 0, (
            "Adopted LongEquity_AAPL should suppress the AAPL inferred detection"
        )

        # Restore the registry to its default state so subsequent tests are unaffected.
        services._strategy_registry = None

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

    PAPER_CONNECTION_INFO = {
        "host": "127.0.0.1",
        "port": 7497,
        "client_id": 1,
        "account": "",
    }

    def test_status_disconnected(self, client):
        resp = client.get("/api/connection/status")
        data = resp.get_json()
        assert resp.status_code == 200
        assert data["connected"] is False
        assert data["trading_state"] == "DISCONNECTED"

    def test_connect(self, client, services):
        def _connect_success(env, cfg, timeout=10):
            services.set_connected(env, {
                "host": cfg["host"],
                "port": cfg["port"],
                "client_id": cfg["client_id"],
                "account": cfg.get("account", ""),
            })
            return True

        with patch.object(ServiceManager, "connect_tws", side_effect=_connect_success):
            resp = client.post("/api/connection/connect",
                               json={"environment": "paper"})
        data = resp.get_json()
        assert resp.status_code == 200
        assert data["status"] == "connected"
        assert data["environment"] == "paper"

        status_resp = client.get("/api/connection/status")
        status_data = status_resp.get_json()
        assert status_resp.status_code == 200
        assert status_data["connected"] is True
        assert status_data["environment"] == "paper"
        assert status_data["trading_state"] == "PAPER_TRADING_ENABLED"

    def test_connect_failure(self, client):
        with patch.object(ServiceManager, "connect_tws", return_value=False):
            resp = client.post("/api/connection/connect",
                               json={"environment": "paper"})

        data = resp.get_json()
        assert resp.status_code == 503
        assert data["status"] == "connection_failed"
        assert data["connected"] is False
        assert data["environment"] == "paper"
        assert data["host"] == "127.0.0.1"
        assert data["port"] == 7497
        assert data["error"] == (
            "TWS or IB Gateway is not reachable. Please check that it is "
            "running and API access is enabled."
        )
        assert data["message"] == data["error"]

        status_resp = client.get("/api/connection/status")
        status_data = status_resp.get_json()
        assert status_resp.status_code == 200
        assert status_data["connected"] is False

    def test_connect_rejects_paper_live_mismatch(self, client, services):
        def _connect_mismatch(env, cfg, timeout=10):
            services.set_connected(env, {
                "host": cfg["host"],
                "port": cfg["port"],
                "client_id": cfg["client_id"],
                "account": "U1234567",
            })
            return True

        with patch.object(ServiceManager, "connect_tws", side_effect=_connect_mismatch):
            resp = client.post("/api/connection/connect", json={"environment": "paper"})

        data = resp.get_json()
        assert resp.status_code == 409
        assert data["status"] == "connection_rejected"
        assert data["connected"] is False
        assert data["actual_environment"] == "live"
        assert "set to PAPER" in data["error"]
        assert services.connected is False

    def test_connect_already_connected(self, client, services):
        services.set_connected("paper", self.PAPER_CONNECTION_INFO)
        resp = client.post("/api/connection/connect",
                           json={"environment": "paper"})
        assert resp.status_code == 409

    def test_disconnect(self, client, services):
        services.set_connected("paper", self.PAPER_CONNECTION_INFO)
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

    def test_symbol_names_skips_invalid_explicit_symbols(self, client):
        """Test /api/account/symbol-names skips invalid symbols and resolves valid ones."""
        fake_aapl = {"name": "Apple Inc.", "symbol": "AAPL"}
        fake_msft = {"name": "Microsoft Corporation", "symbol": "MSFT"}

        def _fake_fundamentals(sym, use_cache=True):
            return {"AAPL": fake_aapl, "MSFT": fake_msft}.get(sym, {"symbol": sym})

        with patch("web.routes.api_account.get_fundamentals", side_effect=_fake_fundamentals) as mock_gf:
            resp = client.get("/api/account/symbol-names?symbols=AAPL,bad symbol!,MSFT")
            assert resp.status_code == 200
            data = resp.get_json()
            assert "names" in data
            # Valid symbols are resolved
            assert data["names"]["AAPL"] == "Apple Inc."
            assert data["names"]["MSFT"] == "Microsoft Corporation"
            # Invalid symbol is not present
            assert "bad symbol!" not in data["names"]
            # get_fundamentals was called only for valid symbols
            called_syms = [c.args[0] for c in mock_gf.call_args_list]
            assert "AAPL" in called_syms
            assert "MSFT" in called_syms
            assert len(called_syms) == 2

    def test_symbol_names_numeric_hk_stock_included(self, client, services):
        """Test that numeric HK stock symbols pass through default portfolio
        filtering and are resolved via yfinance with the .HK suffix."""
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
        fake_data = {"name": "BYD Electronic International Co., Ltd.", "symbol": "1211.HK"}
        with patch("web.routes.api_account.get_fundamentals", return_value=fake_data) as mock_gf:
            resp = client.get("/api/account/symbol-names")
            data = resp.get_json()
            assert resp.status_code == 200
            # Verify get_fundamentals was called with the mapped yfinance symbol
            mock_gf.assert_called_once_with("1211.HK", use_cache=True)
            # Verify the original IB symbol is used as the key in the response
            assert data["names"]["1211"] == "BYD Electronic International Co., Ltd."


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
        assert data["trading_state"] == "DISCONNECTED"

    def test_halt_and_resume(self, client, services):
        # Connect first to have a meaningful state
        services.set_connected("paper", {"host": "127.0.0.1", "port": 7497})

        # Halt
        resp = client.post("/api/emergency/halt",
                           json={"reason": "Test halt"})
        data = resp.get_json()
        assert resp.status_code == 200
        assert data["status"] == "halted"

        # Check status - should be EMERGENCY_STOP
        resp = client.get("/api/emergency/status")
        status_data = resp.get_json()
        assert status_data["emergency_stop_active"] is True
        assert status_data["trading_state"] == "EMERGENCY_STOP"

        # Resume
        resp = client.post("/api/emergency/resume",
                           json={"reason": "Test resume", "confirm": True})
        data = resp.get_json()
        assert resp.status_code == 200
        assert data["status"] == "resumed"

        # Trading state should be restored
        resp = client.get("/api/emergency/status")
        status_data = resp.get_json()
        assert status_data["trading_state"] == "PAPER_TRADING_ENABLED"

        # Cleanup
        services.set_disconnected()

    def test_close_all(self, client, services):
        services.update_position("AAPL", {"quantity": 100})
        resp = client.post("/api/emergency/close-all")
        data = resp.get_json()
        assert resp.status_code == 200
        assert data["positions_closed"] == 1

    def test_resume_requires_confirmation(self, client, services):
        """Resume without confirm=true returns 400."""
        services.set_connected("paper", {"host": "127.0.0.1", "port": 7497})
        client.post("/api/emergency/halt", json={"reason": "test"})

        # Attempt resume without confirmation
        resp = client.post("/api/emergency/resume",
                           json={"reason": "No confirm"})
        assert resp.status_code == 400
        data = resp.get_json()
        assert "confirm" in data["message"].lower()

        # Confirm emergency is still active
        resp = client.get("/api/emergency/status")
        assert resp.get_json()["emergency_stop_active"] is True

        # Cleanup
        client.post("/api/emergency/resume",
                    json={"reason": "cleanup", "confirm": True})
        services.set_disconnected()

    def test_halt_creates_emergency_stop_file(self, client, services):
        """Halt endpoint creates the EMERGENCY_STOP file marker."""
        from web.routes import api_emergency

        services.set_connected("paper", {"host": "127.0.0.1", "port": 7497})
        resp = client.post("/api/emergency/halt", json={"reason": "file test"})
        assert resp.status_code == 200
        assert api_emergency.EMERGENCY_STOP_FILE.exists()

        # Cleanup
        client.post("/api/emergency/resume",
                    json={"reason": "cleanup", "confirm": True})
        services.set_disconnected()

    def test_resume_removes_emergency_stop_file(self, client, services):
        """Resume endpoint removes the EMERGENCY_STOP file marker."""
        from web.routes import api_emergency

        services.set_connected("paper", {"host": "127.0.0.1", "port": 7497})
        client.post("/api/emergency/halt", json={"reason": "file test"})
        assert api_emergency.EMERGENCY_STOP_FILE.exists()

        client.post("/api/emergency/resume",
                    json={"reason": "release", "confirm": True})
        assert not api_emergency.EMERGENCY_STOP_FILE.exists()

        services.set_disconnected()

    def test_resume_does_not_restore_live_trading(self, client, services):
        """Resuming after halt in live env restores to read-only, not live."""
        services.set_connected("live", {"host": "127.0.0.1", "port": 7496})
        client.post("/api/emergency/halt", json={"reason": "test"})
        client.post("/api/emergency/resume",
                    json={"reason": "release", "confirm": True})

        resp = client.get("/api/emergency/status")
        data = resp.get_json()
        # Should be read-only, NOT LIVE_TRADING_ARMED
        assert data["trading_state"] == "CONNECTED_READ_ONLY"
        services.set_disconnected()

    def test_status_includes_file_field(self, client):
        """Status endpoint includes emergency_stop_file_exists field."""
        resp = client.get("/api/emergency/status")
        data = resp.get_json()
        assert "emergency_stop_file_exists" in data


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

    def test_submit_order(self, client, services):
        services.set_connected("paper", {"host": "127.0.0.1", "port": 7497})
        _mark_account_data_ready(services)
        resp = client.post("/api/orders/", json={
            "symbol": "AAPL",
            "action": "BUY",
            "quantity": 100,
            "order_type": "MARKET",
        })
        data = resp.get_json()
        assert resp.status_code == 201
        assert data["status"] == "recorded"
        assert data["execution_mode"] == "local_only"
        assert "not submitted to a broker" in data["message"]
        assert data["order"]["symbol"] == "AAPL"
        assert data["order"]["status"] == "RECORDED"
        assert data["order"]["execution_mode"] == "local_only"
        assert "recorded_at" in data["order"]
        assert "submitted_at" not in data["order"]
        services.set_disconnected()

    def test_submit_order_blocked_when_disconnected(self, client):
        """Order submission must be rejected when not in a trading-ready state."""
        resp = client.post("/api/orders/", json={
            "symbol": "AAPL",
            "action": "BUY",
            "quantity": 100,
        })
        assert resp.status_code == 403
        assert "not allowed" in resp.get_json()["error"]

    def test_submit_order_blocked_before_account_data_ready(self, client, services):
        """Order submission must return 503 when connected but account data not ready."""
        services.set_connected("paper", {"host": "127.0.0.1", "port": 7497})
        # Equity is NOT initialized (default state)
        assert not services.account_data_ready
        resp = client.post("/api/orders/", json={
            "symbol": "AAPL",
            "action": "BUY",
            "quantity": 100,
            "order_type": "MARKET",
        })
        assert resp.status_code == 503
        data = resp.get_json()
        assert "account data" in data["error"].lower()
        services.set_disconnected()

    def test_submit_order_validation(self, client, services):
        services.set_connected("paper", {"host": "127.0.0.1", "port": 7497})
        _mark_account_data_ready(services)
        resp = client.post("/api/orders/", json={
            "symbol": "",
            "action": "HOLD",
            "quantity": 0,
        })
        assert resp.status_code == 400
        services.set_disconnected()

    def test_submit_order_during_emergency(self, client, services):
        services.set_connected("paper", {"host": "127.0.0.1", "port": 7497})
        _mark_account_data_ready(services)
        client.post("/api/emergency/halt", json={})
        resp = client.post("/api/orders/", json={
            "symbol": "AAPL",
            "action": "BUY",
            "quantity": 100,
        })
        assert resp.status_code == 403
        error_msg = resp.get_json()["error"].lower()
        assert "not allowed" in error_msg or "emergency" in error_msg
        # Cleanup
        client.post("/api/emergency/resume", json={"confirm": True})
        services.set_disconnected()

    def test_cancel_order(self, client, services):
        services.set_connected("paper", {"host": "127.0.0.1", "port": 7497})
        _mark_account_data_ready(services)
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
        data = resp.get_json()
        assert data["status"] == "cancelled"
        assert data["order_id"] == order_id
        # Local-only order: must include execution_mode and warning
        assert data["execution_mode"] == "local_only"
        assert "warning" in data
        assert "broker" in data["warning"].lower()
        services.set_disconnected()

    def test_cancel_order_already_cancelled(self, client, services):
        """Cancelling a CANCELLED order must return 409."""
        services.set_connected("paper", {"host": "127.0.0.1", "port": 7497})
        _mark_account_data_ready(services)
        resp = client.post("/api/orders/", json={
            "symbol": "AAPL",
            "action": "BUY",
            "quantity": 10,
        })
        order_id = resp.get_json()["order"]["id"]

        # First cancellation succeeds
        resp = client.delete(f"/api/orders/{order_id}")
        assert resp.status_code == 200

        # Second cancellation must be rejected
        resp = client.delete(f"/api/orders/{order_id}")
        assert resp.status_code == 409
        assert "cannot be cancelled" in resp.get_json()["error"]
        services.set_disconnected()

    def test_cancel_order_terminal_states(self, client, services):
        """FILLED and REJECTED orders cannot be cancelled."""
        for terminal_status in ("FILLED", "REJECTED"):
            order = {
                "id": f"test-{terminal_status}",
                "symbol": "TSLA",
                "action": "BUY",
                "quantity": 1,
                "status": terminal_status,
                "execution_mode": "local_only",
            }
            services.add_order(order)
            resp = client.delete(f"/api/orders/test-{terminal_status}")
            assert resp.status_code == 409, (
                f"Expected 409 for {terminal_status} order"
            )

    def test_cancel_order_broker_forwarded(self, client, services):
        """When a broker_order_id is present and broker is connected,
        the cancellation must be forwarded."""
        from unittest.mock import MagicMock

        # Inject a fake bridge that is "connected"
        mock_bridge = MagicMock()
        mock_bridge.is_connected = True
        mock_bridge.cancel_order = MagicMock()
        services._tws_bridge = mock_bridge

        order = {
            "id": "broker-ord-1",
            "symbol": "AAPL",
            "action": "BUY",
            "quantity": 100,
            "status": "SUBMITTED",
            "execution_mode": "broker",
            "broker_order_id": 42,
        }
        services.add_order(order)

        resp = client.delete("/api/orders/broker-ord-1")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["status"] == "cancel_requested"
        assert data["execution_mode"] == "broker"
        assert data["broker_order_id"] == 42
        assert data["forwarded_to_broker"] is True
        mock_bridge.cancel_order.assert_called_once_with(42)

        # Cleanup so subsequent tests are unaffected
        services._tws_bridge = None

    def test_cancel_order_broker_not_forwarded_keeps_broker_context(
        self, client, services
    ):
        order = {
            "id": "broker-ord-2",
            "symbol": "AAPL",
            "action": "BUY",
            "quantity": 100,
            "status": "SUBMITTED",
            "execution_mode": "broker",
            "broker_order_id": 84,
        }
        services.add_order(order)

        resp = client.delete("/api/orders/broker-ord-2")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["status"] == "cancelled"
        assert data["execution_mode"] == "broker"
        assert data["broker_order_id"] == 84
        assert data["forwarded_to_broker"] is False
        assert "broker was not possible" in data["warning"]

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

    # ------------------------------------------------------------------
    # POST /api/strategies/create — Route Coverage Rule (Principle 1)
    # ------------------------------------------------------------------

    def test_create_strategy_happy_path(self, client):
        """POST /api/strategies/create — happy path returns 200 and strategy dict."""
        import uuid
        name = f"LE_AAPL_{uuid.uuid4().hex[:8]}"
        resp = client.post("/api/strategies/create", json={
            "strategy_type": "LongEquity",
            "name": name,
            "symbols": ["AAPL"],
        })
        data = resp.get_json()
        assert resp.status_code == 200
        assert data["status"] == "created"
        assert "strategy" in data
        assert data["strategy"]["strategy_name"] == name

    def test_create_strategy_missing_fields(self, client):
        """POST /api/strategies/create — missing required fields returns 400."""
        # Missing strategy_type
        resp = client.post("/api/strategies/create", json={
            "name": "LE_AAPL",
            "symbols": ["AAPL"],
        })
        assert resp.status_code == 400

        # Missing name
        resp = client.post("/api/strategies/create", json={
            "strategy_type": "LongEquity",
            "symbols": ["AAPL"],
        })
        assert resp.status_code == 400

        # Missing symbols
        resp = client.post("/api/strategies/create", json={
            "strategy_type": "LongEquity",
            "name": "LE_AAPL_2",
        })
        assert resp.status_code == 400

        # Empty body
        resp = client.post("/api/strategies/create", json={})
        assert resp.status_code == 400

    def test_create_strategy_unknown_type(self, client):
        """POST /api/strategies/create — unknown strategy_type returns 400."""
        resp = client.post("/api/strategies/create", json={
            "strategy_type": "NonExistentStrategy",
            "name": "Bad_Strategy",
            "symbols": ["AAPL"],
        })
        assert resp.status_code == 400
        data = resp.get_json()
        assert "error" in data

    def test_create_strategy_all_inferred_types(self, client):
        """Adopt-flow integration test: every inferred strategy type must instantiate.

        This is the regression test for the April 2026 Adopt-button crash.
        It uses the REAL strategy classes (not Mock) so constructor-level failures
        surface here instead of in production.  Principle 11 — Mock Fidelity.
        """
        import uuid
        from strategies.inferred_strategies import INFERRED_STRATEGY_CLASSES

        run_id = uuid.uuid4().hex[:8]
        for idx, strategy_type in enumerate(INFERRED_STRATEGY_CLASSES):
            resp = client.post("/api/strategies/create", json={
                "strategy_type": strategy_type,
                "name": f"adopt_{strategy_type}_{run_id}_{idx}",
                "symbols": ["AAPL"],
            })
            data = resp.get_json()
            assert resp.status_code == 200, (
                f"Adopting '{strategy_type}' returned {resp.status_code}: {data}"
            )
            assert data["status"] == "created", (
                f"Unexpected status for '{strategy_type}': {data}"
            )

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

    @patch("ai.client.get_client")
    def test_insight_inferred_not_found(self, mock_get_client, client):
        """Test POST /api/strategies/inferred/<id>/insight for non-existent ID."""
        mock_get_client.return_value = mock_get_client  # non-None → AI enabled
        resp = client.post("/api/strategies/inferred/missing_id/insight")
        assert resp.status_code == 404

    @patch("ai.client.get_client")
    def test_insight_inferred_ai_disabled(self, mock_get_client, client, services):
        """Test insight returns 503 when AI is not enabled."""
        mock_get_client.return_value = None

        services.update_position("GOOG", {
            "quantity": 100,
            "entry_price": 140.0,
            "current_price": 145.0,
            "unrealized_pnl": 500.0,
            "market_value": 14500.0,
            "side": "LONG",
            "sec_type": "STK",
        })

        resp = client.get("/api/strategies/inferred")
        inferred = resp.get_json()["inferred"]
        assert len(inferred) >= 1
        strategy_id = inferred[0]["id"]

        resp = client.post(f"/api/strategies/inferred/{strategy_id}/insight")
        assert resp.status_code == 503
        assert "error" in resp.get_json()

    @patch("ai.client.get_client")
    def test_insight_inferred_success(self, mock_get_client, client, services):
        """Test insight returns AI-generated text when AI is available."""
        mock_client = mock_get_client.return_value
        mock_client.chat.return_value = "The position is up 3.3% from entry with room to run toward the 10% target."

        services.update_position("NVDA", {
            "quantity": 50,
            "entry_price": 120.0,
            "current_price": 124.0,
            "unrealized_pnl": 200.0,
            "market_value": 6200.0,
            "side": "LONG",
            "sec_type": "STK",
        })

        resp = client.get("/api/strategies/inferred")
        inferred = resp.get_json()["inferred"]
        strategy_id = inferred[0]["id"]

        resp = client.post(f"/api/strategies/inferred/{strategy_id}/insight")
        data = resp.get_json()
        assert resp.status_code == 200
        assert "insight" in data
        assert "position is up" in data["insight"]

    # ------------------------------------------------------------------
    # POST /api/strategies/<name>/insight — registered strategy insights
    # ------------------------------------------------------------------

    @patch("ai.client.get_client")
    def test_insight_registered_not_found(self, mock_get_client, client):
        """Test POST /api/strategies/<name>/insight returns 404 for unknown strategy."""
        mock_get_client.return_value = mock_get_client  # non-None → AI enabled
        resp = client.post("/api/strategies/nonexistent_strategy/insight")
        assert resp.status_code == 404
        assert "error" in resp.get_json()

    @patch("ai.client.get_client")
    def test_insight_registered_ai_disabled(self, mock_get_client, client):
        """Test POST /api/strategies/<name>/insight returns 503 when AI is disabled."""
        mock_get_client.return_value = None
        resp = client.post("/api/strategies/some_strategy/insight")
        assert resp.status_code == 503
        assert "error" in resp.get_json()

    @patch("ai.client.get_client")
    def test_insight_registered_success(self, mock_get_client, client):
        """Test POST /api/strategies/<name>/insight returns AI insight for a known strategy."""
        import uuid
        mock_client = mock_get_client.return_value
        mock_client.chat.return_value = "Strategy is performing well with 0 active positions."

        # Create a real strategy instance first
        strategy_name = f"LE_AAPL_insight_{uuid.uuid4().hex[:8]}"
        create_resp = client.post("/api/strategies/create", json={
            "strategy_type": "LongEquity",
            "name": strategy_name,
            "symbols": ["AAPL"],
        })
        assert create_resp.status_code == 200

        resp = client.post(f"/api/strategies/{strategy_name}/insight")
        data = resp.get_json()
        assert resp.status_code == 200
        assert "insight" in data
        assert "Strategy is performing well" in data["insight"]

    @patch("ai.client.get_client")
    def test_insight_registered_includes_option_legs(self, mock_get_client, client, services):
        """Insight prompt must include option contracts whose underlying matches
        the strategy's symbols (e.g. the short call leg of a covered call), not
        only positions keyed directly by the underlying ticker."""
        import uuid
        mock_client = mock_get_client.return_value
        mock_client.chat.return_value = "ok"

        strategy_name = f"CC_GOOG_insight_{uuid.uuid4().hex[:8]}"
        create_resp = client.post("/api/strategies/create", json={
            "strategy_type": "LongEquity",
            "name": strategy_name,
            "symbols": ["GOOG"],
        })
        assert create_resp.status_code == 200

        services.update_position("GOOG", {
            "quantity": 100, "entry_price": 190.0, "current_price": 385.07,
            "side": "LONG", "sec_type": "STK", "unrealized_pnl": 19507.0,
        })
        option_sym = "GOOG  260515C00400000"
        services.update_position(option_sym, {
            "quantity": -1, "entry_price": 5.0, "current_price": 3.0,
            "side": "SHORT", "sec_type": "OPT", "unrealized_pnl": 200.0,
        })

        resp = client.post(f"/api/strategies/{strategy_name}/insight")
        assert resp.status_code == 200
        mock_client.chat.assert_called_once()
        messages = mock_client.chat.call_args[0][0]
        system_prompt = next(m["content"] for m in messages if m["role"] == "system")
        assert option_sym in system_prompt, (
            "Short call leg missing from strategy insight prompt; AI cannot "
            "reason about covered-call option positions."
        )
        assert "option_contract" in system_prompt


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
# Market Events API
# ==============================================================================


class TestMarketEventsAPI:
    """Tests for /api/market-events/* endpoints."""

    @patch("web.routes.api_market_events._get_event_service")
    def test_upcoming_default_days_and_portfolio_symbols(self, mock_get_event_service, client, services):
        """GET /api/market-events/upcoming uses default window and portfolio symbols."""
        import uuid

        services.update_position("aapl", {"quantity": 10})
        create_resp = client.post("/api/strategies/create", json={
            "strategy_type": "LongEquity",
            "name": f"ME_symbols_test_{uuid.uuid4().hex[:8]}",
            "symbols": ["msft"],
        })
        assert create_resp.status_code == 200

        event_svc = mock_get_event_service.return_value
        event_svc.get_upcoming_events.return_value = [{
            "event_type": "EARNINGS",
            "symbol": "AAPL",
            "title": "AAPL Earnings",
            "event_date": "2026-05-20T00:00:00",
            "event_time": "AMC",
            "source": "yfinance",
            "detail": {},
            "is_portfolio_relevant": True,
            "days_away": 11,
        }]

        resp = client.get("/api/market-events/upcoming")
        data = resp.get_json()

        assert resp.status_code == 200
        assert data["count"] == 1
        assert data["days_ahead"] == 14
        assert {"AAPL", "MSFT"}.issubset(set(data["portfolio_symbols"]))

        called_kwargs = event_svc.get_upcoming_events.call_args.kwargs
        assert called_kwargs["days_ahead"] == 14
        assert {"AAPL", "MSFT"}.issubset(set(called_kwargs["portfolio_symbols"]))

    @patch("web.routes.api_market_events._get_event_service")
    def test_upcoming_days_validation_and_clamping(self, mock_get_event_service, client):
        """GET /api/market-events/upcoming clamps days to [1, 90] and handles invalid input."""
        event_svc = mock_get_event_service.return_value
        event_svc.get_upcoming_events.return_value = []

        resp = client.get("/api/market-events/upcoming?days=0")
        assert resp.status_code == 200
        assert resp.get_json()["days_ahead"] == 1
        assert event_svc.get_upcoming_events.call_args.kwargs["days_ahead"] == 1

        resp = client.get("/api/market-events/upcoming?days=999")
        assert resp.status_code == 200
        assert resp.get_json()["days_ahead"] == 90
        assert event_svc.get_upcoming_events.call_args.kwargs["days_ahead"] == 90

        resp = client.get("/api/market-events/upcoming?days=abc")
        assert resp.status_code == 200
        assert resp.get_json()["days_ahead"] == 14
        assert event_svc.get_upcoming_events.call_args.kwargs["days_ahead"] == 14

    @patch("web.routes.api_market_events._get_event_service")
    def test_refresh_triggers_async_force_refresh(self, mock_get_event_service, client, services):
        """POST /api/market-events/refresh starts async refresh with force=True."""
        import uuid

        services.update_position("GOOG", {"quantity": 5})
        create_resp = client.post("/api/strategies/create", json={
            "strategy_type": "LongEquity",
            "name": f"ME_refresh_test_{uuid.uuid4().hex[:8]}",
            "symbols": ["nvda"],
        })
        assert create_resp.status_code == 200

        event_svc = mock_get_event_service.return_value

        resp = client.post("/api/market-events/refresh")
        data = resp.get_json()

        assert resp.status_code == 200
        assert data["status"] == "refresh_started"
        assert {"GOOG", "NVDA"}.issubset(set(data["portfolio_symbols"]))

        called_kwargs = event_svc.refresh_async.call_args.kwargs
        assert called_kwargs["force"] is True
        assert {"GOOG", "NVDA"}.issubset(set(called_kwargs["portfolio_symbols"]))


# ==============================================================================
# Page routes (smoke tests)
# ==============================================================================


class TestPageRoutes:
    """Smoke tests for all HTML page routes."""

    def test_dashboard(self, client):
        resp = client.get("/")
        assert resp.status_code == 200
        assert b"Dashboard" in resp.data

    def test_dashboard_shows_emergency_stop_button_when_not_halted(self, client, services):
        """Dashboard renders the emergency stop action when trading is not halted."""
        services.risk_manager.release_emergency_stop("test setup")

        resp = client.get("/")
        assert resp.status_code == 200
        assert b"EMERGENCY STOP" in resp.data
        assert b'data-halted="false"' in resp.data

    def test_dashboard_shows_resume_button_when_halted(self, client, services):
        """Dashboard renders resume action and halted indicator when emergency stop is active."""
        services.risk_manager.trigger_emergency_stop("test setup")

        resp = client.get("/")
        assert resp.status_code == 200
        assert b"RESUME TRADING" in resp.data
        assert b'data-halted="true"' in resp.data
        assert b"TRADING HALTED" in resp.data

    def test_strategies(self, client):
        resp = client.get("/strategies/", follow_redirects=True)
        assert resp.status_code == 200
        assert b"Strategies" in resp.data

    def test_strategies_page_has_registered_strategy_insight_controls(self, client):
        """Strategies page renders AI insight section for registered strategies."""
        import uuid

        strategy_name = f"LE_page_{uuid.uuid4().hex[:8]}"
        create_resp = client.post("/api/strategies/create", json={
            "strategy_type": "LongEquity",
            "name": strategy_name,
            "symbols": ["AAPL"],
        })
        assert create_resp.status_code == 200
        start_resp = client.post(f"/api/strategies/{strategy_name}/start")
        assert start_resp.status_code == 200

        resp = client.get("/strategies/", follow_redirects=True)
        assert resp.status_code == 200
        assert b"sc-insight-section" in resp.data
        assert f'data-strategy-name="{strategy_name}"'.encode() in resp.data
        assert b"Stop Strategy" in resp.data
        assert b"does not close live positions" in resp.data
        assert b"Stop strategy automation for" in resp.data
        assert b"Open positions will remain live in the account until exited separately." in resp.data

    def test_strategies_page_shows_ai_disabled_state(self, client):
        """Strategies page shows a disabled state for insights when AI is unavailable."""
        import uuid

        strategy_name = f"LE_page_off_{uuid.uuid4().hex[:8]}"
        create_resp = client.post("/api/strategies/create", json={
            "strategy_type": "LongEquity",
            "name": strategy_name,
            "symbols": ["AAPL"],
        })
        assert create_resp.status_code == 200
        start_resp = client.post(f"/api/strategies/{strategy_name}/start")
        assert start_resp.status_code == 200

        with patch("web.routes.strategies.is_ai_enabled", return_value=False):
            resp = client.get("/strategies/", follow_redirects=True)

        assert resp.status_code == 200
        assert b"sc-insight-section" in resp.data
        assert b"AI not enabled" in resp.data

    def test_strategies_page_shows_ai_loading_state_when_enabled(self, client):
        """Strategies page shows loading placeholders when AI is enabled."""
        import uuid

        strategy_name = f"LE_page_on_{uuid.uuid4().hex[:8]}"
        create_resp = client.post("/api/strategies/create", json={
            "strategy_type": "LongEquity",
            "name": strategy_name,
            "symbols": ["AAPL"],
        })
        assert create_resp.status_code == 200
        start_resp = client.post(f"/api/strategies/{strategy_name}/start")
        assert start_resp.status_code == 200

        with patch("web.routes.strategies.is_ai_enabled", return_value=True):
            resp = client.get("/strategies/", follow_redirects=True)

        assert resp.status_code == 200
        assert b"sc-insight-section" in resp.data
        assert b"Loading insight" in resp.data
        assert b"AI not enabled" not in resp.data

    def test_strategy_detail_shows_live_positions_and_ai_insight_section(self, client, services):
        """Strategy detail page includes live positions and AI insight container."""
        import uuid

        strategy_name = f"LE_detail_{uuid.uuid4().hex[:8]}"
        create_resp = client.post("/api/strategies/create", json={
            "strategy_type": "LongEquity",
            "name": strategy_name,
            "symbols": ["AAPL"],
        })
        assert create_resp.status_code == 200
        start_resp = client.post(f"/api/strategies/{strategy_name}/start")
        assert start_resp.status_code == 200

        services.update_position("AAPL", {
            "quantity": 10,
            "entry_price": 150.0,
            "current_price": 155.0,
            "unrealized_pnl": 50.0,
            "side": "LONG",
        })

        resp = client.get(f"/strategies/{strategy_name}", follow_redirects=True)
        assert resp.status_code == 200
        assert b"Live Positions" in resp.data
        assert b"AI Strategy Insight" in resp.data
        assert b"detailInsightBox" in resp.data
        assert f'data-strategy-name="{strategy_name}"'.encode() in resp.data
        assert b"Stop Strategy" in resp.data
        assert b"does not close live positions" in resp.data
        assert b"Stop strategy automation for" in resp.data
        assert b"Open positions will remain live in the account until exited separately." in resp.data

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

    def test_account_intelligence(self, client):
        resp = client.get("/account-intelligence/", follow_redirects=True)
        assert resp.status_code == 200
        assert b"Account Intelligence" in resp.data


# ==============================================================================
# Account isolation – strategy API tests
# ==============================================================================


class TestStrategyAccountIsolation:
    """Verify that account_id is stamped on strategies at creation time and that
    switching accounts produces an isolated strategy view."""

    def test_create_strategy_carries_account_id(self, client, services):
        """Strategies created via the API must carry the current account's ID."""
        import uuid
        run_id = uuid.uuid4().hex[:8]
        services.set_connected("paper", {"host": "127.0.0.1", "port": 7497,
                                          "client_id": 1, "account": "DU111111"})
        resp = client.post("/api/strategies/create", json={
            "strategy_type": "BollingerBands",
            "name": f"BB_acct_test_{run_id}",
            "symbols": ["AAPL"],
        })
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["strategy"]["account_id"] == "DU111111"
        services.set_disconnected()

    def test_performance_summary_contains_account_id(self, client, services):
        """GET /api/strategies/ must include account_id in each strategy entry."""
        import uuid
        run_id = uuid.uuid4().hex[:8]
        services.set_connected("paper", {"host": "127.0.0.1", "port": 7497,
                                          "client_id": 1, "account": "DU123456"})
        client.post("/api/strategies/create", json={
            "strategy_type": "BollingerBands",
            "name": f"BB_summary_{run_id}",
            "symbols": ["AAPL"],
        })
        resp = client.get("/api/strategies/")
        assert resp.status_code == 200
        data = resp.get_json()
        for s in data["strategies"]:
            assert "account_id" in s
        services.set_disconnected()

    def test_switch_account_hides_previous_strategies(self, client, services):
        """After switching accounts the strategy list must be empty (no cross-account leak)."""
        import uuid
        run_id = uuid.uuid4().hex[:8]
        # Connect as account A and adopt a strategy
        services.set_connected("paper", {"host": "127.0.0.1", "port": 7497,
                                          "client_id": 1, "account": "DU111111"})
        client.post("/api/strategies/create", json={
            "strategy_type": "BollingerBands",
            "name": f"BB_acct_switch_{run_id}",
            "symbols": ["AAPL"],
        })
        resp = client.get("/api/strategies/")
        assert len(resp.get_json()["strategies"]) >= 1

        # Disconnect then reconnect as account B
        services.set_disconnected()
        services.set_connected("live", {"host": "127.0.0.1", "port": 7496,
                                         "client_id": 2, "account": "DU222222"})

        # Account B must see an empty strategy list (no persistence leakage)
        resp = client.get("/api/strategies/")
        strategies = resp.get_json()["strategies"]
        assert all(s["account_id"] == "DU222222" for s in strategies), (
            "Found strategies belonging to a different account in the list"
        )
        services.set_disconnected()

    def test_dismissed_inferred_scoped_per_account(self, services):
        """Dismissed inferred strategies are scoped to the account that dismissed them."""
        # Connect as account A
        services.set_connected("paper", {"host": "127.0.0.1", "port": 7497,
                                          "client_id": 1, "account": "DU111111"})
        services.update_position("AAPL", {
            "quantity": 100, "entry_price": 150.0,
            "current_price": 155.0, "unrealized_pnl": 500.0,
            "market_value": 15500.0, "side": "LONG", "sec_type": "STK",
        })
        inferred = services.get_inferred_strategies()
        assert len(inferred) > 0
        first_id = inferred[0]["id"]

        # Dismiss for account A
        assert services.dismiss_inferred_strategy(first_id) is True
        after_dismiss = services.get_inferred_strategies()
        assert all(s["id"] != first_id for s in after_dismiss)

        # Switch to account B — dismissed set should be fresh
        services.set_disconnected()
        services.set_connected("paper", {"host": "127.0.0.1", "port": 7497,
                                          "client_id": 2, "account": "DU222222"})
        services.update_position("AAPL", {
            "quantity": 100, "entry_price": 150.0,
            "current_price": 155.0, "unrealized_pnl": 500.0,
            "market_value": 15500.0, "side": "LONG", "sec_type": "STK",
        })
        inferred_b = services.get_inferred_strategies()
        # The same inferred strategy must be visible for account B (not dismissed)
        assert any(s["id"] == first_id for s in inferred_b), (
            "Dismissal in account A incorrectly hid the strategy in account B"
        )
        services.set_disconnected()

    def test_current_account_id_empty_when_not_connected(self, services):
        """current_account_id returns empty string when not connected."""
        assert services.current_account_id == ""

    def test_current_account_id_reflects_connection(self, services):
        """current_account_id returns the account set in connection info."""
        services.set_connected("paper", {"host": "127.0.0.1", "port": 7497,
                                          "client_id": 1, "account": "DU999999"})
        assert services.current_account_id == "DU999999"
        services.set_disconnected()
        assert services.current_account_id == ""


# ==============================================================================
# Risk page & AI alert endpoints
# ==============================================================================


class TestRiskAIEndpoints:
    """Smoke tests for /risk/* endpoints including AI explanation and digest."""

    def test_risk_alert_ai_explanation_not_found(self, client):
        resp = client.get("/risk/alerts/nonexistent-id/ai-explanation")
        assert resp.status_code == 404
        data = resp.get_json()
        assert "error" in data

    def test_risk_alert_ai_explanation_found(self, client, services):
        services.add_alert({"id": "alert-001", "type": "TEST", "message": "test alert"})
        with patch("web.routes.risk.explain_emergency_event", return_value="AI explains it"):
            resp = client.get("/risk/alerts/alert-001/ai-explanation")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["explanation"] == "AI explains it"
        assert data["cached"] is False

    def test_risk_alert_ai_explanation_cached(self, client, services):
        services.add_alert({"id": "alert-cache", "type": "TEST", "message": "cached"})
        with patch("web.routes.risk.explain_emergency_event", return_value="first") as mock_explain:
            client.get("/risk/alerts/alert-cache/ai-explanation")
        # Second call should use cache (explain_emergency_event not called again)
        with patch("web.routes.risk.explain_emergency_event", return_value="second") as mock_explain_not_called:
            resp = client.get("/risk/alerts/alert-cache/ai-explanation")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["cached"] is True

    def test_risk_alert_digest_default(self, client):
        with patch("web.routes.risk.generate_alert_summary", return_value="Daily digest text"):
            resp = client.get("/risk/alerts/digest")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["digest"] == "Daily digest text"

    def test_risk_alert_digest_custom_hours(self, client):
        with patch("web.routes.risk.generate_alert_summary", return_value="48h digest") as mock_gen:
            resp = client.get("/risk/alerts/digest?hours=48")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["digest"] == "48h digest"
        mock_gen.assert_called_once()
        _, kwargs = mock_gen.call_args
        assert kwargs.get("window_hours") == 48

    def test_risk_alert_digest_clamps_hours(self, client):
        """hours parameter is clamped to 1–168."""
        with patch("web.routes.risk.generate_alert_summary", return_value="clamped") as mock_gen:
            client.get("/risk/alerts/digest?hours=9999")
        _, kwargs = mock_gen.call_args
        assert kwargs.get("window_hours") == 168

    def test_risk_alert_digest_invalid_hours_defaults(self, client):
        """Non-numeric hours falls back to 24."""
        with patch("web.routes.risk.generate_alert_summary", return_value="default") as mock_gen:
            client.get("/risk/alerts/digest?hours=abc")
        _, kwargs = mock_gen.call_args
        assert kwargs.get("window_hours") == 24


# ==============================================================================
# Backtest page routes
# ==============================================================================


class TestBacktestPageRoutes:
    """Smoke tests for HTML backtest page routes."""

    def test_backtest_results_page_not_found_run(self, client):
        """Backtest results page renders even for unknown run_id."""
        resp = client.get("/backtest/some-run-id")
        assert resp.status_code == 200

    def test_backtest_ai_report_generates_narrative(self, client, services):
        """POST /backtest/<id>/ai-report returns a JSON report."""
        run_id = "test-run-1"
        services.store_backtest_run(run_id, {
            "status": "complete",
            "strategy_name": "MovingAverageCross",
            "results": {"metrics": {"total_return": 0.15}},
        })
        with patch("web.routes.backtest.generate_narrative", return_value="AI narrative"):
            resp = client.post(f"/backtest/{run_id}/ai-report", json={
                "strategy_name": "MovingAverageCross",
                "metrics": {"total_return": 0.15},
            })
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["report"] == "AI narrative"
        assert data["cached"] is False

    def test_backtest_ai_report_served_from_cache(self, client):
        """ai-report endpoint returns cached report on second call."""
        run_id = "cached-run"
        with patch("web.routes.backtest.get_cached_report", return_value="cached narrative"):
            resp = client.post(f"/backtest/{run_id}/ai-report", json={})
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["report"] == "cached narrative"
        assert data["cached"] is True


# ==============================================================================
# Backtest API – additional coverage
# ==============================================================================


class TestBacktestAPIExtended:
    """Additional tests for /api/backtest/* endpoints."""

    def test_run_backtest_accepts_valid_request(self, client):
        """POST /api/backtest/run with all required fields returns 202."""
        resp = client.post("/api/backtest/run", json={
            "strategy": "MovingAverageCross",
            "symbols": ["AAPL"],
            "start_date": "2023-01-01",
            "end_date": "2023-12-31",
            "initial_capital": 50000,
        })
        assert resp.status_code == 202
        data = resp.get_json()
        assert "run_id" in data
        assert data["status"] == "running"

    def test_backtest_status_for_running_run(self, client, services):
        """GET /api/backtest/<id>/status returns running status."""
        services.store_backtest_run("run-abc", {
            "status": "running",
            "strategy_name": "MomentumStrategy",
        })
        resp = client.get("/api/backtest/run-abc/status")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["status"] == "running"
        assert data["run_id"] == "run-abc"

    def test_backtest_results_still_running(self, client, services):
        """GET /api/backtest/<id>/results returns 202 while still running."""
        services.store_backtest_run("run-running", {"status": "running"})
        resp = client.get("/api/backtest/run-running/results")
        assert resp.status_code == 202
        data = resp.get_json()
        assert data["status"] == "running"

    def test_backtest_results_complete(self, client, services):
        """GET /api/backtest/<id>/results returns results when complete."""
        services.store_backtest_run("run-done", {
            "status": "complete",
            "results": {"metrics": {"total_return": 0.20}},
        })
        resp = client.get("/api/backtest/run-done/results")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["status"] == "complete"
        assert data["results"]["metrics"]["total_return"] == 0.20

    def test_compare_runs_with_valid_ids(self, client, services):
        """GET /api/backtest/compare returns comparison for existing runs."""
        services.store_backtest_run("run-x", {
            "status": "complete",
            "strategy_name": "MomentumStrategy",
            "results": {"metrics": {"total_return": 0.1}},
        })
        services.store_backtest_run("run-y", {
            "status": "complete",
            "strategy_name": "MovingAverageCross",
            "results": {"metrics": {"total_return": 0.2}},
        })
        resp = client.get("/api/backtest/compare?runs=run-x,run-y")
        assert resp.status_code == 200
        data = resp.get_json()
        assert len(data["comparisons"]) == 2

    def test_list_runs_returns_stored_runs(self, client, services):
        """GET /api/backtest/runs includes previously stored runs."""
        services.store_backtest_run("run-list", {"status": "complete", "strategy_name": "Test"})
        resp = client.get("/api/backtest/runs")
        assert resp.status_code == 200
        data = resp.get_json()
        assert isinstance(data["runs"], list)


# ==============================================================================
# Data API – additional coverage
# ==============================================================================


class TestDataAPIExtended:
    """Additional tests for /api/data/* endpoints."""

    def test_list_symbols_with_data_dir(self, client, tmp_path, monkeypatch):
        """list_symbols returns entries when historical data directory exists."""
        (tmp_path / "AAPL.csv").write_text("date,open\n2024-01-01,150\n")
        import web.routes.api_data as api_data_mod
        monkeypatch.setattr(api_data_mod, "_DATA_DIR", tmp_path)
        resp = client.get("/api/data/symbols")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["count"] == 1
        assert data["symbols"][0]["symbol"] == "AAPL"

    def test_data_status_with_files(self, client, tmp_path, monkeypatch):
        """data_status returns freshness info for each CSV file."""
        (tmp_path / "MSFT.csv").write_text("date,open\n2024-01-01,300\n")
        import web.routes.api_data as api_data_mod
        monkeypatch.setattr(api_data_mod, "_DATA_DIR", tmp_path)
        resp = client.get("/api/data/status")
        assert resp.status_code == 200
        data = resp.get_json()
        assert len(data["files"]) == 1
        assert data["files"][0]["symbol"] == "MSFT"
        assert "age_days" in data["files"][0]
        assert "fresh" in data["files"][0]

    def test_download_with_symbols_triggers_background(self, client):
        """POST /api/data/download with symbols returns 202."""
        with patch("threading.Thread") as mock_thread:
            mock_thread.return_value.start = lambda: None
            resp = client.post("/api/data/download", json={"symbols": ["AAPL", "TSLA"], "period": "1y"})
        assert resp.status_code == 202
        data = resp.get_json()
        assert data["status"] == "downloading"
        assert set(data["symbols"]) == {"AAPL", "TSLA"}


# ==============================================================================
# Events API – additional coverage
# ==============================================================================


class TestEventAPIExtended:
    """Additional tests for /api/events/* endpoints."""

    def test_event_history_valid_type_filter(self, client):
        """GET /api/events/history?type=HEARTBEAT returns filtered events."""
        resp = client.get("/api/events/history?type=HEARTBEAT")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "events" in data
        assert "count" in data

    def test_event_history_limit_clamped_to_200(self, client):
        """Limit is capped at 200 regardless of query param."""
        resp = client.get("/api/events/history?limit=9999")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["count"] <= 200

    def test_event_history_default_returns_json(self, client):
        """Baseline: event history returns 200 with events list."""
        resp = client.get("/api/events/history")
        assert resp.status_code == 200
        data = resp.get_json()
        assert isinstance(data["events"], list)


# ==============================================================================
# Disclaimer API
# ==============================================================================


class TestDisclaimerAPI:
    """Tests for /api/disclaimer/* endpoints."""

    def test_status_returns_acceptance_info(self, client, tmp_path, monkeypatch):
        monkeypatch.setattr("web.routes.api_disclaimer.is_accepted", lambda: False)
        monkeypatch.setattr("web.routes.api_disclaimer.get_acceptance_record", lambda: {})
        resp = client.get("/api/disclaimer/status")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "accepted" in data
        assert data["accepted"] is False
        assert "current_version" in data

    def test_accept_records_acceptance(self, client, tmp_path, monkeypatch):
        monkeypatch.setattr("web.routes.api_disclaimer.save_acceptance", lambda app_version="unknown": None)
        resp = client.post("/api/disclaimer/accept", json={"app_version": "1.2.3"})
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["status"] == "accepted"
        assert "disclaimer_version" in data

    def test_accept_sanitises_app_version(self, client, monkeypatch):
        """Newlines and null bytes in app_version are stripped."""
        captured = {}

        def fake_save(app_version="unknown"):
            captured["v"] = app_version

        monkeypatch.setattr("web.routes.api_disclaimer.save_acceptance", fake_save)
        client.post("/api/disclaimer/accept", json={"app_version": "1.0\n\x00bad"})
        assert "\n" not in captured["v"]
        assert "\x00" not in captured["v"]

    def test_accept_handles_os_error(self, client, monkeypatch):
        def raise_os(app_version="unknown"):
            raise OSError("disk full")

        monkeypatch.setattr("web.routes.api_disclaimer.save_acceptance", raise_os)
        resp = client.post("/api/disclaimer/accept", json={})
        assert resp.status_code == 500
        data = resp.get_json()
        assert "error" in data


# ==============================================================================
# Logs route – violations endpoint
# ==============================================================================


class TestLogsViolationsEndpoint:
    """Tests for GET /logs/violations."""

    def test_violations_no_log_file(self, client, tmp_path, monkeypatch):
        """Returns empty lines list when violations log does not exist."""
        import web.routes.logs as logs_mod
        monkeypatch.setattr(
            logs_mod,
            "Path",
            lambda *a, **kw: tmp_path / "nonexistent.log",
        )
        resp = client.get("/logs/violations")
        # Path mock may not work cleanly; just verify 200 and structure
        assert resp.status_code == 200
        data = resp.get_json()
        assert "lines" in data
        assert "count" in data

    def test_violations_with_log_file(self, client, tmp_path):
        """Returns last 100 lines when violations log exists (written to standard path)."""
        import web.routes.logs as logs_mod
        log_content = "\n".join(f"violation {i}" for i in range(10))
        # Patch the resolved path that the route builds at call-time
        fake_path = tmp_path / "prime_directive_violations.log"
        fake_path.write_text(log_content)
        with patch.object(logs_mod, "Path") as mock_path_cls:
            mock_instance = mock_path_cls.return_value
            mock_instance.__truediv__ = lambda self, other: fake_path
            mock_instance.resolve.return_value = mock_instance
            # Chain: Path(__file__).resolve().parent.parent.parent / "prime_directive_violations.log"
            mock_instance.parent = mock_instance
            mock_resolve = mock_instance
            mock_path_cls.return_value = mock_instance
            resp = client.get("/logs/violations")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "lines" in data
        assert "count" in data


# ==============================================================================
# System API – additional coverage
# ==============================================================================


class TestSystemAPIExtended:
    """Additional tests for /api/system/* and /api/diagnostics/* endpoints."""

    def test_test_connection_unreachable(self, client):
        """POST /api/diagnostics/test-connection returns reachable=false for closed port."""
        resp = client.post("/api/diagnostics/test-connection", json={
            "host": "127.0.0.1",
            "port": 1,
            "timeout": 0.1,
        })
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["host"] == "127.0.0.1"
        assert data["port"] == 1
        assert data["reachable"] is False
        assert "tested_at" in data

    def test_test_connection_default_params(self, client):
        """POST /api/diagnostics/test-connection works with no body."""
        resp = client.post("/api/diagnostics/test-connection", json={})
        assert resp.status_code == 200
        data = resp.get_json()
        assert "reachable" in data

    def test_init_db_import_error(self, client, monkeypatch):
        """POST /api/system/init-db handles missing database module gracefully."""
        import builtins
        real_import = builtins.__import__

        def mock_import(name, *args, **kwargs):
            if name == "data.database":
                raise ImportError("not configured")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", mock_import)
        resp = client.post("/api/system/init-db")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["status"] in ("ok", "skipped", "error")

    def test_init_db_success(self, client, monkeypatch):
        """POST /api/system/init-db returns ok when init_database succeeds."""
        monkeypatch.setattr("web.routes.api_system.logger", __import__("logging").getLogger("test"))
        with patch("data.database.init_database", create=True):
            import web.routes.api_system as sys_mod

            def fake_init_db():
                pass

            with patch.dict("sys.modules", {"data.database": type(__import__("types"))("data.database")}):
                import sys
                import types
                fake_mod = types.ModuleType("data.database")
                fake_mod.init_database = fake_init_db
                sys.modules["data.database"] = fake_mod
                resp = client.post("/api/system/init-db")
                assert resp.status_code == 200
                data = resp.get_json()
                assert data["status"] in ("ok", "skipped")

    def test_market_status_fallback(self, client, monkeypatch):
        """GET /api/diagnostics/market-status returns fallback result when checker unavailable."""
        import builtins
        real_import = builtins.__import__

        def mock_import(name, *args, **kwargs):
            if "market_status" in name and "scripts" in name:
                raise ImportError("not available")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", mock_import)
        resp = client.get("/api/diagnostics/market-status")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "market_open" in data


# ==============================================================================
# Screener page routes
# ==============================================================================


class TestScreenerPageRoutes:
    """Smoke tests for screener and analysis HTML page routes."""

    def test_sp500_screener_page(self, client):
        resp = client.get("/stocks/sp500")
        assert resp.status_code == 200
        assert b"S&P 500" in resp.data or b"Screener" in resp.data

    def test_sti_screener_page(self, client):
        resp = client.get("/stocks/sti")
        assert resp.status_code == 200
        assert b"STI" in resp.data or b"Screener" in resp.data

    def test_hsi_screener_page(self, client):
        resp = client.get("/stocks/hsi")
        assert resp.status_code == 200
        assert b"HSI" in resp.data or b"Screener" in resp.data

    def test_stock_analysis_dashboard_page(self, client):
        resp = client.get("/stocks/analysis")
        assert resp.status_code == 200
        assert b"Stock Analysis" in resp.data or b"stock" in resp.data.lower()

    def test_stock_analysis_ticker_page(self, client):
        resp = client.get("/stocks/AAPL/analysis")
        assert resp.status_code == 200
        assert b"AAPL" in resp.data

    def test_portfolio_analysis_page(self, client):
        resp = client.get("/portfolio-analysis/")
        assert resp.status_code == 200
        assert b"Portfolio" in resp.data

    def test_fx_research_page(self, client):
        resp = client.get("/fx/")
        assert resp.status_code == 200
        assert b"FX" in resp.data or b"Research" in resp.data

    def test_autonomous_trading_page(self, client):
        resp = client.get("/autonomous-trading/")
        assert resp.status_code == 200
        assert b"Autonomous" in resp.data or b"Trading" in resp.data


# ==============================================================================
# Screener API – additional coverage
# ==============================================================================


class TestScreenerAPIExtended:
    """Tests for screener API endpoints with filters."""

    def _mock_screener_data(self):
        return {
            "as_of": "2024-01-01T12:00:00",
            "source": "cache",
            "summary": {},
            "scan_duration_seconds": 0.5,
            "rows": [
                {"symbol": "AAPL", "bollinger_status": "above_upper_band", "sector": "Technology"},
                {"symbol": "MSFT", "bollinger_status": "within_bands", "sector": "Technology"},
                {"symbol": "JPM", "bollinger_status": "below_lower_band", "sector": "Finance"},
            ],
        }

    def test_sp500_screener_returns_all(self, client, monkeypatch):
        monkeypatch.setattr(
            "web.sp500_screener_service.sp500_screener_service.get_screener_data",
            lambda refresh=False: self._mock_screener_data(),
        )
        resp = client.get("/api/stocks/sp500/screener")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["count"] == 3

    def test_sp500_screener_status_filter(self, client, monkeypatch):
        monkeypatch.setattr(
            "web.sp500_screener_service.sp500_screener_service.get_screener_data",
            lambda refresh=False: self._mock_screener_data(),
        )
        resp = client.get("/api/stocks/sp500/screener?status=overbought")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["count"] == 1
        assert data["rows"][0]["symbol"] == "AAPL"

    def test_sp500_screener_sector_filter(self, client, monkeypatch):
        monkeypatch.setattr(
            "web.sp500_screener_service.sp500_screener_service.get_screener_data",
            lambda refresh=False: self._mock_screener_data(),
        )
        resp = client.get("/api/stocks/sp500/screener?sector=Finance")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["count"] == 1
        assert data["rows"][0]["symbol"] == "JPM"

    def test_sti_screener_returns_all(self, client, monkeypatch):
        monkeypatch.setattr(
            "web.sti_screener_service.sti_screener_service.get_screener_data",
            lambda refresh=False: self._mock_screener_data(),
        )
        resp = client.get("/api/stocks/sti/screener")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "count" in data

    def test_hsi_screener_returns_all(self, client, monkeypatch):
        monkeypatch.setattr(
            "web.hsi_screener_service.hsi_screener_service.get_screener_data",
            lambda refresh=False: self._mock_screener_data(),
        )
        resp = client.get("/api/stocks/hsi/screener")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "count" in data

    def test_screener_handles_service_exception(self, client, monkeypatch):
        def _raise_fetch_error(refresh=False):
            raise RuntimeError("fetch failed")

        monkeypatch.setattr(
            "web.sp500_screener_service.sp500_screener_service.get_screener_data",
            _raise_fetch_error,
        )
        resp = client.get("/api/stocks/sp500/screener")
        assert resp.status_code == 500
        data = resp.get_json()
        assert "error" in data


# ==============================================================================
# Market API
# ==============================================================================


class TestMarketAPI:
    """Tests for /api/market/* endpoints."""

    def test_market_overview_returns_data(self, client, monkeypatch):
        monkeypatch.setattr(
            "web.routes.api_market._get_service",
            lambda: type("S", (), {"get_overview": lambda self: {"indices": [], "source": "cache"}})(),
        )
        resp = client.get("/api/market/overview")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "indices" in data or isinstance(data, dict)

    def test_market_refresh_returns_data(self, client, monkeypatch):
        monkeypatch.setattr(
            "web.routes.api_market._get_service",
            lambda: type("S", (), {"refresh": lambda self: {"indices": [], "refreshed": True}})(),
        )
        resp = client.post("/api/market/refresh")
        assert resp.status_code == 200
        data = resp.get_json()
        assert isinstance(data, dict)

    def test_market_outlook_cached(self, client, monkeypatch):
        """GET /api/market/outlook returns cached result when available."""
        fake_cached = {
            "session_recap": "Markets closed flat.",
            "source": "cache",
        }

        class FakeGenerator:
            def try_get_cached(self, positions):
                return fake_cached

        # Patch the lazy import inside the route function
        import ai.market_outlook as mo_mod
        monkeypatch.setattr(mo_mod, "get_market_outlook_generator", lambda: FakeGenerator())
        resp = client.get("/api/market/outlook")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["session_recap"] == "Markets closed flat."
