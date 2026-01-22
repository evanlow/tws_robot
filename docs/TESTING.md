# Testing Guide

## Overview

The TWS Robot project maintains **100% test pass rate with zero warnings** (the Prime Directive). This guide explains our testing philosophy, practices, and procedures.

## Prime Directive

> **All tests must pass. Zero failures. Zero warnings.**

This is non-negotiable. Every commit, every change, every new feature must maintain 100% pass rate.

### Why the Prime Directive?

1. **Trust** - 100% pass rate means tests are reliable indicators of system health
2. **Safety** - Trading systems must be bulletproof - money is at stake
3. **Confidence** - Developers can refactor knowing tests will catch regressions
4. **Quality** - Forces proper test design and maintenance

### Enforcement

```bash
# Before every commit
pytest -v

# Expected output:
# ===== 690 passed in 12.34s =====
# 
# ❌ NOT ACCEPTABLE:
# ===== 689 passed, 1 failed =====
# ===== 690 passed, 1 warning =====
```

If tests fail or warn, **DO NOT COMMIT**. Fix the issue first.

## Test Structure

### Directory Organization

```
tws_robot/
├── tests/                    # All test files
│   ├── test_event_bus.py
│   ├── test_strategy_registry.py
│   ├── test_bollinger_bands.py
│   ├── test_risk_manager.py
│   └── ...
├── backtest/                 # Source code
│   ├── __init__.py
│   ├── engine.py
│   └── ...
├── strategies/
├── risk/
└── pytest.ini               # Pytest configuration
```

### Naming Conventions

- **Test files:** `test_<module_name>.py`
- **Test classes:** `Test<ClassName>`
- **Test methods:** `test_<what_it_tests>`

Examples:
```python
# tests/test_strategy_registry.py

class TestStrategyRegistry:
    def test_initialization(self):
        """Test StrategyRegistry initialization"""
        pass
    
    def test_register_strategy(self):
        """Test registering a new strategy"""
        pass
```

## Test Categories

### 1. Unit Tests

Test individual components in isolation.

**Location:** `tests/test_<module>.py`

**Example:**
```python
def test_position_sizer_calculation():
    """Test position size calculation"""
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
    
    # Max risk: $100,000 * 0.02 = $2,000
    # Risk per share: $150 - $147 = $3
    # Expected size: $2,000 / $3 = 666.67 → 666 shares
    assert size == 666
```

**Coverage Goal:** >90% for all modules

### 2. Integration Tests

Test interactions between components.

**Location:** `tests/test_<feature>_integration.py`

**Example:**
```python
def test_risk_integration():
    """Test risk manager with order manager"""
    event_bus = EventBus()
    risk_monitor = RiskMonitor(event_bus, max_daily_loss_pct=0.02)
    order_manager = OrderManager(event_bus)
    
    # Simulate daily loss exceeding limit
    risk_monitor._daily_pnl = -2500  # -2.5% on $100k account
    
    # Try to submit order
    order = create_test_order()
    order_manager.submit_order(order)
    
    # Should be rejected by risk monitor
    assert order.status == OrderStatus.REJECTED
```

### 3. Backtest Tests

Validate backtesting engine and data handling.

**Location:** `tests/test_backtest_<component>.py`

**Example:**
```python
def test_backtest_engine():
    """Test complete backtest execution"""
    # Create strategy
    strategy = BollingerBandsStrategy(
        name="BB_Test",
        symbols=["AAPL"]
    )
    
    # Load test data
    data = load_sample_data()
    
    # Run backtest
    engine = BacktestEngine(
        initial_capital=100000,
        strategies=[strategy],
        data=data
    )
    
    results = engine.run()
    
    # Validate results
    assert results.total_trades > 0
    assert results.sharpe_ratio > 0
    assert results.max_drawdown < 1.0  # Less than 100%
```

### 4. Strategy Tests

Validate trading strategies.

**Location:** `tests/test_<strategy_name>.py`

**Example:**
```python
class TestBollingerBandsStrategy:
    def test_initialization(self):
        """Test strategy initialization"""
        strategy = BollingerBandsStrategy(
            name="BB_Test",
            symbols=["AAPL"]
        )
        
        assert strategy.state == StrategyState.READY
        assert strategy.period == 20
        assert strategy.num_std == 2.0
    
    def test_indicator_calculation(self):
        """Test Bollinger Bands calculation"""
        strategy = BollingerBandsStrategy(
            name="BB_Test",
            symbols=["AAPL"],
            period=5
        )
        strategy.start()
        
        # Feed price data
        prices = [100, 102, 98, 101, 99]
        for price in prices:
            strategy.on_bar("AAPL", create_bar(close=price))
        
        indicators = strategy.get_indicator_values("AAPL")
        
        assert 'sma' in indicators
        assert 'upper_band' in indicators
        assert 'lower_band' in indicators
        assert indicators['sma'] == 100.0
        assert indicators['upper_band'] > indicators['sma']
        assert indicators['lower_band'] < indicators['sma']
    
    def test_signal_generation(self):
        """Test signal generation on band touch"""
        event_bus = EventBus()
        strategy = BollingerBandsStrategy(
            name="BB_Test",
            symbols=["AAPL"],
            period=5,
            num_std=2.0
        )
        strategy.event_bus = event_bus
        strategy.start()
        
        # Feed enough data to calculate bands
        for price in [100, 102, 98, 101, 99]:
            strategy.on_bar("AAPL", create_bar(close=price))
        
        # Price touches lower band (oversold)
        strategy.on_bar("AAPL", create_bar(close=92))  # Below lower band
        
        # Should generate BUY signal
        assert len(strategy.signals_to_emit) > 0
        signal = strategy.signals_to_emit[0]
        assert signal.signal_type == SignalType.BUY
```

## Running Tests

### Basic Commands

```bash
# Run all tests
pytest

# Run with verbose output
pytest -v

# Run specific file
pytest tests/test_strategy_registry.py

# Run specific test
pytest tests/test_strategy_registry.py::TestStrategyRegistry::test_initialization

# Run tests matching pattern
pytest -k "test_signal"
```

### Coverage Analysis

```bash
# Run with coverage
pytest --cov

# Coverage for specific module
pytest --cov=strategies tests/test_strategy_registry.py

# Generate HTML report
pytest --cov --cov-report=html
# Open htmlcov/index.html

# Check coverage percentage
pytest --cov --cov-report=term-missing
```

**Coverage Targets:**

| Component | Target | Current |
|-----------|--------|---------|
| Event Bus | >90% | 84% |
| Strategy Lifecycle | >90% | 97% |
| Metrics Tracker | >90% | 99% |
| Risk Monitor | >90% | 99% |
| Strategies | >90% | 95%+ |

### Continuous Testing

```bash
# Watch mode (requires pytest-watch)
pip install pytest-watch
ptw

# Runs tests automatically when files change
```

## Writing Good Tests

### Test Anatomy

```python
def test_feature_name():
    """
    Test description explaining what is being tested.
    
    This should be clear enough that someone reading the test
    understands what behavior is being validated.
    """
    # ARRANGE: Set up test data and objects
    strategy = BollingerBandsStrategy(
        name="Test",
        symbols=["AAPL"],
        period=20
    )
    
    # ACT: Perform the action being tested
    strategy.start()
    
    # ASSERT: Verify the expected outcome
    assert strategy.state == StrategyState.RUNNING
```

### Best Practices

#### 1. Test One Thing

❌ **Bad:**
```python
def test_strategy():
    """Test strategy"""
    strategy = MyStrategy()
    strategy.start()
    assert strategy.state == StrategyState.RUNNING
    
    strategy.on_bar("AAPL", bar)
    assert len(strategy.signals) > 0
    
    strategy.stop()
    assert strategy.state == StrategyState.STOPPED
```

✅ **Good:**
```python
def test_strategy_start():
    """Test strategy transitions to RUNNING on start"""
    strategy = MyStrategy()
    strategy.start()
    assert strategy.state == StrategyState.RUNNING

def test_strategy_signal_generation():
    """Test strategy generates signals on valid bar data"""
    strategy = MyStrategy()
    strategy.start()
    strategy.on_bar("AAPL", create_test_bar())
    assert len(strategy.signals) > 0

def test_strategy_stop():
    """Test strategy transitions to STOPPED on stop"""
    strategy = MyStrategy()
    strategy.start()
    strategy.stop()
    assert strategy.state == StrategyState.STOPPED
```

#### 2. Use Descriptive Names

❌ **Bad:**
```python
def test_1():
def test_strategy():
def test_bb():
```

✅ **Good:**
```python
def test_bollinger_bands_calculates_sma_correctly():
def test_risk_monitor_rejects_order_exceeding_daily_loss_limit():
def test_strategy_registry_returns_all_running_strategies():
```

#### 3. Use Fixtures for Setup

```python
import pytest

@pytest.fixture
def event_bus():
    """Create event bus for testing"""
    bus = EventBus()
    yield bus
    bus.shutdown()

@pytest.fixture
def strategy(event_bus):
    """Create test strategy"""
    return BollingerBandsStrategy(
        name="Test",
        symbols=["AAPL"],
        event_bus=event_bus
    )

def test_with_fixtures(strategy):
    """Test uses fixtures for setup"""
    strategy.start()
    assert strategy.state == StrategyState.RUNNING
```

#### 4. Mock External Dependencies

```python
from unittest.mock import Mock, patch

def test_tws_connection():
    """Test TWS connection handling"""
    # Mock TWS client
    mock_client = Mock()
    mock_client.connect.return_value = True
    
    with patch('core.connection.TWSClient', return_value=mock_client):
        conn = ConnectionManager()
        result = conn.connect()
        
        assert result is True
        mock_client.connect.assert_called_once()
```

#### 5. Test Edge Cases

```python
def test_position_sizer_with_zero_risk():
    """Test position sizer when entry price equals stop loss"""
    sizer = PositionSizer(account_balance=100000)
    
    # Zero risk per share
    size = sizer.calculate_position_size(
        entry_price=150.0,
        stop_loss=150.0,  # Same as entry
        symbol='AAPL'
    )
    
    # Should return 0 (can't calculate position)
    assert size == 0

def test_position_sizer_with_invalid_stop():
    """Test position sizer with invalid stop loss"""
    sizer = PositionSizer(account_balance=100000)
    
    # Stop loss above entry for long
    with pytest.raises(ValueError):
        sizer.calculate_position_size(
            entry_price=150.0,
            stop_loss=155.0,  # Above entry (invalid for long)
            symbol='AAPL'
        )
```

#### 6. Test Error Conditions

```python
def test_strategy_start_when_already_running():
    """Test starting a strategy that's already running raises error"""
    strategy = MyStrategy()
    strategy.start()
    
    # Try to start again
    with pytest.raises(InvalidStateTransition):
        strategy.start()

def test_order_with_invalid_quantity():
    """Test order submission with invalid quantity"""
    order_manager = OrderManager()
    
    # Negative quantity
    with pytest.raises(ValueError):
        order_manager.submit_order(
            symbol='AAPL',
            quantity=-100,
            order_type='MKT'
        )
```

## Test Patterns

### Pattern: Parameterized Tests

Test same logic with different inputs:

```python
import pytest

@pytest.mark.parametrize("price,expected_signal", [
    (90, SignalType.BUY),   # Below lower band
    (100, None),             # Within bands
    (110, SignalType.SELL),  # Above upper band
])
def test_bollinger_signal_generation(price, expected_signal):
    """Test signal generation at different price levels"""
    strategy = BollingerBandsStrategy(name="Test", symbols=["AAPL"])
    strategy.start()
    
    # Setup bands
    setup_bands(strategy, lower=95, upper=105)
    
    # Feed price
    strategy.on_bar("AAPL", create_bar(close=price))
    
    if expected_signal:
        assert len(strategy.signals_to_emit) == 1
        assert strategy.signals_to_emit[0].signal_type == expected_signal
    else:
        assert len(strategy.signals_to_emit) == 0
```

### Pattern: Test Data Builders

Create reusable test data:

```python
class BarBuilder:
    """Builder for test bar data"""
    
    def __init__(self):
        self.data = {
            'open': 100.0,
            'high': 101.0,
            'low': 99.0,
            'close': 100.0,
            'volume': 1000000,
            'timestamp': datetime.now()
        }
    
    def with_close(self, price: float):
        self.data['close'] = price
        return self
    
    def with_volume(self, volume: int):
        self.data['volume'] = volume
        return self
    
    def build(self):
        return self.data

# Usage
bar = BarBuilder().with_close(150.0).with_volume(2000000).build()
```

### Pattern: State Verification

Verify complete object state:

```python
def test_strategy_complete_state_after_start():
    """Test all state changes when strategy starts"""
    strategy = MyStrategy()
    
    # Before
    assert strategy.state == StrategyState.READY
    assert strategy.start_time is None
    assert len(strategy._positions) == 0
    assert len(strategy.signals_to_emit) == 0
    
    # Act
    strategy.start()
    
    # After
    assert strategy.state == StrategyState.RUNNING
    assert strategy.start_time is not None
    assert isinstance(strategy.start_time, datetime)
    assert len(strategy._positions) == 0  # Still 0, but verified
    assert len(strategy.signals_to_emit) == 0
```

## Debugging Failed Tests

### 1. Read the Output Carefully

```
FAILED tests/test_strategy.py::test_signal_generation - AssertionError: assert 0 > 0
```

- **File:** `tests/test_strategy.py`
- **Test:** `test_signal_generation`
- **Error:** `AssertionError: assert 0 > 0`

### 2. Run with More Detail

```bash
# Show full error traceback
pytest tests/test_strategy.py::test_signal_generation -v --tb=long

# Drop into debugger on failure
pytest tests/test_strategy.py::test_signal_generation --pdb
```

### 3. Add Debug Prints

```python
def test_signal_generation():
    strategy = MyStrategy()
    strategy.start()
    
    # Add debug output
    print(f"State before: {strategy.state}")
    
    strategy.on_bar("AAPL", bar)
    
    print(f"Signals after: {len(strategy.signals_to_emit)}")
    print(f"Indicators: {strategy.get_indicator_values('AAPL')}")
    
    assert len(strategy.signals_to_emit) > 0
```

Run with `-s` to see print output:
```bash
pytest tests/test_strategy.py::test_signal_generation -s
```

### 4. Isolate the Issue

```python
def test_signal_generation_minimal():
    """Minimal reproduction of signal generation issue"""
    strategy = MyStrategy()
    strategy.start()
    
    # Absolute minimum to reproduce
    bar = {'close': 100.0, 'volume': 1000000, 'timestamp': datetime.now()}
    strategy.on_bar("AAPL", bar)
    
    print(f"DEBUG: signals = {strategy.signals_to_emit}")
    assert len(strategy.signals_to_emit) > 0
```

## Common Test Issues

### Issue: Test Passes Locally, Fails in CI

**Causes:**
- Time-dependent tests
- File system differences
- Random data

**Solutions:**
```python
# ❌ Time-dependent
def test_timestamp():
    assert get_timestamp() == datetime.now()  # Will fail due to timing

# ✅ Use fixed times
def test_timestamp():
    fixed_time = datetime(2025, 1, 15, 12, 0, 0)
    with patch('datetime.datetime') as mock_dt:
        mock_dt.now.return_value = fixed_time
        assert get_timestamp() == fixed_time

# ❌ Random data
def test_with_random():
    value = random.randint(1, 100)
    assert value > 50  # Flaky!

# ✅ Fixed seed
def test_with_random():
    random.seed(42)
    value = random.randint(1, 100)
    assert value == 52  # Always same with seed=42
```

### Issue: Tests Are Slow

**Solutions:**

```python
# Use pytest markers for slow tests
@pytest.mark.slow
def test_long_backtest():
    # ... long-running test

# Run fast tests only
pytest -m "not slow"

# Run slow tests separately
pytest -m "slow"

# Parallelize (requires pytest-xdist)
pip install pytest-xdist
pytest -n auto  # Use all CPU cores
```

### Issue: Tests Break After Refactoring

This is actually good - tests catching regressions!

**Process:**
1. Review what broke
2. Decide if tests need updating (API change) or code is wrong
3. Update tests or fix code
4. Verify all tests pass again

## Test Coverage Reports

### Generate Report

```bash
# Terminal report
pytest --cov --cov-report=term-missing

# HTML report (recommended)
pytest --cov --cov-report=html
# Open htmlcov/index.html in browser
```

### Interpret Results

```
Name                          Stmts   Miss  Cover   Missing
-----------------------------------------------------------
strategies/base_strategy.py    150      5    97%   45-47, 89, 120
strategies/bollinger_bands.py   85      3    96%   67, 72, 89
risk/risk_monitor.py           120      1    99%   156
-----------------------------------------------------------
TOTAL                         1234     45    96%
```

- **Stmts:** Total statements
- **Miss:** Uncovered statements
- **Cover:** Coverage percentage
- **Missing:** Line numbers not covered

### Improve Coverage

Find uncovered code:

```bash
pytest --cov --cov-report=term-missing | grep -A 20 "TOTAL"
```

Add tests for uncovered lines:

```python
# If line 89 is uncovered:
def test_edge_case_covering_line_89():
    """Test the edge case that executes line 89"""
    # Setup to trigger line 89
    strategy = MyStrategy()
    # ... specific setup that triggers line 89
```

## Pre-Commit Checklist

Before every commit:

```bash
# 1. Run all tests
pytest -v

# 2. Check coverage
pytest --cov

# 3. Verify no warnings
pytest -v 2>&1 | grep -i warning

# 4. Run specific tests for changed code
pytest tests/test_<your_module>.py -v

# 5. Check if new code needs tests
pytest --cov=<your_module> --cov-report=term-missing
```

**Expected results:**
- ✅ All tests pass
- ✅ Zero failures
- ✅ Zero warnings
- ✅ Coverage >90% for new code

**If any checks fail:** Fix before committing.

## Further Reading

- [pytest Documentation](https://docs.pytest.org/)
- [unittest.mock Guide](https://docs.python.org/3/library/unittest.mock.html)
- [Coverage.py](https://coverage.readthedocs.io/)
- [Prime Directive](../prime_directive.md)
- [Debugging Strategies](../runbooks/debugging-strategies.md)
