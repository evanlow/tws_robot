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
        """Test that non-BASE currency updates are ignored."""
        app = _BridgeApp(mock_service_manager, "DU12345")
        
        app.updateAccountValue("TotalCashBalance", "50000.00", "USD", "DU12345")
        
        mock_service_manager.update_account_summary.assert_not_called()
    
    @pytest.mark.unit
    def test_update_portfolio_long_position(self, mock_service_manager):
        """Test updatePortfolio with a long position."""
        app = _BridgeApp(mock_service_manager, "DU12345")
        
        contract = Contract()
        contract.symbol = "AAPL"
        contract.localSymbol = "AAPL"
        
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
        assert call_args[1]["sec_type"] == ""
        
        # Verify PnL percentage calculated correctly
        expected_pnl_pct = (150.0 - 145.0) / 145.0
        assert abs(call_args[1]["unrealized_pnl_pct"] - expected_pnl_pct) < 0.0001
    
    @pytest.mark.unit
    def test_update_portfolio_short_position(self, mock_service_manager):
        """Test updatePortfolio with a short position."""
        app = _BridgeApp(mock_service_manager, "DU12345")
        
        contract = Contract()
        contract.symbol = "TSLA"
        
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
        assert call_args[1]["sec_type"] == ""
    
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
