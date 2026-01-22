# Runbook: Debugging Strategies

## Overview

This runbook provides systematic approaches to debugging strategy issues in the TWS Robot system.

## Common Scenarios

### 1. Strategy Not Starting

**Symptoms:**
- Strategy remains in READY state
- No signals generated
- No position updates

**Debugging Steps:**

```python
# Check strategy state
print(f"State: {strategy.state}")
print(f"Enabled: {strategy.config.enabled}")

# Check lifecycle
from strategies.base_strategy import StrategyState

if strategy.state == StrategyState.READY:
    print("Strategy not started - call strategy.start()")
elif strategy.state == StrategyState.ERROR:
    print(f"Strategy in error state: {strategy.get_metrics()}")
```

**Common Causes:**
- Forgot to call `strategy.start()`
- Strategy config has `enabled=False`
- Validation failed during start
- Missing required parameters

**Solution:**
```python
# Enable and start
strategy.config.enabled = True
strategy.start()

# Verify
assert strategy.state == StrategyState.RUNNING
```

### 2. No Signals Being Generated

**Symptoms:**
- Strategy running but no signals
- Empty `signals_to_emit` queue
- No trades executed

**Debugging Steps:**

```python
# 1. Check data flow
print(f"Last bar received: {strategy._last_bar_time}")
print(f"Symbols: {strategy.config.symbols}")

# 2. Check indicator calculation
for symbol in strategy.config.symbols:
    indicators = strategy.get_indicator_values(symbol)
    print(f"{symbol} indicators: {indicators}")

# 3. Check price history
for symbol in strategy.config.symbols:
    history = strategy.price_history.get(symbol, [])
    print(f"{symbol} history length: {len(history)}")
    if history:
        print(f"  Latest prices: {history[-5:]}")

# 4. Check positions
print(f"Current positions: {strategy._positions}")

# 5. Enable debug logging
import logging
logging.basicConfig(level=logging.DEBUG)
strategy.logger.setLevel(logging.DEBUG)
```

**Common Causes:**

| Cause | Solution |
|-------|----------|
| Insufficient data | Feed more bars - strategy needs `period` bars before generating signals |
| Indicators not calculated | Check `_calculate_indicators()` method - add debug prints |
| Signal conditions not met | Entry criteria may be too strict - review thresholds |
| Already in position | Strategy won't buy if already holding position |
| Strategy paused | Call `strategy.resume()` |

**Example Debug Session:**

```python
# Enable detailed logging
strategy.logger.setLevel(logging.DEBUG)

# Feed bar and trace execution
bar = {
    'close': 150.0,
    'high': 151.0,
    'low': 149.0,
    'open': 150.5,
    'volume': 1000000,
    'timestamp': datetime.now()
}

print("Before on_bar:")
print(f"  State: {strategy.state}")
print(f"  History length: {len(strategy.price_history.get('AAPL', []))}")

strategy.on_bar('AAPL', bar)

print("After on_bar:")
print(f"  History length: {len(strategy.price_history.get('AAPL', []))}")
print(f"  Indicators: {strategy.get_indicator_values('AAPL')}")
print(f"  Signals: {len(strategy.signals_to_emit)}")
```

### 3. Incorrect Signal Generation

**Symptoms:**
- Too many signals
- Wrong signal types (buying when should sell)
- Invalid signal parameters

**Debugging Steps:**

```python
# 1. Capture signals
signals = []

def signal_handler(signal):
    signals.append(signal)
    print(f"Signal: {signal.signal_type} {signal.symbol} @ {signal.target_price}")
    print(f"  Strength: {signal.strength}")
    print(f"  Stop loss: {signal.stop_loss}")

event_bus.subscribe('strategy.signal', signal_handler)

# 2. Review signal validation
for signal in signals:
    is_valid = strategy.validate_signal(signal)
    print(f"{signal.symbol} {signal.signal_type}: valid={is_valid}")
    
    if not is_valid:
        # Check why invalid
        print(f"  Symbol in config: {signal.symbol in strategy.config.symbols}")
        print(f"  Has indicators: {signal.symbol in strategy.indicators}")

# 3. Check signal logic
# Add debug prints to _check_signals method
def _check_signals_debug(self, symbol, bar_data):
    indicators = self.indicators.get(symbol)
    if not indicators:
        print(f"{symbol}: No indicators yet")
        return
    
    current_price = indicators['current_price']
    threshold_value = indicators.get('threshold_indicator')
    
    print(f"{symbol}: price={current_price}, threshold={threshold_value}")
    
    # Entry condition
    if current_price > threshold_value:
        print(f"  → BUY signal condition met")
        if symbol not in self._positions:
            print(f"  → No position, generating signal")
            # Signal generation...
        else:
            print(f"  → Already in position, skipping")

# Temporarily replace method for debugging
strategy._check_signals = lambda s, b: _check_signals_debug(strategy, s, b)
```

**Common Issues:**

```python
# Issue: Signals generated while paused
# Fix: Check state in on_bar
def on_bar(self, symbol, bar_data):
    if self.state != StrategyState.RUNNING:
        return  # Don't process if not running
    # ... rest of logic

# Issue: Multiple signals for same symbol
# Fix: Check if signal already exists
def _generate_signal(self, signal):
    # Check if we already have pending signal
    pending = [s for s in self.signals_to_emit if s.symbol == signal.symbol]
    if pending:
        self.logger.debug(f"Signal for {signal.symbol} already pending, skipping")
        return
    
    self.signals_to_emit.append(signal)

# Issue: Invalid stop loss prices
# Fix: Validate stop loss calculation
def _calculate_stop_loss(self, entry_price, signal_type):
    if signal_type == SignalType.BUY:
        stop_loss = entry_price * 0.98  # 2% below entry
    else:
        stop_loss = entry_price * 1.02  # 2% above entry
    
    # Validate
    assert stop_loss > 0, f"Invalid stop loss: {stop_loss}"
    assert abs(stop_loss - entry_price) / entry_price < 0.1, "Stop loss too far"
    
    return stop_loss
```

### 4. Performance Issues (Slow)

**Symptoms:**
- Strategy takes long time to process bars
- System lag or unresponsiveness
- Backtest runs slowly

**Profiling:**

```python
import cProfile
import pstats

# Profile strategy execution
profiler = cProfile.Profile()
profiler.enable()

# Run strategy for N bars
for i in range(1000):
    bar = generate_test_bar()
    strategy.on_bar('AAPL', bar)

profiler.disable()

# Print results
stats = pstats.Stats(profiler)
stats.sort_stats('cumulative')
stats.print_stats(20)  # Top 20 functions
```

**Common Bottlenecks:**

```python
# Bottleneck: Recalculating indicators every bar
# Fix: Cache calculations
def _calculate_indicators(self, symbol):
    prices = self.price_history[symbol]
    
    # Only recalculate if new data
    if self._last_calculation.get(symbol) == len(prices):
        return
    
    # Calculate
    self.indicators[symbol] = {
        'sma': sum(prices) / len(prices)
    }
    
    self._last_calculation[symbol] = len(prices)

# Bottleneck: Keeping unlimited history
# Fix: Limit history size
def on_bar(self, symbol, bar_data):
    self.price_history[symbol].append(bar_data['close'])
    
    # Keep only what we need
    max_history = max(self.period * 2, 100)
    if len(self.price_history[symbol]) > max_history:
        self.price_history[symbol] = self.price_history[symbol][-max_history:]

# Bottleneck: Complex calculations on every bar
# Fix: Calculate only when needed
def on_bar(self, symbol, bar_data):
    # Update prices
    self.price_history[symbol].append(bar_data['close'])
    
    # Only calculate indicators when needed (e.g., every N bars)
    if len(self.price_history[symbol]) % self.calculation_frequency == 0:
        self._calculate_indicators(symbol)
```

### 5. Risk Control Violations

**Symptoms:**
- Position size too large
- Stop loss not triggered
- Daily loss limit exceeded

**Debugging:**

```python
from risk.risk_monitor import RiskMonitor

# Check risk state
risk_monitor = RiskMonitor(event_bus)
risk_state = risk_monitor.get_risk_state()

print(f"Account value: ${risk_state['account_value']:,.2f}")
print(f"Daily P&L: ${risk_state['daily_pnl']:,.2f}")
print(f"Max position: {risk_state['max_position_size']}")
print(f"Trading enabled: {risk_state['trading_enabled']}")

# Check position sizing
from risk.position_sizer import PositionSizer

sizer = PositionSizer(
    account_balance=100000,
    max_position_pct=0.05,
    risk_per_trade_pct=0.02
)

size = sizer.calculate_position_size(
    entry_price=150.0,
    stop_loss=147.0,
    symbol='AAPL'
)

print(f"Suggested position size: {size} shares")
print(f"Position value: ${size * 150.0:,.2f}")
print(f"Risk amount: ${size * (150.0 - 147.0):,.2f}")

# Verify risk calculation
max_risk = 100000 * 0.02  # 2% of account
actual_risk = size * (150.0 - 147.0)
print(f"Max risk: ${max_risk:,.2f}")
print(f"Actual risk: ${actual_risk:,.2f}")
assert actual_risk <= max_risk
```

**Common Issues:**

```python
# Issue: Position size calculation wrong
# Debug: Check inputs to position sizer
entry_price = 150.0
stop_loss = 147.0
account_balance = 100000

print(f"Entry: ${entry_price}")
print(f"Stop: ${stop_loss}")
print(f"Risk per share: ${entry_price - stop_loss}")
print(f"Risk % per trade: 2%")
print(f"Max $ risk: ${account_balance * 0.02}")
print(f"Shares: {(account_balance * 0.02) / (entry_price - stop_loss)}")

# Issue: Stop loss not being triggered
# Debug: Check order status
from execution.order_manager import OrderManager

order_manager = OrderManager(event_bus)
orders = order_manager.get_orders_by_strategy(strategy.strategy_id)

for order in orders:
    print(f"Order {order['id']}: {order['status']}")
    print(f"  Symbol: {order['symbol']}")
    print(f"  Type: {order['type']}")
    print(f"  Stop price: {order.get('stop_price')}")
    print(f"  Current price: {get_current_price(order['symbol'])}")
```

### 6. State Machine Issues

**Symptoms:**
- Invalid state transitions
- Strategy stuck in ERROR state
- Can't pause/resume/stop

**Debugging:**

```python
# Check state history
print(f"Current state: {strategy.state}")
print(f"State history: {strategy._state_history}")

# Check transition validity
from strategies.base_strategy import StrategyState

def can_transition(from_state, to_state):
    valid_transitions = {
        StrategyState.READY: [StrategyState.RUNNING],
        StrategyState.RUNNING: [StrategyState.PAUSED, StrategyState.STOPPED, StrategyState.ERROR],
        StrategyState.PAUSED: [StrategyState.RUNNING, StrategyState.STOPPED],
        StrategyState.STOPPED: [],
        StrategyState.ERROR: [StrategyState.STOPPED]
    }
    return to_state in valid_transitions.get(from_state, [])

# Try transition
try:
    strategy.start()
except Exception as e:
    print(f"Start failed: {e}")
    print(f"Current state: {strategy.state}")

# Force state for recovery (use with caution)
if strategy.state == StrategyState.ERROR:
    # Review error
    metrics = strategy.get_metrics()
    print(f"Error metrics: {metrics.get('errors', [])}")
    
    # Fix underlying issue, then reset
    strategy.state = StrategyState.STOPPED
    strategy._error_count = 0
    # Now can restart
    strategy.start()
```

## Debugging Tools

### Enable Logging

```python
import logging

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('strategy_debug.log'),
        logging.StreamHandler()
    ]
)

# Set strategy logger level
strategy.logger.setLevel(logging.DEBUG)
```

### Event Tracing

```python
# Trace all events
def trace_all_events(event_type, data):
    print(f"[EVENT] {event_type}: {data}")

event_bus.subscribe('*', trace_all_events)

# Trace specific events
def trace_signals(signal):
    print(f"[SIGNAL] {signal.signal_type} {signal.symbol} @ {signal.target_price}")

event_bus.subscribe('strategy.signal', trace_signals)
```

### State Inspector

```python
class StrategyInspector:
    """Debug tool for inspecting strategy state"""
    
    def __init__(self, strategy):
        self.strategy = strategy
    
    def print_full_state(self):
        """Print complete strategy state"""
        print("=" * 60)
        print(f"Strategy: {self.strategy.config.name}")
        print(f"State: {self.strategy.state}")
        print(f"Symbols: {self.strategy.config.symbols}")
        print("=" * 60)
        
        # Indicators
        print("\nIndicators:")
        for symbol, indicators in self.strategy.indicators.items():
            print(f"  {symbol}:")
            for name, value in indicators.items():
                print(f"    {name}: {value}")
        
        # Positions
        print("\nPositions:")
        for symbol, position in self.strategy._positions.items():
            print(f"  {symbol}: {position}")
        
        # Metrics
        print("\nMetrics:")
        metrics = self.strategy.get_metrics()
        for key, value in metrics.items():
            print(f"  {key}: {value}")
        
        # Pending signals
        print(f"\nPending signals: {len(self.strategy.signals_to_emit)}")
        
        print("=" * 60)

# Usage
inspector = StrategyInspector(strategy)
inspector.print_full_state()
```

### Performance Monitor

```python
import time

class PerformanceMonitor:
    """Monitor strategy performance metrics"""
    
    def __init__(self, strategy):
        self.strategy = strategy
        self.start_time = time.time()
        self.bar_count = 0
        self.bar_times = []
    
    def on_bar_start(self):
        self.bar_start_time = time.time()
    
    def on_bar_end(self):
        elapsed = time.time() - self.bar_start_time
        self.bar_times.append(elapsed)
        self.bar_count += 1
        
        # Report every 100 bars
        if self.bar_count % 100 == 0:
            avg_time = sum(self.bar_times[-100:]) / min(100, len(self.bar_times))
            print(f"Processed {self.bar_count} bars")
            print(f"  Avg time per bar: {avg_time*1000:.2f}ms")
            print(f"  Signals generated: {len(self.strategy.signals_to_emit)}")

# Usage
monitor = PerformanceMonitor(strategy)

for bar in test_data:
    monitor.on_bar_start()
    strategy.on_bar('AAPL', bar)
    monitor.on_bar_end()
```

## Best Practices

1. **Start Simple** - Test with minimal data first
2. **Add Logging** - Liberal use of debug logging
3. **Unit Test First** - Isolate issues with unit tests
4. **Use Inspectors** - Custom debug tools help visualize state
5. **Profile Performance** - Measure before optimizing
6. **Check Prime Directive** - All tests must pass

## Emergency Procedures

If strategy is causing issues in production:

```python
# 1. STOP THE STRATEGY IMMEDIATELY
strategy.stop()

# 2. Verify stopped
assert strategy.state == StrategyState.STOPPED

# 3. Cancel all pending orders
order_manager.cancel_all_orders(strategy_id=strategy.strategy_id)

# 4. Review positions
positions = order_manager.get_positions(strategy_id=strategy.strategy_id)
print(f"Open positions: {len(positions)}")

# 5. Manual intervention if needed
# - Close positions manually via TWS
# - Review trade history
# - Check risk violations

# 6. Post-mortem analysis
# - Review logs
# - Check metrics
# - Run unit tests
# - Fix issues before restarting
```

## Further Reading

- [Emergency Procedures](emergency-procedures.md)
- [Risk Controls](../architecture/risk-controls.md)
- [Testing Guide](../TESTING.md)
- [Strategy Lifecycle](../architecture/strategy-lifecycle.md)
