"""
Unit tests for Real-time Data Pipeline.

Tests data structures and basic functionality without actual TWS connections.
"""

import pytest
from unittest.mock import Mock
from datetime import datetime

from data.realtime_pipeline import DataSubscription, BarBuffer
from backtest.data_models import Bar, TimeFrame


class TestDataSubscription:
    """Test DataSubscription dataclass"""
    
    def test_subscription_creation(self):
        """Test creating a data subscription"""
        callback = Mock()
        sub = DataSubscription(
            strategy_id="ma_cross_1",
            symbols=["AAPL", "MSFT"],
            callback=callback
        )
        
        assert sub.strategy_id == "ma_cross_1"
        assert sub.symbols == ["AAPL", "MSFT"]
        assert sub.callback == callback
        assert sub.timeframe == TimeFrame.MINUTE_1
        assert sub.active is True
    
    def test_subscription_with_custom_timeframe(self):
        """Test subscription with custom timeframe"""
        callback = Mock()
        sub = DataSubscription(
            strategy_id="test",
            symbols=["SPY"],
            callback=callback,
            timeframe=TimeFrame.MINUTE_5
        )
        
        assert sub.timeframe == TimeFrame.MINUTE_5
    
    def test_subscription_defaults(self):
        """Test subscription default values"""
        callback = Mock()
        sub = DataSubscription("test", ["AAPL"], callback)
        
        assert sub.timeframe == TimeFrame.MINUTE_1
        assert sub.active is True


class TestBarBuffer:
    """Test BarBuffer for tick aggregation"""
    
    def test_buffer_initialization(self):
        """Test buffer initializes correctly"""
        buffer = BarBuffer(symbol="AAPL")
        
        assert buffer.symbol == "AAPL"
        assert buffer.open is None
        assert buffer.high is None
        assert buffer.low is None
        assert buffer.close is None
        assert buffer.volume == 0
        assert buffer.bar_start is None
        assert buffer.last_update is None
    
    def test_buffer_update_first_tick(self):
        """Test buffer updates with first tick"""
        buffer = BarBuffer(symbol="AAPL")
        now = datetime.now()
        buffer.update_price(price=150.00, size=100, timestamp=now)
        
        assert buffer.open == 150.00
        assert buffer.high == 150.00
        assert buffer.low == 150.00
        assert buffer.close == 150.00
        assert buffer.volume == 100
        assert buffer.bar_start == now
    
    def test_buffer_update_multiple_ticks(self):
        """Test buffer updates with multiple ticks"""
        buffer = BarBuffer(symbol="AAPL")
        now = datetime.now()
        
        buffer.update_price(price=150.00, size=100, timestamp=now)
        buffer.update_price(price=151.50, size=200, timestamp=now)  # New high
        buffer.update_price(price=149.00, size=150, timestamp=now)  # New low
        buffer.update_price(price=150.50, size=175, timestamp=now)
        
        assert buffer.open == 150.00
        assert buffer.high == 151.50
        assert buffer.low == 149.00
        assert buffer.close == 150.50
        assert buffer.volume == 625
    
    def test_buffer_to_bar(self):
        """Test converting buffer to Bar"""
        buffer = BarBuffer(symbol="AAPL")
        now = datetime.now()
        buffer.update_price(price=150.00, size=100, timestamp=now)
        buffer.update_price(price=151.00, size=200, timestamp=now)
        buffer.update_price(price=149.50, size=150, timestamp=now)
        
        bar = buffer.to_bar(timeframe=TimeFrame.MINUTE_1)
        
        assert isinstance(bar, Bar)
        assert bar.symbol == "AAPL"
        assert bar.open == 150.00
        assert bar.high == 151.00
        assert bar.low == 149.50
        assert bar.close == 149.50
        assert bar.volume == 450
        assert bar.timeframe == TimeFrame.MINUTE_1
    
    def test_buffer_reset(self):
        """Test buffer reset after bar creation"""
        buffer = BarBuffer(symbol="AAPL")
        now = datetime.now()
        buffer.update_price(price=150.00, size=100, timestamp=now)
        buffer.update_price(price=151.00, size=200, timestamp=now)
        
        buffer.reset()
        
        assert buffer.open is None
        assert buffer.high is None
        assert buffer.low is None
        assert buffer.close is None
        assert buffer.volume == 0
        assert buffer.bar_start is None
    
    def test_buffer_empty_bar_raises_error(self):
        """Test creating bar from empty buffer raises error"""
        buffer = BarBuffer(symbol="AAPL")
        
        with pytest.raises(ValueError, match="Cannot create Bar"):
            buffer.to_bar(timeframe=TimeFrame.MINUTE_1)
    
    def test_buffer_with_zero_size_tick(self):
        """Test buffer handles zero size ticks"""
        buffer = BarBuffer(symbol="AAPL")
        now = datetime.now()
        buffer.update_price(price=150.00, size=100, timestamp=now)
        buffer.update_price(price=151.00, size=0, timestamp=now)  # Zero size
        
        # Volume should still be 100, but high should update
        assert buffer.volume == 100
        assert buffer.high == 151.00


class TestRealtimeManagerPattern:
    """Test RealtimeDataManager design patterns (no actual instantiation)"""
    
    def test_manager_can_be_imported(self):
        """Test that RealtimeDataManager can be imported"""
        from data.realtime_pipeline import RealtimeDataManager
        assert RealtimeDataManager is not None
    
    def test_subscription_storage_pattern(self):
        """Test the subscription storage pattern"""
        callback = Mock()
        sub = DataSubscription("strat1", ["AAPL"], callback)
        
        # Simulate manager storage
        subscriptions = {}
        subscriptions[sub.strategy_id] = sub
        
        assert "strat1" in subscriptions
        assert subscriptions["strat1"].symbols == ["AAPL"]
    
    def test_multiple_strategy_subscriptions(self):
        """Test multiple strategies can subscribe"""
        subscriptions = {}
        
        sub1 = DataSubscription("strat1", ["AAPL"], Mock())
        sub2 = DataSubscription("strat2", ["AAPL", "MSFT"], Mock())
        
        subscriptions[sub1.strategy_id] = sub1
        subscriptions[sub2.strategy_id] = sub2
        
        assert len(subscriptions) == 2
    
    def test_symbol_to_reqid_mapping(self):
        """Test symbol to request ID mapping pattern"""
        symbol_to_req_id = {}
        req_id_to_symbol = {}
        next_req_id = 1
        
        # Simulate subscribing to symbols
        for symbol in ["AAPL", "MSFT", "SPY"]:
            if symbol not in symbol_to_req_id:
                symbol_to_req_id[symbol] = next_req_id
                req_id_to_symbol[next_req_id] = symbol
                next_req_id += 1
        
        assert len(symbol_to_req_id) == 3
        assert symbol_to_req_id["AAPL"] == 1
        assert req_id_to_symbol[1] == "AAPL"
    
    def test_shared_symbol_reuse(self):
        """Test shared symbols reuse same request ID"""
        symbol_to_req_id = {}
        
        # Strategy 1 subscribes to AAPL
        if "AAPL" not in symbol_to_req_id:
            symbol_to_req_id["AAPL"] = 1
        
        req_id_1 = symbol_to_req_id["AAPL"]
        
        # Strategy 2 also subscribes to AAPL (should reuse)
        req_id_2 = symbol_to_req_id.get("AAPL", -1)
        
        assert req_id_1 == req_id_2 == 1


class TestBarAggregation:
    """Test bar aggregation logic"""
    
    def test_minute_bar_aggregation(self):
        """Test aggregating ticks into 1-minute bar"""
        buffer = BarBuffer(symbol="AAPL")
        now = datetime.now()
        
        # Simulate ticks within 1 minute
        prices = [150.20, 150.25, 150.50, 150.10, 150.30]
        sizes = [100, 150, 200, 175, 125]
        
        for price, size in zip(prices, sizes):
            buffer.update_price(price, size, now)
        
        bar = buffer.to_bar(timeframe=TimeFrame.MINUTE_1)
        
        assert bar.open == 150.20
        assert bar.close == 150.30
        assert bar.high == 150.50
        assert bar.low == 150.10
        assert bar.volume == sum(sizes)
    
    def test_bar_timestamp(self):
        """Test bar has valid timestamp"""
        buffer = BarBuffer(symbol="AAPL")
        now = datetime.now()
        buffer.update_price(price=150.00, size=100, timestamp=now)
        
        bar = buffer.to_bar(timeframe=TimeFrame.MINUTE_1)
        
        assert isinstance(bar.timestamp, datetime)
        assert bar.timestamp == now
