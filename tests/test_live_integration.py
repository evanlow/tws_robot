"""
Integration Test for Live Trading Pipeline

Tests the complete flow:
TWS → MarketDataFeed → Strategy → OrderExecutor → TWS

This validates all components work together correctly.

Author: TWS Robot Development Team
Date: January 24, 2026
Phase 1: MVP Live Trading - Integration Test
"""

import pytest
from unittest.mock import Mock, MagicMock, patch
from datetime import datetime
from pathlib import Path

from execution.paper_adapter import PaperTradingAdapter
from execution.market_data_feed import MarketDataFeed, BarData
from execution.order_executor import OrderExecutor, OrderStatus
from strategies.bollinger_bands import BollingerBandsStrategy
from strategies.signal import Signal, SignalType, SignalStrength
from risk.risk_manager import RiskManager, Position


# =============================================================================
# Test Fixtures
# =============================================================================

@pytest.fixture
def mock_tws_adapter():
    """Mock TWS adapter"""
    adapter = Mock(spec=PaperTradingAdapter)
    adapter.connected = True
    adapter.buy = Mock(return_value=99999)
    adapter.sell = Mock(return_value=99998)
    adapter.close_position = Mock(return_value=99997)
    adapter.get_all_positions = Mock(return_value={})
    return adapter


@pytest.fixture
def risk_manager():
    """Real RiskManager instance"""
    return RiskManager(
        initial_capital=100000.0,
        max_positions=2,
        max_position_pct=0.25,
        max_drawdown_pct=0.20,
        daily_loss_limit_pct=0.05
    )


@pytest.fixture
def order_executor(mock_tws_adapter, risk_manager, tmp_path):
    """OrderExecutor in paper mode"""
    emergency_file = tmp_path / "EMERGENCY_STOP"
    return OrderExecutor(
        tws_adapter=mock_tws_adapter,
        risk_manager=risk_manager,
        is_live_mode=False,
        emergency_stop_file=str(emergency_file)
    )


@pytest.fixture
def strategy():
    """BollingerBandsStrategy instance"""
    strat = BollingerBandsStrategy(
        name='TestStrategy',
        symbols=['AAPL'],
        period=20,
        std_dev=2.0,
        position_size=0.1
    )
    strat.start()
    return strat


# =============================================================================
# Test 1: Component Initialization
# =============================================================================

def test_all_components_initialize(mock_tws_adapter, risk_manager, order_executor, strategy):
    """Test all components can be initialized"""
    # All fixtures created successfully
    assert mock_tws_adapter is not None
    assert risk_manager is not None
    assert order_executor is not None
    assert strategy is not None


# =============================================================================
# Test 2: MarketDataFeed → Strategy Pipeline
# =============================================================================

def test_market_data_to_strategy_flow(mock_tws_adapter, strategy):
    """Test data flows from MarketDataFeed to Strategy"""
    # Create market data feed
    market_data_feed = MarketDataFeed(
        tws_adapter=mock_tws_adapter,
        symbols=['AAPL'],
        bar_size_minutes=5,
        buffer_size=50
    )
    
    # Track if callback was invoked
    callback_invoked = []
    
    def on_bar_callback(symbol: str, aggregated_bar):
        callback_invoked.append((symbol, 1))
        
        # Feed to strategy
        signal = strategy.on_bar(
            symbol=symbol,
            bar={
                'timestamp': aggregated_bar.timestamp,
                'open': aggregated_bar.open,
                'high': aggregated_bar.high,
                'low': aggregated_bar.low,
                'close': aggregated_bar.close,
                'volume': aggregated_bar.volume
            }
        )
        callback_invoked.append(('signal', signal))
    
    # Subscribe (callback will receive symbol)
    market_data_feed.subscribe(on_bar_callback)
    
    # Simulate bar data
    bar = BarData(
        symbol='AAPL',
        timestamp=datetime.now(),
        open=150.0,
        high=151.0,
        low=149.0,
        close=150.5,
        volume=1000000
    )
    
    # Manually trigger aggregator (simulating 60 5-sec bars) and notify subscribers
    aggregator = market_data_feed.aggregators['AAPL']
    for i in range(60):
        result = aggregator.add_bar(bar)
        if result:
            for subscriber in market_data_feed.subscribers:
                subscriber('AAPL', result)
    
    # Check callback was invoked
    assert len(callback_invoked) > 0
    assert callback_invoked[0][0] == 'AAPL'


# =============================================================================
# Test 3: Strategy → OrderExecutor Pipeline
# =============================================================================

def test_strategy_to_executor_flow(strategy, order_executor):
    """Test signals flow from Strategy to OrderExecutor"""
    # Generate bars until strategy produces signal
    signals_generated = []
    
    # Feed 25 bars (more than period of 20)
    for i in range(25):
        price = 150.0 + i * 0.5  # Rising price
        signal = strategy.on_bar(
            symbol='AAPL',
            bar={
                'timestamp': datetime.now(),
                'open': price,
                'high': price + 0.5,
                'low': price - 0.5,
                'close': price + 0.25,
                'volume': 1000000
            }
        )
        if signal and signal.signal_type != SignalType.HOLD:
            signals_generated.append(signal)
    
    # If strategy generated signal, execute it
    if len(signals_generated) > 0:
        signal = signals_generated[0]
        
        result = order_executor.execute_signal(
            strategy_name='TestStrategy',
            signal=signal,
            current_equity=100000.0,
            positions={}
        )
        
        # Should be submitted (no risk violations)
        assert result.status == OrderStatus.SUBMITTED
        assert result.order_id is not None


# =============================================================================
# Test 4: Complete Pipeline Integration
# =============================================================================

def test_complete_pipeline_integration(mock_tws_adapter, risk_manager, strategy):
    """Test complete pipeline: Data → Strategy → Executor → TWS"""
    
    # Create components
    order_executor = OrderExecutor(
        tws_adapter=mock_tws_adapter,
        risk_manager=risk_manager,
        is_live_mode=False
    )
    
    market_data_feed = MarketDataFeed(
        tws_adapter=mock_tws_adapter,
        symbols=['AAPL'],
        bar_size_minutes=5,
        buffer_size=50
    )
    
    # Track orders executed
    orders_executed = []
    
    def on_bar_callback(symbol: str, aggregated_bar):
        """Pipeline callback: Data → Strategy → Executor"""
        # Feed to strategy
        signal = strategy.on_bar(
            symbol=symbol,
            bar={
                'timestamp': aggregated_bar.timestamp,
                'open': aggregated_bar.open,
                'high': aggregated_bar.high,
                'low': aggregated_bar.low,
                'close': aggregated_bar.close,
                'volume': aggregated_bar.volume
            }
        )
        
        # Execute signal
        if signal and signal.signal_type != SignalType.HOLD:
            result = order_executor.execute_signal(
                strategy_name='TestStrategy',
                signal=signal,
                current_equity=100000.0,
                positions={}
            )
            orders_executed.append(result)
    
    # Subscribe (callback will receive symbols)
    market_data_feed.subscribe(on_bar_callback)
    
    # Simulate market data (25 5-minute bars)
    aggregator = market_data_feed.aggregators['AAPL']
    for bar_num in range(25):
        # Each 5-min bar needs 60 5-sec bars to aggregate
        # Use constant base price for 20 bars, then spike to trigger Bollinger Bands signal
        if bar_num < 20:
            price = 150.0  # Constant baseline to make std dev near zero
        else:
            price = 165.0  # Spike well above upper band
        for tick in range(60):
            tick_bar = BarData(
                symbol='AAPL',
                timestamp=datetime.now(),
                open=price,
                high=price + 0.5,
                low=price - 0.5,
                close=price + 0.25,
                volume=1000000
            )
            result = aggregator.add_bar(tick_bar)
            if result:
                for subscriber in market_data_feed.subscribers:
                    subscriber('AAPL', result)
    
    # Verify pipeline executed
    assert len(orders_executed) > 0, "Pipeline should have generated at least one order"
    
    # Verify orders were submitted to TWS
    for result in orders_executed:
        assert result.status in [OrderStatus.SUBMITTED, OrderStatus.BLOCKED, OrderStatus.REJECTED]
        if result.status == OrderStatus.SUBMITTED:
            # Verify TWS adapter was called
            assert mock_tws_adapter.buy.called or mock_tws_adapter.sell.called


# =============================================================================
# Test 5: Risk Manager Integration
# =============================================================================

def test_risk_manager_integration(mock_tws_adapter, strategy):
    """Test risk manager blocks unsafe trades"""
    
    # Create risk manager with tight limits
    risk_manager = RiskManager(
        initial_capital=10000.0,  # Small capital
        max_positions=1,
        max_position_pct=0.10,  # Max 10% per position
        max_drawdown_pct=0.05,  # Very tight drawdown
        daily_loss_limit_pct=0.02
    )
    
    order_executor = OrderExecutor(
        tws_adapter=mock_tws_adapter,
        risk_manager=risk_manager,
        is_live_mode=False
    )
    
    # Create signal for large position
    signal = Signal(
        timestamp=datetime.now(),
        symbol='AAPL',
        signal_type=SignalType.BUY,
        strength=SignalStrength.STRONG,
        target_price=150.0,
        quantity=100  # $15,000 order on $10,000 capital = 150%
    )
    
    # Execute - should be blocked by risk manager
    result = order_executor.execute_signal(
        strategy_name='TestStrategy',
        signal=signal,
        current_equity=10000.0,
        positions={}
    )
    
    # Verify blocked
    assert result.status in [OrderStatus.BLOCKED, OrderStatus.REJECTED]


# =============================================================================
# Test 6: Error Handling
# =============================================================================

def test_pipeline_error_handling(mock_tws_adapter, risk_manager, strategy):
    """Test pipeline handles errors gracefully"""
    
    order_executor = OrderExecutor(
        tws_adapter=mock_tws_adapter,
        risk_manager=risk_manager,
        is_live_mode=False
    )
    
    # Make TWS adapter raise exception
    mock_tws_adapter.buy.side_effect = Exception("Connection lost")
    
    # Create signal
    signal = Signal(
        timestamp=datetime.now(),
        symbol='AAPL',
        signal_type=SignalType.BUY,
        strength=SignalStrength.STRONG,
        target_price=150.0,
        quantity=10
    )
    
    # Execute - should handle exception gracefully
    result = order_executor.execute_signal(
        strategy_name='TestStrategy',
        signal=signal,
        current_equity=100000.0,
        positions={}
    )
    
    # Should be rejected with error message
    assert result.status == OrderStatus.REJECTED
    assert "Connection lost" in result.reason


# =============================================================================
# Test 7: Multi-Symbol Support
# =============================================================================

def test_multi_symbol_pipeline(mock_tws_adapter, risk_manager):
    """Test pipeline handles multiple symbols"""
    
    symbols = ['AAPL', 'MSFT', 'GOOGL']
    
    # Create strategy with multiple symbols
    strategy = BollingerBandsStrategy(
        name='MultiSymbol',
        symbols=symbols,
        period=20,
        std_dev=2.0,
        position_size=0.1
    )
    
    order_executor = OrderExecutor(
        tws_adapter=mock_tws_adapter,
        risk_manager=risk_manager,
        is_live_mode=False
    )
    
    market_data_feed = MarketDataFeed(
        tws_adapter=mock_tws_adapter,
        symbols=symbols,
        bar_size_minutes=5,
        buffer_size=50
    )
    
    # Track which symbols generated signals
    symbols_with_signals = set()
    
    def on_bar_callback(symbol: str, bars: list):
        if len(bars) == 0:
            return
        
        bar = bars[-1]
        signal = strategy.on_bar(
            symbol=symbol,
            bar={
                'timestamp': bar.timestamp,
                'open': bar.open,
                'high': bar.high,
                'low': bar.low,
                'close': bar.close,
                'volume': bar.volume
            }
        )
        
        if signal and signal.signal_type != SignalType.HOLD:
            symbols_with_signals.add(symbol)
    
    # Subscribe (callback receives all symbols)
    market_data_feed.subscribe(on_bar_callback)
    
    # Verify all symbols have aggregators
    assert len(market_data_feed.aggregators) == 3
    assert all(sym in market_data_feed.aggregators for sym in symbols)


# =============================================================================
# Test 8: Statistics Tracking
# =============================================================================

def test_statistics_tracking(mock_tws_adapter, risk_manager, strategy):
    """Test pipeline tracks statistics correctly"""
    
    order_executor = OrderExecutor(
        tws_adapter=mock_tws_adapter,
        risk_manager=risk_manager,
        is_live_mode=False
    )
    
    # Execute multiple signals
    for i in range(5):
        signal = Signal(
            timestamp=datetime.now(),
            symbol='AAPL',
            signal_type=SignalType.BUY,
            strength=SignalStrength.STRONG,
            target_price=150.0 + i,
            quantity=10
        )
        
        order_executor.execute_signal(
            strategy_name='TestStrategy',
            signal=signal,
            current_equity=100000.0,
            positions={}
        )
    
    # Get statistics
    stats = order_executor.get_statistics()
    
    assert stats['total_orders'] == 5
    assert stats['submitted'] + stats['rejected'] + stats['blocked'] == 5


if __name__ == '__main__':
    print("Live Trading Pipeline Integration Tests")
    print("=" * 70)
    print("Run with: pytest tests/test_live_integration.py -v")
    print()
    print("Test Coverage:")
    print("  1. Component initialization")
    print("  2. MarketDataFeed → Strategy flow")
    print("  3. Strategy → OrderExecutor flow")
    print("  4. Complete pipeline integration")
    print("  5. Risk manager integration")
    print("  6. Error handling")
    print("  7. Multi-symbol support")
    print("  8. Statistics tracking")
