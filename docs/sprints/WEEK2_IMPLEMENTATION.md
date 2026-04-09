# TWS Robot v2.0 - Week 2 Implementation Guide
## Strategy Framework & Backtesting Engine

**Sprint Goal:** Build strategy execution engine and backtesting capability  
**Duration:** Week 2 of 7-week project (November 18-24, 2025)  
**Prerequisites:** Week 1 Complete (Event Bus, Database, Core Modules)  
**Focus:** Multi-strategy execution and historical validation

---

## 📋 Week 2 Overview

### **Mission Statement**
Transform the TWS Robot from a single-strategy system into a multi-strategy execution platform with comprehensive backtesting and performance validation capabilities.

### **Success Criteria**
- ✅ Abstract strategy framework supports multiple concurrent strategies
- ✅ Backtesting engine validates strategies against historical data
- ✅ Performance metrics provide actionable insights
- ✅ Parameter optimization identifies optimal strategy configurations
- ✅ Existing Bollinger Bands strategy migrated and tested

### **Week 2 Dependencies (from Week 1)**
- Event Bus: Strategy lifecycle events, signal generation events
- Database: Trade/order persistence, performance metrics storage
- Core Modules: Order manager, contract builder, rate limiter
- Testing Framework: Strategy testing, backtest validation

---

## 🎯 Week 2 Deliverables

### **Priority 1: Strategy Framework** (Days 1-2)
1. **BaseStrategy Abstract Class** - Foundation for all trading strategies
2. **Strategy Lifecycle Manager** - Registration, start/stop, monitoring
3. **Signal Generation Framework** - Standardized signal interface
4. **Strategy Configuration System** - YAML-based strategy parameters
5. **Hot-Reload Support** - Update parameters without restart

### **Priority 2: Backtesting Engine** (Days 3-4)
1. **Historical Data Manager** - Fetch and cache market data
2. **Backtest Execution Engine** - Simulate strategy on historical data
3. **Realistic Simulation** - Slippage, commissions, market impact
4. **Performance Metrics Calculator** - Sharpe, Sortino, Calmar ratios
5. **Backtest Report Generator** - Comprehensive strategy analysis

### **Priority 3: Strategy Migration** (Day 5)
1. **Bollinger Bands Migration** - Adapt existing strategy to new framework
2. **Strategy Validation Tests** - Ensure consistent behavior
3. **Configuration Templates** - Example strategy configs
4. **Integration Testing** - End-to-end strategy execution

### **Priority 4: Performance Analytics** (Days 6-7)
1. **Multi-Strategy Comparison** - Compare strategy performance
2. **Parameter Optimization** - Grid search, walk-forward analysis
3. **Risk-Adjusted Metrics** - Beyond simple returns
4. **Reporting System** - Automated performance reports

---

## 🏗️ Architecture Design

### **Strategy Framework Architecture**
```
┌─────────────────────────────────────────────────────────────────┐
│                      Strategy Engine                            │
│                                                                 │
│  ┌─────────────┐   ┌─────────────┐   ┌─────────────┐         │
│  │  Strategy   │   │  Strategy   │   │  Strategy   │         │
│  │  Registry   │   │  Loader     │   │  Monitor    │         │
│  └─────────────┘   └─────────────┘   └─────────────┘         │
│                                                                 │
│  ┌──────────────────────────────────────────────────────────┐ │
│  │              Strategy Instances (Active)                  │ │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  │ │
│  │  │ Bollinger    │  │ Momentum     │  │ Pairs Trade  │  │ │
│  │  │ Bands        │  │ Strategy     │  │ Strategy     │  │ │
│  │  └──────────────┘  └──────────────┘  └──────────────┘  │ │
│  └──────────────────────────────────────────────────────────┘ │
│                            │                                    │
│                    ┌───────┴───────┐                          │
│                    │               │                          │
│          ┌─────────▼─────┐  ┌─────▼──────┐                  │
│          │ Signal        │  │ Risk       │                  │
│          │ Generator     │  │ Manager    │                  │
│          └─────────┬─────┘  └─────┬──────┘                  │
│                    │               │                          │
│                    └───────┬───────┘                          │
│                            │                                    │
└────────────────────────────┼────────────────────────────────────┘
                             │
                    ┌────────▼─────────┐
                    │   Event Bus      │
                    │  (from Week 1)   │
                    └────────┬─────────┘
                             │
                    ┌────────▼─────────┐
                    │  Order Manager   │
                    │  Database        │
                    └──────────────────┘
```

### **Backtesting Architecture**
```
┌─────────────────────────────────────────────────────────────────┐
│                    Backtesting Engine                           │
│                                                                 │
│  ┌──────────────────────────────────────────────────────────┐ │
│  │           Historical Data Pipeline                        │ │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌─────────┐ │ │
│  │  │   TWS    │─▶│  Cache   │─▶│ Validate │─▶│ Storage │ │ │
│  │  │  Fetcher │  │          │  │          │  │ (DB)    │ │ │
│  │  └──────────┘  └──────────┘  └──────────┘  └─────────┘ │ │
│  └──────────────────────────────────────────────────────────┘ │
│                                                                 │
│  ┌──────────────────────────────────────────────────────────┐ │
│  │           Simulation Engine                               │ │
│  │  ┌──────────────────────────────────────────────────┐   │ │
│  │  │  Time Loop (Bar-by-Bar Replay)                   │   │ │
│  │  │  ┌────────┐  ┌────────┐  ┌────────┐  ┌────────┐│   │ │
│  │  │  │ Load   │─▶│ Signal │─▶│ Order  │─▶│ Update ││   │ │
│  │  │  │ Bar    │  │ Gen    │  │ Fill   │  │ P&L    ││   │ │
│  │  │  └────────┘  └────────┘  └────────┘  └────────┘│   │ │
│  │  └──────────────────────────────────────────────────┘   │ │
│  └──────────────────────────────────────────────────────────┘ │
│                                                                 │
│  ┌──────────────────────────────────────────────────────────┐ │
│  │           Performance Analytics                           │ │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌─────────┐ │ │
│  │  │ Returns  │  │  Sharpe  │  │ Drawdown │  │ Report  │ │ │
│  │  │ Calc     │  │  Ratio   │  │ Analysis │  │ Gen     │ │ │
│  │  └──────────┘  └──────────┘  └──────────┘  └─────────┘ │ │
│  └──────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
```

---

## 📂 Project Structure (Week 2 Additions)

```bash
tws_robot/
├── 📁 strategies/              # NEW - Strategy implementations
│   ├── __init__.py
│   ├── base_strategy.py        # Abstract base class for all strategies
│   ├── strategy_registry.py   # Strategy registration and discovery
│   ├── signal.py              # Signal data classes and enums
│   ├── mean_reversion.py      # Bollinger Bands strategy (migrated)
│   └── config/                # Strategy configuration files
│       ├── bollinger_bands.yaml
│       └── strategy_defaults.yaml
│
├── 📁 backtesting/             # NEW - Backtesting framework
│   ├── __init__.py
│   ├── backtest_engine.py     # Main backtesting engine
│   ├── historical_data.py     # Historical data fetching and caching
│   ├── simulator.py           # Order execution simulation
│   ├── performance.py         # Performance metrics calculation
│   └── optimizer.py           # Parameter optimization framework
│
├── 📁 analytics/               # NEW - Performance analytics
│   ├── __init__.py
│   ├── metrics.py             # Sharpe, Sortino, Calmar, etc.
│   ├── reports.py             # Report generation
│   └── visualizations.py      # Performance charts (optional)
│
├── 📁 core/                    # EXISTING (from Week 1)
│   ├── event_bus.py           # Event-driven communication
│   ├── connection.py          # TWS connection
│   ├── order_manager.py       # Order execution
│   ├── contract_builder.py    # Contract creation
│   └── rate_limiter.py        # API rate limiting
│
├── 📁 data/                    # EXISTING (from Week 1)
│   ├── database.py            # Database connection
│   ├── models.py              # SQLAlchemy models
│   └── NEW MODELS:
│       └── backtest_results.py # Backtest result storage
│
├── 📁 tests/                   # ENHANCED (from Week 1)
│   ├── test_strategies.py     # NEW - Strategy tests
│   ├── test_backtesting.py    # NEW - Backtest engine tests
│   ├── test_performance.py    # NEW - Performance metrics tests
│   └── fixtures/              # NEW - Test data fixtures
│       └── sample_bars.csv
│
├── 📁 scripts/                 # NEW - Utility scripts
│   ├── run_backtest.py        # CLI for running backtests
│   ├── fetch_historical.py    # Download historical data
│   └── compare_strategies.py  # Strategy comparison tool
│
└── config/                     # ENHANCED
    └── strategies.yaml         # NEW - Strategy configurations

```

---

## 💻 Implementation Details

### **1. BaseStrategy Abstract Class**
**File:** `strategies/base_strategy.py`

```python
"""
Abstract base class for all trading strategies.

Provides standard interface for strategy lifecycle, signal generation,
and integration with the trading system.
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List
from datetime import datetime
from dataclasses import dataclass
from enum import Enum
import logging

from core.event_bus import Event, EventType, get_event_bus
from strategies.signal import Signal, SignalType


class StrategyState(Enum):
    """Strategy lifecycle states"""
    INITIALIZING = "INITIALIZING"
    READY = "READY"
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    STOPPED = "STOPPED"
    ERROR = "ERROR"


@dataclass
class StrategyConfig:
    """Strategy configuration data"""
    name: str
    symbols: List[str]
    enabled: bool = True
    parameters: Dict[str, Any] = None
    risk_limits: Dict[str, float] = None
    
    def __post_init__(self):
        if self.parameters is None:
            self.parameters = {}
        if self.risk_limits is None:
            self.risk_limits = {
                'max_position_size': 0.05,  # 5% of portfolio
                'max_daily_loss': 0.02      # 2% daily loss limit
            }


class BaseStrategy(ABC):
    """
    Abstract base class for trading strategies.
    
    All strategies must inherit from this class and implement:
    - on_bar(): Process new market data
    - on_signal(): React to generated signals
    - validate_signal(): Validate signal before execution
    
    Provides built-in:
    - Event bus integration
    - State management
    - Configuration hot-reloading
    - Performance tracking
    - Risk management hooks
    """
    
    def __init__(self, config: StrategyConfig):
        self.config = config
        self.name = config.name
        self.symbols = config.symbols
        self.state = StrategyState.INITIALIZING
        
        # Event bus integration
        self.event_bus = get_event_bus()
        
        # Strategy state
        self.positions: Dict[str, float] = {}  # symbol -> quantity
        self.signals_generated = 0
        self.trades_executed = 0
        
        # Performance tracking
        self.pnl = 0.0
        self.trades: List[Dict] = []
        
        # Logging
        self.logger = logging.getLogger(f"strategy.{self.name}")
        
        # Subscribe to relevant events
        self._subscribe_to_events()
        
        self.logger.info(f"Strategy '{self.name}' initialized")
    
    def _subscribe_to_events(self):
        """Subscribe to system events"""
        self.event_bus.subscribe(EventType.MARKET_DATA_RECEIVED, self._handle_market_data)
        self.event_bus.subscribe(EventType.ORDER_FILLED, self._handle_order_filled)
        self.event_bus.subscribe(EventType.POSITION_UPDATED, self._handle_position_update)
    
    # ==================== Lifecycle Methods ====================
    
    def start(self):
        """Start the strategy"""
        if self.state in [StrategyState.RUNNING, StrategyState.READY]:
            self.logger.warning(f"Strategy already running: {self.state}")
            return
        
        try:
            self.on_start()
            self.state = StrategyState.RUNNING
            self.event_bus.publish(Event(
                EventType.STRATEGY_STARTED,
                data={'strategy': self.name, 'timestamp': datetime.now()}
            ))
            self.logger.info(f"Strategy '{self.name}' started")
        except Exception as e:
            self.state = StrategyState.ERROR
            self.logger.error(f"Failed to start strategy: {e}", exc_info=True)
            raise
    
    def stop(self):
        """Stop the strategy"""
        try:
            self.on_stop()
            self.state = StrategyState.STOPPED
            self.event_bus.publish(Event(
                EventType.STRATEGY_STOPPED,
                data={'strategy': self.name, 'timestamp': datetime.now()}
            ))
            self.logger.info(f"Strategy '{self.name}' stopped")
        except Exception as e:
            self.logger.error(f"Error stopping strategy: {e}", exc_info=True)
    
    def pause(self):
        """Pause strategy execution"""
        if self.state == StrategyState.RUNNING:
            self.state = StrategyState.PAUSED
            self.logger.info(f"Strategy '{self.name}' paused")
    
    def resume(self):
        """Resume strategy execution"""
        if self.state == StrategyState.PAUSED:
            self.state = StrategyState.RUNNING
            self.logger.info(f"Strategy '{self.name}' resumed")
    
    def reload_config(self, new_config: StrategyConfig):
        """Hot-reload strategy configuration"""
        self.logger.info(f"Reloading configuration for '{self.name}'")
        old_params = self.config.parameters.copy()
        self.config = new_config
        
        # Allow strategy-specific reload logic
        self.on_config_reload(old_params, new_config.parameters)
    
    # ==================== Event Handlers ====================
    
    def _handle_market_data(self, event: Event):
        """Handle incoming market data"""
        if self.state != StrategyState.RUNNING:
            return
        
        # Extract bar data
        bar_data = event.data
        symbol = bar_data.get('symbol')
        
        # Only process if symbol is in our watchlist
        if symbol not in self.symbols:
            return
        
        try:
            # Call strategy-specific bar processing
            self.on_bar(bar_data)
        except Exception as e:
            self.logger.error(f"Error processing bar: {e}", exc_info=True)
    
    def _handle_order_filled(self, event: Event):
        """Handle order fill notification"""
        fill_data = event.data
        self.trades_executed += 1
        
        # Update performance tracking
        self.trades.append({
            'timestamp': datetime.now(),
            'symbol': fill_data.get('symbol'),
            'side': fill_data.get('side'),
            'quantity': fill_data.get('quantity'),
            'price': fill_data.get('price')
        })
        
        # Call strategy-specific handler
        self.on_order_filled(fill_data)
    
    def _handle_position_update(self, event: Event):
        """Handle position update"""
        position_data = event.data
        symbol = position_data.get('symbol')
        quantity = position_data.get('quantity', 0)
        
        # Update internal position tracking
        self.positions[symbol] = quantity
        
        # Call strategy-specific handler
        self.on_position_update(position_data)
    
    # ==================== Signal Management ====================
    
    def generate_signal(self, signal: Signal):
        """
        Generate and publish a trading signal.
        
        Validates signal and publishes to event bus for execution.
        """
        # Validate signal
        if not self.validate_signal(signal):
            self.logger.warning(f"Signal validation failed: {signal}")
            return
        
        self.signals_generated += 1
        
        # Publish signal event
        self.event_bus.publish(Event(
            EventType.SIGNAL_GENERATED,
            data={
                'strategy': self.name,
                'signal': signal.to_dict(),
                'timestamp': datetime.now()
            }
        ))
        
        self.logger.info(f"Signal generated: {signal}")
    
    # ==================== Abstract Methods (Must Implement) ====================
    
    @abstractmethod
    def on_bar(self, bar_data: Dict[str, Any]):
        """
        Process new market data bar.
        
        Called for each new bar of market data for symbols in watchlist.
        Implement strategy logic here to analyze data and generate signals.
        
        Args:
            bar_data: Dictionary with keys:
                - symbol: str
                - timestamp: datetime
                - open, high, low, close: float
                - volume: int
        """
        pass
    
    @abstractmethod
    def validate_signal(self, signal: Signal) -> bool:
        """
        Validate trading signal before execution.
        
        Implement strategy-specific validation logic:
        - Position size limits
        - Risk checks
        - Market conditions
        
        Args:
            signal: Signal object to validate
            
        Returns:
            bool: True if signal is valid, False otherwise
        """
        pass
    
    # ==================== Optional Hooks ====================
    
    def on_start(self):
        """Called when strategy starts. Override for custom initialization."""
        pass
    
    def on_stop(self):
        """Called when strategy stops. Override for cleanup logic."""
        pass
    
    def on_config_reload(self, old_params: Dict, new_params: Dict):
        """Called when configuration is hot-reloaded. Override to handle parameter changes."""
        pass
    
    def on_order_filled(self, fill_data: Dict[str, Any]):
        """Called when an order is filled. Override for custom fill handling."""
        pass
    
    def on_position_update(self, position_data: Dict[str, Any]):
        """Called when position is updated. Override for custom position tracking."""
        pass
    
    # ==================== Utility Methods ====================
    
    def get_position(self, symbol: str) -> float:
        """Get current position size for symbol"""
        return self.positions.get(symbol, 0.0)
    
    def has_position(self, symbol: str) -> bool:
        """Check if strategy has open position in symbol"""
        return abs(self.get_position(symbol)) > 0
    
    def get_performance_summary(self) -> Dict[str, Any]:
        """Get strategy performance summary"""
        return {
            'name': self.name,
            'state': self.state.value,
            'signals_generated': self.signals_generated,
            'trades_executed': self.trades_executed,
            'pnl': self.pnl,
            'positions': self.positions.copy()
        }
```

### **2. Signal Data Classes**
**File:** `strategies/signal.py`

```python
"""
Trading signal data structures.

Standardized signal format for communication between strategies
and execution systems.
"""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Optional, Dict, Any


class SignalType(Enum):
    """Types of trading signals"""
    BUY = "BUY"
    SELL = "SELL"
    CLOSE = "CLOSE"  # Close existing position
    HOLD = "HOLD"    # No action


class SignalStrength(Enum):
    """Signal confidence levels"""
    WEAK = 1
    MODERATE = 2
    STRONG = 3
    VERY_STRONG = 4


@dataclass
class Signal:
    """
    Trading signal from strategy to execution system.
    
    Contains all information needed to execute a trade.
    """
    symbol: str
    signal_type: SignalType
    strength: SignalStrength
    timestamp: datetime
    
    # Price and sizing
    target_price: Optional[float] = None
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    quantity: Optional[int] = None
    
    # Context and metadata
    reason: Optional[str] = None
    indicators: Optional[Dict[str, float]] = None
    strategy_name: Optional[str] = None
    confidence: float = 0.0  # 0.0 to 1.0
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert signal to dictionary for serialization"""
        return {
            'symbol': self.symbol,
            'signal_type': self.signal_type.value,
            'strength': self.strength.value,
            'timestamp': self.timestamp.isoformat(),
            'target_price': self.target_price,
            'stop_loss': self.stop_loss,
            'take_profit': self.take_profit,
            'quantity': self.quantity,
            'reason': self.reason,
            'indicators': self.indicators,
            'strategy_name': self.strategy_name,
            'confidence': self.confidence
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Signal':
        """Create signal from dictionary"""
        return cls(
            symbol=data['symbol'],
            signal_type=SignalType(data['signal_type']),
            strength=SignalStrength(data['strength']),
            timestamp=datetime.fromisoformat(data['timestamp']),
            target_price=data.get('target_price'),
            stop_loss=data.get('stop_loss'),
            take_profit=data.get('take_profit'),
            quantity=data.get('quantity'),
            reason=data.get('reason'),
            indicators=data.get('indicators'),
            strategy_name=data.get('strategy_name'),
            confidence=data.get('confidence', 0.0)
        )
    
    def is_entry_signal(self) -> bool:
        """Check if this is an entry signal (BUY or SELL)"""
        return self.signal_type in [SignalType.BUY, SignalType.SELL]
    
    def is_exit_signal(self) -> bool:
        """Check if this is an exit signal"""
        return self.signal_type == SignalType.CLOSE
    
    def __str__(self) -> str:
        return (f"Signal({self.signal_type.value} {self.symbol} "
                f"@ {self.target_price:.2f} - {self.reason})")
```

### **3. Backtest Engine**
**File:** `backtesting/backtest_engine.py`

```python
"""
Backtesting engine for strategy validation.

Simulates strategy execution on historical data with realistic
order filling, slippage, and commission modeling.
"""

from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta
import pandas as pd
import logging
from dataclasses import dataclass, field

from strategies.base_strategy import BaseStrategy
from strategies.signal import Signal, SignalType
from analytics.metrics import PerformanceMetrics


@dataclass
class BacktestConfig:
    """Backtesting configuration"""
    start_date: datetime
    end_date: datetime
    initial_capital: float = 100000.0
    commission_per_share: float = 0.005  # $0.005 per share
    slippage_pct: float = 0.001  # 0.1% slippage
    bar_size: str = "1min"  # 1min, 5min, 1day, etc.
    
    # Risk parameters
    max_position_size: float = 0.10  # 10% of capital per position
    max_portfolio_heat: float = 0.50  # 50% max deployed capital
    
    # Execution parameters
    fill_on_next_bar: bool = True  # Fill orders at next bar open
    use_bid_ask: bool = False  # Use bid/ask spread (if available)


@dataclass
class BacktestResult:
    """Backtesting results"""
    strategy_name: str
    config: BacktestConfig
    
    # Performance metrics
    total_return: float = 0.0
    sharpe_ratio: float = 0.0
    sortino_ratio: float = 0.0
    calmar_ratio: float = 0.0
    max_drawdown: float = 0.0
    
    # Trading statistics
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    win_rate: float = 0.0
    avg_win: float = 0.0
    avg_loss: float = 0.0
    profit_factor: float = 0.0
    
    # Time series data
    equity_curve: pd.Series = field(default_factory=pd.Series)
    drawdown_curve: pd.Series = field(default_factory=pd.Series)
    trades: List[Dict] = field(default_factory=list)
    
    # Execution details
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    duration_days: int = 0
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert result to dictionary"""
        return {
            'strategy_name': self.strategy_name,
            'total_return': self.total_return,
            'sharpe_ratio': self.sharpe_ratio,
            'sortino_ratio': self.sortino_ratio,
            'calmar_ratio': self.calmar_ratio,
            'max_drawdown': self.max_drawdown,
            'total_trades': self.total_trades,
            'winning_trades': self.winning_trades,
            'losing_trades': self.losing_trades,
            'win_rate': self.win_rate,
            'avg_win': self.avg_win,
            'avg_loss': self.avg_loss,
            'profit_factor': self.profit_factor,
            'duration_days': self.duration_days
        }


class BacktestEngine:
    """
    Main backtesting engine.
    
    Simulates strategy execution on historical data with:
    - Bar-by-bar replay
    - Realistic order filling
    - Commission and slippage
    - Position and P&L tracking
    """
    
    def __init__(self, config: BacktestConfig):
        self.config = config
        self.logger = logging.getLogger(__name__)
        
        # Portfolio state
        self.cash = config.initial_capital
        self.positions: Dict[str, int] = {}  # symbol -> quantity
        self.position_avg_price: Dict[str, float] = {}
        
        # Performance tracking
        self.equity_history: List[tuple] = []  # (timestamp, equity)
        self.trades: List[Dict] = []
        self.pending_orders: List[Signal] = []
        
        # Metrics calculator
        self.metrics = PerformanceMetrics()
    
    def run(self, strategy: BaseStrategy, 
            historical_data: Dict[str, pd.DataFrame]) -> BacktestResult:
        """
        Run backtest for given strategy and data.
        
        Args:
            strategy: Strategy instance to backtest
            historical_data: Dict of symbol -> DataFrame with OHLCV data
            
        Returns:
            BacktestResult with performance metrics and trade history
        """
        self.logger.info(f"Starting backtest: {strategy.name}")
        self.logger.info(f"Period: {self.config.start_date} to {self.config.end_date}")
        
        # Reset state
        self._reset_state()
        
        # Get aligned bars across all symbols
        all_bars = self._align_historical_data(historical_data)
        
        # Bar-by-bar simulation
        for bar_time, bars_dict in all_bars:
            # Process pending orders first (fill at open)
            self._process_pending_orders(bars_dict)
            
            # Feed bars to strategy
            for symbol, bar in bars_dict.items():
                strategy.on_bar({
                    'symbol': symbol,
                    'timestamp': bar_time,
                    'open': bar['open'],
                    'high': bar['high'],
                    'low': bar['low'],
                    'close': bar['close'],
                    'volume': bar['volume']
                })
            
            # Update portfolio value
            portfolio_value = self._calculate_portfolio_value(bars_dict)
            self.equity_history.append((bar_time, portfolio_value))
        
        # Calculate final metrics
        result = self._calculate_results(strategy.name)
        
        self.logger.info(f"Backtest complete: {result.total_trades} trades, "
                        f"{result.total_return:.2%} return")
        
        return result
    
    def _reset_state(self):
        """Reset backtest state"""
        self.cash = self.config.initial_capital
        self.positions = {}
        self.position_avg_price = {}
        self.equity_history = []
        self.trades = []
        self.pending_orders = []
    
    def _align_historical_data(self, 
                              historical_data: Dict[str, pd.DataFrame]) -> List[tuple]:
        """
        Align historical data across symbols.
        
        Returns list of (timestamp, {symbol: bar_data}) tuples
        """
        # Implementation: Merge dataframes on timestamp
        # Handle missing bars, forward-fill prices, etc.
        # For now, simplified version
        
        aligned_bars = []
        # ... implementation details ...
        return aligned_bars
    
    def _process_pending_orders(self, bars_dict: Dict[str, Dict]):
        """Process pending orders at bar open"""
        for signal in self.pending_orders[:]:
            symbol = signal.symbol
            if symbol not in bars_dict:
                continue
            
            bar = bars_dict[symbol]
            fill_price = bar['open']
            
            # Apply slippage
            if signal.signal_type == SignalType.BUY:
                fill_price *= (1 + self.config.slippage_pct)
            else:
                fill_price *= (1 - self.config.slippage_pct)
            
            # Execute order
            self._execute_order(signal, fill_price, bar['timestamp'])
            
            # Remove from pending
            self.pending_orders.remove(signal)
    
    def _execute_order(self, signal: Signal, fill_price: float, timestamp: datetime):
        """Execute order and update positions"""
        symbol = signal.symbol
        quantity = signal.quantity or 100  # Default quantity
        
        # Calculate commission
        commission = quantity * self.config.commission_per_share
        
        if signal.signal_type == SignalType.BUY:
            # Check if we have enough cash
            cost = quantity * fill_price + commission
            if cost > self.cash:
                self.logger.warning(f"Insufficient cash for {symbol}: need ${cost:.2f}")
                return
            
            # Open/add to position
            self.positions[symbol] = self.positions.get(symbol, 0) + quantity
            self.cash -= cost
            
            # Update average price
            current_qty = self.positions[symbol] - quantity
            if current_qty == 0:
                self.position_avg_price[symbol] = fill_price
            else:
                total_cost = (self.position_avg_price[symbol] * current_qty + 
                            fill_price * quantity)
                self.position_avg_price[symbol] = total_cost / self.positions[symbol]
            
        elif signal.signal_type == SignalType.SELL:
            # Close position
            if symbol not in self.positions or self.positions[symbol] == 0:
                self.logger.warning(f"No position to close for {symbol}")
                return
            
            quantity = self.positions[symbol]  # Sell entire position
            proceeds = quantity * fill_price - commission
            self.cash += proceeds
            
            # Calculate P&L
            avg_price = self.position_avg_price[symbol]
            pnl = (fill_price - avg_price) * quantity - commission
            
            # Record trade
            self.trades.append({
                'symbol': symbol,
                'entry_price': avg_price,
                'exit_price': fill_price,
                'quantity': quantity,
                'pnl': pnl,
                'timestamp': timestamp
            })
            
            # Remove position
            del self.positions[symbol]
            del self.position_avg_price[symbol]
    
    def _calculate_portfolio_value(self, bars_dict: Dict[str, Dict]) -> float:
        """Calculate total portfolio value"""
        value = self.cash
        
        for symbol, quantity in self.positions.items():
            if symbol in bars_dict:
                value += quantity * bars_dict[symbol]['close']
        
        return value
    
    def _calculate_results(self, strategy_name: str) -> BacktestResult:
        """Calculate final performance metrics"""
        result = BacktestResult(
            strategy_name=strategy_name,
            config=self.config
        )
        
        # Convert equity history to Series
        equity_df = pd.DataFrame(self.equity_history, columns=['timestamp', 'equity'])
        equity_df.set_index('timestamp', inplace=True)
        result.equity_curve = equity_df['equity']
        
        # Calculate returns
        returns = result.equity_curve.pct_change().dropna()
        result.total_return = (result.equity_curve.iloc[-1] / 
                              self.config.initial_capital - 1)
        
        # Calculate metrics
        result.sharpe_ratio = self.metrics.sharpe_ratio(returns)
        result.sortino_ratio = self.metrics.sortino_ratio(returns)
        result.max_drawdown = self.metrics.max_drawdown(result.equity_curve)
        result.calmar_ratio = (result.total_return / abs(result.max_drawdown) 
                              if result.max_drawdown != 0 else 0)
        
        # Trade statistics
        result.trades = self.trades
        result.total_trades = len(self.trades)
        
        if result.total_trades > 0:
            winning = [t for t in self.trades if t['pnl'] > 0]
            losing = [t for t in self.trades if t['pnl'] <= 0]
            
            result.winning_trades = len(winning)
            result.losing_trades = len(losing)
            result.win_rate = result.winning_trades / result.total_trades
            
            if winning:
                result.avg_win = sum(t['pnl'] for t in winning) / len(winning)
            if losing:
                result.avg_loss = sum(t['pnl'] for t in losing) / len(losing)
            
            if result.avg_loss != 0:
                result.profit_factor = abs(result.avg_win / result.avg_loss)
        
        # Duration
        result.start_date = self.config.start_date
        result.end_date = self.config.end_date
        result.duration_days = (result.end_date - result.start_date).days
        
        return result
```

---

## 📅 Week 2 Daily Schedule

### **Day 1 (Monday): Strategy Framework Foundation**
**Morning (4 hours):**
- Create `strategies/` directory structure
- Implement `BaseStrategy` abstract class
- Implement `Signal` and related enums
- Write unit tests for strategy framework

**Afternoon (4 hours):**
- Implement `StrategyRegistry` for strategy management
- Create strategy lifecycle manager
- Add event bus integration
- Test strategy registration and lifecycle

**Deliverables:**
- ✅ `base_strategy.py` with full lifecycle support
- ✅ `signal.py` with signal data structures
- ✅ `strategy_registry.py` for strategy management
- ✅ Unit tests for strategy framework

### **Day 2 (Tuesday): Configuration & Hot-Reload**
**Morning (4 hours):**
- Design strategy configuration YAML schema
- Implement configuration loading system
- Add configuration validation
- Create default configuration templates

**Afternoon (4 hours):**
- Implement hot-reload capability
- Add configuration change detection
- Create configuration management tests
- Document configuration options

**Deliverables:**
- ✅ Strategy configuration system
- ✅ Hot-reload functionality
- ✅ Configuration validation
- ✅ Example configuration files

### **Day 3 (Wednesday): Historical Data & Backtest Setup**
**Morning (4 hours):**
- Create `backtesting/` directory
- Implement historical data fetcher
- Add data caching mechanism
- Create data validation utilities

**Afternoon (4 hours):**
- Design backtest engine architecture
- Implement `BacktestConfig` and `BacktestResult`
- Create portfolio state tracking
- Write initial backtest engine skeleton

**Deliverables:**
- ✅ Historical data manager
- ✅ Backtest engine framework
- ✅ Portfolio tracking system
- ✅ Data validation tests

### **Day 4 (Thursday): Backtest Engine Implementation**
**Morning (4 hours):**
- Implement bar-by-bar simulation loop
- Add order execution simulation
- Implement slippage and commission modeling
- Create position and P&L tracking

**Afternoon (4 hours):**
- Add performance metrics calculation
- Implement equity curve generation
- Create trade history logging
- Write backtest engine tests

**Deliverables:**
- ✅ Complete backtest engine
- ✅ Realistic order execution simulation
- ✅ Performance metrics calculation
- ✅ Backtest engine tests

### **Day 5 (Friday): Bollinger Bands Migration**
**Morning (4 hours):**
- Extract Bollinger Bands logic from old code
- Adapt to new `BaseStrategy` framework
- Implement signal generation logic
- Add strategy-specific configuration

**Afternoon (4 hours):**
- Create strategy unit tests
- Run backtests on historical data
- Compare results with old implementation
- Document strategy parameters

**Deliverables:**
- ✅ Migrated Bollinger Bands strategy
- ✅ Strategy validation tests
- ✅ Backtest results comparison
- ✅ Strategy documentation

### **Day 6 (Saturday): Performance Analytics**
**Morning (4 hours):**
- Create `analytics/` directory
- Implement `PerformanceMetrics` class
- Add Sharpe, Sortino, Calmar ratios
- Implement drawdown analysis

**Afternoon (4 hours):**
- Create performance report generator
- Add strategy comparison tools
- Implement visualization utilities
- Write analytics tests

**Deliverables:**
- ✅ Performance metrics library
- ✅ Report generation system
- ✅ Strategy comparison tools
- ✅ Analytics tests

### **Day 7 (Sunday): Integration & Testing**
**Morning (4 hours):**
- End-to-end integration testing
- Run full backtest suite
- Performance benchmarking
- Bug fixes and optimization

**Afternoon (4 hours):**
- Update documentation
- Create user guides
- Prepare Week 3 planning
- Code review and cleanup

**Deliverables:**
- ✅ Comprehensive integration tests
- ✅ Backtest suite validation
- ✅ Complete Week 2 documentation
- ✅ Week 3 preparation

---

## ✅ Week 2 Completion Checklist

### **Strategy Framework**
- [ ] BaseStrategy abstract class with lifecycle methods
- [ ] Signal data structures and enums
- [ ] Strategy registration and discovery
- [ ] Event bus integration
- [ ] Configuration management with hot-reload
- [ ] Strategy state management (RUNNING, PAUSED, STOPPED)

### **Backtesting Engine**
- [ ] Historical data fetcher and cache
- [ ] Bar-by-bar simulation engine
- [ ] Realistic order execution (slippage, commission)
- [ ] Portfolio and position tracking
- [ ] Performance metrics calculation
- [ ] Backtest result reporting

### **Performance Analytics**
- [ ] Sharpe ratio calculation
- [ ] Sortino ratio calculation
- [ ] Calmar ratio calculation
- [ ] Maximum drawdown analysis
- [ ] Win rate and profit factor
- [ ] Equity curve generation
- [ ] Report generator

### **Strategy Migration**
- [ ] Bollinger Bands strategy migrated
- [ ] Strategy validation tests
- [ ] Backtest comparison with old code
- [ ] Configuration templates created

### **Testing & Documentation**
- [ ] Unit tests for all modules (>80% coverage)
- [ ] Integration tests for backtest engine
- [ ] Strategy development guide
- [ ] API documentation
- [ ] Configuration documentation

### **Integration Points**
- [ ] Event bus integration complete
- [ ] Database models for backtest results
- [ ] Order manager integration
- [ ] Contract builder integration

---

## 🎯 Success Metrics

### **Technical Metrics**
- **Code Coverage**: >80% for strategy framework and backtest engine
- **Backtest Speed**: >1000 bars/second for single strategy
- **Memory Efficiency**: <500MB for 1-year daily backtest
- **Signal Latency**: <10ms from bar to signal generation

### **Functional Metrics**
- **Multi-Strategy Support**: 5+ strategies running concurrently
- **Backtest Accuracy**: <1% deviation from manual calculation
- **Configuration Hot-Reload**: <1 second to apply new parameters
- **Strategy Validation**: Zero breaking changes to existing code

### **Quality Metrics**
- **Test Pass Rate**: 100% of unit and integration tests
- **Code Quality**: Zero critical issues from linters
- **Documentation**: All public APIs documented
- **Performance**: No performance regressions vs Week 1

---

## 🚀 Week 3 Preview

**Focus:** Risk Management System
- Real-time risk monitoring
- Position sizing algorithms
- Portfolio heat maps
- Drawdown protection
- Emergency stop mechanisms

**Dependencies from Week 2:**
- Strategy framework for risk-aware signal generation
- Performance metrics for risk-adjusted returns
- Backtest engine for risk simulation

---

This Week 2 plan builds directly on the Week 1 foundation (Event Bus, Database, Core Modules) and sets up the essential strategy and backtesting infrastructure needed for Week 3's risk management system. Each day has clear, actionable deliverables that move the project forward systematically.

Ready to start Week 2?
