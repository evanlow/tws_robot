"""Tests for TWS Bridge module.

Tests the TWSBridge class that manages the connection between
the TWS/IB Gateway API and the ServiceManager.
"""

import pytest
import threading
import time
from unittest.mock import Mock, MagicMock, patch, call
from datetime import datetime

from core.tws_bridge import TWSBridge, _BridgeApp, _to_float
from core.event_bus import EventBus, Event, EventType
from ibapi.contract import Contract
from ibapi.order import Order
from ibapi.order_cancel import OrderCancel


# ==============================================================================
# Fixtures
# ==============================================================================


@pytest.fixture
def mock_service_manager():
    """Create a mock ServiceManager with required methods."""
    svc = Mock()
    svc.event_bus = Mock(spec=EventBus)
    svc.event_bus.publish = Mock()
    svc.update_account_summary = Mock()
    svc.update_position = Mock()
    svc.remove_position = Mock()
    svc._lock = threading.Lock()
    svc._account_summary = {}

    # Mock risk manager
    svc.risk_manager = Mock()
    svc.risk_manager.current_equity = 100000.0
    svc.risk_manager.peak_equity = 100000.0
    svc.risk_manager.daily_start_equity = 100000.0
    svc.risk_manager.initial_capital = 100000.0
    
    return svc


@pytest.fixture
def bridge_config():
    """Standard bridge configuration."""
    return {
        "host": "127.0.0.1",
        "port": 7497,
        "client_id": 1,
        "account": "DU12345",
    }


@pytest.fixture
def bridge(mock_service_manager, bridge_config):
    """Create a TWSBridge instance."""
    return TWSBridge(mock_service_manager, bridge_config)


# ==============================================================================
# Helper function tests
# ==============================================================================


class TestToFloat:
    """Tests for _to_float helper function."""
    
    @pytest.mark.unit
    def test_string_number(self):
        assert _to_float("123.45") == 123.45
    
    @pytest.mark.unit
    def test_integer(self):
        assert _to_float(100) == 100.0
    
    @pytest.mark.unit
    def test_float(self):
        assert _to_float(99.99) == 99.99
    
    @pytest.mark.unit
    def test_invalid_string(self):
        assert _to_float("not_a_number") == 0.0
    
    @pytest.mark.unit
    def test_none(self):
        assert _to_float(None) == 0.0
    
    @pytest.mark.unit
    def test_empty_string(self):
        assert _to_float("") == 0.0
    
    @pytest.mark.unit
    def test_negative_number(self):
        assert _to_float("-50.25") == -50.25


# ==============================================================================
# _BridgeApp tests
# ==============================================================================


class TestBridgeApp:
    """Tests for _BridgeApp internal class."""
    
    @pytest.mark.unit
    def test_initialization(self, mock_service_manager):
        """Test _BridgeApp initialization."""
        app = _BridgeApp(mock_service_manager, "DU12345")
        
        assert app._svc == mock_service_manager
        assert app._account == "DU12345"
        assert app._connected is False
        assert app._ready is False
    
    @pytest.mark.unit
    def test_connect_ack(self, mock_service_manager):
        """Test connectAck sets connection flag."""
        app = _BridgeApp(mock_service_manager, "DU12345")
        
        app.connectAck()
        
        assert app._connected is True
    
    @pytest.mark.unit
    def test_next_valid_id(self, mock_service_manager):
        """Test nextValidId sets ready flag."""
        app = _BridgeApp(mock_service_manager, "DU12345")
        
        app.nextValidId(100)
        
        assert app._ready is True

    @pytest.mark.unit
    def test_next_valid_id_stores_order_id(self, mock_service_manager):
        """nextValidId must cache the broker-issued order ID."""
        app = _BridgeApp(mock_service_manager, "DU12345")

        app.nextValidId(4242)

        assert app._next_valid_order_id == 4242

    @pytest.mark.unit
    def test_next_valid_id_only_advances(self, mock_service_manager):
        """Subsequent nextValidId callbacks must not roll the cursor back."""
        app = _BridgeApp(mock_service_manager, "DU12345")

        app.nextValidId(4242)
        # A stale/lower callback (e.g. from a delayed ``reqIds``) must
        # not regress the cursor — we'd otherwise hand out IDs the
        # broker has already issued.
        app.nextValidId(100)

        assert app._next_valid_order_id == 4242

        app.nextValidId(5000)
        assert app._next_valid_order_id == 5000
    
    @pytest.mark.unit
    def test_connection_closed(self, mock_service_manager):
        """Test connectionClosed resets flags and publishes event."""
        app = _BridgeApp(mock_service_manager, "DU12345")
        app._connected = True
        app._ready = True
        
        app.connectionClosed()
        
        assert app._connected is False
        assert app._ready is False
        mock_service_manager.event_bus.publish.assert_called_once()
        
        # Verify event structure
        call_args = mock_service_manager.event_bus.publish.call_args[0][0]
        assert call_args.event_type == EventType.CONNECTION_LOST
        assert call_args.source == "TWSBridge"
    
    @pytest.mark.unit
    def test_update_account_value_cash_balance(self, mock_service_manager):
        """Test updateAccountValue for cash balance."""
        app = _BridgeApp(mock_service_manager, "DU12345")
        
        app.updateAccountValue("TotalCashBalance", "50000.00", "BASE", "DU12345")
        
        mock_service_manager.update_account_summary.assert_called_with(
            {"cash_balance": 50000.0}
        )
        mock_service_manager.event_bus.publish.assert_called_once()
    
    @pytest.mark.unit
    def test_update_account_value_equity(self, mock_service_manager):
        """Test updateAccountValue for equity updates risk manager."""
        app = _BridgeApp(mock_service_manager, "DU12345")
        
        app.updateAccountValue("NetLiquidationByCurrency", "105000.00", "BASE", "DU12345")
        
        # Verify account summary updated
        mock_service_manager.update_account_summary.assert_called_with(
            {"equity": 105000.0}
        )
        
        # Verify risk manager updated
        assert mock_service_manager.risk_manager.current_equity == 105000.0
        assert mock_service_manager.risk_manager.peak_equity == 105000.0
        
        # Verify event published
        mock_service_manager.event_bus.publish.assert_called_once()
    
    @pytest.mark.unit
    def test_update_account_value_buying_power(self, mock_service_manager):
        """Test updateAccountValue for buying power."""
        app = _BridgeApp(mock_service_manager, "DU12345")
        
        app.updateAccountValue("BuyingPower", "200000.00", "BASE", "DU12345")
        
        mock_service_manager.update_account_summary.assert_called_with(
            {"buying_power": 200000.0}
        )
    
    @pytest.mark.unit
    def test_update_account_value_ignores_non_base_currency(self, mock_service_manager):
        """Test that non-BASE currency cash balances are stored per-currency but
        do not trigger an update_account_summary call."""
        app = _BridgeApp(mock_service_manager, "DU12345")

        app.updateAccountValue("TotalCashBalance", "50000.00", "USD", "DU12345")

        # update_account_summary must NOT be called for per-currency events
        mock_service_manager.update_account_summary.assert_not_called()
        # But the balance should have been stored in cash_by_currency
        assert mock_service_manager._account_summary.get("cash_by_currency", {}).get("USD") == 50000.0
    
    @pytest.mark.unit
    def test_update_portfolio_long_position(self, mock_service_manager):
        """Test updatePortfolio with a long position."""
        app = _BridgeApp(mock_service_manager, "DU12345")
        
        contract = Contract()
        contract.symbol = "AAPL"
        contract.localSymbol = "AAPL"
        contract.secType = "STK"
        
        app.updatePortfolio(
            contract=contract,
            position=100,
            marketPrice=150.0,
            marketValue=15000.0,
            averageCost=145.0,
            unrealizedPNL=500.0,
            realizedPNL=0.0,
            accountName="DU12345"
        )
        
        # Verify position updated
        mock_service_manager.update_position.assert_called_once()
        call_args = mock_service_manager.update_position.call_args[0]
        
        assert call_args[0] == "AAPL"
        assert call_args[1]["quantity"] == 100.0
        assert call_args[1]["entry_price"] == 145.0
        assert call_args[1]["current_price"] == 150.0
        assert call_args[1]["market_value"] == 15000.0
        assert call_args[1]["unrealized_pnl"] == 500.0
        assert call_args[1]["side"] == "LONG"
        assert call_args[1]["sec_type"] == "STK"
        
        # Verify PnL percentage calculated correctly
        expected_pnl_pct = (150.0 - 145.0) / 145.0
        assert abs(call_args[1]["unrealized_pnl_pct"] - expected_pnl_pct) < 0.0001
    
    @pytest.mark.unit
    def test_update_portfolio_short_position(self, mock_service_manager):
        """Test updatePortfolio with a short position."""
        app = _BridgeApp(mock_service_manager, "DU12345")
        
        contract = Contract()
        contract.symbol = "TSLA"
        contract.secType = "STK"
        
        app.updatePortfolio(
            contract=contract,
            position=-50,
            marketPrice=200.0,
            marketValue=-10000.0,
            averageCost=210.0,
            unrealizedPNL=500.0,
            realizedPNL=0.0,
            accountName="DU12345"
        )
        
        call_args = mock_service_manager.update_position.call_args[0]
        assert call_args[1]["quantity"] == -50.0
        assert call_args[1]["side"] == "SHORT"
        assert call_args[1]["sec_type"] == "STK"
    
    @pytest.mark.unit
    def test_update_portfolio_short_option_stores_sec_type(self, mock_service_manager):
        """Test updatePortfolio stores sec_type for option contracts."""
        app = _BridgeApp(mock_service_manager, "DU12345")
        
        contract = Contract()
        contract.symbol = "GOOG"
        contract.localSymbol = "GOOG 260515P00240000"
        contract.secType = "OPT"
        
        app.updatePortfolio(
            contract=contract,
            position=-1,
            marketPrice=0.28,
            marketValue=-28.0,
            averageCost=273.95,
            unrealizedPNL=245.54,
            realizedPNL=0.0,
            accountName="DU12345"
        )
        
        call_args = mock_service_manager.update_position.call_args[0]
        assert call_args[0] == "GOOG 260515P00240000"
        assert call_args[1]["quantity"] == -1.0
        assert call_args[1]["side"] == "SHORT"
        assert call_args[1]["sec_type"] == "OPT"
        assert call_args[1]["unrealized_pnl"] == 245.54
    
    @pytest.mark.unit
    def test_update_portfolio_zero_position_removes(self, mock_service_manager):
        """Test that zero position removes the position."""
        app = _BridgeApp(mock_service_manager, "DU12345")
        
        contract = Contract()
        contract.symbol = "MSFT"
        
        app.updatePortfolio(
            contract=contract,
            position=0,
            marketPrice=300.0,
            marketValue=0.0,
            averageCost=295.0,
            unrealizedPNL=0.0,
            realizedPNL=100.0,
            accountName="DU12345"
        )
        
        mock_service_manager.remove_position.assert_called_once_with("MSFT")
        mock_service_manager.update_position.assert_not_called()
    
    @pytest.mark.unit
    def test_update_portfolio_zero_average_cost(self, mock_service_manager):
        """Test updatePortfolio handles zero average cost gracefully."""
        app = _BridgeApp(mock_service_manager, "DU12345")
        
        contract = Contract()
        contract.symbol = "GOOGL"
        
        app.updatePortfolio(
            contract=contract,
            position=10,
            marketPrice=2800.0,
            marketValue=28000.0,
            averageCost=0.0,
            unrealizedPNL=0.0,
            realizedPNL=0.0,
            accountName="DU12345"
        )
        
        call_args = mock_service_manager.update_position.call_args[0]
        assert call_args[1]["unrealized_pnl_pct"] == 0.0
    
    @pytest.mark.unit
    def test_account_download_end(self, mock_service_manager):
        """Test accountDownloadEnd doesn't crash (just logs)."""
        app = _BridgeApp(mock_service_manager, "DU12345")
        
        # Should not raise exception
        app.accountDownloadEnd("DU12345")
    
    @pytest.mark.unit
    def test_tick_price(self, mock_service_manager):
        """Test tickPrice method (placeholder implementation)."""
        app = _BridgeApp(mock_service_manager, "DU12345")
        
        # Should not raise exception
        app.tickPrice(1, 1, 150.0, None)
    
    @pytest.mark.unit
    def test_error_informational_codes(self, mock_service_manager):
        """Test that informational error codes are handled gracefully."""
        app = _BridgeApp(mock_service_manager, "DU12345")
        
        # Should not change connection state
        for code in [2104, 2106, 2158]:
            app.error(0, 0, code, "Informational message")
            assert app._connected is False  # Stays at initial value
    
    @pytest.mark.unit
    def test_error_critical_codes(self, mock_service_manager):
        """Test that critical error codes set connection flag to False."""
        app = _BridgeApp(mock_service_manager, "DU12345")
        app._connected = True
        
        app.error(0, 0, 502, "Connection failed")
        
        assert app._connected is False
    
    @pytest.mark.unit
    def test_error_other_codes(self, mock_service_manager):
        """Test that other error codes are logged as warnings."""
        app = _BridgeApp(mock_service_manager, "DU12345")
        
        # Should not raise exception
        app.error(1, 0, 999, "Some other error")


# ==============================================================================
# TWSBridge tests
# ==============================================================================


class TestTWSBridge:
    """Tests for TWSBridge public API."""
    
    @pytest.mark.unit
    def test_initialization(self, mock_service_manager, bridge_config):
        """Test TWSBridge initialization."""
        bridge = TWSBridge(mock_service_manager, bridge_config)
        
        assert bridge._svc == mock_service_manager
        assert bridge._config == bridge_config
        assert bridge._app is None
        assert bridge._thread is None
    
    @pytest.mark.unit
    def test_is_connected_when_not_connected(self, bridge):
        """Test is_connected property when disconnected."""
        assert bridge.is_connected is False
    
    @pytest.mark.unit
    @patch('core.tws_bridge._BridgeApp')
    def test_connect_success(self, mock_app_class, bridge, mock_service_manager):
        """Test successful connection."""
        # Setup mock app
        mock_app_instance = Mock()
        mock_app_instance._connected = False
        mock_app_instance._ready = False
        mock_app_instance.connect = Mock()
        mock_app_instance.run = Mock()
        mock_app_instance.reqMarketDataType = Mock()
        mock_app_instance.reqAccountUpdates = Mock()
        mock_app_class.return_value = mock_app_instance
        
        # Simulate connection happening quickly
        def simulate_connect(*args):
            mock_app_instance._connected = True
            mock_app_instance._ready = True
        
        mock_app_instance.connect.side_effect = simulate_connect
        
        result = bridge.connect(timeout=5)
        
        assert result is True
        mock_app_instance.connect.assert_called_once_with("127.0.0.1", 7497, 1)
        mock_app_instance.reqAccountUpdates.assert_called_once_with(True, "DU12345")
    
    @pytest.mark.unit
    @patch('core.tws_bridge._BridgeApp')
    @patch('core.tws_bridge.threading.Thread')
    def test_connect_timeout(self, mock_thread_class, mock_app_class, bridge):
        """Test connection timeout."""
        # Setup mock app that never becomes ready
        mock_app_instance = Mock()
        mock_app_instance._connected = False
        mock_app_instance._ready = False
        mock_app_instance.connect = Mock()
        mock_app_instance.run = Mock()
        mock_app_instance.disconnect = Mock()
        mock_app_instance.isConnected = Mock(return_value=False)
        mock_app_class.return_value = mock_app_instance
        
        # Mock thread
        mock_thread = Mock()
        mock_thread_class.return_value = mock_thread
        
        result = bridge.connect(timeout=1)
        
        assert result is False
        assert bridge._app is None
    
    @pytest.mark.unit
    @patch('core.tws_bridge._BridgeApp')
    @patch('core.tws_bridge.threading.Thread')
    def test_disconnect(self, mock_thread_class, mock_app_class, bridge):
        """Test disconnect method."""
        # Setup mock app
        mock_app_instance = Mock()
        mock_app_instance._connected = True
        mock_app_instance._ready = True
        mock_app_instance.isConnected = Mock(return_value=True)
        mock_app_instance.reqAccountUpdates = Mock()
        mock_app_instance.disconnect = Mock()
        
        bridge._app = mock_app_instance
        bridge._thread = Mock()
        
        bridge.disconnect()
        
        mock_app_instance.reqAccountUpdates.assert_called_once_with(False, "DU12345")
        mock_app_instance.disconnect.assert_called_once()
        assert bridge._app is None
        assert bridge._thread is None
    
    @pytest.mark.unit
    def test_disconnect_when_not_connected(self, bridge):
        """Test disconnect when no connection exists."""
        # Should not raise exception
        bridge.disconnect()
        assert bridge._app is None
    
    @pytest.mark.unit
    def test_disconnect_with_exception(self, bridge):
        """Test disconnect handles exceptions gracefully."""
        mock_app = Mock()
        mock_app.isConnected = Mock(return_value=True)
        mock_app.reqAccountUpdates = Mock(side_effect=Exception("Network error"))
        
        bridge._app = mock_app
        bridge._config = {"account": "DU12345"}
        
        # Should not raise exception
        bridge.disconnect()
        assert bridge._app is None
    
    @pytest.mark.unit
    @patch('core.tws_bridge._BridgeApp')
    def test_is_connected_when_connected(self, mock_app_class, bridge):
        """Test is_connected property when connected."""
        mock_app_instance = Mock()
        mock_app_instance._connected = True
        mock_app_instance._ready = True
        
        bridge._app = mock_app_instance
        
        assert bridge.is_connected is True
    
    @pytest.mark.unit
    @patch('core.tws_bridge._BridgeApp')
    def test_is_connected_partial_state(self, mock_app_class, bridge):
        """Test is_connected requires both connected and ready."""
        mock_app_instance = Mock()
        
        # Connected but not ready
        mock_app_instance._connected = True
        mock_app_instance._ready = False
        bridge._app = mock_app_instance
        assert bridge.is_connected is False
        
        # Ready but not connected
        mock_app_instance._connected = False
        mock_app_instance._ready = True
        assert bridge.is_connected is False

    @pytest.mark.unit
    def test_cancel_order_when_connected(self, bridge):
        """Test cancel_order forwards the cancel request to TWS."""
        mock_app = Mock()
        mock_app._connected = True
        mock_app._ready = True
        mock_app.cancelOrder = Mock()
        bridge._app = mock_app

        bridge.cancel_order(42)

        mock_app.cancelOrder.assert_called_once()
        call_args = mock_app.cancelOrder.call_args[0]
        assert call_args[0] == 42
        assert isinstance(call_args[1], OrderCancel)

    @pytest.mark.unit
    def test_cancel_order_requires_ready_connection(self, bridge):
        """Test cancel_order rejects partially connected bridge state."""
        mock_app = Mock()
        mock_app._connected = True
        mock_app._ready = False
        mock_app.cancelOrder = Mock()
        bridge._app = mock_app

        with pytest.raises(RuntimeError, match="not connected to TWS"):
            bridge.cancel_order(42)

        mock_app.cancelOrder.assert_not_called()

    @pytest.mark.unit
    def test_reserve_order_id_uses_broker_cursor(self, bridge):
        """reserve_order_id returns the broker-issued ID and advances."""
        # Use a real _BridgeApp so the lock and cursor behave like prod.
        app = _BridgeApp(bridge._svc, "DU12345")
        app._connected = True
        app.nextValidId(4242)
        bridge._app = app

        first = bridge.reserve_order_id()
        second = bridge.reserve_order_id()

        assert first == 4242
        assert second == 4243
        # The cached cursor is advanced even when nextValidId isn't
        # re-broadcast — otherwise back-to-back orders would collide.
        assert app._next_valid_order_id == 4244

    @pytest.mark.unit
    def test_reserve_order_id_without_handshake_raises(self, bridge):
        """reserve_order_id rejects calls before nextValidId arrives."""
        app = _BridgeApp(bridge._svc, "DU12345")
        app._connected = True
        # No nextValidId yet → no broker-issued cursor.
        bridge._app = app

        with pytest.raises(RuntimeError, match="nextValidId"):
            bridge.reserve_order_id()

    @pytest.mark.unit
    def test_reserve_order_id_requires_connection(self, bridge):
        """reserve_order_id refuses to mint IDs when disconnected."""
        bridge._app = None

        with pytest.raises(RuntimeError, match="not connected to TWS"):
            bridge.reserve_order_id()


# ==============================================================================
# Integration-style tests
# ==============================================================================


class TestTWSBridgeIntegration:
    """Integration tests verifying bridge behavior with real EventBus."""
    
    @pytest.mark.integration
    def test_bridge_publishes_events(self):
        """Test that _BridgeApp publishes events to real EventBus."""
        # Create real EventBus
        event_bus = EventBus()
        received_events = []
        
        def capture_event(event):
            received_events.append(event)
        
        event_bus.subscribe(EventType.ACCOUNT_UPDATE, capture_event)
        
        # Create mock service manager with real event bus
        svc = Mock()
        svc.event_bus = event_bus
        svc.update_account_summary = Mock()
        svc._lock = threading.Lock()
        svc.risk_manager = Mock()
        svc.risk_manager.current_equity = 100000.0
        svc.risk_manager.peak_equity = 100000.0
        svc.risk_manager.daily_start_equity = 100000.0
        svc.risk_manager.initial_capital = 100000.0
        
        app = _BridgeApp(svc, "DU12345")
        
        # Trigger account update
        app.updateAccountValue("TotalCashBalance", "50000.00", "BASE", "DU12345")
        
        # Verify event published
        assert len(received_events) == 1
        assert received_events[0].event_type == EventType.ACCOUNT_UPDATE
        assert received_events[0].data["key"] == "TotalCashBalance"
        assert received_events[0].source == "TWSBridge"
    
    @pytest.mark.integration
    def test_position_update_publishes_event(self):
        """Test that portfolio updates publish events."""
        event_bus = EventBus()
        received_events = []
        
        def capture_event(event):
            received_events.append(event)
        
        event_bus.subscribe(EventType.PORTFOLIO_UPDATE, capture_event)
        
        svc = Mock()
        svc.event_bus = event_bus
        svc.update_position = Mock()
        
        app = _BridgeApp(svc, "DU12345")
        
        contract = Contract()
        contract.symbol = "AAPL"
        
        app.updatePortfolio(
            contract=contract,
            position=100,
            marketPrice=150.0,
            marketValue=15000.0,
            averageCost=145.0,
            unrealizedPNL=500.0,
            realizedPNL=0.0,
            accountName="DU12345"
        )
        
        assert len(received_events) == 1
        assert received_events[0].event_type == EventType.PORTFOLIO_UPDATE
        assert received_events[0].data["symbol"] == "AAPL"
        assert received_events[0].data["position"] == 100.0



# ==============================================================================
# OrderExecutor adapter surface
# ==============================================================================


class TestTWSBridgeAdapterSurface:
    """Tests for the OrderExecutor-compatible adapter methods on TWSBridge.

    These verify the surface exposed for actual-live trading where the
    persistent bridge is reused as the OrderExecutor adapter (instead of
    opening a second EClient socket that TWS would reject)."""

    @pytest.mark.unit
    def test_environment_live_for_live_port(self, mock_service_manager):
        bridge = TWSBridge(mock_service_manager, {"port": 7496})
        assert bridge.environment == "live"

    @pytest.mark.unit
    def test_environment_live_for_gateway_live_port(self, mock_service_manager):
        bridge = TWSBridge(mock_service_manager, {"port": 4001})
        assert bridge.environment == "live"

    @pytest.mark.unit
    def test_environment_paper_for_paper_port(self, mock_service_manager):
        bridge = TWSBridge(mock_service_manager, {"port": 7497})
        assert bridge.environment == "paper"

    @pytest.mark.unit
    def test_environment_paper_for_unknown_port_failclosed(self, mock_service_manager):
        """Unknown ports default to 'paper' so the live confirmation check
        will reject the order with a clear port-mismatch message rather
        than risk sending a real-money order to an unrecognised port."""
        bridge = TWSBridge(mock_service_manager, {"port": 9999})
        assert bridge.environment == "paper"

    @pytest.mark.unit
    def test_port_returns_configured_port_stable_across_reconnect(self, bridge):
        """Unlike EClient.port (which is nulled by EClient.reset on every
        socket close), TWSBridge.port reads from the immutable config."""
        assert bridge.port == 7497

    @pytest.mark.unit
    def test_ready_mirrors_is_connected(self, bridge):
        bridge._app = None
        assert bridge.ready is False

        app = _BridgeApp(bridge._svc, "DU12345")
        app._connected = True
        app._ready = True
        bridge._app = app
        assert bridge.ready is True

    @pytest.mark.unit
    def test_buy_reserves_id_and_calls_place_order(self, bridge):
        app = _BridgeApp(bridge._svc, "DU12345")
        app._connected = True
        app._ready = True
        app._next_valid_order_id = 1000
        app.placeOrder = Mock()
        bridge._app = app

        order_id = bridge.buy("AAPL", 10)

        assert order_id == 1000
        app.placeOrder.assert_called_once()
        called_id, contract, order = app.placeOrder.call_args[0]
        assert called_id == 1000
        assert contract.symbol == "AAPL"
        assert contract.secType == "STK"
        assert order.action == "BUY"
        assert order.totalQuantity == 10
        assert order.orderType == "MARKET"

    @pytest.mark.unit
    def test_sell_reserves_id_and_calls_place_order(self, bridge):
        app = _BridgeApp(bridge._svc, "DU12345")
        app._connected = True
        app._ready = True
        app._next_valid_order_id = 2000
        app.placeOrder = Mock()
        bridge._app = app

        order_id = bridge.sell("AAPL", 5, order_type="LIMIT", limit_price=150.0)

        assert order_id == 2000
        called_id, _contract, order = app.placeOrder.call_args[0]
        assert order.action == "SELL"
        assert order.totalQuantity == 5
        assert order.orderType == "LIMIT"
        assert order.lmtPrice == 150.0

    @pytest.mark.unit
    def test_place_order_when_disconnected_raises(self, bridge):
        bridge._app = None
        with pytest.raises(RuntimeError, match="not connected"):
            bridge.buy("AAPL", 10)

    @pytest.mark.unit
    def test_close_position_long_submits_sell(self, bridge):
        app = _BridgeApp(bridge._svc, "DU12345")
        app._connected = True
        app._ready = True
        app._next_valid_order_id = 3000
        app.placeOrder = Mock()
        bridge._app = app

        bridge._svc.get_positions = Mock(return_value={
            "AAPL": {"quantity": 10, "sec_type": "STK", "entry_price": 100.0,
                     "current_price": 150.0, "realized_pnl": 0.0}
        })

        order_id = bridge.close_position("AAPL")

        assert order_id == 3000
        _called_id, _contract, order = app.placeOrder.call_args[0]
        assert order.action == "SELL"
        assert order.totalQuantity == 10

    @pytest.mark.unit
    def test_close_position_short_submits_buy(self, bridge):
        app = _BridgeApp(bridge._svc, "DU12345")
        app._connected = True
        app._ready = True
        app._next_valid_order_id = 4000
        app.placeOrder = Mock()
        bridge._app = app

        bridge._svc.get_positions = Mock(return_value={
            "AAPL": {"quantity": -5, "sec_type": "STK", "entry_price": 100.0,
                     "current_price": 80.0, "realized_pnl": 0.0}
        })

        order_id = bridge.close_position("AAPL")

        assert order_id == 4000
        _called_id, _contract, order = app.placeOrder.call_args[0]
        assert order.action == "BUY"
        assert order.totalQuantity == 5

    @pytest.mark.unit
    def test_close_position_no_position_returns_none(self, bridge):
        app = _BridgeApp(bridge._svc, "DU12345")
        app._connected = True
        app._ready = True
        app._next_valid_order_id = 5000
        app.placeOrder = Mock()
        bridge._app = app

        bridge._svc.get_positions = Mock(return_value={})

        assert bridge.close_position("AAPL") is None
        app.placeOrder.assert_not_called()

    @pytest.mark.unit
    def test_close_position_rejects_limit_order_type(self, bridge):
        with pytest.raises(ValueError, match="LIMIT"):
            bridge.close_position("AAPL", order_type="LIMIT")

    @pytest.mark.unit
    def test_get_all_positions_filters_non_stock(self, bridge):
        bridge._svc.get_positions = Mock(return_value={
            "AAPL": {"quantity": 10, "sec_type": "STK", "entry_price": 100.0,
                     "current_price": 150.0, "realized_pnl": 5.0},
            "SPY  240315C00500000": {
                "quantity": -1, "sec_type": "OPT", "entry_price": 2.5,
                "current_price": 1.0, "realized_pnl": 0.0,
            },
        })

        positions = bridge.get_all_positions()

        assert set(positions.keys()) == {"AAPL"}
        aapl = positions["AAPL"]
        assert aapl.symbol == "AAPL"
        assert aapl.quantity == 10
        assert aapl.average_cost == 100.0
        assert aapl.current_price == 150.0
        assert aapl.realized_pnl == 5.0

    @pytest.mark.unit
    def test_get_all_positions_skips_zero_quantity(self, bridge):
        bridge._svc.get_positions = Mock(return_value={
            "AAPL": {"quantity": 0, "sec_type": "STK", "entry_price": 100.0},
        })
        assert bridge.get_all_positions() == {}

    @pytest.mark.unit
    def test_get_all_positions_defaults_missing_sec_type_to_stk(self, bridge):
        """Older callbacks may omit sec_type; treat as STK to be safe."""
        bridge._svc.get_positions = Mock(return_value={
            "AAPL": {"quantity": 10, "entry_price": 100.0},
        })
        positions = bridge.get_all_positions()
        assert "AAPL" in positions

    @pytest.mark.unit
    def test_get_all_positions_swallows_service_errors(self, bridge):
        bridge._svc.get_positions = Mock(side_effect=RuntimeError("boom"))
        assert bridge.get_all_positions() == {}


# ==============================================================================
# Order rejection error codes
# ==============================================================================


class TestBridgeAppErrorHandler:
    """Tests for _BridgeApp.error() classification of TWS error codes."""

    @pytest.mark.unit
    def test_read_only_api_rejection_logs_error_with_hint(
        self, mock_service_manager, caplog
    ):
        app = _BridgeApp(mock_service_manager, "DU12345")
        with caplog.at_level("ERROR", logger="core.tws_bridge"):
            app.error(
                1,
                0,
                321,
                "Error validating request.-'v' : cause - The API interface "
                "is currently in Read-Only mode.",
            )
        joined = " ".join(r.getMessage() for r in caplog.records)
        assert "ORDER REJECTED" in joined
        assert "code 321" in joined
        assert "Read-Only" in joined  # actionable hint

    @pytest.mark.unit
    def test_other_order_reject_codes_logged_as_error(
        self, mock_service_manager, caplog
    ):
        app = _BridgeApp(mock_service_manager, "DU12345")
        with caplog.at_level("ERROR", logger="core.tws_bridge"):
            app.error(42, 0, 201, "Order rejected - reason: insufficient buying power")
        rejections = [r for r in caplog.records if "ORDER REJECTED" in r.getMessage()]
        assert len(rejections) == 1
        assert "code 201" in rejections[0].getMessage()
        assert "orderId 42" in rejections[0].getMessage()

    @pytest.mark.unit
    def test_connection_error_marks_disconnected(self, mock_service_manager):
        app = _BridgeApp(mock_service_manager, "DU12345")
        app._connected = True
        app.error(-1, 0, 1100, "Connectivity lost")
        assert app._connected is False

    @pytest.mark.unit
    def test_info_codes_dont_pollute_warnings(self, mock_service_manager, caplog):
        app = _BridgeApp(mock_service_manager, "DU12345")
        with caplog.at_level("WARNING", logger="core.tws_bridge"):
            app.error(-1, 0, 2104, "Market data farm connection is OK")
            app.error(-1, 0, 2106, "HMDS data farm connection is OK")
        bridge_records = [r for r in caplog.records if r.name == "core.tws_bridge"]
        assert bridge_records == []


# ==============================================================================
# pop_rejected_order_ids
# ==============================================================================


class TestBridgeRejectedOrderTracking:
    """Tests for TWSBridge.pop_rejected_order_ids and the underlying set."""

    @pytest.mark.unit
    def test_order_reject_adds_to_set(self, bridge):
        app = _BridgeApp(bridge._svc, "DU12345")
        bridge._app = app
        app.error(7, 0, 321, "Read-Only API")
        app.error(8, 0, 201, "rejected")
        drained = bridge.pop_rejected_order_ids()
        assert drained == {7, 8}

    @pytest.mark.unit
    def test_drain_clears_the_set(self, bridge):
        app = _BridgeApp(bridge._svc, "DU12345")
        bridge._app = app
        app.error(7, 0, 321, "Read-Only API")
        bridge.pop_rejected_order_ids()
        # Second drain is empty.
        assert bridge.pop_rejected_order_ids() == set()

    @pytest.mark.unit
    def test_non_order_errors_dont_pollute_set(self, bridge):
        app = _BridgeApp(bridge._svc, "DU12345")
        bridge._app = app
        app.error(-1, 0, 2104, "Market data farm OK")  # info
        app.error(99, 0, 1100, "Connectivity lost")    # connection
        app.error(50, 0, 9999, "unknown")              # generic warning
        assert bridge.pop_rejected_order_ids() == set()

    @pytest.mark.unit
    def test_invalid_req_id_ignored(self, bridge):
        app = _BridgeApp(bridge._svc, "DU12345")
        bridge._app = app
        app.error(-1, 0, 321, "Read-Only API")  # reqId -1 → ignore
        app.error(0, 0, 321, "Read-Only API")   # reqId 0  → ignore
        assert bridge.pop_rejected_order_ids() == set()

    @pytest.mark.unit
    def test_pop_when_no_app_returns_empty(self, bridge):
        bridge._app = None
        assert bridge.pop_rejected_order_ids() == set()


# ==============================================================================
# pop_filled_order_ids / orderStatus fill tracking
# ==============================================================================


class TestBridgeFilledOrderTracking:
    """Tests for TWSBridge.pop_filled_order_ids and the orderStatus override."""

    @pytest.mark.unit
    def test_filled_status_records_order_id(self, bridge, mock_service_manager):
        app = _BridgeApp(mock_service_manager, "DU12345")
        bridge._app = app
        app.orderStatus(
            orderId=101, status="Filled", filled=1.0, remaining=0.0,
            avgFillPrice=100.5, permId=0, parentId=0, lastFillPrice=100.5,
            clientId=1, whyHeld="", mktCapPrice=0.0,
        )
        assert bridge.pop_filled_order_ids() == {101}

    @pytest.mark.unit
    def test_order_status_forwards_snapshot_to_service_manager(
        self, bridge, mock_service_manager
    ):
        app = _BridgeApp(mock_service_manager, "DU12345")
        bridge._app = app

        app.orderStatus(
            orderId=101, status="Filled", filled=1.0, remaining=0.0,
            avgFillPrice=100.5, permId=10, parentId=0, lastFillPrice=100.5,
            clientId=1, whyHeld="", mktCapPrice=0.0,
        )

        mock_service_manager.add_order.assert_called_once()
        payload = mock_service_manager.add_order.call_args.args[0]
        assert payload["broker_order_id"] == 101
        assert payload["status"] == "FILLED"
        assert payload["filled"] == 1.0
        assert payload["remaining"] == 0.0
        assert payload["avg_fill_price"] == 100.5
        mock_service_manager.event_bus.publish.assert_called()

    @pytest.mark.unit
    def test_partial_fill_does_not_record(self, bridge, mock_service_manager):
        app = _BridgeApp(mock_service_manager, "DU12345")
        bridge._app = app
        app.orderStatus(
            orderId=101, status="Filled", filled=1.0, remaining=5.0,
            avgFillPrice=100.5, permId=0, parentId=0, lastFillPrice=100.5,
            clientId=1, whyHeld="", mktCapPrice=0.0,
        )
        assert bridge.pop_filled_order_ids() == set()

    @pytest.mark.unit
    def test_non_filled_status_ignored(self, bridge, mock_service_manager):
        app = _BridgeApp(mock_service_manager, "DU12345")
        bridge._app = app
        for status in ("Submitted", "PreSubmitted", "PendingSubmit", "Cancelled"):
            app.orderStatus(
                orderId=200, status=status, filled=0.0, remaining=1.0,
                avgFillPrice=0.0, permId=0, parentId=0, lastFillPrice=0.0,
                clientId=1, whyHeld="", mktCapPrice=0.0,
            )
        assert bridge.pop_filled_order_ids() == set()

    @pytest.mark.unit
    def test_drain_clears_set(self, bridge, mock_service_manager):
        app = _BridgeApp(mock_service_manager, "DU12345")
        bridge._app = app
        app.orderStatus(
            orderId=101, status="Filled", filled=1.0, remaining=0.0,
            avgFillPrice=100.5, permId=0, parentId=0, lastFillPrice=100.5,
            clientId=1, whyHeld="", mktCapPrice=0.0,
        )
        bridge.pop_filled_order_ids()
        assert bridge.pop_filled_order_ids() == set()

    @pytest.mark.unit
    def test_pop_when_no_app_returns_empty(self, bridge):
        bridge._app = None
        assert bridge.pop_filled_order_ids() == set()


# ==============================================================================
# Open-order snapshots for autonomous protection verification
# ==============================================================================


class TestBridgeOpenOrderSnapshots:
    """Tests for broker-visible open-order snapshots."""

    @pytest.mark.unit
    def test_open_order_snapshot_records_and_terminal_status_removes(
        self, bridge, mock_service_manager
    ):
        app = _BridgeApp(mock_service_manager, "DU12345")
        bridge._app = app
        contract = Contract()
        contract.symbol = "AAA"
        contract.secType = "STK"
        contract.exchange = "SMART"
        contract.currency = "USD"
        order = Order()
        order.action = "SELL"
        order.orderType = "STP"
        order.totalQuantity = 2
        order.parentId = 700
        order.auxPrice = 95.0

        app.openOrder(702, contract, order, Mock(status="Submitted"))

        snapshots = bridge.get_open_order_snapshots()
        assert len(snapshots) == 1
        assert snapshots[0]["order_id"] == 702
        assert snapshots[0]["symbol"] == "AAA"
        assert snapshots[0]["action"] == "SELL"
        assert snapshots[0]["order_type"] == "STP"
        assert snapshots[0]["quantity"] == 2.0
        assert snapshots[0]["parent_id"] == 700
        mock_service_manager.add_order.assert_called()

        app.orderStatus(
            orderId=702, status="Cancelled", filled=0.0, remaining=0.0,
            avgFillPrice=0.0, permId=0, parentId=700, lastFillPrice=0.0,
            clientId=1, whyHeld="", mktCapPrice=0.0,
        )
        assert bridge.get_open_order_snapshots() == []


# ==============================================================================
# place_bracket_buy
# ==============================================================================


class TestBridgePlaceBracketBuy:
    """Tests for TWSBridge.place_bracket_buy (parent BUY LMT + target + stop)."""

    @pytest.mark.unit
    def test_submits_three_orders_with_correct_legs(self, bridge, mock_service_manager):
        app = _BridgeApp(mock_service_manager, "DU12345")
        # Mark connected + ready so place_bracket_buy passes the guards.
        app._connected = True
        app._ready = True
        app._next_valid_order_id = 1000
        bridge._app = app
        placed = []
        app.placeOrder = lambda oid, contract, order: placed.append((oid, contract, order))

        ids = bridge.place_bracket_buy(
            symbol="AKAM",
            quantity=10,
            limit_price=100.0,
            target_price=110.0,
            stop_price=95.0,
        )

        assert ids == {"parent_id": 1000, "target_id": 1001, "stop_id": 1002}
        assert len(placed) == 3
        parent_oid, parent_contract, parent_order = placed[0]
        target_oid, _, target_order = placed[1]
        stop_oid, _, stop_order = placed[2]

        # Parent: BUY LMT 100.0, transmit=False, no parentId.
        assert parent_oid == 1000
        assert parent_order.action == "BUY"
        assert parent_order.orderType == "LMT"
        assert parent_order.lmtPrice == 100.0
        assert parent_order.totalQuantity == 10
        assert parent_order.transmit is False
        assert parent_contract.symbol == "AKAM"
        assert parent_contract.secType == "STK"

        # Child target: SELL LMT 110.0, parentId=1000, transmit=False.
        assert target_oid == 1001
        assert target_order.action == "SELL"
        assert target_order.orderType == "LMT"
        assert target_order.lmtPrice == 110.0
        assert target_order.parentId == 1000
        assert target_order.transmit is False

        # Child stop: SELL STP 95.0, parentId=1000, transmit=True (last leg).
        assert stop_oid == 1002
        assert stop_order.action == "SELL"
        assert stop_order.orderType == "STP"
        assert stop_order.auxPrice == 95.0
        assert stop_order.parentId == 1000
        assert stop_order.transmit is True

    @pytest.mark.unit
    def test_rejects_when_not_connected(self, bridge):
        bridge._app = None
        with pytest.raises(RuntimeError, match="not connected"):
            bridge.place_bracket_buy("AKAM", 10, 100.0, 110.0, 95.0)

    @pytest.mark.unit
    def test_rejects_zero_quantity(self, bridge, mock_service_manager):
        app = _BridgeApp(mock_service_manager, "DU12345")
        app._connected = True
        app._ready = True
        app._next_valid_order_id = 1
        bridge._app = app
        with pytest.raises(ValueError, match="quantity must be > 0"):
            bridge.place_bracket_buy("AKAM", 0, 100.0, 110.0, 95.0)

    @pytest.mark.unit
    def test_rejects_target_not_above_entry(self, bridge, mock_service_manager):
        app = _BridgeApp(mock_service_manager, "DU12345")
        app._connected = True
        app._ready = True
        app._next_valid_order_id = 1
        bridge._app = app
        with pytest.raises(ValueError, match="target.*must be > entry"):
            bridge.place_bracket_buy("AKAM", 10, 100.0, 100.0, 95.0)

    @pytest.mark.unit
    def test_rejects_stop_not_below_entry(self, bridge, mock_service_manager):
        app = _BridgeApp(mock_service_manager, "DU12345")
        app._connected = True
        app._ready = True
        app._next_valid_order_id = 1
        bridge._app = app
        with pytest.raises(ValueError, match="stop.*must be < entry"):
            bridge.place_bracket_buy("AKAM", 10, 100.0, 110.0, 100.0)
