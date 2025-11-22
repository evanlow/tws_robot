"""
Unit tests for Paper Trading Adapter.

Tests order execution, position tracking, and TWS integration (mocked).
"""

import pytest
from unittest.mock import Mock, MagicMock, patch
import threading
from time import sleep

from execution.paper_adapter import PaperTradingAdapter, PendingOrder
from backtest.data_models import Position


class TestPendingOrder:
    """Test PendingOrder dataclass"""
    
    def test_pending_order_creation(self):
        """Test creating pending order"""
        order = PendingOrder(
            order_id=1,
            symbol="AAPL",
            action="BUY",
            quantity=100,
            order_type="MARKET"
        )
        assert order.order_id == 1
        assert order.symbol == "AAPL"
        assert order.action == "BUY"
        assert order.status == "PENDING"
        assert order.filled_qty == 0
    
    def test_pending_order_with_prices(self):
        """Test pending order with limit/stop prices"""
        order = PendingOrder(
            order_id=2,
            symbol="MSFT",
            action="SELL",
            quantity=50,
            order_type="LIMIT",
            limit_price=350.00
        )
        assert order.limit_price == 350.00
        assert order.stop_price is None


class TestPaperTradingAdapter:
    """Test PaperTradingAdapter"""
    
    @pytest.fixture
    def adapter(self):
        """Create adapter instance"""
        adapter = PaperTradingAdapter(
            host="127.0.0.1",
            port=7497,
            client_id=100,
            commission_per_share=0.005
        )
        # Mock the EClient methods
        adapter.connect = Mock(return_value=True)
        adapter.run = Mock()
        adapter.disconnect = Mock()
        adapter.placeOrder = Mock()
        adapter.cancelOrder = Mock()
        adapter.reqPositions = Mock()
        
        return adapter
    
    def test_initialization(self, adapter):
        """Test adapter initializes correctly"""
        assert adapter.host == "127.0.0.1"
        assert adapter.port == 7497
        assert adapter.client_id == 100
        assert adapter.commission_per_share == 0.005
        assert adapter.connected is False
        assert adapter.ready is False
        assert len(adapter._positions) == 0
        assert len(adapter._orders) == 0
    
    def test_connection_ack(self, adapter):
        """Test connectAck callback"""
        assert adapter.connected is False
        adapter.connectAck()
        assert adapter.connected is True
    
    def test_next_valid_id(self, adapter):
        """Test nextValidId callback"""
        assert adapter.ready is False
        assert adapter.next_valid_order_id is None
        
        adapter.nextValidId(1000)
        
        assert adapter.ready is True
        assert adapter.next_valid_order_id == 1000
    
    def test_buy_order(self, adapter):
        """Test placing BUY order"""
        adapter.ready = True
        adapter.next_valid_order_id = 1000
        
        order_id = adapter.buy("AAPL", 100, "MARKET")
        
        assert order_id == 1000
        assert adapter.next_valid_order_id == 1001
        assert order_id in adapter._orders
        
        order = adapter._orders[order_id]
        assert order.symbol == "AAPL"
        assert order.action == "BUY"
        assert order.quantity == 100
        assert order.order_type == "MARKET"
        assert order.status == "PENDING"
        
        # Verify TWS API called
        adapter.placeOrder.assert_called_once()
    
    def test_sell_order(self, adapter):
        """Test placing SELL order"""
        adapter.ready = True
        adapter.next_valid_order_id = 2000
        
        order_id = adapter.sell("MSFT", 50, "MARKET")
        
        assert order_id == 2000
        assert order_id in adapter._orders
        
        order = adapter._orders[order_id]
        assert order.symbol == "MSFT"
        assert order.action == "SELL"
        assert order.quantity == 50
    
    def test_limit_order(self, adapter):
        """Test placing LIMIT order"""
        adapter.ready = True
        adapter.next_valid_order_id = 3000
        
        order_id = adapter.buy("AAPL", 100, "LIMIT", limit_price=150.50)
        
        assert order_id in adapter._orders
        order = adapter._orders[order_id]
        assert order.order_type == "LIMIT"
        assert order.limit_price == 150.50
    
    def test_stop_order(self, adapter):
        """Test placing STOP order"""
        adapter.ready = True
        adapter.next_valid_order_id = 4000
        
        order_id = adapter.sell("MSFT", 50, "STOP", stop_price=340.00)
        
        assert order_id in adapter._orders
        order = adapter._orders[order_id]
        assert order.order_type == "STOP"
        assert order.stop_price == 340.00
    
    def test_order_when_not_ready(self, adapter):
        """Test placing order when not ready raises error"""
        adapter.ready = False
        
        with pytest.raises(RuntimeError, match="Not connected"):
            adapter.buy("AAPL", 100)
    
    def test_cancel_order(self, adapter):
        """Test cancelling an order"""
        adapter.ready = True
        adapter.next_valid_order_id = 5000
        
        order_id = adapter.buy("AAPL", 100)
        success = adapter.cancel_order(order_id)
        
        assert success is True
        adapter.cancelOrder.assert_called_once_with(order_id)
    
    def test_get_order_status(self, adapter):
        """Test getting order status"""
        adapter.ready = True
        adapter.next_valid_order_id = 6000
        
        order_id = adapter.buy("AAPL", 100)
        status = adapter.get_order_status(order_id)
        
        assert status == "PENDING"
    
    def test_get_nonexistent_order(self, adapter):
        """Test getting nonexistent order returns None"""
        status = adapter.get_order_status(9999)
        assert status is None
    
    def test_position_callback(self, adapter):
        """Test position update callback"""
        # Create mock contract
        contract = Mock()
        contract.symbol = "AAPL"
        
        # Simulate position update
        adapter.position("DU123456", contract, 100.0, 150.00)
        
        # Check position tracked
        position = adapter.get_position("AAPL")
        assert position is not None
        assert position.symbol == "AAPL"
        assert position.quantity == 100
        assert position.average_cost == 150.00
    
    def test_position_closed(self, adapter):
        """Test position closed (quantity = 0)"""
        contract = Mock()
        contract.symbol = "AAPL"
        
        # Add position
        adapter.position("DU123456", contract, 100.0, 150.00)
        assert "AAPL" in adapter._positions
        
        # Close position
        adapter.position("DU123456", contract, 0.0, 150.00)
        assert "AAPL" not in adapter._positions
    
    def test_get_all_positions(self, adapter):
        """Test getting all positions"""
        # Add multiple positions
        for symbol, qty, price in [("AAPL", 100, 150.00), ("MSFT", 50, 340.00), ("SPY", 200, 450.00)]:
            contract = Mock()
            contract.symbol = symbol
            adapter.position("DU123456", contract, float(qty), price)
        
        positions = adapter.get_all_positions()
        assert len(positions) == 3
        assert "AAPL" in positions
        assert "MSFT" in positions
        assert "SPY" in positions
    
    def test_close_position_long(self, adapter):
        """Test closing long position"""
        adapter.ready = True
        adapter.next_valid_order_id = 7000
        
        # Add long position
        adapter._positions["AAPL"] = Position(symbol="AAPL", quantity=100, average_cost=150.00)
        
        # Close position
        order_id = adapter.close_position("AAPL")
        
        assert order_id is not None
        order = adapter._orders[order_id]
        assert order.action == "SELL"
        assert order.quantity == 100
    
    def test_close_position_short(self, adapter):
        """Test closing short position"""
        adapter.ready = True
        adapter.next_valid_order_id = 8000
        
        # Add short position
        adapter._positions["MSFT"] = Position(symbol="MSFT", quantity=-50, average_cost=340.00)
        
        # Close position
        order_id = adapter.close_position("MSFT")
        
        assert order_id is not None
        order = adapter._orders[order_id]
        assert order.action == "BUY"
        assert order.quantity == 50
    
    def test_close_nonexistent_position(self, adapter):
        """Test closing position that doesn't exist returns None"""
        adapter.ready = True
        adapter.next_valid_order_id = 9000
        
        order_id = adapter.close_position("AAPL")
        assert order_id is None
    
    def test_order_status_callback(self, adapter):
        """Test orderStatus callback updates order"""
        adapter.ready = True
        adapter.next_valid_order_id = 10000
        
        # Place order
        order_id = adapter.buy("AAPL", 100, "MARKET")
        
        # Simulate partial fill
        adapter.orderStatus(
            orderId=order_id,
            status="PartiallyFilled",
            filled=50.0,
            remaining=50.0,
            avgFillPrice=150.25,
            permId=0,
            parentId=0,
            lastFillPrice=150.25,
            clientId=100,
            whyHeld="",
            mktCapPrice=0.0
        )
        
        order = adapter._orders[order_id]
        assert order.status == "PartiallyFilled"
        assert order.filled_qty == 50
        assert order.avg_fill_price == 150.25
        assert order.commission == 50 * 0.005  # 50 shares * $0.005
    
    def test_order_status_filled(self, adapter):
        """Test order fully filled updates position"""
        adapter.ready = True
        adapter.next_valid_order_id = 11000
        
        # Place order
        order_id = adapter.buy("AAPL", 100, "MARKET")
        
        # Simulate full fill
        adapter.orderStatus(
            orderId=order_id,
            status="Filled",
            filled=100.0,
            remaining=0.0,
            avgFillPrice=150.50,
            permId=0,
            parentId=0,
            lastFillPrice=150.50,
            clientId=100,
            whyHeld="",
            mktCapPrice=0.0
        )
        
        # Check order updated
        order = adapter._orders[order_id]
        assert order.status == "Filled"
        assert order.filled_qty == 100
        
        # Check position created
        position = adapter.get_position("AAPL")
        assert position is not None
        assert position.quantity == 100
        assert position.average_cost == 150.50
    
    def test_update_existing_position(self, adapter):
        """Test adding to existing position updates average price"""
        adapter.ready = True
        adapter.next_valid_order_id = 12000
        
        # Create initial position
        adapter._positions["AAPL"] = Position(symbol="AAPL", quantity=100, average_cost=150.00)
        
        # Place another buy order
        order_id = adapter.buy("AAPL", 100, "MARKET")
        
        # Simulate fill at different price
        adapter.orderStatus(
            orderId=order_id,
            status="Filled",
            filled=100.0,
            remaining=0.0,
            avgFillPrice=160.00,  # Higher price
            permId=0,
            parentId=0,
            lastFillPrice=160.00,
            clientId=100,
            whyHeld="",
            mktCapPrice=0.0
        )
        
        # Check position updated with weighted average
        position = adapter.get_position("AAPL")
        assert position.quantity == 200
        # Average: (100 * 150 + 100 * 160) / 200 = 155
        assert position.average_cost == 155.00
    
    def test_reduce_position(self, adapter):
        """Test reducing position size"""
        adapter.ready = True
        adapter.next_valid_order_id = 13000
        
        # Create initial position
        adapter._positions["AAPL"] = Position(symbol="AAPL", quantity=100, average_cost=150.00)
        
        # Sell half
        order_id = adapter.sell("AAPL", 50, "MARKET")
        
        adapter.orderStatus(
            orderId=order_id,
            status="Filled",
            filled=50.0,
            remaining=0.0,
            avgFillPrice=155.00,
            permId=0,
            parentId=0,
            lastFillPrice=155.00,
            clientId=100,
            whyHeld="",
            mktCapPrice=0.0
        )
        
        # Check position reduced but avg price maintained
        position = adapter.get_position("AAPL")
        assert position.quantity == 50
        assert position.average_cost == 150.00  # Original cost basis
    
    def test_close_position_via_fill(self, adapter):
        """Test position closed when fully sold"""
        adapter.ready = True
        adapter.next_valid_order_id = 14000
        
        # Create position
        adapter._positions["AAPL"] = Position(symbol="AAPL", quantity=100, average_cost=150.00)
        
        # Sell all
        order_id = adapter.sell("AAPL", 100, "MARKET")
        
        adapter.orderStatus(
            orderId=order_id,
            status="Filled",
            filled=100.0,
            remaining=0.0,
            avgFillPrice=155.00,
            permId=0,
            parentId=0,
            lastFillPrice=155.00,
            clientId=100,
            whyHeld="",
            mktCapPrice=0.0
        )
        
        # Check position removed
        position = adapter.get_position("AAPL")
        assert position is None
    
    def test_error_callback(self, adapter):
        """Test error handling"""
        error_callback = Mock()
        adapter.set_on_error_callback(error_callback)
        
        # Simulate error
        adapter.error(reqId=1, errorCode=200, errorString="Test error")
        
        # Check callback called
        error_callback.assert_called_once_with(1, 200, "Test error")
    
    def test_error_rejects_order(self, adapter):
        """Test error marks order as rejected"""
        adapter.ready = True
        adapter.next_valid_order_id = 15000
        
        order_id = adapter.buy("AAPL", 100)
        
        # Simulate order rejection
        adapter.error(reqId=order_id, errorCode=201, errorString="Order rejected")
        
        order = adapter._orders[order_id]
        assert order.status == "REJECTED"
    
    def test_informational_errors_ignored(self, adapter):
        """Test informational TWS messages don't trigger error callback"""
        error_callback = Mock()
        adapter.set_on_error_callback(error_callback)
        
        # Simulate informational message (2100-2199 range)
        adapter.error(reqId=-1, errorCode=2104, errorString="Market data farm connected")
        
        # Should not trigger error callback
        error_callback.assert_not_called()
    
    def test_fill_callback(self, adapter):
        """Test fill callback is triggered"""
        fill_callback = Mock()
        adapter.set_on_fill_callback(fill_callback)
        
        adapter.ready = True
        adapter.next_valid_order_id = 16000
        
        order_id = adapter.buy("AAPL", 100)
        
        # Simulate fill
        adapter.orderStatus(
            orderId=order_id,
            status="Filled",
            filled=100.0,
            remaining=0.0,
            avgFillPrice=150.00,
            permId=0,
            parentId=0,
            lastFillPrice=150.00,
            clientId=100,
            whyHeld="",
            mktCapPrice=0.0
        )
        
        # Check callback called with order
        fill_callback.assert_called_once()
        called_order = fill_callback.call_args[0][0]
        assert called_order.order_id == order_id
        assert called_order.status == "Filled"
    
    def test_request_positions(self, adapter):
        """Test requesting positions from TWS"""
        adapter.request_positions()
        adapter.reqPositions.assert_called_once()
    
    def test_disconnect_gracefully(self, adapter):
        """Test graceful disconnection"""
        adapter.connected = True
        adapter.ready = True
        
        adapter.disconnect_gracefully()
        
        assert adapter.connected is False
        assert adapter.ready is False
        adapter.disconnect.assert_called_once()


class TestPaperAdapterThreadSafety:
    """Test thread safety of adapter"""
    
    @pytest.fixture
    def adapter(self):
        """Create adapter with mocked TWS methods"""
        adapter = PaperTradingAdapter()
        adapter.connect = Mock()
        adapter.run = Mock()
        adapter.placeOrder = Mock()
        adapter.ready = True
        adapter.next_valid_order_id = 1000
        return adapter
    
    def test_concurrent_orders(self, adapter):
        """Test placing orders from multiple threads"""
        order_ids = []
        
        def place_orders():
            for i in range(10):
                order_id = adapter.buy("AAPL", 100)
                order_ids.append(order_id)
        
        # Place orders from 3 threads
        threads = [threading.Thread(target=place_orders) for _ in range(3)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        
        # Check all orders tracked uniquely
        assert len(set(order_ids)) == 30  # 3 threads * 10 orders each
        assert len(adapter._orders) == 30
    
    def test_concurrent_position_updates(self, adapter):
        """Test position updates from multiple threads"""
        contract = Mock()
        contract.symbol = "AAPL"
        
        def update_position(qty):
            adapter.position("DU123456", contract, float(qty), 150.00)
        
        threads = [threading.Thread(target=update_position, args=(i*10,)) for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        
        # Should have one position (last update wins)
        positions = adapter.get_all_positions()
        assert len(positions) <= 1  # Could be 0 if last update was 0
