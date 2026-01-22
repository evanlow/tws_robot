# Runbook: Adding a New Strategy

## Overview

This runbook walks through creating and deploying a new trading strategy in the TWS Robot system, from initial concept to live trading.

**Time Estimate:** 2-3 days (development) + 30 days (paper trading validation)

## Prerequisites

- ✅ Virtual environment activated
- ✅ All tests passing (`pytest`)
- ✅ Strategy concept backtested externally
- ✅ Understanding of risk management requirements

## Steps

### 1. Create Strategy Class

**Location:** `strategies/your_strategy_name.py`

**Template:**
```python
"""
YourStrategy - Brief description

Strategy logic:
- Entry condition: ...
- Exit condition: ...
- Risk management: ...
"""

from typing import List, Dict, Optional
from datetime import datetime

from strategies.base_strategy import BaseStrategy, StrategyConfig, StrategyState
from strategies.signal import Signal, SignalType, SignalStrength
from backtest.data_models import Bar


class YourStrategy(BaseStrategy):
    """
    Your strategy implementation.
    
    Parameters:
        period: Lookback period for calculations
        threshold: Entry/exit threshold
        ... (add your parameters)
    """
    
    def __init__(
        self,
        name: str,
        symbols: List[str],
        event_bus=None,
        # Your parameters
        period: int = 20,
        threshold: float = 0.02
    ):
        # Create config
        config = StrategyConfig(
            name=name,
            symbols=symbols,
            enabled=True,
            parameters={
                'period': period,
                'threshold': threshold
            }
        )
        
        super().__init__(config, event_bus)
        
        # Store parameters
        self.period = period
        self.threshold = threshold
        
        # Initialize data structures
        self.price_history: Dict[str, List[float]] = {s: [] for s in symbols}
        self.indicators: Dict[str, Dict[str, float]] = {}
    
    def on_bar(self, symbol: str, bar_data: dict):
        """
        Process new bar data.
        
        Args:
            symbol: Trading symbol
            bar_data: OHLCV data
        """
        # Only process if running
        if self.state != StrategyState.RUNNING:
            return
        
        # Update price history
        close_price = bar_data['close']
        self.price_history[symbol].append(close_price)
        
        # Keep only required history
        if len(self.price_history[symbol]) > self.period:
            self.price_history[symbol].pop(0)
        
        # Need enough data to calculate indicators
        if len(self.price_history[symbol]) < self.period:
            return
        
        # Calculate indicators
        self._calculate_indicators(symbol)
        
        # Check for signals
        self._check_signals(symbol, bar_data)
    
    def _calculate_indicators(self, symbol: str):
        """Calculate strategy indicators"""
        prices = self.price_history[symbol]
        
        # Example: Simple moving average
        sma = sum(prices) / len(prices)
        
        # Store indicators
        self.indicators[symbol] = {
            'sma': sma,
            'current_price': prices[-1]
        }
    
    def _check_signals(self, symbol: str, bar_data: dict):
        """Check for entry/exit signals"""
        if symbol not in self.indicators:
            return
        
        indicators = self.indicators[symbol]
        current_price = indicators['current_price']
        sma = indicators['sma']
        
        # Example entry logic: Price crosses above SMA
        if current_price > sma * (1 + self.threshold):
            if symbol not in self._positions:
                self._generate_buy_signal(symbol, current_price)
        
        # Example exit logic: Price crosses below SMA
        elif current_price < sma * (1 - self.threshold):
            if symbol in self._positions:
                self._generate_sell_signal(symbol, current_price)
    
    def _generate_buy_signal(self, symbol: str, current_price: float):
        """Generate buy signal"""
        # Calculate stop loss (example: 2% below entry)
        stop_loss = current_price * 0.98
        
        signal = Signal(
            symbol=symbol,
            signal_type=SignalType.BUY,
            strength=SignalStrength.STRONG,
            timestamp=datetime.now(),
            target_price=current_price,
            stop_loss=stop_loss,
            strategy_id=self.strategy_id
        )
        
        # Emit signal
        self.generate_signal(signal)
    
    def _generate_sell_signal(self, symbol: str, current_price: float):
        """Generate sell signal"""
        position = self._positions[symbol]
        
        signal = Signal(
            symbol=symbol,
            signal_type=SignalType.SELL,
            strength=SignalStrength.STRONG,
            timestamp=datetime.now(),
            target_price=current_price,
            quantity=position['quantity'],
            strategy_id=self.strategy_id
        )
        
        self.generate_signal(signal)
    
    def validate_signal(self, signal: Signal) -> bool:
        """
        Validate signal before submission.
        
        Args:
            signal: Signal to validate
            
        Returns:
            True if valid, False otherwise
        """
        # Check symbol matches strategy
        if signal.symbol not in self.config.symbols:
            return False
        
        # Check we have indicators
        if signal.symbol not in self.indicators:
            return False
        
        # Add custom validation logic
        
        return True
    
    def get_indicator_values(self, symbol: str) -> Dict[str, float]:
        """Get current indicator values for a symbol"""
        return self.indicators.get(symbol, {})
```

### 2. Write Unit Tests

**Location:** `tests/test_your_strategy.py`

**Template:**
```python
"""
Unit tests for YourStrategy
"""

import pytest
from datetime import datetime
from unittest.mock import Mock

from strategies.your_strategy_name import YourStrategy
from strategies.base_strategy import StrategyState
from strategies.signal import SignalType


class TestYourStrategy:
    
    def test_initialization(self):
        """Test strategy initialization"""
        strategy = YourStrategy(
            name="Test_Strategy",
            symbols=["AAPL"]
        )
        
        assert strategy.config.name == "Test_Strategy"
        assert strategy.state == StrategyState.READY
        assert strategy.period == 20  # Default
    
    def test_custom_parameters(self):
        """Test custom parameter initialization"""
        strategy = YourStrategy(
            name="Test",
            symbols=["AAPL"],
            period=30,
            threshold=0.03
        )
        
        assert strategy.period == 30
        assert strategy.threshold == 0.03
    
    def test_lifecycle(self):
        """Test strategy lifecycle"""
        strategy = YourStrategy(
            name="Test",
            symbols=["AAPL"]
        )
        
        # Start
        strategy.start()
        assert strategy.state == StrategyState.RUNNING
        
        # Pause
        strategy.pause()
        assert strategy.state == StrategyState.PAUSED
        
        # Resume
        strategy.resume()
        assert strategy.state == StrategyState.RUNNING
        
        # Stop
        strategy.stop()
        assert strategy.state == StrategyState.STOPPED
    
    def test_indicator_calculation(self):
        """Test indicator calculations"""
        strategy = YourStrategy(
            name="Test",
            symbols=["AAPL"],
            period=5
        )
        strategy.start()
        
        # Feed price data
        prices = [100, 102, 98, 101, 99]
        for price in prices:
            bar = {
                'close': price,
                'volume': 1000000,
                'timestamp': datetime.now()
            }
            strategy.on_bar("AAPL", bar)
        
        # Check indicators calculated
        indicators = strategy.get_indicator_values("AAPL")
        assert 'sma' in indicators
        assert indicators['sma'] == 100  # Average of prices
    
    def test_signal_generation(self):
        """Test signal generation"""
        event_bus = Mock()
        strategy = YourStrategy(
            name="Test",
            symbols=["AAPL"],
            period=3,
            threshold=0.05
        )
        strategy.event_bus = event_bus
        strategy.start()
        
        # Feed data to trigger signal
        # (Add your specific signal trigger logic)
        
        # Verify signal generated
        assert len(strategy.signals_to_emit) > 0


# Run tests
if __name__ == '__main__':
    pytest.main([__file__, '-v'])
```

### 3. Run Tests

```bash
# Run your strategy tests
pytest tests/test_your_strategy.py -v

# Run full test suite to ensure no regressions
pytest -v

# Check coverage
pytest tests/test_your_strategy.py --cov=strategies.your_strategy_name
```

**Success Criteria:**
- ✅ All tests pass
- ✅ No warnings
- ✅ Strategy test coverage > 90%
- ✅ Full suite still passes (no regressions)

### 4. Register Strategy in Registry

**Location:** Your main initialization code

```python
from strategies.strategy_registry import StrategyRegistry
from strategies.your_strategy_name import YourStrategy

# Create registry
registry = StrategyRegistry(event_bus)

# Register your strategy class
registry.register_strategy_class("YourStrategy", YourStrategy)

# Create instance
config = StrategyConfig(
    name="YourStrategy_AAPL",
    symbols=["AAPL"],
    enabled=True,
    parameters={
        'period': 20,
        'threshold': 0.02
    }
)

strategy = registry.create_strategy("YourStrategy", config)
```

### 5. Backtest Validation

```python
from backtest.engine import BacktestEngine
from backtest.data_manager import DataManager

# Load historical data
data_manager = DataManager()
historical_data = data_manager.load_data(
    symbols=["AAPL"],
    start_date="2024-01-01",
    end_date="2025-01-01"
)

# Run backtest
engine = BacktestEngine(
    initial_capital=100000,
    strategies=[strategy],
    data=historical_data
)

results = engine.run()

# Check results
print(f"Total Return: {results.total_return:.2%}")
print(f"Sharpe Ratio: {results.sharpe_ratio:.2f}")
print(f"Max Drawdown: {results.max_drawdown:.2%}")
print(f"Win Rate: {results.win_rate:.2%}")
print(f"Total Trades: {results.total_trades}")
```

**Success Criteria:**
- ✅ Sharpe Ratio > 1.5
- ✅ Max Drawdown < 15%
- ✅ Win Rate > 50%
- ✅ Total Trades > 30 (for validation)

### 6. Paper Trading Validation

```python
from execution.paper_adapter import PaperTradingAdapter

# Create paper trading adapter
paper_adapter = PaperTradingAdapter(
    event_bus=event_bus,
    initial_cash=100000
)

# Register strategy
registry.register_strategy_class("YourStrategy", YourStrategy)
strategy = registry.create_strategy("YourStrategy", config)

# Start paper trading
strategy.start()
registry.start_all()

# Monitor for 30 days
# Check daily performance, metrics, risk controls
```

**Requirements:**
- ⏱️ **Duration:** Minimum 30 days
- 📊 **Trades:** Minimum 30 trades
- 📈 **Performance:** Sharpe > 1.5, Drawdown < 15%, Win Rate > 50%
- ⚠️ **Monitoring:** Daily review of performance and risk metrics

### 7. Validation & Promotion

```python
from strategy.lifecycle import StrategyLifecycle, ValidationCriteria

lifecycle = StrategyLifecycle(event_bus)

# Get strategy metrics after 30 days
metrics = strategy.get_metrics()

# Validate
criteria = ValidationCriteria()
can_go_live = criteria.validate(metrics)

if can_go_live:
    print("✅ Strategy ready for live trading")
    print(criteria.get_validation_report(metrics))
    
    # Promote to live (requires manual approval)
    lifecycle.promote_to_live(strategy.strategy_id)
else:
    print("❌ Strategy not ready")
    print(criteria.get_validation_report(metrics))
```

### 8. Live Trading Deployment

```python
from execution.live_adapter import LiveTradingAdapter

# Create live adapter (requires TWS connection)
live_adapter = LiveTradingAdapter(
    event_bus=event_bus,
    tws_host="127.0.0.1",
    tws_port=7497
)

# Start strategy in live mode
strategy.transition_to_live()
strategy.start()

# Monitor closely for first week
# - Check fills vs. expected
# - Verify risk controls working
# - Monitor for unexpected behavior
```

## Checklist

### Development Phase
- [ ] Strategy class created
- [ ] Unit tests written (>90% coverage)
- [ ] All tests passing
- [ ] Strategy registered in registry
- [ ] Backtest validation passed

### Paper Trading Phase (30 days)
- [ ] Paper trading started
- [ ] Daily monitoring in place
- [ ] 30+ trades executed
- [ ] Performance metrics tracked
- [ ] Risk controls validated

### Pre-Live Checklist
- [ ] Validation criteria met
- [ ] Validation report reviewed
- [ ] Manual approval obtained
- [ ] Emergency procedures reviewed
- [ ] Monitoring alerts configured

### Live Trading Phase
- [ ] Live adapter configured
- [ ] Strategy promoted to live
- [ ] First week close monitoring
- [ ] Performance matches paper
- [ ] Risk controls working

## Common Issues

### Issue: Tests Failing

**Symptom:** `pytest` shows failures

**Solution:**
```bash
# Check specific test
pytest tests/test_your_strategy.py -v

# Check error details
pytest tests/test_your_strategy.py -v --tb=long

# Common fixes:
# 1. Mock event bus
# 2. Initialize strategy before calling methods
# 3. Provide enough data for indicators
```

### Issue: Strategy Not Generating Signals

**Debugging:**
```python
# Add logging
import logging
logging.basicConfig(level=logging.DEBUG)

# Check indicator values
indicators = strategy.get_indicator_values("AAPL")
print(f"Indicators: {indicators}")

# Check price history
print(f"Price history length: {len(strategy.price_history['AAPL'])}")

# Verify running state
print(f"Strategy state: {strategy.state}")
```

### Issue: Paper Trading Validation Taking Too Long

**Options:**
1. **Wait it out** - 30 days is minimum for statistical significance
2. **Check strategy frequency** - Low-frequency strategies may need longer
3. **Add more symbols** - Increases trade count
4. **Review entry criteria** - May be too restrictive

## Best Practices

1. **Start Simple** - Get basic version working first
2. **Test Thoroughly** - Write tests before implementation
3. **Monitor Closely** - Especially in paper and early live trading
4. **Document Everything** - Comments, docstrings, ADRs
5. **Follow Prime Directive** - 100% pass rate, zero warnings

## Further Reading

- [Strategy Base Class](../strategies/base_strategy.py)
- [Risk Management](../docs/architecture/risk-controls.md)
- [Testing Guide](../docs/TESTING.md)
- [Event Flow](../docs/architecture/event-flow.md)
