"""
Unit tests for multi-strategy orchestration system.

Tests StrategyOrchestrator, signal aggregation, conflict resolution,
and portfolio-level risk coordination.
"""

import pytest
from datetime import datetime, timedelta
from typing import Dict, List
from decimal import Decimal

from strategies.strategy_orchestrator import (
    StrategyOrchestrator, 
    SignalAggregator,
    ConflictResolver,
    AllocationManager
)
from strategies.base_strategy import BaseStrategy as Strategy, StrategyConfig
from strategies.signal import Signal, SignalType, SignalStrength


# Helper Functions

def create_signal(symbol: str, signal_type: SignalType, quantity: int, price: float, 
                  confidence: float, strategy_name: str) -> Signal:
    """Helper to create test signals with required fields"""
    return Signal(
        symbol=symbol,
        signal_type=signal_type,
        strength=SignalStrength.STRONG if confidence > 0.7 else SignalStrength.MODERATE,
        timestamp=datetime.now(),
        quantity=quantity,
        target_price=price,
        confidence=confidence,
        strategy_name=strategy_name
    )


# Fixtures

@pytest.fixture
def orchestrator():
    """Create strategy orchestrator"""
    return StrategyOrchestrator(
        total_capital=100000.0,
        portfolio_heat_limit=0.5,
        max_concentration=0.2
    )


class MockStrategy(Strategy):
    """Mock strategy for testing"""
    def on_bar(self, symbol: str, bar_data: dict):
        pass
    
    def validate_signal(self, signal: Signal) -> bool:
        return signal.validate()


@pytest.fixture
def sample_strategies():
    """Create sample strategies for testing"""
    strategies = []
    
    # Strategy 1: MA Cross
    config1 = StrategyConfig(
        name="MA_Cross",
        symbols=["AAPL", "MSFT"],
        parameters={'fast': 10, 'slow': 20}
    )
    strategy1 = MockStrategy(config1)
    strategies.append(strategy1)
    
    # Strategy 2: Mean Reversion
    config2 = StrategyConfig(
        name="Mean_Reversion",
        symbols=["AAPL", "GOOGL"],
        parameters={'period': 20, 'std_dev': 2.0}
    )
    strategy2 = MockStrategy(config2)
    strategies.append(strategy2)
    
    # Strategy 3: Momentum
    config3 = StrategyConfig(
        name="Momentum",
        symbols=["TSLA", "NVDA"],
        parameters={'lookback': 14}
    )
    strategy3 = MockStrategy(config3)
    strategies.append(strategy3)
    
    return strategies


@pytest.fixture
def sample_signals():
    """Create sample signals for testing"""
    now = datetime.now()
    return [
        Signal(
            symbol="AAPL",
            signal_type=SignalType.BUY,
            strength=SignalStrength.STRONG,
            timestamp=now,
            quantity=100,
            target_price=150.0,
            confidence=0.8,
            strategy_name="MA_Cross"
        ),
        Signal(
            symbol="MSFT",
            signal_type=SignalType.BUY,
            strength=SignalStrength.MODERATE,
            timestamp=now,
            quantity=50,
            target_price=300.0,
            confidence=0.7,
            strategy_name="MA_Cross"
        ),
        Signal(
            symbol="AAPL",
            signal_type=SignalType.BUY,
            strength=SignalStrength.MODERATE,
            timestamp=now,
            quantity=75,
            target_price=150.0,
            confidence=0.6,
            strategy_name="Mean_Reversion"
        )
    ]


# Test StrategyOrchestrator Initialization

def test_orchestrator_initialization():
    """Test orchestrator initialization"""
    orch = StrategyOrchestrator(
        total_capital=100000.0,
        portfolio_heat_limit=0.5,
        max_concentration=0.2
    )
    
    assert orch.total_capital == 100000.0
    assert orch.portfolio_heat_limit == 0.5
    assert orch.max_concentration == 0.2
    assert len(orch.active_strategies) == 0
    assert orch.is_running is False


def test_orchestrator_default_parameters():
    """Test orchestrator with default parameters"""
    orch = StrategyOrchestrator()
    
    assert orch.total_capital == 100000.0  # Default
    assert orch.portfolio_heat_limit == 0.5
    assert orch.max_concentration == 0.3


# Test Strategy Registration

def test_register_single_strategy(orchestrator, sample_strategies):
    """Test registering single strategy"""
    strategy = sample_strategies[0]
    
    orchestrator.register_strategy(strategy, allocation=0.33)
    
    assert len(orchestrator.active_strategies) == 1
    assert strategy.config.name in orchestrator.active_strategies
    assert orchestrator.get_strategy_allocation(strategy.config.name) == 0.33


def test_register_multiple_strategies(orchestrator, sample_strategies):
    """Test registering multiple strategies"""
    orchestrator.register_strategy(sample_strategies[0], allocation=0.33)
    orchestrator.register_strategy(sample_strategies[1], allocation=0.33)
    orchestrator.register_strategy(sample_strategies[2], allocation=0.34)
    
    assert len(orchestrator.active_strategies) == 3
    
    # Total allocation should equal 1.0
    total_allocation = sum(orchestrator.get_strategy_allocation(s.config.name) 
                          for s in sample_strategies)
    assert abs(total_allocation - 1.0) < 0.01


def test_register_duplicate_strategy(orchestrator, sample_strategies):
    """Test registering duplicate strategy raises error"""
    strategy = sample_strategies[0]
    
    orchestrator.register_strategy(strategy, allocation=0.5)
    
    with pytest.raises(ValueError, match="already registered"):
        orchestrator.register_strategy(strategy, allocation=0.5)


def test_register_strategy_invalid_allocation(orchestrator, sample_strategies):
    """Test registering strategy with invalid allocation"""
    strategy = sample_strategies[0]
    
    # Allocation > 1.0
    with pytest.raises(ValueError, match="allocation"):
        orchestrator.register_strategy(strategy, allocation=1.5)
    
    # Negative allocation
    with pytest.raises(ValueError, match="allocation"):
        orchestrator.register_strategy(strategy, allocation=-0.1)


def test_register_strategy_exceeds_total_allocation(orchestrator, sample_strategies):
    """Test registering strategies that exceed 100% allocation"""
    orchestrator.register_strategy(sample_strategies[0], allocation=0.6)
    orchestrator.register_strategy(sample_strategies[1], allocation=0.3)
    
    # Third strategy would exceed 100%
    with pytest.raises(ValueError, match="Total allocation exceeds"):
        orchestrator.register_strategy(sample_strategies[2], allocation=0.2)


# Test Strategy Unregistration

def test_unregister_strategy(orchestrator, sample_strategies):
    """Test unregistering strategy"""
    strategy = sample_strategies[0]
    orchestrator.register_strategy(strategy, allocation=0.5)
    
    assert len(orchestrator.active_strategies) == 1
    
    orchestrator.unregister_strategy(strategy.config.name)
    
    assert len(orchestrator.active_strategies) == 0


def test_unregister_nonexistent_strategy(orchestrator):
    """Test unregistering non-existent strategy"""
    with pytest.raises(ValueError, match="not found"):
        orchestrator.unregister_strategy("NonExistent")


def test_unregister_frees_allocation(orchestrator, sample_strategies):
    """Test unregistering strategy frees allocation"""
    orchestrator.register_strategy(sample_strategies[0], allocation=0.5)
    orchestrator.register_strategy(sample_strategies[1], allocation=0.5)
    
    # Unregister one strategy
    orchestrator.unregister_strategy(sample_strategies[0].config.name)
    
    # Should be able to register another with 0.5 allocation
    orchestrator.register_strategy(sample_strategies[2], allocation=0.5)
    assert len(orchestrator.active_strategies) == 2


# Test Market Data Distribution

def test_distribute_market_data_to_all_strategies(orchestrator, sample_strategies):
    """Test market data is distributed to all strategies"""
    for strategy in sample_strategies:
        orchestrator.register_strategy(strategy, allocation=0.33)
    
    orchestrator.start()  # Must start orchestrator for distribution
    
    market_data = {
        'symbol': 'AAPL',
        'price': 150.0,
        'timestamp': datetime.now()
    }
    
    # Track which strategies received data
    received = orchestrator.distribute_market_data(market_data)
    
    # AAPL is only in MA_Cross and Mean_Reversion (not Momentum which has TSLA/NVDA)
    assert len(received) == 2
    assert 'MA_Cross' in received
    assert 'Mean_Reversion' in received


def test_distribute_market_data_only_to_subscribed(orchestrator, sample_strategies):
    """Test market data only sent to strategies subscribing to symbol"""
    for strategy in sample_strategies:
        orchestrator.register_strategy(strategy, allocation=0.33)
    
    orchestrator.start()  # Must start orchestrator for distribution
    
    # TSLA only subscribed by Momentum strategy
    market_data = {
        'symbol': 'TSLA',
        'price': 200.0,
        'timestamp': datetime.now()
    }
    
    received = orchestrator.distribute_market_data(market_data)
    
    # Only Momentum strategy should receive it
    assert len(received) == 1
    assert received[0] == "Momentum"


def test_distribute_market_data_when_stopped(orchestrator, sample_strategies):
    """Test market data distribution when orchestrator stopped"""
    strategy = sample_strategies[0]
    orchestrator.register_strategy(strategy, allocation=1.0)
    
    # Stop orchestrator
    orchestrator.stop()
    
    market_data = {'symbol': 'AAPL', 'price': 150.0, 'timestamp': datetime.now()}
    
    # Should not distribute when stopped
    received = orchestrator.distribute_market_data(market_data)
    assert len(received) == 0


# Test Signal Processing

def test_process_single_signal(orchestrator, sample_strategies):
    """Test processing single signal from strategy"""
    strategy = sample_strategies[0]
    orchestrator.register_strategy(strategy, allocation=1.0)
    orchestrator.start()
    
    signal = create_signal(
        symbol="AAPL",
        signal_type=SignalType.BUY,
        quantity=100,
        price=150.0,
        confidence=0.8,
        strategy_name=strategy.config.name
    )
    
    result = orchestrator.process_signal(strategy.config.name, signal)
    
    assert result['accepted'] is True
    assert result['signal'] == signal


def test_process_signal_from_unregistered_strategy(orchestrator):
    """Test processing signal from unregistered strategy raises error"""
    signal = create_signal(
        symbol="AAPL",
        signal_type=SignalType.BUY,
        quantity=100,
        price=150.0,
        confidence=0.8,
        strategy_name="Unknown"
    )
    
    with pytest.raises(ValueError, match="not registered"):
        orchestrator.process_signal("Unknown", signal)


def test_process_signal_exceeds_allocation(orchestrator, sample_strategies):
    """Test signal rejected when exceeds strategy allocation"""
    strategy = sample_strategies[0]
    orchestrator.register_strategy(strategy, allocation=0.1)  # 10% = $10k
    orchestrator.start()
    
    # Signal worth $50k (exceeds $10k allocation)
    signal = create_signal(
        symbol="AAPL",
        signal_type=SignalType.BUY,
        quantity=333,
        price=150.0,
        confidence=0.8,
        strategy_name=strategy.config.name
    )
    
    result = orchestrator.process_signal(strategy.config.name, signal)
    
    assert result['accepted'] is False
    assert 'allocation' in result['reason'].lower()


# Test Signal Aggregation

def test_aggregate_signals_same_direction(orchestrator):
    """Test aggregating signals in same direction"""
    signal1 = create_signal(
        symbol="AAPL",
        signal_type=SignalType.BUY,
        quantity=100,
        price=150.0,
        confidence=0.8,
        strategy_name="Strategy1"
    )
    
    signal2 = create_signal(
        symbol="AAPL",
        signal_type=SignalType.BUY,
        quantity=50,
        price=150.0,
        confidence=0.6,
        strategy_name="Strategy2"
    )
    
    aggregator = SignalAggregator()
    result = aggregator.aggregate([signal1, signal2])
    
    # Should combine quantities (weighted by confidence)
    assert result.symbol == "AAPL"
    assert result.signal_type == SignalType.BUY
    # Weighted: 100*0.8 + 50*0.6 = 80 + 30 = 110
    assert result.quantity == 110
    assert result.confidence > 0  # Weighted average


def test_aggregate_signals_opposite_direction(orchestrator):
    """Test aggregating signals in opposite directions"""
    signal1 = create_signal(
        symbol="AAPL",
        signal_type=SignalType.BUY,
        quantity=100,
        price=150.0,
        confidence=0.8,
        strategy_name="Strategy1"
    )
    
    signal2 = create_signal(
        symbol="AAPL",
        signal_type=SignalType.SELL,
        quantity=50,
        price=150.0,
        confidence=0.6,
        strategy_name="Strategy2"
    )
    
    aggregator = SignalAggregator()
    result = aggregator.aggregate([signal1, signal2])
    
    # Higher confidence signal wins, net quantity
    assert result.symbol == "AAPL"
    assert result.signal_type == SignalType.BUY  # Stronger signal
    assert result.quantity == 50  # Net: 100 - 50


def test_aggregate_signals_complete_offset(orchestrator):
    """Test aggregating signals that completely offset"""
    signal1 = create_signal(
        symbol="AAPL",
        signal_type=SignalType.BUY,
        quantity=100,
        price=150.0,
        confidence=0.7,
        strategy_name="Strategy1"
    )
    
    signal2 = create_signal(
        symbol="AAPL",
        signal_type=SignalType.SELL,
        quantity=100,
        price=150.0,
        confidence=0.7,
        strategy_name="Strategy2"
    )
    
    aggregator = SignalAggregator()
    result = aggregator.aggregate([signal1, signal2])
    
    # Should result in no signal
    assert result is None or result.quantity == 0


# Test Conflict Resolution

def test_resolve_conflict_priority_based(orchestrator):
    """Test conflict resolution using priority (confidence)"""
    signal1 = create_signal(
        symbol="AAPL",
        signal_type=SignalType.BUY,
        quantity=100,
        price=150.0,
        confidence=0.9,
        strategy_name="Strategy1"
    )
    
    signal2 = create_signal(
        symbol="AAPL",
        signal_type=SignalType.SELL,
        quantity=100,
        price=150.0,
        confidence=0.5,
        strategy_name="Strategy2"
    )
    
    resolver = ConflictResolver()
    result = resolver.resolve([signal1, signal2])
    
    # Higher confidence signal wins
    assert result.signal_type == SignalType.BUY
    assert result.strategy_name == "Strategy1"


def test_resolve_conflict_multiple_signals(orchestrator):
    """Test resolving conflicts with multiple signals"""
    signals = [
        create_signal("AAPL", SignalType.BUY, 100, 150.0, 0.8, "S1"),
        create_signal("AAPL", SignalType.SELL, 50, 150.0, 0.6, "S2"),
        create_signal("AAPL", SignalType.BUY, 75, 150.0, 0.7, "S3")
    ]
    
    resolver = ConflictResolver()
    result = resolver.resolve(signals)
    
    # Should aggregate BUY signals and offset with SELL
    assert result.signal_type == SignalType.BUY
    assert result.quantity > 0


# Test Portfolio Constraints

def test_portfolio_heat_limit_enforced(orchestrator, sample_strategies):
    """Test portfolio heat limit is enforced"""
    strategy = sample_strategies[0]
    orchestrator.register_strategy(strategy, allocation=1.0)
    orchestrator.start()
    
    # Large signal that would exceed heat limit
    large_signal = create_signal(
        symbol="AAPL",
        signal_type=SignalType.BUY,
        quantity=1000,
        price=150.0,
        confidence=0.8,
        strategy_name=strategy.config.name
    )
    
    result = orchestrator.process_signal(strategy.config.name, large_signal)
    
    # Should be rejected (allocation or heat limit)
    assert result['accepted'] is False
    assert 'allocation' in result['reason'].lower() or 'heat' in result['reason'].lower()


def test_concentration_limit_enforced(orchestrator, sample_strategies):
    """Test concentration limit is enforced"""
    strategy = sample_strategies[0]
    orchestrator.register_strategy(strategy, allocation=1.0)
    orchestrator.start()
    
    # Signal that would create excessive concentration
    signal = create_signal(
        symbol="AAPL",
        signal_type=SignalType.BUY,
        quantity=200,
        price=150.0,
        confidence=0.8,
        strategy_name=strategy.config.name
    )
    
    result = orchestrator.process_signal(strategy.config.name, signal)
    
    # Check if concentration constraint is considered
    constraints = orchestrator.check_portfolio_constraints(signal)
    assert 'concentration' in constraints['checks'].keys()


def test_multiple_strategies_same_symbol(orchestrator, sample_strategies):
    """Test multiple strategies targeting same symbol"""
    # MA_Cross and Mean_Reversion both trade AAPL
    orchestrator.register_strategy(sample_strategies[0], allocation=0.5)
    orchestrator.register_strategy(sample_strategies[1], allocation=0.5)
    orchestrator.start()
    
    signal1 = create_signal("AAPL", SignalType.BUY, 100, 150.0, 0.8, sample_strategies[0].config.name)
    signal2 = create_signal("AAPL", SignalType.BUY, 50, 150.0, 0.7, sample_strategies[1].config.name)
    
    result1 = orchestrator.process_signal(sample_strategies[0].config.name, signal1)
    result2 = orchestrator.process_signal(sample_strategies[1].config.name, signal2)
    
    # Both might be accepted, but total position should respect constraints
    total_position = orchestrator.get_position("AAPL")
    assert total_position <= orchestrator.total_capital * orchestrator.max_concentration


# Test Allocation Management

def test_rebalance_allocations(orchestrator, sample_strategies):
    """Test dynamic allocation rebalancing"""
    orchestrator.register_strategy(sample_strategies[0], allocation=0.33)
    orchestrator.register_strategy(sample_strategies[1], allocation=0.33)
    orchestrator.register_strategy(sample_strategies[2], allocation=0.34)
    
    # Rebalance allocations
    new_allocations = {
        sample_strategies[0].config.name: 0.5,
        sample_strategies[1].config.name: 0.3,
        sample_strategies[2].config.name: 0.2
    }
    
    orchestrator.rebalance_allocations(new_allocations)
    
    assert orchestrator.get_strategy_allocation(sample_strategies[0].config.name) == 0.5
    assert orchestrator.get_strategy_allocation(sample_strategies[1].config.name) == 0.3
    assert orchestrator.get_strategy_allocation(sample_strategies[2].config.name) == 0.2


def test_rebalance_allocations_invalid_total(orchestrator, sample_strategies):
    """Test rebalancing with invalid total allocation"""
    orchestrator.register_strategy(sample_strategies[0], allocation=0.5)
    orchestrator.register_strategy(sample_strategies[1], allocation=0.5)
    
    # Total allocation != 1.0
    invalid_allocations = {
        sample_strategies[0].config.name: 0.6,
        sample_strategies[1].config.name: 0.6
    }
    
    with pytest.raises(ValueError, match="must sum to 1.0"):
        orchestrator.rebalance_allocations(invalid_allocations)


def test_get_available_capital_per_strategy(orchestrator, sample_strategies):
    """Test getting available capital for each strategy"""
    orchestrator.register_strategy(sample_strategies[0], allocation=0.4)
    orchestrator.register_strategy(sample_strategies[1], allocation=0.6)
    
    capital0 = orchestrator.get_available_capital(sample_strategies[0].config.name)
    capital1 = orchestrator.get_available_capital(sample_strategies[1].config.name)
    
    assert capital0 == 40000.0  # 40% of 100k
    assert capital1 == 60000.0  # 60% of 100k


# Test Portfolio Status

def test_get_portfolio_status_empty(orchestrator):
    """Test portfolio status with no strategies"""
    status = orchestrator.get_portfolio_status()
    
    assert status['total_strategies'] == 0
    assert status['active_strategies'] == 0
    assert status['total_capital'] == 100000.0
    assert status['allocated_capital'] == 0.0


def test_get_portfolio_status_with_strategies(orchestrator, sample_strategies):
    """Test portfolio status with active strategies"""
    orchestrator.register_strategy(sample_strategies[0], allocation=0.33)
    orchestrator.register_strategy(sample_strategies[1], allocation=0.33)
    orchestrator.register_strategy(sample_strategies[2], allocation=0.34)
    
    status = orchestrator.get_portfolio_status()
    
    assert status['total_strategies'] == 3
    assert status['active_strategies'] == 3
    assert abs(status['allocated_capital'] - 100000.0) < 1.0


def test_get_strategy_status(orchestrator, sample_strategies):
    """Test getting individual strategy status"""
    strategy = sample_strategies[0]
    orchestrator.register_strategy(strategy, allocation=0.5)
    
    status = orchestrator.get_strategy_status(strategy.config.name)
    
    assert status['name'] == strategy.config.name
    assert status['allocation'] == 0.5
    assert status['available_capital'] == 50000.0
    assert 'signals_processed' in status
    assert 'signals_accepted' in status


# Test Orchestrator Lifecycle

def test_orchestrator_start_stop(orchestrator):
    """Test starting and stopping orchestrator"""
    assert orchestrator.is_running is False
    
    orchestrator.start()
    assert orchestrator.is_running is True
    
    orchestrator.stop()
    assert orchestrator.is_running is False


def test_orchestrator_cannot_register_while_running(orchestrator, sample_strategies):
    """Test cannot register strategies while running"""
    orchestrator.start()
    
    with pytest.raises(RuntimeError, match="Cannot register.*while running"):
        orchestrator.register_strategy(sample_strategies[0], allocation=1.0)
    
    orchestrator.stop()


def test_orchestrator_context_manager(sample_strategies):
    """Test using orchestrator as context manager"""
    with StrategyOrchestrator() as orch:
        assert orch.is_running is True
    
    assert orch.is_running is False


# Test Error Handling

def test_strategy_error_doesnt_crash_orchestrator(orchestrator, sample_strategies):
    """Test that strategy error doesn't crash orchestrator"""
    strategy = sample_strategies[0]
    orchestrator.register_strategy(strategy, allocation=1.0)
    orchestrator.start()
    
    # Simulate strategy error
    def faulty_process(data):
        raise ValueError("Strategy error")
    
    strategy.process_market_data = faulty_process
    
    market_data = {'symbol': 'AAPL', 'price': 150.0, 'timestamp': datetime.now()}
    
    # Should handle error gracefully
    try:
        orchestrator.distribute_market_data(market_data)
        assert True  # No exception propagated
    except ValueError:
        pytest.fail("Strategy error should not propagate to orchestrator")


def test_invalid_signal_rejected(orchestrator, sample_strategies):
    """Test invalid signal is rejected"""
    strategy = sample_strategies[0]
    orchestrator.register_strategy(strategy, allocation=1.0)
    orchestrator.start()
    
    # Invalid signal (negative quantity)
    invalid_signal = create_signal(
        symbol="AAPL",
        signal_type=SignalType.BUY,
        quantity=-100,
        price=150.0,
        confidence=0.8,
        strategy_name=strategy.config.name
    )
    
    result = orchestrator.process_signal(strategy.config.name, invalid_signal)
    
    assert result['accepted'] is False
    assert 'invalid' in result['reason'].lower()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
