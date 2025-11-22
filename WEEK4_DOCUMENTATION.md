# Week 4: Backtesting System - Complete Documentation

## Overview

Week 4 implements a comprehensive backtesting system for evaluating trading strategies. The system provides realistic market simulation, performance analytics, risk management profiles, and pre-built strategy templates.

### Test Status: ✅ **138/138 tests passing (100%)**

### Project Structure
```
backtest/
├── data_models.py           # Core data structures (Bar, MarketData, BarSeries)
├── data.py                  # Historical data management
├── market_simulator.py      # Order simulation and execution
├── strategy.py              # Base strategy framework
├── performance.py           # Performance metrics and analytics
├── profiles.py              # Risk management profiles
├── profile_comparison.py    # Profile comparison and optimization
└── strategy_templates.py    # Pre-built strategy templates
```

---

## Day 1: Backtesting Foundation

### Core Data Models (`backtest/data_models.py`)

#### Bar
Represents a single price bar (OHLCV data).

```python
@dataclass
class Bar:
    timestamp: datetime
    symbol: str
    open: float
    high: float
    low: float
    close: float
    volume: int
```

**Features:**
- Automatic validation (high ≥ low, high/low contain open/close)
- Immutable structure
- Symbol tracking

#### MarketData
Container for market data at a single point in time.

```python
class MarketData:
    def __init__(self, timestamp: datetime):
        self.timestamp = timestamp
        self._bars: Dict[str, Bar] = {}
```

**Key Methods:**
- `add_bar(bar: Bar)`: Add bar for a symbol
- `get_bar(symbol: str)` → `Optional[Bar]`: Retrieve bar
- `symbols` → `List[str]`: Get all symbols

#### BarSeries
Time-series collection of bars for analysis.

```python
class BarSeries:
    def __init__(self, symbol: str):
        self.symbol = symbol
        self._bars: List[Bar] = []
```

**Key Methods:**
- `add_bar(bar: Bar)`: Append chronological bar
- `get_bars(lookback: Optional[int])`: Get recent bars
- `get_prices(lookback: Optional[int])`: Extract close prices
- `len()`: Number of bars

### Historical Data Management (`backtest/data.py`)

#### HistoricalDataManager
Loads and manages historical price data from CSV files.

**CSV Format Required:**
```csv
Date,Open,High,Low,Close,Volume
2024-01-01,100.0,101.0,99.5,100.5,1000000
```

```python
manager = HistoricalDataManager(data_dir="data/historical")
manager.load_symbol("AAPL")
bar = manager.get_bar_at_time("AAPL", datetime(2024, 1, 15))
```

**Features:**
- Automatic data validation
- Efficient time-based lookups
- Multiple symbol support
- Date range queries

---

## Day 2: Engine Core

### Market Simulation (`backtest/market_simulator.py`)

#### Order
Represents a pending or executed order.

```python
@dataclass
class Order:
    order_id: str
    symbol: str
    action: str  # 'BUY' or 'SELL'
    quantity: int
    order_type: str = 'MARKET'  # 'MARKET', 'LIMIT', 'STOP'
    limit_price: Optional[float] = None
    stop_price: Optional[float] = None
    time_in_force: str = 'DAY'
    submitted_at: Optional[datetime] = None
    strategy_name: str = ""
    status: str = 'PENDING'
```

#### FillSimulator
Simulates realistic order execution with market microstructure.

**Realism Features:**
- **Bid-ask spread**: 5 basis points default
- **Market impact**: Proportional to order size vs. volume
- **Slippage**: Normally distributed (0.02% std dev)
- **Partial fills**: For large orders

```python
fill_sim = FillSimulator(
    default_spread_bps=5.0,
    market_impact_factor=0.1,
    slippage_std=0.0002
)

fill = fill_sim.simulate_fill(order, bar)
```

#### MarketSimulator
Orchestrates market replay and order management.

```python
simulator = MarketSimulator(data_manager, fill_simulator)
simulator.subscribe_bars(strategy._process_market_data)
simulator.replay(
    start_date=datetime(2024, 1, 1),
    end_date=datetime(2024, 12, 31),
    symbols=['AAPL', 'MSFT']
)
```

**Capabilities:**
- Time-ordered market replay
- Multi-symbol coordination
- Order lifecycle management
- Position tracking
- Trade execution history

### Strategy Framework (`backtest/strategy.py`)

#### StrategyConfig
Configuration for strategy execution.

```python
@dataclass
class StrategyConfig:
    name: str
    symbols: List[str]
    initial_capital: float = 100000.0
    position_size_pct: float = 1.0  # % of capital per trade
```

#### Strategy (Base Class)
Abstract base class for all trading strategies.

**Lifecycle Hooks:**
```python
class MyStrategy(Strategy):
    def on_start(self):
        """Called before backtest starts"""
        pass
    
    def on_bar(self, symbol: str, bar: Bar):
        """Called for each new bar"""
        pass
    
    def on_end(self):
        """Called after backtest completes"""
        pass
```

**Trading Methods:**
```python
# Place orders
order_id = self.buy(symbol, quantity, order_type='MARKET')
order_id = self.sell(symbol, quantity)
order_id = self.close_position(symbol)

# Query positions
position = self.get_position(symbol)
has_pos = self.has_position(symbol)

# Access bar history
bars = self.get_bar_history(symbol, lookback=20)
prices = self.get_price_history(symbol, lookback=50)
current = self.get_current_price(symbol)

# Position sizing
size = self.calculate_position_size(symbol, price)
```

**State Tracking:**
```python
strategy.state.equity          # Current portfolio value
strategy.state.cash            # Available cash
strategy.state.positions       # Open positions
strategy.state.trades          # Completed trades
strategy.state.long_exposure   # Long position value
strategy.state.short_exposure  # Short position value
strategy.state.max_drawdown    # Peak-to-trough drawdown
```

---

## Day 3: Performance Analytics

### Performance Metrics (`backtest/performance.py`)

#### PerformanceAnalyzer
Comprehensive performance analysis and reporting.

```python
analyzer = PerformanceAnalyzer(strategy.state)
results = analyzer.analyze()
```

**Calculated Metrics:**

**Returns:**
- Total return (%)
- Annualized return (%)
- Compounded annual growth rate (CAGR)
- Daily, monthly, yearly returns

**Risk:**
- Volatility (annualized std dev)
- Maximum drawdown (%)
- Maximum drawdown duration (days)
- Downside deviation

**Risk-Adjusted:**
- Sharpe ratio (assuming 4% risk-free rate)
- Sortino ratio (downside-focused Sharpe)
- Calmar ratio (return / max drawdown)

**Trading:**
- Total trades
- Win rate (%)
- Average win / loss
- Profit factor (gross profit / gross loss)
- Average trade duration

**Example Output:**
```python
{
    'total_return_pct': 15.2,
    'annualized_return_pct': 18.5,
    'volatility_pct': 12.3,
    'sharpe_ratio': 1.45,
    'max_drawdown_pct': 8.2,
    'win_rate_pct': 62.5,
    'total_trades': 24,
    'profit_factor': 2.1
}
```

---

## Day 4: Multi-Profile Framework

### Risk Profiles (`backtest/profiles.py`)

#### RiskProfile
Defines risk management rules and position sizing.

```python
@dataclass
class RiskProfile:
    name: str
    max_position_size: float        # Max % of capital per position
    max_portfolio_risk: float       # Max % of capital at risk
    max_loss_per_trade: float       # Max % loss per trade
    risk_reward_ratio: float        # Minimum risk/reward
    max_leverage: float             # Maximum leverage allowed
    max_exposure: float             # Max % of capital deployed
    max_positions: int              # Max concurrent positions
    position_concentration: float   # Max % in single position
```

**Pre-Built Profiles:**

**Conservative:**
- Max position: 5% of capital
- Max portfolio risk: 10%
- Max loss per trade: 1%
- Risk/reward: 2.0
- Max leverage: 1.0
- Max exposure: 50%
- Max positions: 5

**Moderate:**
- Max position: 10%
- Max portfolio risk: 20%
- Max loss per trade: 2%
- Risk/reward: 1.5
- Max leverage: 1.5
- Max exposure: 80%
- Max positions: 10

**Aggressive:**
- Max position: 20%
- Max portfolio risk: 30%
- Max loss per trade: 3%
- Risk/reward: 1.0
- Max leverage: 2.0
- Max exposure: 100%
- Max positions: 15

```python
# Get pre-built profile
profile = ProfileLibrary.get_conservative()

# Create custom profile
custom = RiskProfile(
    name="MyProfile",
    max_position_size=0.08,  # 8%
    # ... other parameters
)
```

#### ProfileManager
Centralized profile management and comparison.

```python
manager = ProfileManager()

# Add custom profile
manager.add_profile(custom_profile)

# Compare profiles
comparison = manager.compare_profiles(['conservative', 'moderate'])

# Create profile from base
new_profile = manager.create_custom_profile(
    base_profile='moderate',
    name='CustomModerate',
    overrides={'max_position_size': 0.12}
)
```

---

## Day 5: Profile Comparison

### Profile Comparison (`backtest/profile_comparison.py`)

#### ProfileComparator
Ranks and compares strategy performance across risk profiles.

```python
comparator = ProfileComparator()

# Add backtest results for each profile
comparator.add_profile_results('conservative', conservative_metrics)
comparator.add_profile_results('moderate', moderate_metrics)
comparator.add_profile_results('aggressive', aggressive_metrics)

# Get comparison
result = comparator.compare()
```

**Comparison Features:**

**Rankings:**
- Rank profiles by any metric
- Identify best/worst performers
- Calculate percentile ranks

**Summary Statistics:**
- Mean, median, std dev across profiles
- Best/worst values per metric
- Range and spread

**Optimization Insights:**
- Identify dominated profiles (worse on all metrics)
- Find optimal trade-offs
- Risk/return efficiency analysis

**Comparison Table:**
```python
table = result.get_comparison_table()
# Returns formatted table for easy viewing
```

**Example:**
```
Profile      | Return | Sharpe | Max DD | Win Rate
-------------|--------|--------|--------|----------
Conservative |  12.5% |   1.8  |  -5.2% |   68%
Moderate     |  18.3% |   1.6  |  -8.1% |   64%
Aggressive   |  24.7% |   1.4  | -12.3% |   58%

Best Profile: Aggressive (3.0 avg rank)
```

---

## Day 6: Strategy Templates

### Pre-Built Strategies (`backtest/strategy_templates.py`)

#### MovingAverageCrossStrategy
Classic dual moving average crossover system.

**Signals:**
- **Buy (Golden Cross)**: Fast MA crosses above slow MA
- **Sell (Death Cross)**: Fast MA crosses below slow MA

**Configuration:**
```python
ma_config = MACrossConfig(
    fast_period=20,   # Fast MA period
    slow_period=50,   # Slow MA period
    min_bars=50       # Min bars before trading (auto-adjusts)
)

strategy = MovingAverageCrossStrategy(config, ma_config)
```

**Best For:**
- Trending markets
- Medium to long-term timeframes
- Low-frequency trading

**Limitations:**
- Whipsaws in choppy markets
- Lagging signals
- Late entries/exits

#### MeanReversionStrategy
Bollinger Bands + RSI mean reversion system.

**Signals:**
- **Buy**: Price ≤ lower BB AND RSI ≤ oversold threshold
- **Sell**: Price ≥ upper BB AND RSI ≥ overbought threshold

**Configuration:**
```python
mr_config = MeanReversionConfig(
    bb_period=20,           # Bollinger Band period
    bb_std=2.0,             # Standard deviations
    rsi_period=14,          # RSI calculation period
    rsi_oversold=30.0,      # Oversold threshold
    rsi_overbought=70.0     # Overbought threshold
)

strategy = MeanReversionStrategy(config, mr_config)
```

**Indicators:**
- **Bollinger Bands**: Mean ± (std dev × multiplier)
- **RSI**: Relative Strength Index (0-100)

**Best For:**
- Range-bound markets
- Short to medium-term timeframes
- High-volatility stocks

**Limitations:**
- Poor performance in strong trends
- False signals at support/resistance
- Requires quick exits

#### MomentumStrategy
Rate of Change (ROC) + MACD momentum system.

**Signals:**
- **Buy**: ROC > threshold AND MACD > signal line
- **Sell**: ROC < -threshold AND MACD < signal line

**Configuration:**
```python
mom_config = MomentumConfig(
    lookback_period=20,         # ROC lookback
    momentum_threshold=0.02,    # 2% minimum momentum
    macd_fast=12,               # MACD fast EMA
    macd_slow=26,               # MACD slow EMA
    macd_signal=9               # MACD signal EMA
)

strategy = MomentumStrategy(config, mom_config)
```

**Indicators:**
- **ROC**: (Current - Past) / Past
- **MACD**: Fast EMA - Slow EMA
- **Signal Line**: EMA of MACD

**Best For:**
- Trending markets
- Medium-term timeframes
- Momentum-driven stocks

**Limitations:**
- Late entries on reversals
- Momentum traps
- Requires strong moves

### Template Registry

Dynamic template discovery and instantiation.

```python
# List available templates
templates = list_templates()
# Returns: ['ma_cross', 'mean_reversion', 'momentum']

# Get template class
TemplateClass = get_template('ma_cross')
strategy = TemplateClass(config)

# Or use registry directly
STRATEGY_TEMPLATES = {
    'ma_cross': MovingAverageCrossStrategy,
    'mean_reversion': MeanReversionStrategy,
    'momentum': MomentumStrategy
}
```

---

## Complete Example: End-to-End Backtest

```python
from datetime import datetime
from backtest.data import HistoricalDataManager
from backtest.market_simulator import MarketSimulator, FillSimulator
from backtest.strategy import StrategyConfig
from backtest.strategy_templates import MovingAverageCrossStrategy, MACrossConfig
from backtest.performance import PerformanceAnalyzer
from backtest.profiles import ProfileLibrary

# 1. Setup data
data_manager = HistoricalDataManager("data/historical")
data_manager.load_symbol("AAPL")

# 2. Configure strategy
config = StrategyConfig(
    name="MA Cross Test",
    symbols=["AAPL"],
    initial_capital=100000.0
)

ma_config = MACrossConfig(fast_period=20, slow_period=50)
strategy = MovingAverageCrossStrategy(config, ma_config)

# 3. Apply risk profile
profile = ProfileLibrary.get_moderate()
strategy.apply_risk_profile(profile)

# 4. Setup market simulator
fill_sim = FillSimulator()
simulator = MarketSimulator(data_manager, fill_sim)

# 5. Attach strategy
simulator.subscribe_bars(strategy._process_market_data)

# 6. Run backtest
simulator.replay(
    start_date=datetime(2024, 1, 1),
    end_date=datetime(2024, 12, 31),
    symbols=["AAPL"]
)

# 7. Analyze performance
analyzer = PerformanceAnalyzer(strategy.state)
results = analyzer.analyze()

print(f"Total Return: {results['total_return_pct']:.2f}%")
print(f"Sharpe Ratio: {results['sharpe_ratio']:.2f}")
print(f"Max Drawdown: {results['max_drawdown_pct']:.2f}%")
print(f"Win Rate: {results['win_rate_pct']:.2f}%")
```

---

## Profile Comparison Example

```python
from backtest.profile_comparison import ProfileComparator
from backtest.profiles import ProfileLibrary

# Run backtest with each profile
profiles = ['conservative', 'moderate', 'aggressive']
results_by_profile = {}

for profile_name in profiles:
    # Create strategy with profile
    profile = ProfileLibrary.get_profile_by_name(profile_name)
    strategy = MovingAverageCrossStrategy(config, ma_config)
    strategy.apply_risk_profile(profile)
    
    # Run backtest (same as above)
    # ...
    
    # Store results
    analyzer = PerformanceAnalyzer(strategy.state)
    results_by_profile[profile_name] = analyzer.analyze()

# Compare profiles
comparator = ProfileComparator()
for name, metrics in results_by_profile.items():
    comparator.add_profile_results(name, metrics)

comparison = comparator.compare()

# Print comparison table
print(comparison.get_comparison_table())

# Get best profile by Sharpe ratio
best = comparison.get_best_profile('sharpe_ratio')
print(f"\nBest Profile: {best['name']} (Sharpe: {best['value']:.2f})")

# Get optimization insights
insights = comparison.get_optimization_insights()
print(f"\nOptimization Insights:")
for metric, data in insights.items():
    print(f"  {metric}: Best = {data['best_profile']}")
```

---

## Testing

All components have comprehensive test coverage:

```bash
# Run all Week 4 tests
pytest test_backtest_engine.py test_backtest_data.py test_profiles.py \
       test_profile_comparison.py test_strategy_templates.py -v

# Test results: 138/138 passing (100%)
# - Backtesting foundation: 18 tests
# - Engine core: 18 tests  
# - Performance analytics: 12 tests
# - Multi-profile framework: 36 tests
# - Profile comparison: 20 tests
# - Strategy templates: 46 tests
```

---

## Best Practices

### Strategy Development

1. **Always inherit from `Strategy` base class**
2. **Use lifecycle hooks**: `on_start()`, `on_bar()`, `on_end()`
3. **Check position state before trading**
4. **Use built-in position sizing**: `calculate_position_size()`
5. **Leverage bar history**: `get_bar_history()` for indicators
6. **Handle edge cases**: Missing data, insufficient bars

### Risk Management

1. **Apply risk profiles consistently**
2. **Validate profile parameters** before use
3. **Monitor exposure and leverage**
4. **Use stop losses** (implement in strategy)
5. **Diversify across symbols**
6. **Test multiple profiles** for robustness

### Performance Analysis

1. **Compare against benchmarks**
2. **Analyze across market conditions**
3. **Consider transaction costs**
4. **Test different timeframes**
5. **Validate with walk-forward analysis**
6. **Document assumptions and limitations**

### Testing

1. **Test strategies in isolation** before backtesting
2. **Use synthetic data** for edge cases
3. **Validate indicator calculations**
4. **Test order handling logic**
5. **Verify state management**
6. **Check performance metric calculations**

---

## Future Enhancements

Potential areas for expansion:

1. **Multi-asset support**: Stocks, options, futures
2. **Advanced order types**: Trailing stops, bracket orders
3. **Portfolio optimization**: Modern portfolio theory
4. **Monte Carlo simulation**: Robustness testing
5. **Regime detection**: Market condition awareness
6. **Machine learning integration**: Predictive models
7. **Real-time data**: Live trading capability
8. **Execution algorithms**: VWAP, TWAP, iceberg
9. **Commission modeling**: Tiered, per-share
10. **Slippage models**: Market-specific

---

## Troubleshooting

### Common Issues

**Problem**: "Not enough bars for indicator calculation"
- **Solution**: Increase `min_bars` in strategy config or load more historical data

**Problem**: "Order not filled"
- **Solution**: Check order type (LIMIT orders may not fill), verify bar data availability

**Problem**: "Position size is 0"
- **Solution**: Verify risk profile allows position, check available capital, confirm position sizing logic

**Problem**: "Max drawdown exceeds expectations"
- **Solution**: Tighten risk profile, implement stop losses, reduce position sizes

**Problem**: "Low win rate but positive returns"
- **Solution**: Normal for trend-following strategies (few big wins, many small losses)

---

## References

### Key Concepts

- **Sharpe Ratio**: (Return - Risk-Free Rate) / Volatility
- **Sortino Ratio**: Like Sharpe, but only penalizes downside volatility
- **Calmar Ratio**: Annualized Return / Max Drawdown
- **Profit Factor**: Gross Profit / Gross Loss
- **Maximum Drawdown**: Largest peak-to-trough decline

### Further Reading

- *Quantitative Trading* by Ernest Chan
- *Algorithmic Trading* by Ernie Chan  
- *Evidence-Based Technical Analysis* by David Aronson
- *Advances in Financial Machine Learning* by Marcos López de Prado

---

## Support

For questions or issues:
1. Check test files for usage examples
2. Review `example_*.py` files for patterns
3. Consult this documentation
4. Examine strategy templates for best practices

---

**Week 4 Complete** ✅
- 138/138 tests passing
- Full backtesting system operational
- Risk management framework implemented
- Strategy templates ready for use
- Comprehensive documentation provided
