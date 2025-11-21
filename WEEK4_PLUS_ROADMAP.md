# TWS Robot - Week 4+ Roadmap
## Validation-First Approach with Multi-Profile Support

**Date Created:** November 21, 2025  
**Status:** Planning  
**Approach:** Extensive validation before live trading  

---

## 📋 Project Preferences & Requirements

### **Primary Goals**
- ✅ **Validation First**: Extensive backtesting and paper trading before going live
- ✅ **Multi-Profile Support**: Test both conservative and aggressive risk profiles simultaneously
- ✅ **Strategy Flexibility**: Support 1-2 existing strategies + build additional ones for diversification
- ✅ **Dual Monitoring**: Both terminal-based (quick checks) and web dashboard (detailed analysis)
- ✅ **Usability Focus**: Keep existing `tws_client.py` functionality where it works well

### **Risk Approach**
- Test multiple risk profiles side-by-side
- Compare conservative vs. aggressive performance
- Data-driven parameter tuning
- No live trading until fully validated

### **Strategy Approach**
- Integrate 1-2 existing strategies (need fine-tuning)
- Build additional strategies for diversification
- Multi-strategy portfolio support
- Easy strategy addition framework

---

## 🗓️ Week 4: Backtesting Engine & Multi-Profile Support

**Sprint Goal:** Build robust backtesting system to validate risk management with historical data

### **Day 1: Backtesting Foundation - Data Infrastructure**

**Focus:** Historical data management and replay engine

**Deliverables:**
- [ ] `backtest/` module structure
- [ ] `backtest/data_manager.py` - Historical data loading and management
- [ ] `backtest/market_simulator.py` - Simulate market conditions from historical data
- [ ] Data format standardization (OHLCV + volume)
- [ ] Sample historical data for testing

**Technical Tasks:**
```python
# Priority 1: Data Management
1. Create backtest module structure
2. Implement HistoricalDataManager class
3. Support multiple data sources (CSV, database, APIs)
4. Data validation and cleaning
5. Time-based data windowing

# Priority 2: Market Simulator
6. Historical bar replay system
7. Realistic timestamp progression
8. Market data events generation
9. Order fill simulation (realistic slippage)
```

**Key Classes:**
```python
class HistoricalDataManager:
    def load_data(symbol, start_date, end_date)
    def get_bars(symbol, timestamp, lookback)
    def validate_data()
    
class MarketSimulator:
    def replay_history(start_date, end_date)
    def get_current_bar(symbol)
    def simulate_fill(order, current_bar)
```

**Success Criteria:**
- ✅ Load historical data for multiple symbols
- ✅ Replay market conditions chronologically
- ✅ Realistic order fill simulation
- ✅ Clean, validated data

---

### **Day 2: Backtesting Engine Core**

**Focus:** Build the core backtesting execution engine

**Deliverables:**
- [ ] `backtest/backtest_engine.py` - Main backtesting engine
- [ ] `backtest/trade_simulator.py` - Trade execution simulation
- [ ] Integration with risk management system
- [ ] Position tracking during backtest
- [ ] P&L calculation

**Technical Tasks:**
```python
# Priority 1: Backtest Engine
1. BacktestEngine class with event loop
2. Strategy signal processing
3. Risk validation integration
4. Order execution simulation
5. Position and equity tracking

# Priority 2: Trade Simulator
6. Realistic fill prices (slippage modeling)
7. Commission calculation
8. Partial fills support
9. Order rejection handling
```

**Key Classes:**
```python
class BacktestEngine:
    def __init__(risk_manager, position_sizer, strategies)
    def run(start_date, end_date, initial_capital)
    def process_bar(timestamp, market_data)
    def execute_signals(signals)
    def calculate_metrics()
    
class TradeSimulator:
    def simulate_order_fill(order, market_data)
    def calculate_slippage(order_type, volume)
    def apply_commissions(trade)
```

**Integration Points:**
- RiskManager: Pre-trade validation
- PositionSizer: Calculate position sizes
- DrawdownMonitor: Track drawdown during backtest
- EmergencyController: Test circuit breakers

**Success Criteria:**
- ✅ Run complete backtests with risk system
- ✅ Realistic trade simulation
- ✅ Accurate P&L tracking
- ✅ Risk limits enforced during backtest

---

### **Day 3: Performance Analytics**

**Focus:** Calculate comprehensive performance metrics

**Deliverables:**
- [ ] `backtest/performance_metrics.py` - Performance calculation
- [ ] `backtest/report_generator.py` - Backtest reports
- [ ] Risk-adjusted return metrics
- [ ] Trade analysis statistics
- [ ] Visualization helpers

**Technical Tasks:**
```python
# Priority 1: Core Metrics
1. Return metrics (total, annualized, CAGR)
2. Risk metrics (volatility, max drawdown, Calmar)
3. Risk-adjusted metrics (Sharpe, Sortino, Information Ratio)
4. Trade statistics (win rate, profit factor, avg win/loss)

# Priority 2: Advanced Analytics
5. Monthly/yearly breakdowns
6. Drawdown analysis (duration, recovery)
7. Trade distribution analysis
8. Risk exposure over time
```

**Key Metrics:**
```python
class PerformanceMetrics:
    # Return Metrics
    - total_return
    - annualized_return
    - cagr
    
    # Risk Metrics
    - max_drawdown
    - max_drawdown_duration
    - volatility (daily, annual)
    - downside_deviation
    - calmar_ratio
    
    # Risk-Adjusted
    - sharpe_ratio
    - sortino_ratio
    - information_ratio
    - omega_ratio
    
    # Trade Stats
    - total_trades
    - win_rate
    - profit_factor
    - avg_win / avg_loss
    - largest_win / largest_loss
    - consecutive_wins / losses
    
    # Exposure
    - avg_exposure
    - max_positions
    - time_in_market
```

**Success Criteria:**
- ✅ Comprehensive performance metrics calculated
- ✅ Professional-grade reports generated
- ✅ Trade-by-trade analysis available
- ✅ Easy to compare different backtests

---

### **Day 4: Multi-Profile Framework**

**Focus:** Support multiple risk profiles for comparison

**Deliverables:**
- [ ] `backtest/profile_manager.py` - Risk profile management
- [ ] `backtest/profile_comparator.py` - Side-by-side comparison
- [ ] Pre-configured profiles (Conservative, Moderate, Aggressive, Custom)
- [ ] Profile optimization tools
- [ ] Comparison reports and visualizations

**Technical Tasks:**
```python
# Priority 1: Profile Management
1. RiskProfile configuration class
2. Profile presets (Conservative/Moderate/Aggressive)
3. Custom profile creation
4. Profile validation

# Priority 2: Multi-Profile Backtesting
5. Run same strategy with different profiles
6. Parallel profile execution
7. Profile comparison metrics
8. Optimal profile identification
```

**Profile Definitions:**
```python
# Conservative Profile
RiskProfile(
    name="Conservative",
    max_position_pct=0.01,      # 1% per position
    max_positions=8,
    max_drawdown_pct=0.10,      # 10% max DD
    daily_loss_limit_pct=0.02,  # 2% daily loss
    position_sizer='risk_based',
    risk_per_trade=0.005        # 0.5% risk
)

# Moderate Profile
RiskProfile(
    name="Moderate",
    max_position_pct=0.02,      # 2% per position
    max_positions=10,
    max_drawdown_pct=0.20,      # 20% max DD
    daily_loss_limit_pct=0.03,  # 3% daily loss
    position_sizer='volatility_adjusted',
    risk_per_trade=0.01         # 1% risk
)

# Aggressive Profile
RiskProfile(
    name="Aggressive",
    max_position_pct=0.03,      # 3% per position
    max_positions=15,
    max_drawdown_pct=0.30,      # 30% max DD
    daily_loss_limit_pct=0.05,  # 5% daily loss
    position_sizer='kelly',
    risk_per_trade=0.015        # 1.5% risk
)
```

**Comparison Features:**
```python
class ProfileComparator:
    def compare_profiles(strategy, profiles, data)
    def generate_comparison_report()
    def visualize_profiles()
    def recommend_optimal_profile()
```

**Success Criteria:**
- ✅ Easy to test multiple profiles
- ✅ Side-by-side performance comparison
- ✅ Clear visualization of trade-offs
- ✅ Data-driven profile selection

---

### **Day 5: Strategy Framework - Base Classes**

**Focus:** Create flexible framework for strategy development

**Deliverables:**
- [ ] `strategies/` module structure
- [ ] `strategies/base_strategy.py` - Abstract base class
- [ ] `strategies/strategy_manager.py` - Strategy lifecycle management
- [ ] Signal generation framework
- [ ] Strategy parameter management

**Technical Tasks:**
```python
# Priority 1: Base Framework
1. BaseStrategy abstract class
2. Signal generation interface
3. Strategy state management
4. Parameter hot-reloading support

# Priority 2: Strategy Manager
5. Strategy registration and discovery
6. Multi-strategy orchestration
7. Strategy allocation management
8. Strategy health monitoring
```

**Base Strategy Interface:**
```python
from abc import ABC, abstractmethod

class BaseStrategy(ABC):
    """
    Abstract base class for all trading strategies
    """
    
    def __init__(self, name: str, params: dict):
        self.name = name
        self.params = params
        self.positions = {}
        self.is_active = True
        
    @abstractmethod
    def generate_signals(self, data: MarketData) -> List[Signal]:
        """
        Generate trading signals based on current market data
        Must be implemented by each strategy
        """
        pass
    
    @abstractmethod
    def update_state(self, data: MarketData) -> None:
        """
        Update internal strategy state (indicators, etc.)
        """
        pass
    
    def on_fill(self, trade: Trade) -> None:
        """Called when order is filled"""
        pass
    
    def on_cancel(self, order: Order) -> None:
        """Called when order is cancelled"""
        pass
    
    def validate_signal(self, signal: Signal) -> bool:
        """Validate signal before submission"""
        return True
    
    def get_metrics(self) -> dict:
        """Get strategy-specific metrics"""
        return {}
```

**Signal Class:**
```python
@dataclass
class Signal:
    """Trading signal generated by strategy"""
    timestamp: datetime
    symbol: str
    action: str  # 'BUY', 'SELL', 'CLOSE'
    signal_strength: float  # 0-1, confidence level
    strategy_name: str
    metadata: dict = field(default_factory=dict)
    
    # Optional fields for advanced signals
    target_price: Optional[float] = None
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    time_in_force: str = 'DAY'
```

**Success Criteria:**
- ✅ Clean, intuitive base class
- ✅ Easy to implement new strategies
- ✅ Built-in validation and state management
- ✅ Multi-strategy support

---

### **Day 6: Strategy Library - Mean Reversion**

**Focus:** Build first complete strategy implementation

**Deliverables:**
- [ ] `strategies/mean_reversion.py` - Bollinger Bands strategy
- [ ] `strategies/indicators.py` - Technical indicators library
- [ ] Strategy parameter optimization tools
- [ ] Mean reversion strategy backtests

**Technical Tasks:**
```python
# Priority 1: Technical Indicators
1. Moving averages (SMA, EMA, WMA)
2. Bollinger Bands
3. RSI (Relative Strength Index)
4. ATR (Average True Range)
5. Standard deviation

# Priority 2: Mean Reversion Strategy
6. Bollinger Band mean reversion implementation
7. RSI oversold/overbought strategy
8. Parameter optimization framework
9. Entry/exit signal generation
```

**Example Strategy:**
```python
class BollingerBandsMeanReversion(BaseStrategy):
    """
    Mean reversion strategy using Bollinger Bands
    - Buy when price touches lower band
    - Sell when price touches upper band or middle band
    """
    
    def __init__(self, params: dict):
        super().__init__("BB_MeanReversion", params)
        self.bb_period = params.get('bb_period', 20)
        self.bb_std = params.get('bb_std', 2.0)
        self.rsi_period = params.get('rsi_period', 14)
        self.rsi_oversold = params.get('rsi_oversold', 30)
        self.rsi_overbought = params.get('rsi_overbought', 70)
        
    def generate_signals(self, data: MarketData) -> List[Signal]:
        signals = []
        
        for symbol in self.watchlist:
            bars = data.get_bars(symbol, lookback=self.bb_period + 10)
            
            # Calculate indicators
            bb_upper, bb_middle, bb_lower = self.calculate_bollinger_bands(bars)
            rsi = self.calculate_rsi(bars)
            current_price = bars[-1].close
            
            # Generate buy signal
            if (current_price <= bb_lower and 
                rsi < self.rsi_oversold and
                symbol not in self.positions):
                
                signals.append(Signal(
                    timestamp=bars[-1].timestamp,
                    symbol=symbol,
                    action='BUY',
                    signal_strength=0.8,
                    strategy_name=self.name,
                    target_price=bb_middle,
                    stop_loss=current_price * 0.98,
                    metadata={
                        'bb_lower': bb_lower,
                        'rsi': rsi,
                        'entry_reason': 'oversold_at_lower_band'
                    }
                ))
            
            # Generate sell signal
            elif (symbol in self.positions and
                  (current_price >= bb_upper or 
                   current_price >= bb_middle)):
                
                signals.append(Signal(
                    timestamp=bars[-1].timestamp,
                    symbol=symbol,
                    action='SELL',
                    signal_strength=0.7,
                    strategy_name=self.name,
                    metadata={
                        'exit_reason': 'target_reached',
                        'bb_middle': bb_middle,
                        'rsi': rsi
                    }
                ))
        
        return signals
```

**Success Criteria:**
- ✅ Working mean reversion strategy
- ✅ Technical indicators library
- ✅ Backtestable with risk system
- ✅ Parameter optimization ready

---

### **Day 7: Testing & Documentation**

**Focus:** Comprehensive testing and Week 4 documentation

**Deliverables:**
- [ ] Unit tests for all backtest components
- [ ] Integration tests for full backtest runs
- [ ] Example backtests with sample data
- [ ] Week 4 documentation
- [ ] Usage examples and tutorials

**Technical Tasks:**
```python
# Priority 1: Testing
1. test_backtest_engine.py (unit tests)
2. test_performance_metrics.py
3. test_profile_manager.py
4. test_strategy_framework.py
5. Integration test: full backtest with risk system

# Priority 2: Documentation
6. Backtest module README
7. Strategy development guide
8. Profile configuration guide
9. Example backtests with analysis
```

**Example Test Cases:**
- Backtest with single strategy, single profile
- Backtest with single strategy, multiple profiles
- Multi-strategy backtest
- Risk limit testing during backtest
- Drawdown protection validation
- Emergency control triggers

**Success Criteria:**
- ✅ All tests passing
- ✅ Complete documentation
- ✅ Working examples
- ✅ Week 4 objectives met

---

## 🗓️ Week 5: Strategy Development & Validation

**Sprint Goal:** Import existing strategies, build additional ones, optimize parameters

### **Day 1: Existing Strategy Migration**

**Focus:** Take your 1-2 existing strategies and migrate them

**Deliverables:**
- [ ] Review and document existing strategies
- [ ] Migrate Strategy #1 to new framework
- [ ] Migrate Strategy #2 to new framework
- [ ] Add risk management integration
- [ ] Initial backtesting of migrated strategies

**Migration Checklist:**
- [ ] Extract strategy logic from existing code
- [ ] Implement BaseStrategy interface
- [ ] Add indicator calculations
- [ ] Define entry/exit rules clearly
- [ ] Add stop loss and take profit logic
- [ ] Test signal generation

---

### **Day 2: Strategy Parameter Tuning**

**Focus:** Fine-tune existing strategies with backtesting

**Deliverables:**
- [ ] Parameter optimization framework
- [ ] Grid search implementation
- [ ] Walk-forward optimization
- [ ] Overfitting prevention measures
- [ ] Optimal parameters for each strategy

**Optimization Approach:**
```python
# Parameter Grid Search
parameters = {
    'bb_period': [10, 15, 20, 25],
    'bb_std': [1.5, 2.0, 2.5],
    'rsi_period': [7, 14, 21],
    'rsi_oversold': [20, 25, 30],
    'rsi_overbought': [70, 75, 80]
}

optimizer = ParameterOptimizer(
    strategy=BollingerBandsMeanReversion,
    parameters=parameters,
    optimization_metric='sharpe_ratio'
)

results = optimizer.run_grid_search(
    data=historical_data,
    train_period='2020-01-01:2023-12-31',
    test_period='2024-01-01:2024-12-31'
)
```

---

### **Day 3-4: Additional Strategy Development**

**Focus:** Build 2-3 additional strategies for diversification

**Suggested Strategies:**

**Option 1: Momentum Breakout**
```python
class MomentumBreakout(BaseStrategy):
    """
    Trend following strategy
    - Buy on breakout above 20-day high
    - Sell on breakdown below 10-day low
    """
```

**Option 2: Pairs Trading**
```python
class PairsTrading(BaseStrategy):
    """
    Statistical arbitrage between correlated pairs
    - Find correlated pairs (e.g., AAPL-MSFT)
    - Trade mean reversion of spread
    """
```

**Option 3: Volatility Strategy**
```python
class VolatilityMeanReversion(BaseStrategy):
    """
    Trade volatility compression/expansion
    - Buy when IV is low relative to HV
    - Sell when IV spikes
    """
```

**Deliverables:**
- [ ] 2-3 new strategy implementations
- [ ] Backtests for each strategy
- [ ] Performance comparison
- [ ] Correlation analysis between strategies

---

### **Day 5: Multi-Strategy Portfolio**

**Focus:** Combine strategies into a portfolio

**Deliverables:**
- [ ] `strategies/portfolio_manager.py` - Multi-strategy orchestration
- [ ] Strategy allocation system
- [ ] Inter-strategy risk management
- [ ] Portfolio-level performance tracking

**Portfolio Management:**
```python
class PortfolioManager:
    """
    Manage multiple strategies with allocation
    """
    
    def __init__(self, strategies: List[BaseStrategy], allocations: dict):
        self.strategies = strategies
        self.allocations = allocations  # % of capital per strategy
        
    def allocate_capital(self, total_capital: float):
        """Allocate capital to each strategy"""
        pass
    
    def aggregate_signals(self) -> List[Signal]:
        """Collect signals from all strategies"""
        pass
    
    def check_portfolio_risk(self):
        """Ensure portfolio-level risk limits"""
        pass
```

**Example Portfolio:**
```python
portfolio = PortfolioManager(
    strategies=[
        BollingerBandsMeanReversion(params1),
        MomentumBreakout(params2),
        PairsTrading(params3)
    ],
    allocations={
        'BB_MeanReversion': 0.40,  # 40% of capital
        'MomentumBreakout': 0.35,  # 35% of capital
        'PairsTrading': 0.25       # 25% of capital
    }
)
```

---

### **Day 6: Validation & Robustness Testing**

**Focus:** Ensure strategies are robust across different market conditions

**Deliverables:**
- [ ] Out-of-sample testing
- [ ] Different market regimes (bull, bear, sideways)
- [ ] Crisis period testing (2020 COVID, 2022 bear market)
- [ ] Monte Carlo simulation
- [ ] Stress testing

**Robustness Checks:**
- Test on different time periods
- Test on different asset classes
- Test with different transaction costs
- Test with realistic slippage
- Test position sizing impact

---

### **Day 7: Strategy Documentation & Week 5 Summary**

**Focus:** Document all strategies and create comprehensive guide

**Deliverables:**
- [ ] Strategy development guide
- [ ] Each strategy's logic documented
- [ ] Parameter optimization results
- [ ] Backtest reports for all strategies
- [ ] Week 5 summary document

---

## 🗓️ Week 6: Monitoring & Visualization

**Sprint Goal:** Build dual monitoring system (terminal + web)

### **Day 1-2: Terminal Dashboard**

**Focus:** Rich terminal-based monitoring interface

**Deliverables:**
- [ ] `monitoring/terminal_dashboard.py` - Beautiful terminal UI
- [ ] Real-time risk metrics display
- [ ] Position monitoring
- [ ] Alert feed
- [ ] Performance charts (ASCII art)

**Technology:** Use `rich` or `textual` library for beautiful terminal UI

**Features:**
- Live updating metrics
- Color-coded alerts
- ASCII charts for equity curve
- Position table with P&L
- Keyboard shortcuts for controls

**Example Layout:**
```
╔═══════════════════════════════════════════════════════════════════╗
║                    TWS Robot Risk Dashboard                        ║
║                    Live Monitoring - 14:23:45                      ║
╠═══════════════════════════════════════════════════════════════════╣
║  Health Score: 87/100 ✓ HEALTHY     Profile: MODERATE             ║
║  Portfolio Value: $105,234 (+5.2%)  Daily P&L: +$1,234 (+1.2%)   ║
╠═══════════════════════════════════════════════════════════════════╣
║  Risk Metrics                                                      ║
║  ├─ Positions: 8/10 (80%)           Drawdown: -3.2% / 20% max    ║
║  ├─ Portfolio Heat: 4.8% / 6% max   Daily Loss: -$456 / $3k max  ║
║  └─ Leverage: 1.2x / 1.5x max       HHI: 0.18 (well diversified) ║
╠═══════════════════════════════════════════════════════════════════╣
║  Active Positions                                                  ║
║  Symbol  Qty   Entry    Current   P&L      ROI    Risk            ║
║  AAPL    100   $150.00  $152.34   +$234   +1.6%  Low             ║
║  MSFT     50   $380.00  $375.20   -$240   -1.3%  Medium          ║
║  TSLA     30   $245.00  $251.80   +$204   +2.8%  High            ║
╠═══════════════════════════════════════════════════════════════════╣
║  Active Alerts (2)                                                 ║
║  ⚠ WARNING [14:15:32] High correlation detected: AAPL-MSFT (0.82) ║
║  ℹ INFO    [14:10:15] Position TSLA approaching size limit (85%)  ║
╠═══════════════════════════════════════════════════════════════════╣
║  Equity Curve (Last 30 Days)                                      ║
║  105k ┤                                               ╭──          ║
║  103k ┤                                      ╭────────╯            ║
║  101k ┤                            ╭─────────╯                     ║
║   99k ┤                    ╭───────╯                               ║
║   97k ┤        ╭───────────╯                                       ║
║   95k ┼────────╯                                                   ║
╠═══════════════════════════════════════════════════════════════════╣
║  Controls: [E] Emergency Stop  [P] Pause  [R] Resume  [Q] Quit    ║
╚═══════════════════════════════════════════════════════════════════╝
```

---

### **Day 3-5: Web Dashboard**

**Focus:** Professional web-based monitoring and control

**Technology Stack:**
- **Backend:** FastAPI (REST + WebSockets)
- **Frontend:** Simple HTML/CSS/JavaScript (or React if preferred)
- **Charts:** Chart.js or Plotly
- **Real-time:** WebSocket for live updates

**Backend Structure:**
```
web/
├── backend/
│   ├── main.py              # FastAPI application
│   ├── api/
│   │   ├── risk.py          # Risk metrics endpoints
│   │   ├── portfolio.py     # Portfolio endpoints
│   │   ├── strategies.py    # Strategy management
│   │   └── controls.py      # Manual controls
│   ├── websocket/
│   │   └── live_feed.py     # Real-time data streaming
│   └── models/
│       └── schemas.py       # API data models
└── frontend/
    ├── index.html           # Main dashboard
    ├── css/
    │   └── styles.css
    ├── js/
    │   ├── dashboard.js     # Main dashboard logic
    │   ├── websocket.js     # WebSocket handling
    │   └── charts.js        # Chart rendering
    └── components/
        ├── risk-panel.html
        ├── positions.html
        └── alerts.html
```

**API Endpoints:**
```python
# Risk & Portfolio
GET  /api/risk/metrics          # Current risk metrics
GET  /api/risk/health           # Health score
GET  /api/portfolio/summary     # Portfolio summary
GET  /api/portfolio/positions   # Current positions
GET  /api/portfolio/history     # Equity curve data

# Strategies
GET  /api/strategies            # List all strategies
GET  /api/strategies/{id}/performance
POST /api/strategies/{id}/start
POST /api/strategies/{id}/stop
PUT  /api/strategies/{id}/params

# Controls
POST /api/controls/emergency-stop
POST /api/controls/pause
POST /api/controls/resume
GET  /api/controls/status

# Alerts
GET  /api/alerts                # Active alerts
GET  /api/alerts/history        # Alert history

# WebSocket
WS   /ws/live                   # Real-time data stream
```

**Dashboard Features:**
- Real-time metric updates
- Interactive charts (equity curve, drawdown, position sizes)
- Alert management interface
- Strategy control panel
- Risk profile switcher
- Manual override controls
- Performance analytics
- Mobile-responsive design

---

### **Day 6-7: Dual-Mode Integration**

**Focus:** Make terminal and web dashboards work together seamlessly

**Deliverables:**
- [ ] Shared data backend
- [ ] Event broadcasting to both interfaces
- [ ] Synchronized state management
- [ ] User preference management
- [ ] Documentation for both modes

**Architecture:**
```
┌─────────────────┐     ┌─────────────────┐
│  Terminal       │     │  Web Dashboard  │
│  Dashboard      │     │  (Browser)      │
└────────┬────────┘     └────────┬────────┘
         │                       │
         │    ┌──────────────┐   │
         └────┤  Data Layer  ├───┘
              │  (FastAPI)   │
              └──────┬───────┘
                     │
         ┌───────────┴───────────┐
         │                       │
    ┌────▼────┐          ┌──────▼─────┐
    │  Risk   │          │  Strategy  │
    │  System │          │  Engine    │
    └─────────┘          └────────────┘
```

**Use Cases:**
- Use terminal dashboard for quick checks while monitoring other work
- Use web dashboard for detailed analysis and strategy management
- Both can run simultaneously
- Both show same real-time data
- Actions in one reflect in the other

---

## 🗓️ Week 7: TWS Integration & Paper Trading

**Sprint Goal:** Connect risk system to Interactive Brokers for paper trading

### **Day 1-2: TWS Integration Analysis**

**Focus:** Understand existing code and plan integration

**Deliverables:**
- [ ] Review `tws_client.py` - document current capabilities
- [ ] Review `trading_bot_template.py` - understand trading flow
- [ ] Identify integration points for risk system
- [ ] Design data flow architecture
- [ ] Plan minimal-disruption refactoring

**Analysis Checklist:**
- [ ] TWS connection management
- [ ] Market data handling
- [ ] Order submission process
- [ ] Position tracking
- [ ] Account data updates
- [ ] Error handling
- [ ] Existing strategy logic

**Integration Points:**
```python
# Key places to add risk validation
1. Before order submission → risk_manager.check_trade_risk()
2. After position update → update_risk_metrics()
3. On account equity change → drawdown_monitor.update()
4. Periodic check (every minute) → emergency_controller.check()
5. On order fill → position_sizer.recalculate()
```

---

### **Day 3-5: Risk System Integration**

**Focus:** Connect all risk components to live TWS feed

**Deliverables:**
- [ ] `integration/tws_risk_bridge.py` - Bridge between TWS and risk system
- [ ] Pre-trade validation hooks
- [ ] Real-time position tracking
- [ ] Account equity monitoring
- [ ] Emergency control integration
- [ ] Monitoring integration

**Implementation Plan:**

**Step 1: Create Bridge Layer**
```python
class TWSRiskBridge:
    """
    Bridge between TWS client and risk management system
    Translates TWS callbacks to risk system updates
    """
    
    def __init__(self, tws_client, risk_manager, position_sizer, 
                 drawdown_monitor, emergency_controller):
        self.tws = tws_client
        self.risk_manager = risk_manager
        self.position_sizer = position_sizer
        self.drawdown_monitor = drawdown_monitor
        self.emergency_controller = emergency_controller
        
    def validate_order(self, symbol, quantity, action, price):
        """Validate order with risk system before submission"""
        # Check emergency conditions
        # Validate with risk manager
        # Calculate position size
        # Check drawdown status
        pass
    
    def update_positions(self, positions):
        """Update risk system when positions change"""
        pass
    
    def update_account(self, equity, cash):
        """Update risk metrics when account changes"""
        pass
```

**Step 2: Add Pre-Trade Validation**
```python
# In trading logic, before submitting order:

def place_order(symbol, quantity, action, price):
    # NEW: Risk validation
    allowed, reason = risk_bridge.validate_order(
        symbol, quantity, action, price
    )
    
    if not allowed:
        logger.warning(f"Order rejected by risk system: {reason}")
        return False
    
    # EXISTING: Submit to TWS
    order_id = tws_client.place_order(symbol, quantity, action, price)
    return order_id
```

**Step 3: Real-time Updates**
```python
# Hook into TWS callbacks

def position_callback(account, contract, position, avg_cost):
    """Called by TWS when position updates"""
    # Update risk system
    risk_bridge.update_positions(current_positions)
    
def account_summary_callback(account, tag, value, currency):
    """Called by TWS when account data updates"""
    if tag == 'NetLiquidation':
        risk_bridge.update_account(float(value), cash_balance)
```

---

### **Day 6-7: Paper Trading**

**Focus:** Start paper trading with full risk management

**Setup:**
- [ ] Connect to IBKR paper trading account
- [ ] Configure conservative risk profile initially
- [ ] Enable all monitoring (terminal + web)
- [ ] Set up alert notifications
- [ ] Start with 1 strategy only

**Paper Trading Checklist:**
- [ ] Risk system validates all orders
- [ ] Position tracking working
- [ ] Drawdown monitoring active
- [ ] Emergency controls responsive
- [ ] Alerts triggering correctly
- [ ] Dashboard showing real-time data
- [ ] Performance tracking accurate

**Daily Monitoring Routine:**
- Morning: Check overnight positions, review alerts
- During market: Monitor terminal dashboard, respond to alerts
- Evening: Review performance, check metrics, tune if needed
- Weekly: Full performance review, compare to backtest

**Validation Period:** Run paper trading for at least 2 weeks before considering live trading

---

## 🗓️ Week 8 (Optional): Extended Validation & Live Prep

### **Week 8A: Extended Paper Trading**
- Continue paper trading for 2-4 more weeks
- Test both conservative and aggressive profiles
- Test with multiple strategies
- Simulate various market conditions
- Build operational confidence

### **Week 8B: Live Trading Preparation**
- Final system audit
- Production configuration lock-down
- Backup and disaster recovery setup
- Emergency response plan documentation
- Go/No-Go decision

### **Week 8C: Cautious Live Deployment** (If validated)
- Start with micro positions (10% of normal size)
- Conservative profile only
- Single strategy only
- Daily review and adjustment
- Gradual scale-up over 4-6 weeks

---

## 📊 Success Metrics

### **Backtesting Validation** (Week 4-5)
- ✅ Positive Sharpe ratio (>1.0) in backtests
- ✅ Maximum drawdown acceptable (<15% for conservative)
- ✅ Consistent performance across different time periods
- ✅ Risk system prevents catastrophic losses in backtest
- ✅ All strategies profitable in out-of-sample tests

### **Paper Trading Validation** (Week 7-8)
- ✅ 2+ weeks of stable paper trading
- ✅ No emergency control triggers (or proper handling if triggered)
- ✅ Actual results match backtest expectations
- ✅ All risk limits respected
- ✅ Monitoring systems working perfectly
- ✅ No critical bugs or issues

### **Live Trading Readiness**
- ✅ All validation criteria met
- ✅ Team confidence high
- ✅ Emergency procedures tested
- ✅ Monitoring 24/7 capable
- ✅ Backup systems in place

---

## 🎯 Key Principles

### **1. Validation First**
- Never skip testing
- Backtest thoroughly
- Paper trade extensively
- Don't rush to live trading

### **2. Start Small**
- Begin with conservative profile
- Small position sizes
- Single strategy initially
- Gradual scale-up only after proven success

### **3. Monitor Continuously**
- Check terminal dashboard frequently
- Review web dashboard daily
- Respond to all critical alerts
- Weekly performance reviews

### **4. Respect Risk Limits**
- Never override risk system without strong reason
- Honor all circuit breaker trips
- Investigate all emergency conditions
- Tune parameters based on data, not emotion

### **5. Document Everything**
- Log all decisions
- Document parameter changes
- Track performance
- Record lessons learned

---

## 📝 Review Schedule

**Weekly Reviews:**
- Every Friday: Review week's progress
- Compare actual vs. planned deliverables
- Adjust next week's plan if needed
- Document blockers and solutions

**Decision Points:**
- End of Week 4: Backtest results review - Continue to Week 5?
- End of Week 5: Strategy validation - Strategies profitable?
- End of Week 6: Monitoring ready - Systems working?
- End of Week 7: Paper trading review - Ready for extended validation or go live?
- After 2 weeks paper trading: Go/No-Go for live trading

---

## 🚀 Current Status

**Week 3:** ✅ COMPLETE - Risk Management System
- All 6 components built and tested
- 44 tests passing
- 4700+ lines of production code
- Complete documentation

**Week 4:** 🎯 READY TO START
- Day 1: Backtesting Foundation - Ready to begin
- Team aligned on approach
- Requirements clear
- Technical plan defined

---

## 📚 Related Documents

- `PROJECT_PLAN.md` - Original 7-week plan
- `WEEK3_SUMMARY.md` - Week 3 completion summary
- `risk/README.md` - Risk system documentation
- `WEEK2_DAY7_PLAN.md` - Week 2 planning document

---

**Document Version:** 1.0  
**Last Updated:** November 21, 2025  
**Next Review:** End of Week 4  
**Status:** Active Planning 🎯
