"""
Unit tests for MarketDataFeed

Tests real-time data pipeline components:
- BarAggregator (5-sec bars → 5-min bars)
- MarketDataFeed (TWS integration, subscriptions, buffering)
- Thread safety

Author: TWS Robot Development Team
Date: January 24, 2026
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import Mock, MagicMock, patch
from collections import deque

from execution.market_data_feed import (
    BarData, TickData, BarAggregator, MarketDataFeed
)


# ==================== Fixtures ====================

@pytest.fixture
def sample_bar():
    """Create sample bar data"""
    return BarData(
        symbol='AAPL',
        timestamp=datetime(2026, 1, 24, 10, 30, 0),
        open=150.0,
        high=151.0,
        low=149.5,
        close=150.5,
        volume=1000
    )


@pytest.fixture
def mock_tws_adapter():
    """Create mock TWS adapter"""
    adapter = Mock()
    adapter.connected = True
    adapter.ready = True
    adapter.reqRealTimeBars = Mock()
    adapter.cancelRealTimeBars = Mock()
    return adapter


# ==================== BarData Tests ====================

class TestBarData:
    """Test BarData dataclass"""
    
    def test_bar_data_creation(self):
        """Test creating bar data"""
        bar = BarData(
            symbol='AAPL',
            timestamp=datetime(2026, 1, 24, 10, 0, 0),
            open=150.0,
            high=152.0,
            low=149.0,
            close=151.0,
            volume=10000
        )
        
        assert bar.symbol == 'AAPL'
        assert bar.open == 150.0
        assert bar.high == 152.0
        assert bar.low == 149.0
        assert bar.close == 151.0
        assert bar.volume == 10000
    
    def test_bar_data_immutable(self, sample_bar):
        """Test that bar data fields are accessible"""
        assert sample_bar.symbol == 'AAPL'
        assert sample_bar.close == 150.5


# ==================== BarAggregator Tests ====================

class TestBarAggregator:
    """Test bar aggregation (5-sec → 5-min bars)"""
    
    def test_aggregator_initialization(self):
        """Test aggregator creation"""
        agg = BarAggregator('AAPL', bar_size_minutes=5)
        
        assert agg.symbol == 'AAPL'
        assert agg.bar_size_minutes == 5
        assert agg.bars_per_period == 60  # 5 min * 12 bars/min
        assert len(agg.current_bars) == 0
        assert agg.last_complete_bar is None
    
    def test_aggregator_single_bar_incomplete(self):
        """Test adding single bar (not enough to aggregate)"""
        agg = BarAggregator('AAPL', bar_size_minutes=5)
        
        bar = BarData(
            symbol='AAPL',
            timestamp=datetime(2026, 1, 24, 10, 0, 0),
            open=150.0, high=150.5, low=149.5, close=150.2, volume=100
        )
        
        result = agg.add_bar(bar)
        
        assert result is None  # Not complete yet
        assert len(agg.current_bars) == 1
    
    def test_aggregator_complete_period(self):
        """Test completing full aggregation period"""
        agg = BarAggregator('AAPL', bar_size_minutes=5)
        
        # Add 60 bars (5 minutes worth)
        base_time = datetime(2026, 1, 24, 10, 0, 0)
        bars = []
        
        for i in range(60):
            bar = BarData(
                symbol='AAPL',
                timestamp=base_time + timedelta(seconds=i*5),
                open=150.0 + i*0.01,
                high=150.0 + i*0.01 + 0.5,
                low=150.0 + i*0.01 - 0.3,
                close=150.0 + i*0.01 + 0.2,
                volume=100
            )
            bars.append(bar)
        
        # Add first 59 bars - should return None
        for bar in bars[:59]:
            result = agg.add_bar(bar)
            assert result is None
        
        # Add 60th bar - should return aggregated bar
        result = agg.add_bar(bars[59])
        
        assert result is not None
        assert isinstance(result, BarData)
        assert result.symbol == 'AAPL'
        assert result.open == bars[0].open  # First bar's open
        assert result.close == bars[59].close  # Last bar's close
        assert result.volume == 6000  # Sum of all volumes (100 * 60)
        
        # High should be max of all bars
        expected_high = max(bar.high for bar in bars)
        assert result.high == expected_high
        
        # Low should be min of all bars
        expected_low = min(bar.low for bar in bars)
        assert result.low == expected_low
    
    def test_aggregator_resets_after_completion(self):
        """Test that aggregator resets after completing period"""
        agg = BarAggregator('AAPL', bar_size_minutes=5)
        
        # Add 60 bars
        base_time = datetime(2026, 1, 24, 10, 0, 0)
        for i in range(60):
            bar = BarData(
                symbol='AAPL',
                timestamp=base_time + timedelta(seconds=i*5),
                open=150.0, high=150.5, low=149.5, close=150.2, volume=100
            )
            agg.add_bar(bar)
        
        # Current bars should be reset
        assert len(agg.current_bars) == 0
        
        # Adding next bar should start new period
        next_bar = BarData(
            symbol='AAPL',
            timestamp=base_time + timedelta(seconds=300),
            open=150.3, high=150.6, low=150.0, close=150.4, volume=100
        )
        result = agg.add_bar(next_bar)
        
        assert result is None  # New period just started
        assert len(agg.current_bars) == 1
    
    def test_aggregator_different_timeframes(self):
        """Test aggregator with different timeframes"""
        # 1-minute bars (12 five-second bars)
        agg_1min = BarAggregator('AAPL', bar_size_minutes=1)
        assert agg_1min.bars_per_period == 12
        
        # 15-minute bars (180 five-second bars)
        agg_15min = BarAggregator('AAPL', bar_size_minutes=15)
        assert agg_15min.bars_per_period == 180


# ==================== MarketDataFeed Tests ====================

class TestMarketDataFeed:
    """Test market data feed"""
    
    def test_feed_initialization(self, mock_tws_adapter):
        """Test feed creation"""
        feed = MarketDataFeed(
            tws_adapter=mock_tws_adapter,
            symbols=['AAPL', 'MSFT'],
            bar_size_minutes=5,
            buffer_size=100
        )
        
        assert feed.tws_adapter == mock_tws_adapter
        assert feed.symbols == ['AAPL', 'MSFT']
        assert feed.bar_size_minutes == 5
        assert feed.buffer_size == 100
        assert len(feed.aggregators) == 2
        assert 'AAPL' in feed.aggregators
        assert 'MSFT' in feed.aggregators
        assert len(feed.buffers) == 2
        assert not feed.running
    
    def test_subscribe_callback(self, mock_tws_adapter):
        """Test subscribing to bar data"""
        feed = MarketDataFeed(mock_tws_adapter, ['AAPL'])
        
        callback = Mock()
        feed.subscribe(callback)
        
        assert len(feed.subscribers) == 1
        assert callback in feed.subscribers
    
    def test_multiple_subscribers(self, mock_tws_adapter):
        """Test multiple subscribers"""
        feed = MarketDataFeed(mock_tws_adapter, ['AAPL'])
        
        callback1 = Mock()
        callback2 = Mock()
        callback3 = Mock()
        
        feed.subscribe(callback1)
        feed.subscribe(callback2)
        feed.subscribe(callback3)
        
        assert len(feed.subscribers) == 3
    
    def test_start_requests_realtime_bars(self, mock_tws_adapter):
        """Test that start() requests bars for all symbols"""
        feed = MarketDataFeed(mock_tws_adapter, ['AAPL', 'MSFT'])
        
        feed.start()
        
        assert feed.running
        assert mock_tws_adapter.reqRealTimeBars.call_count == 2
        
        # Verify contracts were created correctly
        calls = mock_tws_adapter.reqRealTimeBars.call_args_list
        
        # Check that request IDs are unique
        req_ids = [call.kwargs['reqId'] for call in calls]
        assert len(req_ids) == 2
        assert len(set(req_ids)) == 2  # All unique
    
    def test_stop_cancels_subscriptions(self, mock_tws_adapter):
        """Test that stop() cancels all subscriptions"""
        feed = MarketDataFeed(mock_tws_adapter, ['AAPL', 'MSFT'])
        
        feed.start()
        req_ids_before = list(feed.req_id_to_symbol.keys())
        
        feed.stop()
        
        assert not feed.running
        assert mock_tws_adapter.cancelRealTimeBars.call_count == 2
        
        # Verify it cancelled the correct request IDs
        cancel_calls = [call.args[0] for call in mock_tws_adapter.cancelRealTimeBars.call_args_list]
        assert set(cancel_calls) == set(req_ids_before)
    
    def test_on_realtime_bar_adds_to_buffer(self, mock_tws_adapter):
        """Test processing real-time bar"""
        feed = MarketDataFeed(mock_tws_adapter, ['AAPL'], bar_size_minutes=5)
        feed.start()
        
        # Get the request ID that was used
        req_id = list(feed.req_id_to_symbol.keys())[0]
        
        # Simulate receiving 60 bars (to complete one 5-min period)
        base_timestamp = int(datetime(2026, 1, 24, 10, 0, 0).timestamp())
        
        for i in range(60):
            feed._on_realtime_bar(
                reqId=req_id,
                time=base_timestamp + i*5,
                open_=150.0,
                high=150.5,
                low=149.5,
                close=150.2,
                volume=100,
                wap=150.1,
                count=10
            )
        
        # Should have one aggregated bar in buffer
        buffer = feed.buffers['AAPL']
        assert len(buffer) == 1
        
        bar = buffer[0]
        assert bar.symbol == 'AAPL'
        assert bar.open == 150.0
        assert bar.volume == 6000  # 100 * 60
    
    def test_on_realtime_bar_notifies_subscribers(self, mock_tws_adapter):
        """Test that completed bars notify subscribers"""
        feed = MarketDataFeed(mock_tws_adapter, ['AAPL'], bar_size_minutes=5)
        
        callback = Mock()
        feed.subscribe(callback)
        feed.start()
        
        req_id = list(feed.req_id_to_symbol.keys())[0]
        base_timestamp = int(datetime(2026, 1, 24, 10, 0, 0).timestamp())
        
        # Send 60 bars to complete one period
        for i in range(60):
            feed._on_realtime_bar(
                reqId=req_id,
                time=base_timestamp + i*5,
                open_=150.0,
                high=150.5,
                low=149.5,
                close=150.2,
                volume=100,
                wap=150.1,
                count=10
            )
        
        # Callback should have been called once with aggregated bar
        assert callback.call_count == 1
        
        call_args = callback.call_args
        symbol = call_args.args[0]
        bar = call_args.args[1]
        
        assert symbol == 'AAPL'
        assert isinstance(bar, BarData)
        assert bar.volume == 6000
    
    def test_get_historical_bars(self, mock_tws_adapter):
        """Test retrieving historical bars from buffer"""
        feed = MarketDataFeed(mock_tws_adapter, ['AAPL'], buffer_size=50)
        
        # Manually add bars to buffer
        base_time = datetime(2026, 1, 24, 10, 0, 0)
        for i in range(30):
            bar = BarData(
                symbol='AAPL',
                timestamp=base_time + timedelta(minutes=i*5),
                open=150.0 + i,
                high=151.0 + i,
                low=149.0 + i,
                close=150.5 + i,
                volume=1000
            )
            feed.buffers['AAPL'].append(bar)
        
        # Get last 20 bars
        bars = feed.get_historical_bars('AAPL', count=20)
        
        assert len(bars) == 20
        assert bars[0].open == 160.0  # 150 + 10 (starting from bar 10)
        assert bars[-1].open == 179.0  # 150 + 29 (last bar)
    
    def test_get_latest_bar(self, mock_tws_adapter):
        """Test getting most recent bar"""
        feed = MarketDataFeed(mock_tws_adapter, ['AAPL'])
        
        # Add bars to buffer
        bar1 = BarData('AAPL', datetime(2026, 1, 24, 10, 0), 150, 151, 149, 150.5, 1000)
        bar2 = BarData('AAPL', datetime(2026, 1, 24, 10, 5), 151, 152, 150, 151.5, 1000)
        bar3 = BarData('AAPL', datetime(2026, 1, 24, 10, 10), 152, 153, 151, 152.5, 1000)
        
        feed.buffers['AAPL'].append(bar1)
        feed.buffers['AAPL'].append(bar2)
        feed.buffers['AAPL'].append(bar3)
        
        latest = feed.get_latest_bar('AAPL')
        
        assert latest is not None
        assert latest.close == 152.5
        assert latest.timestamp == datetime(2026, 1, 24, 10, 10)
    
    def test_get_latest_bar_empty_buffer(self, mock_tws_adapter):
        """Test getting latest bar when buffer is empty"""
        feed = MarketDataFeed(mock_tws_adapter, ['AAPL'])
        
        latest = feed.get_latest_bar('AAPL')
        
        assert latest is None
    
    def test_buffer_max_size(self, mock_tws_adapter):
        """Test that buffer respects max size"""
        feed = MarketDataFeed(mock_tws_adapter, ['AAPL'], buffer_size=10)
        
        # Add 20 bars (more than buffer size)
        base_time = datetime(2026, 1, 24, 10, 0)
        for i in range(20):
            bar = BarData('AAPL', base_time + timedelta(minutes=i*5), 150+i, 151+i, 149+i, 150.5+i, 1000)
            feed.buffers['AAPL'].append(bar)
        
        # Buffer should only have last 10
        assert len(feed.buffers['AAPL']) == 10
        
        # First bar should be bar 10 (0-9 were dropped)
        first_bar = list(feed.buffers['AAPL'])[0]
        assert first_bar.open == 160.0  # 150 + 10
    
    def test_multiple_symbols_independent(self, mock_tws_adapter):
        """Test that multiple symbols maintain independent buffers"""
        feed = MarketDataFeed(mock_tws_adapter, ['AAPL', 'MSFT'])
        feed.start()
        
        # Get request IDs
        aapl_req_id = None
        msft_req_id = None
        for req_id, symbol in feed.req_id_to_symbol.items():
            if symbol == 'AAPL':
                aapl_req_id = req_id
            elif symbol == 'MSFT':
                msft_req_id = req_id
        
        base_timestamp = int(datetime(2026, 1, 24, 10, 0).timestamp())
        
        # Send 60 bars for AAPL
        for i in range(60):
            feed._on_realtime_bar(aapl_req_id, base_timestamp + i*5, 150.0, 150.5, 149.5, 150.2, 100, 150.1, 10)
        
        # Send 60 bars for MSFT
        for i in range(60):
            feed._on_realtime_bar(msft_req_id, base_timestamp + i*5, 300.0, 300.5, 299.5, 300.2, 200, 300.1, 10)
        
        # Check both have bars in buffers
        assert len(feed.buffers['AAPL']) == 1
        assert len(feed.buffers['MSFT']) == 1
        
        # Check values are correct for each
        aapl_bar = feed.buffers['AAPL'][0]
        msft_bar = feed.buffers['MSFT'][0]
        
        assert aapl_bar.open == 150.0
        assert msft_bar.open == 300.0
        assert aapl_bar.volume == 6000
        assert msft_bar.volume == 12000


# ==================== Thread Safety Tests ====================

class TestMarketDataFeedThreadSafety:
    """Test thread-safe operations"""
    
    def test_concurrent_subscriptions(self, mock_tws_adapter):
        """Test adding subscribers from multiple threads"""
        import threading
        
        feed = MarketDataFeed(mock_tws_adapter, ['AAPL'])
        callbacks = [Mock() for _ in range(10)]
        
        def add_subscriber(callback):
            feed.subscribe(callback)
        
        threads = []
        for callback in callbacks:
            t = threading.Thread(target=add_subscriber, args=(callback,))
            threads.append(t)
            t.start()
        
        for t in threads:
            t.join()
        
        # All subscribers should be added
        assert len(feed.subscribers) == 10
    
    def test_concurrent_bar_processing(self, mock_tws_adapter):
        """Test processing bars from multiple threads"""
        import threading
        
        feed = MarketDataFeed(mock_tws_adapter, ['AAPL', 'MSFT'])
        feed.start()
        
        aapl_req_id = None
        msft_req_id = None
        for req_id, symbol in feed.req_id_to_symbol.items():
            if symbol == 'AAPL':
                aapl_req_id = req_id
            elif symbol == 'MSFT':
                msft_req_id = req_id
        
        base_timestamp = int(datetime(2026, 1, 24, 10, 0).timestamp())
        
        def send_aapl_bars():
            for i in range(60):
                feed._on_realtime_bar(aapl_req_id, base_timestamp + i*5, 150, 151, 149, 150.5, 100, 150, 10)
        
        def send_msft_bars():
            for i in range(60):
                feed._on_realtime_bar(msft_req_id, base_timestamp + i*5, 300, 301, 299, 300.5, 100, 300, 10)
        
        t1 = threading.Thread(target=send_aapl_bars)
        t2 = threading.Thread(target=send_msft_bars)
        
        t1.start()
        t2.start()
        
        t1.join()
        t2.join()
        
        # Both should have bars
        assert len(feed.buffers['AAPL']) == 1
        assert len(feed.buffers['MSFT']) == 1


# Run tests
if __name__ == '__main__':
    pytest.main([__file__, '-v'])
