# TWS Robot - API Reference

**Developer documentation for extending and customizing TWS Robot.**

---

## 📚 Documentation Navigation

**You are here:** API Reference - Developer documentation  
**New to coding?** [Your First 30 Minutes](GETTING_STARTED_30MIN.md) - Start here instead ⭐  
**Want to contribute?** [Contributing Guide](CONTRIBUTING.md) - Development workflow  
**Start here:** [README](../README.md) - Installation and overview  
**Learn concepts:** [User Guide](USER_GUIDE.md) - How strategies work  
**Quick lookup:** [Quick Reference](QUICK_REFERENCE.md) - Commands cheat sheet

**Need help?**
- [Adding New Strategy](runbooks/adding-new-strategy.md) - Step-by-step guide
- [Debugging Guide](runbooks/debugging-strategies.md) - Troubleshooting
- [Architecture Overview](architecture/overview.md) - System design
- [Web API Reference](WEB_API_REFERENCE.md) - REST API for web dashboard

---

## 📚 Table of Contents

1. [Strategy Development API](#strategy-development-api)
2. [Risk Management API](#risk-management-api)
3. [Backtest Engine API](#backtest-engine-api)
4. [Data Management API](#data-management-api)
5. [Event System API](#event-system-api)
6. [Core Modules API](#core-modules-api)
7. [Common Patterns](#common-patterns)

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

### Strategy-Aware Drawdown Tracking

The RiskManager now provides separate tracking for stock-only positions vs. short options, preventing false emergency stops from option premium fluctuations.

#### Stock-Only Drawdown

Tracks drawdown for long stock positions, excluding short option mark-to-market:

```python
from risk.risk_manager import RiskManager

risk_mgr = RiskManager(
    initial_capital=100000.0,
    max_drawdown_pct=0.15,  # 15% stock drawdown triggers emergency stop
    emergency_stop_enabled=True
)

# Update with total equity
metrics = risk_mgr.update(equity=105000, positions={}, timestamp=datetime.now())

# Check stock-specific metrics
print(f"Stock Drawdown: {metrics.stock_drawdown_pct:.2%}")
print(f"Stock Equity: ${risk_mgr.stock_equity:,.2f}")
print(f"Peak Stock Equity: ${risk_mgr.peak_stock_equity:,.2f}")

# Emergency stop triggers on stock_drawdown_pct, not total drawdown_pct
if metrics.risk_status == RiskStatus.EMERGENCY_STOP:
    print("Emergency stop triggered by stock position losses")
```

**How It Works:**

- **Without position data**: `stock_equity` mirrors total `equity` (fallback mode)
- **With positions**: `stock_equity = cash_balance + sum(market_value for LONG STK positions)`
- Short option positions are excluded from stock equity calculations
- Emergency stops trigger when `stock_drawdown_pct` exceeds `max_drawdown_pct`

#### Premium Retention for Short Options

Tracks collected premium vs. current liability for short option positions:

```python
# Metrics include premium retention data
print(f"Premium Collected: ${metrics.short_options_premium_collected:,.2f}")
print(f"Current Liability: ${metrics.short_options_current_liability:,.2f}")
print(f"Premium Retention: {metrics.premium_retention_pct:.1%}")

# Calculate how much premium has been given back
giveback = metrics.short_options_premium_collected - metrics.short_options_current_liability
print(f"Premium Giveback: ${giveback:,.2f}")
```

**Premium Retention Formula:**
```
premium_retention_pct = 1 - (current_liability / premium_collected)
```

- `1.0` (100%) = Retaining all collected premium (options expired or decreased in value)
- `0.85` (85%) = Given back 15% of premium to mark-to-market
- `0.0` (0%) = Current liability equals collected premium (break-even)

#### Integration with ServiceManager

When using the web dashboard, position data is automatically processed:

```python
from web.services import get_services

services = get_services()

# After TWSBridge updates positions, ServiceManager automatically calls
# recompute_strategy_metrics() to update stock_equity and premium tracking
services.update_position("AAPL", {
    "quantity": 100,
    "side": "LONG",
    "sec_type": "STK",
    "market_value": 15000.00,
    # ... other fields
})

# This triggers:
# - Stock equity recalculation (cash + long stock value)
# - Premium retention updates (if short options exist)
# - Risk manager state updates

# Access updated metrics
risk = services.risk_manager.get_risk_summary()
print(f"Stock Drawdown: {risk['stock_drawdown_pct']:.2%}")
```

#### Use Case: Covered Call Strategy

Strategy-aware tracking prevents false stops when selling covered calls:

```python
# Scenario: Long 1000 shares AAPL @ $150, sold 10 covered calls
# Stock rises to $165 (+10% gain)
# Calls rise from $2 to $8 premium ($6 loss per call)

positions = {
    "AAPL": {
        "quantity": 1000,
        "side": "LONG",
        "sec_type": "STK",
        "entry_price": 150.00,
        "current_price": 165.00,
        "market_value": 165000.00,
        "unrealized_pnl": 15000.00  # +$15k profit
    },
    "AAPL_CALL": {
        "quantity": -10,
        "side": "SHORT",
        "sec_type": "OPT",
        "premium_collected": 2000.00,    # Collected $2 * 10 * 100
        "current_liability": 8000.00,    # Now worth $8 * 10 * 100
        "unrealized_pnl": -6000.00       # -$6k loss
    }
}

# Traditional drawdown: ($165k stock - $6k calls) - $150k start = +$9k (+6%)
# Stock drawdown: $165k - $150k = +$15k (+10%) ← No emergency stop
# Premium retention: 1 - (8000 / 2000) = -3.0 (gave back 300% - need more premium!)

# Emergency stops won't trigger because stock positions are profitable
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

### MarketOverviewService - Global Market Indices

The `MarketOverviewService` fetches and caches real-time data for major global market indices from Yahoo Finance.

#### Overview

Tracks 14 major indices across US, European, and Asian markets including S&P 500, Dow Jones, Nasdaq, VIX, FTSE 100, DAX, Nikkei 225, Hang Seng, and more. Data is cached for 5 minutes with automatic background refresh.

#### Basic Usage

```python
from data.market_overview import get_market_overview_service

# Get singleton instance
svc = get_market_overview_service()

# Get latest market overview (from cache or DB)
overview = svc.get_overview()

# Access data
snapshots = overview["snapshots"]
for snap in snapshots:
    print(f"{snap['name']}: ${snap['price']} ({snap['change_pct']:.2f}%)")

# Check market status
status = overview["market_status"]
if status["US"] == "open":
    print("US markets are open")

# Get sparklines for charts
sparklines = overview["sparklines"]
sp500_trend = sparklines["^GSPC"]  # 5-day close prices
```

#### Manual Refresh

```python
# Trigger immediate refresh (blocks until complete)
fresh_data = svc.refresh()

# Refresh runs automatically in background when data is stale (>5 min),
# but you can force a refresh if needed
```

#### Data Model

Each snapshot contains:

```python
{
    "symbol": "^GSPC",           # Index ticker
    "name": "S&P 500",           # Display name
    "region": "US",              # US / Europe / Asia
    "price": 5234.18,            # Current price
    "change": 12.45,             # Absolute change from previous close
    "change_pct": 0.24,          # Percentage change
    "day_high": 5245.67,         # Day's high
    "day_low": 5220.34,          # Day's low
    "prev_close": 5221.73,       # Previous close
    "volume": null,              # Volume (often null for indices)
    "timestamp": "2026-04-17T14:30:00+00:00",
    "market_date": "2026-04-17"
}
```

#### Tracked Indices

**US:**
- S&P 500 (^GSPC), Dow Jones (^DJI), Nasdaq (^IXIC), Russell 2000 (^RUT), VIX (^VIX)

**Europe:**
- FTSE 100 (^FTSE), DAX (^GDAXI), Euro Stoxx 50 (^STOXX50E), CAC 40 (^FCHI)

**Asia:**
- Nikkei 225 (^N225), Hang Seng (^HSI), Shanghai Composite (000001.SS), KOSPI (^KS11), ASX 200 (^AXJO)

#### Market Status Detection

```python
# Get market open/closed status by region
status = svc.get_overview()["market_status"]

if status["US"] == "open":
    print("NYSE/Nasdaq trading hours")
if status["Europe"] == "open":
    print("LSE/Xetra trading hours")
if status["Asia"] == "open":
    print("TSE/HSI trading hours")
```

**Note:** Market status is a heuristic based on typical trading hours in UTC. It does not account for holidays.

#### Integration with Dashboard

The service is automatically used by the web dashboard to display the market overview section:

```python
# In your Flask route (handled automatically by dashboard)
from data.market_overview import get_market_overview_service

@app.route("/dashboard")
def dashboard():
    svc = get_market_overview_service()
    overview = svc.get_overview()
    return render_template("dashboard.html", market_data=overview)
```

#### Database Persistence

Market snapshots are stored in SQLite for:
- Offline viewing when Yahoo Finance is unavailable
- Historical sparklines (5-day trends)
- Reduced API calls through caching

```python
# Snapshots are automatically persisted to database
# Old snapshots (>30 days) are periodically cleaned up
```

#### Configuration

Service configuration is built-in with sensible defaults:

```python
# Cache TTL: 5 minutes (300 seconds)
# Sparkline history: 5 days
# Tracked indices: Defined in INDEX_DEFINITIONS dict

# To customize tracked indices, modify data/market_overview.py:
INDEX_DEFINITIONS = {
    "^GSPC": {"name": "S&P 500", "region": "US"},
    # Add your custom indices here
}
```

#### Error Handling

```python
try:
    overview = svc.get_overview()
    if not overview["snapshots"]:
        print("No market data available - check yfinance installation")
except Exception as exc:
    print(f"Market data error: {exc}")
    # Service returns cached/empty data on errors
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

## Core Modules API

### TWSBridge - TWS Connection Bridge

The `TWSBridge` module manages real-time connections to Interactive Brokers TWS/Gateway, forwarding account and portfolio updates to the web dashboard.

#### Overview

`TWSBridge` acts as a bridge between the IB API and the `ServiceManager`, automatically forwarding:
- Account updates (equity, cash, buying power)
- Portfolio updates (positions, P&L)
- Connection events (connected, disconnected, errors)

#### Basic Usage

```python
from core.tws_bridge import TWSBridge
from web.services import get_services

# Get service manager
service_manager = get_services()

# Configure connection
config = {
    "host": "127.0.0.1",
    "port": 7497,           # Paper trading: 7497, Live: 7496
    "client_id": 1,
    "account": "DU12345"    # Your account number
}

# Create and connect bridge
bridge = TWSBridge(service_manager, config)
connected = bridge.connect(timeout=10)

if connected:
    print(f"Connected to TWS")
    print(f"Status: {bridge.is_connected}")
    # Bridge now automatically forwards all updates

# Later, disconnect
bridge.disconnect()
```

#### Connection Management

```python
# Connect with custom timeout
success = bridge.connect(timeout=15)  # Wait up to 15 seconds

# Check connection status
if bridge.is_connected:
    print("Bridge is connected and ready")

# Disconnect gracefully
bridge.disconnect()
```

#### Automatic Data Forwarding

The bridge automatically forwards TWS callbacks:

**Account Updates:**
- `TotalCashBalance` → `service_manager.update_account_summary({"cash_balance": value})`
- `NetLiquidationByCurrency` → Updates equity and risk manager
- `BuyingPower` → `service_manager.update_account_summary({"buying_power": value})`

**Portfolio Updates:**
- Position changes → `service_manager.update_position(symbol, position_data)`
- Zero positions → `service_manager.remove_position(symbol)`
- P&L updates → Included in position data

**Events Published:**
- `EventType.CONNECTION_LOST` - When TWS connection drops
- `EventType.ACCOUNT_UPDATE` - On account value changes
- `EventType.PORTFOLIO_UPDATE` - On position changes

#### Error Handling

```python
try:
    bridge = TWSBridge(service_manager, config)
    if not bridge.connect(timeout=10):
        print("Connection timeout - TWS may not be running")
except Exception as exc:
    print(f"Bridge error: {exc}")
finally:
    if bridge:
        bridge.disconnect()
```

#### Integration with ServiceManager

```python
from web.services import get_services

services = get_services()

# After bridge connects, data is available via ServiceManager:
account = services.get_account_summary()
print(f"Equity: ${account['equity']:,.2f}")
print(f"Cash: ${account['cash_balance']:,.2f}")

positions = services.get_positions()
for symbol, pos in positions.items():
    print(f"{symbol}: {pos['quantity']} shares @ ${pos['current_price']}")
```

### ServiceManager - Web Dashboard Backend

The `ServiceManager` acts as the central singleton for managing state in the web dashboard.

#### Accessing ServiceManager

```python
from web.services import get_services

# Get singleton instance
services = get_services()
```

#### Connection State

```python
# Check connection
if services.connected:
    print(f"Connected to {services.connection_env}")  # "paper" or "live"
    print(f"Info: {services.connection_info}")

# Set connection state (typically done by TWSBridge)
services.set_connected("paper", {
    "host": "127.0.0.1",
    "port": 7497,
    "client_id": 1,
    "account": "DU12345"
})

# Disconnect
services.set_disconnected()
```

#### TWS Bridge Integration

```python
# Connect via TWSBridge
success = services.connect_tws(env="paper", config=tws_config, timeout=10)

# Disconnect
services.disconnect_tws()
```

#### Account Data

```python
# Get account summary
summary = services.get_account_summary()
# Returns: {"equity": float, "cash_balance": float, "buying_power": float, ...}

# Update account summary (called by TWSBridge)
services.update_account_summary({"equity": 105000.0, "cash_balance": 50000.0})

# Get calculated account insights (NEW in v1.5)
insights = services.get_account_insights()
# Returns: {
#   "total_unrealized_pnl": float,    # Sum of all positions' unrealized P&L
#   "daily_pnl_dollar": float,        # Dollar P&L for today (equity - daily_start_equity)
#   "buying_power": float             # Current buying power
# }
# This is the single source of truth for derived metrics used by
# both the dashboard and the /api/account/summary endpoint.

# Example: Display account insights in dashboard
insights = services.get_account_insights()
print(f"Total Unrealized P&L: ${insights['total_unrealized_pnl']:,.2f}")
print(f"Today's P&L: ${insights['daily_pnl_dollar']:,.2f}")
print(f"Buying Power: ${insights['buying_power']:,.2f}")

# Example: Used by API endpoints to avoid duplicating calculation logic
# (from web/routes/api_account.py)
@bp.route("/summary", methods=["GET"])
def summary():
    svc = get_services()
    risk = svc.risk_manager.get_risk_summary()
    account = svc.get_account_summary()
    insights = svc.get_account_insights()  # Single source of truth
    
    return jsonify({
        "equity": risk.get("current_equity", 0),
        "daily_pnl_dollar": insights["daily_pnl_dollar"],  # From insights
        "unrealized_pnl": insights["total_unrealized_pnl"],  # From insights
        "buying_power": insights["buying_power"],  # From insights
        # ... other fields
    })
```

#### Position Management

```python
# Get all positions
positions = services.get_positions()
# Returns: {"AAPL": {...}, "MSFT": {...}}

# Update a position (called by TWSBridge)
services.update_position("AAPL", {
    "quantity": 100,
    "entry_price": 145.00,
    "current_price": 150.00,
    "market_value": 15000.00,
    "unrealized_pnl": 500.00,
    "unrealized_pnl_pct": 3.45,
    "realized_pnl": 0.00,
    "side": "LONG"
})

# Remove a position
services.remove_position("AAPL")
```

#### Strategy-Aware Metrics Computation

```python
# Recompute stock-only equity and short-option premium aggregates
# (automatically called after portfolio updates, but can be triggered manually)
services.recompute_strategy_metrics()

# This updates the risk manager with:
# - stock_equity: cash_balance + sum(market_value for LONG STK positions)
# - peak_stock_equity: highest stock_equity reached
# - short_options_premium_collected: sum of premium from SHORT OPT positions
# - short_options_current_liability: sum of current mark-to-market for SHORT OPT

# The method intelligently handles position types:
positions = {
    "AAPL": {
        "side": "LONG",
        "sec_type": "STK",           # Included in stock_equity
        "market_value": 15000.00
    },
    "AAPL_CALL": {
        "side": "SHORT",
        "sec_type": "OPT",           # Tracked separately for premium retention
        "premium_collected": 2000.00,
        "current_liability": 1500.00
    },
    "SPY_PUT": {
        "side": "LONG",
        "sec_type": "OPT",           # Excluded from stock_equity (not a stock)
        "market_value": 3000.00
    }
}

# After recompute_strategy_metrics():
# stock_equity = cash_balance + 15000 (only AAPL stock)
# short_options_premium_collected = 2000
# short_options_current_liability = 1500
# premium_retention_pct = 1 - (1500 / 2000) = 0.25 (25% retained)
```

**When to Call:**

- **Automatically called**: After `update_position()`, `remove_position()`, or `update_account_summary()` with cash balance changes
- **Manual call**: When positions are bulk-updated or you need to force recalculation
- **Requires**: `cash_balance` must be present in account summary (skips silently otherwise)

**Thread Safety:**

The method is thread-safe (uses internal lock) and safe to call from TWSBridge callbacks.

```python
# Example: Manual recalculation after bulk position update
services._positions = {
    # ... bulk position data from external source
}
services.recompute_strategy_metrics()  # Update derived metrics
```

#### Portfolio Analysis

```python
# Get comprehensive portfolio analysis (concentration, attribution, drawdown)
# (NEW in v1.6 - PR #14)
analysis = services.get_portfolio_analysis()

# Returns a dictionary with:
{
    "allocation": [
        {
            "symbol": "AAPL",
            "market_value": 15000.00,
            "weight": 0.48,               # 48% of portfolio
            "unrealized_pnl": 500.00
        },
        {
            "symbol": "MSFT",
            "market_value": 10000.00,
            "weight": 0.32,               # 32% of portfolio
            "unrealized_pnl": -200.00
        }
        # ... more positions
    ],
    "total_value": 31000.00,              # Total gross market value
    
    "concentration": {
        "herfindahl_index": 0.31,         # HHI: 0-1 (1=concentrated, 0=diversified)
        "top_position_pct": 0.48,         # Largest position weight
        "top_3_positions_pct": 0.85,      # Top 3 combined weight
        "top_5_positions_pct": 0.95       # Top 5 combined weight
    },
    
    "diversification": {
        "score": 68.5,                    # 0-100 (100=well diversified)
        "effective_positions": 3.2        # Effective number of independent positions
    },
    
    "sector_exposure": {
        "Technology": 0.65,               # 65% in tech sector
        "Healthcare": 0.25,               # 25% in healthcare
        "Finance": 0.10                   # 10% in finance
    },
    
    "risk_flags": {
        "is_concentrated": true,          # HHI > 0.25
        "has_high_correlations": false,   # Any pair correlation > 0.8
        "sector_risk": true               # Single sector > 50%
    },
    
    "drawdown": {
        "current_pct": 0.045,             # 4.5% drawdown from peak
        "peak_equity": 110000.00,
        "current_equity": 105000.00
    },
    
    "attribution": {
        "by_symbol": [
            {"name": "AAPL", "pnl": 1250.00},
            {"name": "MSFT", "pnl": 850.00},
            {"name": "TSLA", "pnl": -300.00}
        ],
        "by_strategy": [
            {"name": "momentum", "pnl": 2100.00},
            {"name": "mean_reversion", "pnl": -200.00}
        ],
        "win_rate": 0.625,                # 62.5% of trades profitable
        "total_pnl": 1800.00
    },
    
    "suggestions": [
        "Portfolio is concentrated (HHI=0.31). Consider adding 2-3 more positions.",
        "Technology sector exposure (65%) exceeds diversification threshold. Reduce to <50%.",
        "Top position (AAPL) represents 48% of portfolio. Reduce to <25% for better risk management."
    ]
}
```

**What It Provides:**

- **Allocation**: Per-symbol breakdown with weights and P&L
- **Concentration Metrics**: Herfindahl-Hirschman Index (HHI) and top-N concentration percentages
- **Diversification Score**: 0-100 rating based on position count, weights, and correlations
- **Sector Exposure**: Portfolio weight distribution across sectors
- **Risk Flags**: Automated warnings for concentration, correlation, and sector risks
- **Drawdown Tracking**: Current drawdown from peak equity
- **P&L Attribution**: Performance breakdown by symbol and by strategy (from closed trades)
- **Actionable Suggestions**: Specific recommendations for improving diversification

**When to Use:**

- Dashboard portfolio analysis tab (called automatically on page load)
- API endpoint: `GET /api/account/portfolio-analysis`
- Periodic risk reviews (check concentration and correlation risks)
- Strategy performance analysis (attribution breakdown)

**Dependencies:**

This method combines data from:

- **CorrelationAnalyzer** (`risk/correlation_analyzer.py`): Calculates concentration metrics (HHI), sector exposure, and diversification scores
- **PerformanceAttribution** (`strategies/performance_attribution.py`): Analyzes P&L sources from closed trades, attributing performance by symbol, strategy, date, etc.
- **RiskManager**: Provides peak equity and current equity for drawdown calculation

**Example: Portfolio Health Check**

```python
from web.services import get_services

services = get_services()
analysis = services.get_portfolio_analysis()

# Check concentration risk
if analysis["risk_flags"]["is_concentrated"]:
    hhi = analysis["concentration"]["herfindahl_index"]
    print(f"⚠️ Portfolio concentrated (HHI={hhi:.2f})")
    for suggestion in analysis["suggestions"]:
        print(f"  💡 {suggestion}")

# Check top position exposure
top_pct = analysis["concentration"]["top_position_pct"]
if top_pct > 0.25:
    print(f"⚠️ Largest position is {top_pct:.1%} of portfolio (target: <25%)")

# Check sector concentration
for sector, weight in analysis["sector_exposure"].items():
    if weight > 0.50:
        print(f"⚠️ {sector} sector exposure ({weight:.1%}) exceeds 50% threshold")

# Review performance attribution
print("\n📊 Top Performers:")
for item in analysis["attribution"]["by_symbol"][:3]:
    print(f"  {item['name']}: ${item['pnl']:,.2f}")

print(f"\n🎯 Win Rate: {analysis['attribution']['win_rate']:.1%}")
print(f"💰 Total P&L: ${analysis['attribution']['total_pnl']:,.2f}")
```

**Thread Safety:**

This method is read-only and safe to call from any thread. It internally creates temporary analyzer instances and doesn't modify shared state.

**Performance Note:**

Portfolio analysis involves calculating correlations and metrics across all positions. For portfolios with 100+ positions, this may take 1-2 seconds. The dashboard caches results and handles exceptions gracefully to avoid blocking page loads.

#### Order Management

```python
# Get all orders
orders = services.get_orders()
# Returns: [{"id": "ord_1", "symbol": "AAPL", ...}, ...]

# Add an order
services.add_order({
    "id": "ord_123",
    "symbol": "AAPL",
    "action": "BUY",
    "quantity": 100,
    "status": "SUBMITTED"
})
```

#### Alert Management

```python
# Get alerts
alerts = services.get_alerts()
# Returns: [{"id": "alert_1", "level": "WARNING", ...}, ...]

# Add an alert
services.add_alert({
    "id": "alert_2",
    "level": "WARNING",
    "type": "RISK_LIMIT",
    "message": "Daily loss limit approaching",
    "timestamp": "2026-04-15T14:30:00Z"
})

# Dismiss an alert
dismissed = services.dismiss_alert("alert_1")  # Returns True if found
```

#### Backtest Management

```python
# Store backtest run
services.store_backtest_run("bt_123", {
    "strategy_name": "Bollinger Bands",
    "status": "complete",
    "final_equity": 112500.00,
    "created": "2026-04-15T10:00:00Z"
})

# List all runs
runs = services.list_backtest_runs()
# Returns: [{"run_id": "bt_123", ...}, ...]

# Get specific run
run = services.get_backtest_run("bt_123")
# Returns: {"run_id": "bt_123", "strategy_name": ..., ...}
```

#### System Health

```python
# Get system health status
health = services.get_system_health()
# Returns: {
#   "status": "ok",
#   "uptime_seconds": 3600,
#   "connected": True,
#   "strategies_running": 0,
#   "last_heartbeat": "2026-04-15T15:45:00Z"
# }
```

#### Event Bus Integration

```python
# ServiceManager has an event bus for real-time updates
from core.event_bus import EventType

def on_account_update(event):
    print(f"Account updated: {event.data}")

services.event_bus.subscribe(EventType.ACCOUNT_UPDATE, on_account_update)
```

### OrderManager - Order Execution

```python
from core.order_manager import OrderManager, Order, OrderType

# Initialize order manager
ib_client = EClient()  # Your IB API client
order_mgr = OrderManager(ib_client)

# Submit market order
order = order_mgr.submit_market_order(
    symbol="AAPL",
    action="BUY",
    quantity=100
)

# Submit limit order
order = order_mgr.submit_limit_order(
    symbol="AAPL",
    action="BUY",
    quantity=100,
    limit_price=148.50
)

# Cancel order
order_mgr.cancel_order(order_id)

# Get order status
status = order_mgr.get_order_status(order_id)
```

### ContractBuilder - Create IB Contracts

```python
from core.contract_builder import ContractBuilder

# Build stock contract
contract = ContractBuilder.stock("AAPL", "SMART", "USD")

# Build option contract
contract = ContractBuilder.option(
    symbol="AAPL",
    strike=150.0,
    expiry="20260619",  # YYYYMMDD
    right="C",  # Call
    exchange="SMART"
)

# Build futures contract
contract = ContractBuilder.future(
    symbol="ES",
    expiry="202606",
    exchange="CME"
)
```

### AIClient - OpenAI Integration

The `ai.client` module provides a thin wrapper around OpenAI's API with automatic retry logic and environment-based configuration.

#### Configuration

AI features are configured via environment variables (in `.env`):

```bash
# Auto-enable AI when API key is present
OPENAI_API_KEY=sk-...

# Optional: Choose model (default: gpt-4o)
OPENAI_MODEL=gpt-4o

# Optional: Force-disable AI even with key present
AI_ENABLED=false
```

**Behavior:**
- When `OPENAI_API_KEY` is set → AI auto-enabled
- When `AI_ENABLED=false` → AI disabled (even with key)
- When `AI_ENABLED=true` → AI enabled (but requires key to work)

#### Check AI Status

```python
from ai.client import is_ai_enabled

if is_ai_enabled():
    print("AI features are enabled")
else:
    print("AI features are disabled")
```

**Use Case:** Routes and features can check `is_ai_enabled()` to conditionally show/hide AI-powered functionality.

```python
# Example: Settings page shows AI status
from ai.client import is_ai_enabled

def settings_view():
    return {
        "ai_enabled": is_ai_enabled(),
        "has_api_key": bool(os.getenv("OPENAI_API_KEY", "").strip()),
        "model": os.getenv("OPENAI_MODEL", "gpt-4o")
    }
```

#### Get AI Client

```python
from ai.client import get_client

# Returns AIClient instance or None
client = get_client()

if client:
    # AI is enabled and configured
    reply = client.chat([
        {"role": "user", "content": "Analyze this trading strategy"}
    ])
    print(reply)
else:
    print("AI not available - check OPENAI_API_KEY in .env")
```

#### Chat Completion

```python
from ai.client import get_client

client = get_client()
if not client:
    return  # AI disabled

# Basic chat
messages = [
    {"role": "system", "content": "You are a trading strategy advisor."},
    {"role": "user", "content": "Explain Bollinger Bands"}
]

reply = client.chat(messages)
print(reply)

# Custom temperature (default: 0.3)
reply = client.chat(
    messages,
    temperature=0.7  # More creative responses
)

# Override model per-call
reply = client.chat(
    messages,
    model="gpt-3.5-turbo"  # Use faster/cheaper model
)
```

#### Error Handling & Retries

The AI client automatically retries on rate limits with exponential backoff (max 3 attempts):

```python
from ai.client import get_client

client = get_client()

try:
    reply = client.chat(messages)
except RuntimeError as exc:
    print(f"AI request failed after retries: {exc}")
    # Handle gracefully - show cached response or disable feature
```

**Retry Behavior:**
- **Rate limits:** Automatically retry with exponential backoff (2s, 4s, 8s)
- **API errors:** No retry, fails immediately
- **Other errors:** No retry, fails immediately

#### Reset Configuration

Call `reset_client()` after changing environment variables:

```python
from ai.client import reset_client
import os

# Change configuration
os.environ["OPENAI_API_KEY"] = "new-key"
os.environ["OPENAI_MODEL"] = "gpt-4"

# Reset to pick up new values
reset_client()

# Next get_client() call uses new config
client = get_client()
```

**Use Case:** Hot-reloading AI config without restarting the application.

#### Integration Example: Strategy Analysis

```python
from ai.client import get_client

def analyze_strategy(strategy_code: str) -> str:
    """Use AI to analyze a trading strategy."""
    client = get_client()
    
    if not client:
        return "AI analysis not available (set OPENAI_API_KEY)"
    
    messages = [
        {
            "role": "system",
            "content": "You are an expert at analyzing trading strategies. "
                      "Provide concise, actionable feedback."
        },
        {
            "role": "user",
            "content": f"Analyze this strategy:\n\n{strategy_code}"
        }
    ]
    
    try:
        reply = client.chat(messages, temperature=0.3)
        return reply
    except RuntimeError as exc:
        return f"Analysis failed: {exc}"

# Usage
strategy_code = """
class MyStrategy(Strategy):
    def on_bar(self, market_data):
        # Buy when RSI < 30
        if rsi < 30:
            self.buy("AAPL", 100)
"""

analysis = analyze_strategy(strategy_code)
print(analysis)
```

### Portfolio Intelligence - AI-Powered Portfolio Analysis

**NEW in v1.7 (PR #17)** - AI-powered portfolio strategy deduction and stock deep-dive analysis.

The portfolio intelligence system combines rule-based heuristics with optional LLM narration to:
- Deduce trading strategies from position characteristics
- Generate portfolio-level insights and recommendations
- Provide on-demand deep-dive analysis for individual stocks
- Track portfolio evolution via snapshots

#### PortfolioAnalyzer - Strategy Deduction

Analyzes your entire portfolio to deduce what strategies are being employed and provides AI-powered insights.

```python
from ai.portfolio_analyzer import PortfolioAnalyzer

analyzer = PortfolioAnalyzer()

# Get positions from ServiceManager
from web.services import get_services
svc = get_services()
positions = svc.get_positions()
account_summary = svc.get_account_summary()
account_summary["equity"] = svc.risk_manager.current_equity

# Analyze with AI narration (default)
result = analyzer.analyze_portfolio(
    positions,
    account_summary=account_summary,
    use_ai=True  # Enable AI narrative and recommendations
)

# Access results
for pos in result["positions_enriched"]:
    print(f"{pos['symbol']}: {pos['deduced_strategy']} "
          f"({pos['strategy_confidence']:.1%} confidence)")

# Strategy mix breakdown
print(f"\nStrategy Mix: {result['strategy_mix']}")
# {'momentum': 0.35, 'buy_and_hold': 0.45, 'income': 0.20}

# AI-powered narrative
print(f"\n{result['ai_narrative']}")

# AI recommendations
for rec in result['ai_recommendations']:
    print(f"💡 {rec}")

# AI risk assessment
print(f"\n⚠️ {result['ai_risk_assessment']}")
```

**Strategy Classification:**

The analyzer uses rule-based heuristics to classify each position:

| Strategy | Detection Rules |
|----------|----------------|
| **Momentum** | Short-term holding (< 5 days), positive P&L momentum |
| **Mean Reversion** | Short-term (< 5 days), negative entry momentum |
| **Buy and Hold** | Long-term holding (> 90 days) |
| **Value** | Medium/long-term, positive fundamentals (P/E, P/B) |
| **Income** | Dividend-paying stocks, income-focused |
| **Speculative** | High volatility, rapid position changes |
| **Hedging** | Protective positions (puts, inverse ETFs) |
| **Covered Call** | **NEW** Long stock + short call(s) on same underlying (income/exit strategy) |
| **Protective Put** | **NEW** Long stock + long put(s) on same underlying (downside protection) |
| **Collar** | **NEW** Long stock + short call + long put (capped upside/downside) |

**Return Value:**

```python
{
    "positions_enriched": [
        {
            "symbol": "AAPL",
            "deduced_strategy": "buy_and_hold",
            "strategy_confidence": 0.85,
            "holding_days": 120.5,
            "unrealized_pnl_pct": 15.2,
            "position_type": "core",  # 'core' or 'satellite'
            "risk_level": "moderate",
            # ... original position data
        },
        # ... more positions
    ],
    "strategy_mix": {
        "buy_and_hold": 0.50,
        "momentum": 0.30,
        "income": 0.20
    },
    "multi_leg_strategies": [
        {
            "strategy": "covered_call",
            "underlying": "GOOG",
            "legs": ["GOOG", "GOOG 260515C00200000"],
            "description": "Covered call on GOOG: the short call(s) are backed by the long stock position..."
        }
    ],
    "ai_narrative": "Your portfolio demonstrates a balanced approach...",
    "ai_recommendations": [
        "Consider reducing momentum allocation from 30% to 20%",
        "Tech sector concentration (45%) exceeds diversification threshold"
    ],
    "ai_risk_assessment": "Moderate risk profile with some concentration concerns",
    "ai_strategy_mix": "Core-satellite structure with 50% long-term holds"
}
```

**When AI is Disabled (`use_ai=False`):**

- `ai_narrative`, `ai_recommendations`, `ai_risk_assessment`, `ai_strategy_mix` will be `None`
- Strategy deduction still works using rule-based classification
- Significantly faster (no LLM API calls)

#### StockAnalyzer - Deep-Dive Analysis

Performs comprehensive analysis of individual stocks combining fundamentals, technicals, and position data.

```python
from ai.stock_analyzer import StockAnalyzer

analyzer = StockAnalyzer()

# Get position data
position = svc.get_positions()["AAPL"]

# Fetch fundamentals
from data.fundamentals import get_fundamentals
fundamentals = get_fundamentals("AAPL")

# Compute technical context (from price history)
history = [...]  # List of OHLCV dicts
from ai.stock_analyzer import compute_technical_context
technicals = compute_technical_context(
    current_price=position.get("current_price", 0),
    history=history
)

# Analyze with AI deep-dive
result = analyzer.analyze_stock(
    symbol="AAPL",
    position=position,
    fundamentals=fundamentals,
    technicals=technicals,
    use_ai=True
)

print(result["ai_analysis"])
```

**Return Value:**

```python
{
    "symbol": "AAPL",
    "position_summary": {
        "quantity": 100,
        "market_value": 17500.0,
        "unrealized_pnl": 2500.0,
        "unrealized_pnl_pct": 16.7,
        "holding_days": 45.2
    },
    "fundamental_summary": {
        "pe_trailing": 28.5,
        "pe_forward": 25.3,
        "market_cap": 2800000000000,
        "dividend_yield": 0.0045,
        "analyst_target_mean": 185.0
    },
    "technical_summary": {
        "current_price": 175.0,
        "sma_50": 168.5,
        "sma_200": 155.2,
        "rsi_14": 62.3,
        "weeks_52_high": 185.0,
        "weeks_52_low": 140.0
    },
    "ai_analysis": "AAPL demonstrates strong momentum with price above both 50 and 200-day moving averages. RSI at 62.3 indicates healthy bullish momentum without overbought conditions. Valuation appears fair with forward P/E of 25.3 slightly below industry average. Consider taking partial profits if price approaches $185 resistance (52-week high and analyst target).",
    "timestamp": "2026-04-18T12:30:00Z"
}
```

**Technical Context Calculation:**

```python
from ai.stock_analyzer import compute_technical_context

history = [
    {"close": 170.0, "high": 171.0, "low": 169.0, "volume": 50000000},
    {"close": 172.0, "high": 173.0, "low": 170.5, "volume": 55000000},
    # ... more bars (needs 200+ for full analysis)
]

technicals = compute_technical_context(
    current_price=175.0,
    history=history
)

# Returns:
# {
#     "current_price": 175.0,
#     "sma_50": 168.5,      # 50-day simple moving average
#     "sma_200": 155.2,     # 200-day simple moving average
#     "rsi_14": 62.3,       # 14-period RSI
#     "weeks_52_high": 185.0,
#     "weeks_52_low": 140.0,
#     "distance_from_high_pct": -5.4,  # % below 52-week high
#     "distance_from_low_pct": 25.0    # % above 52-week low
# }
```

#### Fundamentals Fetcher

Retrieves and caches stock fundamental data via yfinance.

```python
from data.fundamentals import get_fundamentals

# Fetch with caching (24-hour TTL)
data = get_fundamentals("GOOG", use_cache=True)

# Force fresh fetch
data = get_fundamentals("GOOG", use_cache=False)

# Returns comprehensive fundamental data:
{
    "symbol": "GOOG",
    "fetched_at": "2026-04-18T12:00:00Z",
    "name": "Alphabet Inc.",
    "sector": "Technology",
    "industry": "Internet Content & Information",
    "market_cap": 1800000000000,
    
    # Valuation ratios
    "pe_trailing": 25.3,
    "pe_forward": 22.1,
    "peg_ratio": 1.45,
    "price_to_book": 6.2,
    "price_to_sales": 5.8,
    
    # Profitability
    "profit_margin": 0.21,
    "operating_margin": 0.26,
    "gross_margin": 0.57,
    "roe": 0.28,
    
    # Growth metrics
    "revenue_growth": 0.14,
    "earnings_growth": 0.18,
    
    # Dividend info (if applicable)
    "dividend_yield": 0.0,
    "payout_ratio": None,
    
    # Analyst consensus
    "analyst_target_mean": 165.0,
    "analyst_target_high": 200.0,
    "analyst_target_low": 130.0,
    "recommendation": "buy"  # buy, hold, sell
}
```

**Caching:**

- Fundamentals are cached in SQLite for 24 hours
- Reduces API calls to yfinance
- Configurable TTL via `_CACHE_TTL_SECONDS` constant

**Data Sanitization:**

**NEW in v1.7.1 (PR #18)** - Automatic sanitization of invalid numeric values.

yfinance occasionally returns placeholder strings (`"?"`), `NaN`, or `Infinity` for unavailable metrics. The fundamentals fetcher automatically sanitizes all numeric fields:

```python
from data.fundamentals import get_fundamentals

data = get_fundamentals("SOME_SYMBOL")

# Invalid values are converted to None:
# - Placeholder strings: "?", "N/A", ""
# - NaN values: float('nan')
# - Infinity values: float('inf'), float('-inf')

# Example:
if data["pe_trailing"] is None:
    print("P/E ratio not available")
else:
    print(f"P/E: {data['pe_trailing']:.2f}")

# String fields (symbol, name, sector, industry) are never sanitized
print(data["name"])  # Always a string, never None
```

**Sanitization Behavior:**

| Input Value | Output | Reason |
|------------|--------|--------|
| `25.3` | `25.3` | Valid number preserved |
| `"42.5"` | `42.5` | String numbers converted |
| `"?"` | `None` | Placeholder string rejected |
| `"N/A"` | `None` | Placeholder string rejected |
| `float('nan')` | `None` | NaN rejected |
| `float('inf')` | `None` | Infinity rejected |
| `None` | `None` | Already None |

**Why Sanitization Matters:**

- Prevents frontend display errors (e.g., showing "?" instead of "--")
- Ensures numeric calculations don't fail on invalid data
- Provides consistent `None` values for missing data
- Safe for JSON serialization (NaN/Infinity are not valid JSON)

**Error Handling:**

```python
data = get_fundamentals("INVALID_SYMBOL")

if "error" in data:
    print(f"Failed to fetch: {data['error']}")
    # Returns: {"error": "...", "symbol": "INVALID_SYMBOL"}
```

#### Portfolio Persistence

Save and retrieve portfolio snapshots for historical tracking.

```python
from data.portfolio_persistence import (
    save_portfolio_snapshot,
    get_recent_snapshots,
    save_stock_analysis,
    get_latest_stock_analysis,
    get_stock_analysis_history
)

# Save current portfolio state
snapshot_id = save_portfolio_snapshot(
    positions=svc.get_positions(),
    account_summary=svc.get_account_summary(),
    strategy_analysis={
        "strategy_mix": {"buy_and_hold": 0.5, "momentum": 0.3},
        "ai_narrative": "Portfolio is well-diversified..."
    }
)

# Retrieve recent snapshots
snapshots = get_recent_snapshots(limit=10)
for snap in snapshots:
    print(f"{snap['snapshot_date']}: ${snap['total_value']:,.2f}")

# Save stock deep-dive analysis
save_stock_analysis(
    symbol="AAPL",
    position=position,
    fundamentals=fundamentals,
    technical=technicals,
    ai_analysis="Strong buy signal based on momentum..."
)

# Get latest analysis for a symbol
latest = get_latest_stock_analysis("AAPL")
if latest:
    print(f"Last analyzed: {latest['analysis_date']}")
    print(latest['ai_analysis'])

# Get analysis history
history = get_stock_analysis_history("AAPL", limit=5)
for analysis in history:
    print(f"{analysis['analysis_date']}: {analysis['ai_analysis'][:100]}...")
```

#### Usage Example: Complete Portfolio Intelligence Workflow

```python
from web.services import get_services
from ai.portfolio_analyzer import PortfolioAnalyzer
from ai.stock_analyzer import StockAnalyzer
from data.fundamentals import get_fundamentals
from data.portfolio_persistence import save_portfolio_snapshot

# 1. Analyze entire portfolio
svc = get_services()
positions = svc.get_positions()
account = svc.get_account_summary()
account["equity"] = svc.risk_manager.current_equity

portfolio_analyzer = PortfolioAnalyzer()
portfolio_result = portfolio_analyzer.analyze_portfolio(
    positions, account, use_ai=True
)

# 2. Save portfolio snapshot
snapshot_id = save_portfolio_snapshot(
    positions=positions,
    account_summary=account,
    strategy_analysis={
        "strategy_mix": portfolio_result["strategy_mix"],
        "ai_narrative": portfolio_result["ai_narrative"]
    }
)

# 3. Deep-dive on top position
top_symbol = max(positions.keys(), 
    key=lambda s: abs(positions[s].get("market_value", 0)))

stock_analyzer = StockAnalyzer()
fundamentals = get_fundamentals(top_symbol)
# ... compute technicals from price history

stock_result = stock_analyzer.analyze_stock(
    symbol=top_symbol,
    position=positions[top_symbol],
    fundamentals=fundamentals,
    technicals=technicals,
    use_ai=True
)

print(f"\n📊 Portfolio Analysis:\n{portfolio_result['ai_narrative']}")
print(f"\n🔍 Deep-Dive on {top_symbol}:\n{stock_result['ai_analysis']}")
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
