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
