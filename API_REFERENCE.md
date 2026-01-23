# TWS Robot - API Reference

**Developer documentation for extending and customizing TWS Robot.**

---

## 📚 Table of Contents

1. [Strategy Development API](#strategy-development-api)
2. [Risk Management API](#risk-management-api)
3. [Backtest Engine API](#backtest-engine-api)
4. [Data Management API](#data-management-api)
5. [Event System API](#event-system-api)
6. [Common Patterns](#common-patterns)

---

## Strategy Development API

### Base Strategy Class

All strategies must inherit from `Strategy` base class:

```python
from backtest.strategy import Strategy, StrategyConfig
from backtest.data_models import MarketData, Bar

class MyCustomStrategy(Strategy):
    """Your custom trading strategy."""
    
    def __init__(self, config: StrategyConfig):
        super().__init__(config)
        # Your initialization here
        self.fast_period = config.parameters.get('fast_period', 10)
        self.slow_period = config.parameters.get('slow_period', 20)
        self.ma_values = {}
    
    def on_start(self):
        """Called once when backtest starts."""
        print(f"Starting {self.config.name} with {self.config.initial_capital}")
    
    def on_bar(self, market_data: MarketData):
        """Called for each new bar of market data."""
        for symbol, bar in market_data.bars.items():
            # Your trading logic here
            if self.should_buy(symbol, bar):
                self.buy(symbol, quantity=100)
            elif self.should_sell(symbol, bar):
                self.sell(symbol, quantity=100)
    
    def on_stop(self):
        """Called once when backtest ends."""
        print(f"Final equity: ${self.state.equity:,.2f}")
    
    def on_trade(self, trade):
        """Called when an order is filled."""
        print(f"Trade executed: {trade.symbol} {trade.action} {trade.quantity}@${trade.price}")
```

### StrategyConfig

Configuration object for strategies:

```python
from backtest.strategy import StrategyConfig

config = StrategyConfig(
    name="MyStrategy",              # Strategy name
    symbols=['AAPL', 'MSFT'],       # Symbols to trade
    initial_capital=100000.0,       # Starting capital
    
    # Risk parameters
    max_position_size=0.10,         # 10% max per position
    max_total_exposure=1.0,         # 100% total exposure
    use_risk_management=True,       # Enable risk controls
    
    # Custom strategy parameters
    parameters={
        'fast_period': 20,
        'slow_period': 50,
        'threshold': 0.02
    }
)
```

### Strategy Methods

#### Order Management

```python
# Market orders
order_id = self.buy(symbol='AAPL', quantity=100)
order_id = self.sell(symbol='AAPL', quantity=100)

# Limit orders
order_id = self.buy(
    symbol='AAPL',
    quantity=100,
    order_type='LIMIT',
    limit_price=150.00
)

# Stop orders
order_id = self.sell(
    symbol='AAPL',
    quantity=100,
    order_type='STOP',
    stop_price=145.00
)

# Close entire position
order_id = self.close_position(symbol='AAPL')

# Cancel pending order
success = self.cancel_order(order_id='order_123')
```

#### Position Queries

```python
# Get current position
position = self.get_position('AAPL')
if position:
    print(f"Quantity: {position.quantity}")
    print(f"Avg Cost: ${position.average_cost}")
    print(f"Unrealized P&L: ${position.unrealized_pnl}")

# Position checks
has_pos = self.has_position('AAPL')      # True if any position
is_long = self.is_long('AAPL')           # True if long
is_short = self.is_short('AAPL')         # True if short
is_flat = self.is_flat('AAPL')           # True if no position
```

#### Market Data Access

```python
# Get recent bars
bars = self.get_bar_history(symbol='AAPL', lookback=20)
for bar in bars:
    print(f"{bar.timestamp}: O={bar.open} H={bar.high} L={bar.low} C={bar.close}")

# Current prices
current_price = self.current_prices.get('AAPL')

# All bar history
all_bars = self.bar_history['AAPL']  # List[Bar]
```

#### Strategy State

```python
# Current equity and cash
equity = self.state.equity
cash = self.state.cash

# Performance metrics
total_trades = self.state.total_trades
win_rate = self.state.winning_trades / self.state.total_trades if self.state.total_trades > 0 else 0
total_pnl = self.state.total_pnl

# Exposure tracking
long_exp = self.state.long_exposure
short_exp = self.state.short_exposure
total_exp = self.state.total_exposure

# Drawdown
max_dd = self.state.max_drawdown
peak = self.state.peak_equity
```

---

## Risk Management API

### RiskManager Class

```python
from risk.risk_manager import RiskManager, Position, RiskStatus

# Initialize risk manager
risk_mgr = RiskManager(
    initial_capital=100000.0,
    max_positions=5,                # Max concurrent positions
    max_position_pct=0.20,          # 20% max per position
    max_drawdown_pct=0.15,          # 15% max drawdown
    daily_loss_limit_pct=0.05,      # 5% daily loss limit
    max_leverage=1.0,               # No leverage
    emergency_stop_enabled=True
)
```

### Pre-Trade Risk Check

```python
# Check if trade is allowed
result = risk_mgr.check_trade_risk(
    symbol="AAPL",
    side="BUY",
    quantity=100,
    price=150.00,
    current_positions=positions,
    current_equity=equity
)

if result.approved:
    # Execute trade
    execute_order(symbol, quantity, price)
else:
    # Trade rejected
    print(f"Trade rejected: {result.reason}")
```

### Position Sizing

```python
from risk.position_sizer import FixedPercentSizer, VolatilityAdjustedSizer

# Fixed percent sizing
sizer = FixedPercentSizer(risk_pct=0.02)  # Risk 2% per trade
size = sizer.calculate_size(
    equity=100000,
    entry_price=150.00,
    stop_loss=145.00
)

# Volatility-adjusted sizing
vol_sizer = VolatilityAdjustedSizer(target_volatility=0.15)
size = vol_sizer.calculate_size(
    equity=100000,
    price=150.00,
    volatility=0.25  # Historical volatility
)
```

### Risk Metrics

```python
# Get current risk snapshot
metrics = risk_mgr.get_risk_metrics(
    positions=current_positions,
    equity=current_equity
)

print(f"Leverage: {metrics.leverage:.2f}x")
print(f"Largest position: {metrics.largest_position_pct:.1%}")
print(f"Drawdown: {metrics.drawdown_pct:.1%}")
print(f"Risk Status: {metrics.risk_status}")
```

---

## Backtest Engine API

### Running a Backtest

```python
from backtest import BacktestEngine, BacktestConfig
from backtest.data_manager import HistoricalDataManager
from datetime import datetime

# Load historical data
data_mgr = HistoricalDataManager("data/historical")
data_mgr.load_symbol("AAPL")
data_mgr.load_symbol("MSFT")

# Configure backtest
backtest_config = BacktestConfig(
    start_date=datetime(2023, 1, 1),
    end_date=datetime(2023, 12, 31),
    initial_capital=100000.0,
    commission=0.001,  # 0.1% commission
    slippage=0.0005    # 0.05% slippage
)

# Create strategy
strategy = MyCustomStrategy(strategy_config)

# Run backtest
engine = BacktestEngine(data_mgr, backtest_config)
result = engine.run(strategy)

# Analyze results
print(f"Total Return: {result.total_return:.2%}")
print(f"Sharpe Ratio: {result.sharpe_ratio:.2f}")
print(f"Max Drawdown: {result.max_drawdown:.2%}")
print(f"Win Rate: {result.win_rate:.2%}")
```

### BacktestConfig Options

```python
from backtest import BacktestConfig

config = BacktestConfig(
    start_date=datetime(2023, 1, 1),
    end_date=datetime(2023, 12, 31),
    initial_capital=100000.0,
    
    # Trading costs
    commission=0.001,          # Per-trade commission (0.1%)
    slippage=0.0005,          # Slippage per trade (0.05%)
    
    # Execution settings
    fill_on_bar_close=True,   # Fill orders at bar close
    allow_fractional=False,   # Allow fractional shares
    
    # Risk management
    use_risk_manager=True,    # Enable risk controls
    max_drawdown=0.20,        # 20% max drawdown
    
    # Logging
    verbose=True,             # Print progress
    log_trades=True          # Log all trades
)
```

---

## Data Management API

### HistoricalDataManager

```python
from backtest.data_manager import HistoricalDataManager
from backtest.data_models import TimeFrame

# Initialize data manager
data_mgr = HistoricalDataManager("data/historical")

# Load data for symbols
data_mgr.load_symbol("AAPL")
data_mgr.load_symbol("MSFT", timeframe=TimeFrame.DAILY)

# Get bars for date range
bars = data_mgr.get_bars(
    symbol="AAPL",
    start_date=datetime(2023, 1, 1),
    end_date=datetime(2023, 12, 31)
)

# Get latest bar
latest = data_mgr.get_latest_bar("AAPL")
print(f"Latest close: ${latest.close}")

# Check if data available
has_data = data_mgr.has_data("AAPL")
```

### Bar Data Model

```python
from backtest.data_models import Bar

# Bar object structure
bar = Bar(
    timestamp=datetime(2023, 1, 3, 16, 0),
    open=150.25,
    high=152.50,
    low=149.75,
    close=151.00,
    volume=1000000,
    symbol="AAPL"
)

# Accessing bar data
price = bar.close
high_price = bar.high
volume = bar.volume
date = bar.timestamp
```

---

## Event System API

### EventBus

```python
from core.event_bus import EventBus, Event, EventType

# Get global event bus
bus = EventBus.get_instance()

# Subscribe to events
def on_market_data(event: Event):
    print(f"Market data: {event.data}")

bus.subscribe(EventType.MARKET_DATA_RECEIVED, on_market_data)

# Publish events
bus.publish(Event(
    event_type=EventType.SIGNAL_GENERATED,
    data={
        'symbol': 'AAPL',
        'signal': 'BUY',
        'strength': 0.75
    }
))

# Unsubscribe
bus.unsubscribe(EventType.MARKET_DATA_RECEIVED, on_market_data)
```

### Event Types

```python
from core.event_bus import EventType

# Available event types:
EventType.MARKET_DATA_RECEIVED   # New market data arrived
EventType.SIGNAL_GENERATED       # Strategy generated signal
EventType.ORDER_SUBMITTED        # Order sent to broker
EventType.ORDER_FILLED           # Order executed
EventType.ORDER_CANCELLED        # Order cancelled
EventType.POSITION_OPENED        # New position opened
EventType.POSITION_CLOSED        # Position closed
EventType.RISK_VIOLATION         # Risk limit breached
EventType.STRATEGY_STARTED       # Strategy started
EventType.STRATEGY_STOPPED       # Strategy stopped
EventType.ERROR_OCCURRED         # Error happened
```

---

## Common Patterns

### Pattern 1: Moving Average Crossover

```python
class MACrossStrategy(Strategy):
    def __init__(self, config: StrategyConfig):
        super().__init__(config)
        self.fast_period = config.parameters.get('fast_period', 20)
        self.slow_period = config.parameters.get('slow_period', 50)
        self.fast_ma = {}
        self.slow_ma = {}
    
    def on_bar(self, market_data: MarketData):
        for symbol, bar in market_data.bars.items():
            # Get bar history
            bars = self.get_bar_history(symbol, self.slow_period)
            if len(bars) < self.slow_period:
                continue
            
            # Calculate MAs
            closes = [b.close for b in bars]
            self.fast_ma[symbol] = sum(closes[-self.fast_period:]) / self.fast_period
            self.slow_ma[symbol] = sum(closes) / self.slow_period
            
            # Generate signals
            if self.fast_ma[symbol] > self.slow_ma[symbol] and not self.is_long(symbol):
                # Golden cross - buy
                self.buy(symbol, 100)
            elif self.fast_ma[symbol] < self.slow_ma[symbol] and self.is_long(symbol):
                # Death cross - sell
                self.close_position(symbol)
```

### Pattern 2: Mean Reversion with Bollinger Bands

```python
class BollingerStrategy(Strategy):
    def __init__(self, config: StrategyConfig):
        super().__init__(config)
        self.period = config.parameters.get('period', 20)
        self.std_dev = config.parameters.get('std_dev', 2.0)
    
    def on_bar(self, market_data: MarketData):
        for symbol, bar in market_data.bars.items():
            bars = self.get_bar_history(symbol, self.period)
            if len(bars) < self.period:
                continue
            
            # Calculate Bollinger Bands
            closes = [b.close for b in bars]
            sma = sum(closes) / self.period
            variance = sum((c - sma) ** 2 for c in closes) / self.period
            std = variance ** 0.5
            
            upper_band = sma + (self.std_dev * std)
            lower_band = sma - (self.std_dev * std)
            
            # Generate signals
            if bar.close < lower_band and not self.is_long(symbol):
                # Oversold - buy
                self.buy(symbol, 100)
            elif bar.close > sma and self.is_long(symbol):
                # Return to mean - sell
                self.close_position(symbol)
```

### Pattern 3: Risk-Aware Position Sizing

```python
from risk.position_sizer import FixedPercentSizer

class RiskAwareStrategy(Strategy):
    def __init__(self, config: StrategyConfig):
        super().__init__(config)
        self.sizer = FixedPercentSizer(risk_pct=0.02)  # Risk 2% per trade
    
    def on_bar(self, market_data: MarketData):
        for symbol, bar in market_data.bars.items():
            if self.should_buy(symbol, bar):
                # Calculate position size based on risk
                entry_price = bar.close
                stop_loss = entry_price * 0.98  # 2% stop loss
                
                size = self.sizer.calculate_size(
                    equity=self.state.equity,
                    entry_price=entry_price,
                    stop_loss=stop_loss
                )
                
                self.buy(symbol, quantity=int(size))
```

### Pattern 4: Multi-Timeframe Analysis

```python
class MultiTimeframeStrategy(Strategy):
    def __init__(self, config: StrategyConfig):
        super().__init__(config)
        self.daily_bars = {}
        self.hourly_bars = {}
    
    def on_bar(self, market_data: MarketData):
        for symbol, bar in market_data.bars.items():
            # Store bars by timeframe
            if self.is_daily_bar(bar):
                self.daily_bars.setdefault(symbol, []).append(bar)
            if self.is_hourly_bar(bar):
                self.hourly_bars.setdefault(symbol, []).append(bar)
            
            # Analyze daily trend
            daily_trend = self.get_trend(self.daily_bars[symbol])
            
            # Trade on hourly signals only if daily trend is favorable
            if daily_trend == 'BULLISH':
                hourly_signal = self.get_hourly_signal(self.hourly_bars[symbol])
                if hourly_signal == 'BUY':
                    self.buy(symbol, 100)
```

---

## Best Practices

### 1. Always Validate Configuration

```python
def __init__(self, config: StrategyConfig):
    super().__init__(config)
    
    # Validate parameters
    if config.initial_capital <= 0:
        raise ValueError("Initial capital must be positive")
    
    self.period = config.parameters.get('period', 20)
    if self.period < 2:
        raise ValueError("Period must be at least 2")
```

### 2. Handle Edge Cases

```python
def on_bar(self, market_data: MarketData):
    for symbol, bar in market_data.bars.items():
        # Check sufficient history
        bars = self.get_bar_history(symbol, self.period)
        if len(bars) < self.period:
            continue  # Skip until we have enough data
        
        # Avoid division by zero
        if bar.close == 0:
            continue
```

### 3. Use Logging

```python
import logging

logger = logging.getLogger(__name__)

def on_trade(self, trade):
    logger.info(f"Trade executed: {trade.symbol} {trade.action} {trade.quantity}@${trade.price}")
    
    # Log strategy-specific info
    position = self.get_position(trade.symbol)
    logger.debug(f"New position size: {position.quantity}")
```

### 4. Test with Multiple Scenarios

```python
# Test with different parameters
configs = [
    {'fast_period': 10, 'slow_period': 20},
    {'fast_period': 20, 'slow_period': 50},
    {'fast_period': 50, 'slow_period': 200}
]

for params in configs:
    config = StrategyConfig(
        name=f"MA_{params['fast_period']}_{params['slow_period']}",
        symbols=['AAPL'],
        initial_capital=100000,
        parameters=params
    )
    strategy = MACrossStrategy(config)
    result = engine.run(strategy)
    print(f"{config.name}: Return={result.total_return:.2%}")
```

---

## Documentation Index

- [User Guide](USER_GUIDE.md) - Learn how to use strategies
- [Examples Guide](EXAMPLES_GUIDE.md) - Working code examples
- [Quick Reference](QUICK_REFERENCE.md) - Commands cheat sheet
- [Architecture Docs](docs/architecture/overview.md) - System design
- [Adding New Strategy](docs/runbooks/adding-new-strategy.md) - Step-by-step guide

---

**Questions?** See [Debugging Guide](docs/runbooks/debugging-strategies.md) or check GitHub issues.
