"""
Unit tests for strategy framework components.

Tests Signal, StrategyConfig, StrategyState, and BaseStrategy.
"""

import pytest
from datetime import datetime, timedelta
from decimal import Decimal

from core.event_bus import Event, EventType
from strategies.signal import Signal, SignalType, SignalStrength
from strategies.base_strategy import (
    BaseStrategy, StrategyState, StrategyConfig
)


# Test Signal class

def test_signal_creation():
    """Test creating a basic signal"""
    signal = Signal(
        symbol="AAPL",
        signal_type=SignalType.BUY,
        strength=SignalStrength.STRONG,
        timestamp=datetime.now()
    )
    
    assert signal.symbol == "AAPL"
    assert signal.signal_type == SignalType.BUY
    assert signal.strength == SignalStrength.STRONG
    assert signal.confidence == 0.0


def test_signal_with_prices():
    """Test signal with price levels"""
    signal = Signal(
        symbol="AAPL",
        signal_type=SignalType.BUY,
        strength=SignalStrength.STRONG,
        timestamp=datetime.now(),
        target_price=150.0,
        stop_loss=145.0,
        take_profit=160.0,
        quantity=100
    )
    
    assert signal.target_price == 150.0
    assert signal.stop_loss == 145.0
    assert signal.take_profit == 160.0
    assert signal.quantity == 100


def test_signal_serialization():
    """Test signal to_dict and from_dict"""
    timestamp = datetime.now()
    signal = Signal(
        symbol="AAPL",
        signal_type=SignalType.BUY,
        strength=SignalStrength.STRONG,
        timestamp=timestamp,
        target_price=150.0,
        reason="Test signal",
        confidence=0.85
    )
    
    # Convert to dict
    signal_dict = signal.to_dict()
    assert signal_dict['symbol'] == "AAPL"
    assert signal_dict['signal_type'] == "BUY"
    assert signal_dict['confidence'] == 0.85
    
    # Convert back to Signal
    signal2 = Signal.from_dict(signal_dict)
    assert signal2.symbol == signal.symbol
    assert signal2.signal_type == signal.signal_type
    assert signal2.confidence == signal.confidence


def test_signal_is_entry():
    """Test is_entry_signal method"""
    buy_signal = Signal(
        symbol="AAPL",
        signal_type=SignalType.BUY,
        strength=SignalStrength.STRONG,
        timestamp=datetime.now()
    )
    
    sell_signal = Signal(
        symbol="AAPL",
        signal_type=SignalType.SELL,
        strength=SignalStrength.STRONG,
        timestamp=datetime.now()
    )
    
    close_signal = Signal(
        symbol="AAPL",
        signal_type=SignalType.CLOSE,
        strength=SignalStrength.STRONG,
        timestamp=datetime.now()
    )
    
    assert buy_signal.is_entry_signal() is True
    assert sell_signal.is_entry_signal() is True
    assert close_signal.is_entry_signal() is False


def test_signal_is_exit():
    """Test is_exit_signal method"""
    close_signal = Signal(
        symbol="AAPL",
        signal_type=SignalType.CLOSE,
        strength=SignalStrength.STRONG,
        timestamp=datetime.now()
    )
    
    buy_signal = Signal(
        symbol="AAPL",
        signal_type=SignalType.BUY,
        strength=SignalStrength.STRONG,
        timestamp=datetime.now()
    )
    
    assert close_signal.is_exit_signal() is True
    assert buy_signal.is_exit_signal() is False


def test_signal_validation():
    """Test signal validation"""
    # Valid signal
    valid_signal = Signal(
        symbol="AAPL",
        signal_type=SignalType.BUY,
        strength=SignalStrength.STRONG,
        timestamp=datetime.now(),
        target_price=150.0,
        stop_loss=145.0,
        take_profit=160.0,
        confidence=0.85
    )
    assert valid_signal.validate() is True
    
    # Invalid confidence
    invalid_confidence = Signal(
        symbol="AAPL",
        signal_type=SignalType.BUY,
        strength=SignalStrength.STRONG,
        timestamp=datetime.now(),
        confidence=1.5  # Invalid
    )
    assert invalid_confidence.validate() is False
    
    # Invalid BUY signal (stop loss above target)
    invalid_buy = Signal(
        symbol="AAPL",
        signal_type=SignalType.BUY,
        strength=SignalStrength.STRONG,
        timestamp=datetime.now(),
        target_price=150.0,
        stop_loss=155.0  # Should be below target
    )
    assert invalid_buy.validate() is False
    
    # Invalid SELL signal (stop loss below target)
    invalid_sell = Signal(
        symbol="AAPL",
        signal_type=SignalType.SELL,
        strength=SignalStrength.STRONG,
        timestamp=datetime.now(),
        target_price=150.0,
        stop_loss=145.0  # Should be above target
    )
    assert invalid_sell.validate() is False


def test_signal_str_repr():
    """Test signal string representations"""
    signal = Signal(
        symbol="AAPL",
        signal_type=SignalType.BUY,
        strength=SignalStrength.STRONG,
        timestamp=datetime.now(),
        target_price=150.0,
        reason="Test reason",
        confidence=0.85
    )
    
    str_repr = str(signal)
    assert "AAPL" in str_repr
    assert "BUY" in str_repr
    assert "150.00" in str_repr
    
    repr_repr = repr(signal)
    assert "AAPL" in repr_repr
    assert "BUY" in repr_repr
    assert "0.85" in repr_repr


# Test StrategyConfig class

def test_strategy_config_creation():
    """Test creating strategy configuration"""
    config = StrategyConfig(
        name="TestStrategy",
        symbols=["AAPL", "MSFT"],
        enabled=True,
        parameters={"period": 20},
        risk_limits={"max_position_size": 1000}
    )
    
    assert config.name == "TestStrategy"
    assert config.symbols == ["AAPL", "MSFT"]
    assert config.enabled is True
    assert config.parameters["period"] == 20


def test_strategy_config_validation():
    """Test strategy configuration validation"""
    # Valid config
    valid_config = StrategyConfig(
        name="TestStrategy",
        symbols=["AAPL"],
        risk_limits={
            "max_position_size": 1000,
            "max_daily_loss": 500.0
        }
    )
    assert valid_config.validate() is True
    
    # Invalid - no name
    invalid_no_name = StrategyConfig(
        name="",
        symbols=["AAPL"]
    )
    assert invalid_no_name.validate() is False
    
    # Invalid - no symbols
    invalid_no_symbols = StrategyConfig(
        name="TestStrategy",
        symbols=[]
    )
    assert invalid_no_symbols.validate() is False
    
    # Invalid - negative position size
    invalid_position_size = StrategyConfig(
        name="TestStrategy",
        symbols=["AAPL"],
        risk_limits={"max_position_size": -100}
    )
    assert invalid_position_size.validate() is False


# Test BaseStrategy class

class MockStrategy(BaseStrategy):
    """Mock strategy for testing"""
    
    def __init__(self, config, event_bus=None):
        super().__init__(config, event_bus)
        self.bars_processed = 0
        self.validation_calls = 0
    
    def on_bar(self, symbol: str, bar_data: dict):
        """Process bar data"""
        self.bars_processed += 1
        
        # Generate a test signal
        if self.bars_processed == 1:
            signal = Signal(
                symbol=symbol,
                signal_type=SignalType.BUY,
                strength=SignalStrength.STRONG,
                timestamp=datetime.now(),
                confidence=0.8
            )
            self.generate_signal(signal)
    
    def validate_signal(self, signal: Signal) -> bool:
        """Validate signal"""
        self.validation_calls += 1
        return signal.validate()


def test_strategy_initialization():
    """Test strategy initialization"""
    config = StrategyConfig(
        name="TestStrategy",
        symbols=["AAPL"]
    )
    
    strategy = MockStrategy(config)
    
    assert strategy.config.name == "TestStrategy"
    assert strategy.state == StrategyState.READY
    assert strategy.signals_generated == 0


def test_strategy_lifecycle():
    """Test strategy lifecycle transitions"""
    config = StrategyConfig(
        name="TestStrategy",
        symbols=["AAPL"]
    )
    strategy = MockStrategy(config)
    
    # Initial state
    assert strategy.state == StrategyState.READY
    
    # Start
    strategy.start()
    assert strategy.state == StrategyState.RUNNING
    assert strategy.start_time is not None
    
    # Pause
    strategy.pause()
    assert strategy.state == StrategyState.PAUSED
    
    # Resume
    strategy.resume()
    assert strategy.state == StrategyState.RUNNING
    
    # Stop
    strategy.stop()
    assert strategy.state == StrategyState.STOPPED
    assert strategy.stop_time is not None


def test_strategy_invalid_transitions():
    """Test invalid state transitions"""
    config = StrategyConfig(
        name="TestStrategy",
        symbols=["AAPL"]
    )
    strategy = MockStrategy(config)
    
    # Can't pause from READY
    strategy.pause()
    assert strategy.state == StrategyState.READY
    
    # Can't resume from READY
    strategy.resume()
    assert strategy.state == StrategyState.READY
    
    # Stop, then can't start
    strategy.stop()
    strategy.start()
    assert strategy.state == StrategyState.STOPPED


def test_strategy_signal_generation():
    """Test signal generation and validation"""
    config = StrategyConfig(
        name="TestStrategy",
        symbols=["AAPL"]
    )
    strategy = MockStrategy(config)
    strategy.start()
    
    # Generate valid signal
    signal = Signal(
        symbol="AAPL",
        signal_type=SignalType.BUY,
        strength=SignalStrength.STRONG,
        timestamp=datetime.now(),
        target_price=150.0,
        stop_loss=145.0,
        confidence=0.85
    )
    
    strategy.generate_signal(signal)
    
    assert strategy.signals_generated == 1
    assert strategy.signals_accepted == 1
    assert strategy.signals_rejected == 0
    assert strategy.validation_calls == 1


def test_strategy_signal_rejection():
    """Test signal rejection"""
    config = StrategyConfig(
        name="TestStrategy",
        symbols=["AAPL"]
    )
    strategy = MockStrategy(config)
    strategy.start()
    
    # Generate invalid signal (confidence > 1.0)
    invalid_signal = Signal(
        symbol="AAPL",
        signal_type=SignalType.BUY,
        strength=SignalStrength.STRONG,
        timestamp=datetime.now(),
        confidence=1.5  # Invalid
    )
    
    strategy.generate_signal(invalid_signal)
    
    assert strategy.signals_generated == 1
    assert strategy.signals_accepted == 0
    assert strategy.signals_rejected == 1


def test_strategy_position_tracking():
    """Test position tracking"""
    config = StrategyConfig(
        name="TestStrategy",
        symbols=["AAPL"]
    )
    strategy = MockStrategy(config)
    
    # No position initially
    assert strategy.has_position("AAPL") is False
    assert strategy.get_position("AAPL") is None
    
    # Update position
    position_data = {
        'symbol': 'AAPL',
        'quantity': 100,
        'avg_price': 150.0,
        'market_value': 15000.0,
        'unrealized_pnl': 100.0
    }
    strategy._update_position(position_data)
    
    # Check position
    assert strategy.has_position("AAPL") is True
    position = strategy.get_position("AAPL")
    assert position is not None
    assert position['quantity'] == 100
    assert position['avg_price'] == 150.0


def test_strategy_performance_summary():
    """Test performance summary"""
    config = StrategyConfig(
        name="TestStrategy",
        symbols=["AAPL"]
    )
    strategy = MockStrategy(config)
    strategy.start()
    
    # Generate some signals
    for i in range(5):
        signal = Signal(
            symbol="AAPL",
            signal_type=SignalType.BUY,
            strength=SignalStrength.STRONG,
            timestamp=datetime.now(),
            confidence=0.8
        )
        strategy.generate_signal(signal)
    
    summary = strategy.get_performance_summary()
    
    assert summary['strategy_name'] == "TestStrategy"
    assert summary['state'] == StrategyState.RUNNING.value
    assert summary['signals_generated'] == 5
    assert summary['signals_accepted'] == 5
    assert summary['acceptance_rate'] == 1.0
    assert summary['uptime_seconds'] is not None


def test_strategy_config_reload():
    """Test configuration hot-reload"""
    config = StrategyConfig(
        name="TestStrategy",
        symbols=["AAPL"],
        parameters={"period": 20}
    )
    strategy = MockStrategy(config)
    
    # Reload with new config
    new_config = StrategyConfig(
        name="TestStrategy",
        symbols=["AAPL", "MSFT"],
        parameters={"period": 30}
    )
    strategy.reload_config(new_config)
    
    assert strategy.config.symbols == ["AAPL", "MSFT"]
    assert strategy.config.parameters["period"] == 30


def test_strategy_str_repr():
    """Test strategy string representations"""
    config = StrategyConfig(
        name="TestStrategy",
        symbols=["AAPL"]
    )
    strategy = MockStrategy(config)
    
    str_repr = str(strategy)
    assert "TestStrategy" in str_repr
    assert "READY" in str_repr
    
    repr_repr = repr(strategy)
    assert "TestStrategy" in repr_repr
    assert "AAPL" in repr_repr


# Test event handling (requires mock event bus)

class MockEventBus:
    """Mock event bus for testing"""
    
    def __init__(self):
        self.subscriptions = {}
        self.published_events = []
    
    def subscribe(self, event_type, callback):
        """Subscribe to event"""
        if event_type not in self.subscriptions:
            self.subscriptions[event_type] = []
        self.subscriptions[event_type].append(callback)
    
    def publish(self, event):
        """Publish event"""
        self.published_events.append(event)
        
        # Call subscribers
        if event.event_type in self.subscriptions:
            for callback in self.subscriptions[event.event_type]:
                callback(event.data)


def test_strategy_event_subscription():
    """Test strategy subscribes to events"""
    event_bus = MockEventBus()
    config = StrategyConfig(
        name="TestStrategy",
        symbols=["AAPL"]
    )
    strategy = MockStrategy(config, event_bus)
    
    # Check subscriptions
    assert EventType.MARKET_DATA_RECEIVED in event_bus.subscriptions
    assert EventType.ORDER_FILLED in event_bus.subscriptions
    assert EventType.POSITION_UPDATED in event_bus.subscriptions


def test_strategy_market_data_handling():
    """Test strategy processes market data"""
    event_bus = MockEventBus()
    config = StrategyConfig(
        name="TestStrategy",
        symbols=["AAPL"]
    )
    strategy = MockStrategy(config, event_bus)
    strategy.start()
    
    # Send market data event
    market_data = {
        'symbol': 'AAPL',
        'timestamp': datetime.now(),
        'open': 150.0,
        'high': 152.0,
        'low': 149.0,
        'close': 151.0,
        'volume': 1000000
    }
    
    event_bus.publish(Event(EventType.MARKET_DATA_RECEIVED, data=market_data))
    
    # Check strategy processed it
    assert strategy.bars_processed == 1


def test_strategy_signal_publishing():
    """Test strategy publishes signals to event bus"""
    event_bus = MockEventBus()
    config = StrategyConfig(
        name="TestStrategy",
        symbols=["AAPL"]
    )
    strategy = MockStrategy(config, event_bus)
    strategy.start()
    
    # Generate signal
    signal = Signal(
        symbol="AAPL",
        signal_type=SignalType.BUY,
        strength=SignalStrength.STRONG,
        timestamp=datetime.now(),
        confidence=0.8
    )
    strategy.generate_signal(signal)
    
    # Check event was published
    signal_events = [e for e in event_bus.published_events 
                    if e.event_type == EventType.SIGNAL_GENERATED]
    assert len(signal_events) == 1
    assert signal_events[0].data['symbol'] == "AAPL"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
