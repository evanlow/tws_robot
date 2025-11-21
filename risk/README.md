# Risk Management System

**Week 3 Implementation - Complete Trading Risk Management Framework**

## 🎯 Overview

This risk management system provides comprehensive protection for automated trading operations. It implements multiple layers of defense against catastrophic losses, monitors risks in real-time, and provides emergency controls for critical situations.

### Key Features

- **Multi-Layer Risk Protection**: Position sizing, portfolio heat management, drawdown monitoring
- **Real-Time Monitoring**: Continuous risk assessment with multi-level alerts
- **Emergency Controls**: Circuit breakers, kill switch, panic button
- **Correlation Analysis**: Cross-asset correlation tracking and concentration limits
- **Automated Protection**: Dynamic position sizing and exposure management
- **Recovery Protocols**: Controlled resumption after emergency stops

---

## 📋 Architecture

### Component Overview

```
Risk Management System
│
├── RiskManager (Core Risk Engine)
│   ├── Position sizing validation
│   ├── Portfolio heat management
│   ├── Daily loss tracking
│   └── Risk limits enforcement
│
├── PositionSizer (Position Sizing Algorithms)
│   ├── Fixed fractional sizing
│   ├── Kelly criterion
│   ├── Volatility-based sizing
│   ├── Risk parity allocation
│   └── ATR-based sizing
│
├── DrawdownMonitor (Drawdown Protection)
│   ├── Real-time drawdown tracking
│   ├── Protection mode activation
│   ├── Recovery protocols
│   └── Historical tracking
│
├── CorrelationAnalyzer (Portfolio Diversification)
│   ├── Rolling correlation calculation
│   ├── Concentration analysis
│   ├── Sector exposure tracking
│   └── Diversification scoring
│
├── RiskMonitor (Real-Time Alerts)
│   ├── Multi-level alert system
│   ├── Health scoring
│   ├── Dashboard data generation
│   └── Alert deduplication
│
└── EmergencyController (Circuit Breakers)
    ├── 5-level emergency system
    ├── Multiple circuit breakers
    ├── Kill switch / Panic button
    └── Recovery management
```

### Component Integration Flow

```
Trading Decision
      ↓
[PositionSizer] → Calculate position size
      ↓
[RiskManager] → Validate against limits
      ↓
[CorrelationAnalyzer] → Check diversification
      ↓
[DrawdownMonitor] → Check drawdown status
      ↓
[RiskMonitor] → Real-time health check
      ↓
[EmergencyController] → Emergency conditions check
      ↓
Execute Trade (if all checks pass)
      ↓
Continuous Monitoring & Updates
```

---

## 🚀 Quick Start

### Basic Setup

```python
from datetime import datetime
from risk import (
    RiskManager, PositionSizerFactory, DrawdownMonitor,
    CorrelationAnalyzer, RiskMonitor, EmergencyController,
    Position, PositionInfo
)

# Initialize core components
risk_manager = RiskManager(
    initial_capital=100000.0,
    max_positions=10,              # Max 10 concurrent positions
    max_position_pct=0.02,         # 2% max per position
    max_drawdown_pct=0.20,         # 20% max drawdown
    daily_loss_limit_pct=0.03,     # 3% daily loss limit
    concentration_limit=0.30       # 30% max sector concentration
)

# Use PositionSizerFactory to create sizers
position_sizer = PositionSizerFactory.create(
    'risk_based',                  # 'fixed', 'kelly', 'risk_based', 'risk_parity'
    risk_pct=0.02,                 # Risk 2% per trade
    max_position_pct=0.25
)

drawdown_monitor = DrawdownMonitor(
    initial_equity=100000.0,
    max_drawdown_pct=0.20,         # Hard stop at 20% DD
    daily_loss_limit_pct=0.05,     # 5% daily loss limit
    scale_positions_on_drawdown=True,
    minor_drawdown_threshold=0.05, # Minor DD at 5%
    moderate_drawdown_threshold=0.10, # Moderate DD at 10%
    severe_drawdown_threshold=0.15 # Severe DD at 15%
)

correlation_analyzer = CorrelationAnalyzer(
    concentration_threshold=0.25,  # HHI threshold
    high_correlation_threshold=0.8, # High correlation warning
    max_sector_concentration=0.50, # 50% max per sector
    max_industry_concentration=0.35 # 35% max per industry
)

risk_monitor = RiskMonitor(
    risk_manager=risk_manager,
    drawdown_monitor=drawdown_monitor,
    correlation_analyzer=correlation_analyzer
)

emergency_controller = EmergencyController(
    max_drawdown_pct=0.20,        # 20% max drawdown
    critical_drawdown_pct=0.15,   # 15% triggers circuit breaker
    max_daily_loss_pct=0.05,      # 5% max daily loss
    cooldown_minutes=30,          # 30-min cooldown after emergency
    require_manual_review=True    # Require approval to resume
)
```

### Basic Usage

```python
from datetime import datetime
from risk import Position

# Current positions dict (symbol -> Position)
positions = {}

# 1. Calculate position size
result = position_sizer.calculate(
    symbol='AAPL',
    price=150.0,
    equity=100000.0,
    stop_loss_pct=0.033  # 5/150 = 3.3% stop
)

print(f"Position size: {result.shares} shares")
print(f"Position value: ${result.position_value:,.2f}")
print(f"Position %: {result.position_pct:.2%}")

# 2. Validate with risk manager
allowed, reason = risk_manager.check_trade_risk(
    symbol='AAPL',
    side='LONG',
    quantity=result.shares,
    price=150.0,
    positions=positions
)

if not allowed:
    print(f"Trade rejected: {reason}")
    exit()

# 3. Check emergency conditions
emergency_status = emergency_controller.check_emergency_conditions(
    current_equity=100000.0,
    starting_equity=100000.0,
    daily_starting_equity=100000.0,
    peak_equity=105000.0,
    positions=positions,
    timestamp=datetime.now()
)

if not emergency_status.trading_allowed:
    print(f"Trading blocked: {emergency_status.level}")
    exit()

# 4. Execute trade
# ... your broker API call here ...

# Add position to tracking
positions['AAPL'] = Position(
    symbol='AAPL',
    quantity=result.shares,
    entry_price=150.0,
    current_price=150.0,
    side='LONG'
)

# 5. Update risk tracking
risk_metrics = risk_manager.update(
    equity=100000.0,
    positions=positions,
    current_date=datetime.now()
)

dd_metrics = drawdown_monitor.update(
    current_equity=100000.0,
    current_date=datetime.now()
)

print(f"Risk Status: {risk_metrics.risk_status}")
print(f"Drawdown: {dd_metrics.drawdown_pct:.2%}")
print(f"Position Scaling: {dd_metrics.position_scale_factor:.0%}")
```

---

## 📚 Component Documentation

### 1. RiskManager

**Purpose**: Core risk management engine that enforces position limits, drawdown limits, and daily loss limits.

**Key Methods**:
- `check_trade_risk(symbol, side, quantity, price, positions)` → `Tuple[bool, str]` - Validates trade
- `update(equity, positions, current_date)` → `RiskMetrics` - Updates risk state
- `calculate_position_size(symbol, price, strategy, **kwargs)` → `int` - Calculates shares
- `trigger_emergency_stop(reason)` - Activate emergency stop
- `release_emergency_stop(reason)` - Release emergency stop
- `get_risk_summary()` → `Dict` - Get current risk status

**Configuration**:
```python
RiskManager(
    initial_capital=100000.0,
    max_positions=10,               # Max 10 concurrent positions
    max_position_pct=0.25,          # Max 25% per position
    max_drawdown_pct=0.20,          # Max 20% drawdown
    daily_loss_limit_pct=0.05,      # Max 5% daily loss
    max_leverage=1.0,               # No leverage by default
    concentration_limit=0.50,       # Max 50% sector concentration
    emergency_stop_enabled=True
)
```

**Usage Example**:
```python
# Check if trade is allowed
allowed, reason = risk_manager.check_trade_risk(
    symbol='AAPL',
    side='LONG',
    quantity=100,
    price=150.0,
    positions=current_positions
)

# Update risk state
metrics = risk_manager.update(
    equity=100000.0,
    positions=current_positions,
    current_date=datetime.now()
)

print(f"Leverage: {metrics.leverage:.2f}x")
print(f"Drawdown: {metrics.drawdown_pct:.2%}")
```

---

### 2. PositionSizer

**Purpose**: Calculate optimal position sizes using various algorithms based on risk tolerance and market conditions.

**Important**: Use `PositionSizerFactory` to create position sizers - `PositionSizer` is an abstract base class.

**Sizing Methods**:

1. **Fixed Percent** - Fixed percentage of capital
   ```python
   sizer = PositionSizerFactory.create(
       'fixed',
       fixed_pct=0.05,            # 5% per position
       max_position_pct=0.25
   )
   
   result = sizer.calculate(
       symbol='AAPL',
       price=150.0,
       equity=100000.0
   )
   print(f"Shares: {result.shares}")
   ```

2. **Kelly Criterion** - Optimal sizing based on win rate
   ```python
   sizer = PositionSizerFactory.create(
       'kelly',
       kelly_fraction=0.5,        # Half-Kelly for safety
       max_position_pct=0.25
   )
   
   result = sizer.calculate(
       symbol='AAPL',
       price=150.0,
       equity=100000.0,
       win_rate=0.55,             # 55% win rate
       avg_win=0.05,              # 5% average win
       avg_loss=0.03              # 3% average loss
   )
   ```

3. **Risk-Based** - Size based on risk per trade and stop loss
   ```python
   sizer = PositionSizerFactory.create(
       'risk_based',
       risk_pct=0.02,             # Risk 2% per trade
       max_position_pct=0.25
   )
   
   result = sizer.calculate(
       symbol='AAPL',
       price=150.0,
       equity=100000.0,
       stop_loss_pct=0.033        # 3.3% stop (5 points / 150)
   )
   ```

4. **Risk Parity** - Equal risk contribution
   ```python
   sizer = PositionSizerFactory.create(
       'risk_parity',
       target_risk_pct=0.10,      # 10% target portfolio risk
       max_position_pct=0.25
   )
   
   result = sizer.calculate(
       symbol='AAPL',
       price=150.0,
       equity=100000.0,
       volatility=0.02,           # 2% daily volatility
       num_positions=5
   )
   ```

**Factory Methods**:
```python
# List available strategies
strategies = PositionSizerFactory.list_strategies()
# Returns: ['fixed_percent', 'kelly', 'risk_based', 'risk_parity']

# Create specific sizer
sizer = PositionSizerFactory.create('risk_based', risk_pct=0.02)
```

---

### 3. DrawdownMonitor

**Purpose**: Track drawdowns in real-time and implement protection measures including position scaling and trading halts.

**Key Features**:
- Real-time drawdown calculation from peak equity
- Daily and weekly loss tracking
- Automatic position scaling during drawdowns
- Trading halt triggers based on severity
- Detailed drawdown event logging

**Drawdown Severity Levels**:
- **NORMAL**: No significant drawdown
- **MINOR**: 5-10% drawdown
- **MODERATE**: 10-15% drawdown
- **SEVERE**: 15-20% drawdown
- **CRITICAL**: >20% drawdown

**Usage**:
```python
# Update with current equity
metrics = drawdown_monitor.update(
    current_equity=95000.0,
    current_date=datetime.now()
)

print(f"Drawdown: {metrics.drawdown_pct:.2%}")
print(f"Severity: {metrics.severity}")
print(f"Position scale: {metrics.position_scale_factor:.0%}")
print(f"Trading halted: {metrics.is_trading_halted}")

if metrics.is_trading_halted:
    print(f"Halt reason: {metrics.halt_reason}")
    
# Use scaling factor for position sizing
if metrics.position_scale_factor < 1.0:
    # Reduce all position sizes by scale factor
    scaled_size = base_size * metrics.position_scale_factor
```

**Configuration**:
```python
DrawdownMonitor(
    initial_equity=100000.0,
    max_drawdown_pct=0.20,          # Hard stop at 20% DD
    daily_loss_limit_pct=0.05,      # 5% daily loss limit
    weekly_loss_limit_pct=0.10,     # 10% weekly loss limit
    scale_positions_on_drawdown=True, # Auto-scale positions
    minor_drawdown_threshold=0.05,  # 5% minor threshold
    moderate_drawdown_threshold=0.10, # 10% moderate threshold
    severe_drawdown_threshold=0.15  # 15% severe threshold
)
```

**Key Methods**:
- `update(current_equity, current_date)` → `DrawdownMetrics`
- `get_current_metrics()` → `DrawdownMetrics`
- `reset_to_peak(new_peak)` - Reset peak equity
- `get_drawdown_events()` → `List[DrawdownEvent]` - Historical events

---

### 4. CorrelationAnalyzer

**Purpose**: Monitor portfolio diversification through correlation analysis, concentration metrics, and sector/industry exposure tracking.

**Key Features**:
- Correlation matrix calculation between positions
- Portfolio concentration metrics (Herfindahl Index)
- Sector and industry exposure tracking
- Diversification scoring (0-100)
- High correlation pair identification

**Usage**:
```python
from risk import PositionInfo

# Create position info list
positions = [
    PositionInfo(
        symbol='AAPL',
        quantity=100,
        market_value=15000.0,
        weight=0.15,
        sector='Technology',
        industry='Consumer Electronics',
        returns=[0.01, -0.005, 0.02, ...]  # Optional historical returns
    ),
    PositionInfo(
        symbol='MSFT',
        quantity=50,
        market_value=18000.0,
        weight=0.18,
        sector='Technology',
        industry='Software'
    )
]

# Analyze portfolio
metrics = correlation_analyzer.analyze(
    positions=positions,
    timestamp=datetime.now()
)

print(f"HHI: {metrics.herfindahl_index:.3f}")  # 0-1, lower is better
print(f"Avg correlation: {metrics.avg_correlation:.2f}")
print(f"Diversification score: {metrics.diversification_score:.0f}")  # 0-100
print(f"Top sector: {max(metrics.sector_concentration, key=metrics.sector_concentration.get)}")
print(f"Concentrated: {metrics.is_concentrated}")
print(f"High correlations: {metrics.has_high_correlations}")

# Get high correlation pairs
pairs = correlation_analyzer.get_high_correlation_pairs(positions)
for pair in pairs:
    print(f"{pair.symbol1}-{pair.symbol2}: {pair.correlation:.2f} ({pair.risk_level})")
```

**Configuration**:
```python
CorrelationAnalyzer(
    concentration_threshold=0.25,       # HHI threshold
    high_correlation_threshold=0.8,     # High correlation warning
    critical_correlation_threshold=0.9, # Critical correlation
    max_sector_concentration=0.50,      # 50% max per sector
    max_industry_concentration=0.35,    # 35% max per industry
    min_diversification_score=60.0      # Minimum acceptable score
)
```

**Key Metrics**:
- **Herfindahl Index (HHI)**: 0-1, measures concentration (lower = more diversified)
- **Diversification Score**: 0-100 (higher = better diversification)
- **Effective Positions**: Number of truly independent positions

---

### 5. RiskMonitor

**Purpose**: Real-time unified monitoring across all risk components with multi-level alert system and health scoring.

**Alert Levels**:
- **INFO**: Informational notices (no action required)
- **WARNING**: Caution required (monitor closely)
- **CRITICAL**: Immediate attention required

**Alert Categories**:
- `POSITION_SIZE`, `PORTFOLIO_RISK`, `DRAWDOWN`, `CORRELATION`, `CONCENTRATION`, `SECTOR_RISK`, `DAILY_LOSS`

**Usage**:
```python
from risk import RiskMonitor, PositionInfo

# Create monitor with all components
monitor = RiskMonitor(
    risk_manager=risk_manager,
    drawdown_monitor=drawdown_monitor,
    correlation_analyzer=correlation_analyzer
)

# Comprehensive risk check
status = monitor.check_all_risks(
    current_equity=105000.0,
    positions=[
        PositionInfo(symbol='AAPL', quantity=100, market_value=15000.0, weight=0.15),
        PositionInfo(symbol='MSFT', quantity=50, market_value=18000.0, weight=0.18)
    ],
    returns_data={'AAPL': [0.01, -0.005], 'MSFT': [0.02, 0.01]},
    timestamp=datetime.now()
)

# Check overall health
print(f"Health: {status.overall_health}")  # "HEALTHY", "CAUTION", or "CRITICAL"
print(f"Score: {status.health_score:.0f}/100")

# Review alerts
if status.has_critical_issues():
    for alert in status.get_critical_alerts():
        print(f"CRITICAL: {alert.category.value}: {alert.message}")

# Check limits status
for limit_name, limit_info in status.limits_status.items():
    usage_pct = (limit_info['usage'] / limit_info['limit']) * 100
    print(f"{limit_name}: {usage_pct:.1f}% used")

# Get dashboard data
dashboard = monitor.get_dashboard_data()
```

**Health Score Calculation**:
- **90-100**: HEALTHY (all systems normal)
- **70-89**: CAUTION (monitor closely)
- **<70**: CRITICAL (immediate action required)

**Configuration**:
```python
RiskMonitor(
    risk_manager=risk_manager,
    drawdown_monitor=drawdown_monitor,           # Optional
    correlation_analyzer=correlation_analyzer,   # Optional
    critical_drawdown_threshold=0.15,            # 15% drawdown → critical
    warning_drawdown_threshold=0.10,             # 10% drawdown → warning
    critical_daily_loss_threshold=0.05,          # 5% daily loss → critical
    warning_daily_loss_threshold=0.03,           # 3% daily loss → warning
    critical_position_size_threshold=0.25,       # 25% position → critical
    warning_position_size_threshold=0.20,        # 20% position → warning
    critical_correlation_threshold=0.90,         # 0.90 correlation → critical
    warning_correlation_threshold=0.80,          # 0.80 correlation → warning
    alert_retention_hours=24                     # Keep alerts 24 hours
)
```

---

### 6. EmergencyController

**Purpose**: Circuit breaker protection system that halts trading during catastrophic scenarios with manual resume controls.

**Emergency Levels**:
- **NONE**: Normal operation
- **WARNING**: Minor concern (configurable threshold)
- **ALERT**: Elevated risk (requires monitoring)
- **CRITICAL**: Circuit breaker activated (trading halted)
- **SHUTDOWN**: Complete system shutdown

**Circuit Breakers** (auto-trigger trading halts):
1. **Drawdown Breaker**: Trips on portfolio drawdown threshold
2. **Daily Loss Breaker**: Trips on daily loss limit
3. **Position Loss Breaker**: Trips on single large position loss
4. **Volatility Breaker**: Trips on market volatility spike

**Usage**:
```python
from risk import EmergencyController, Position

# Check emergency conditions
status = emergency_controller.check_emergency_conditions(
    current_equity=92000.0,
    starting_equity=100000.0,
    daily_starting_equity=95000.0,
    peak_equity=108000.0,
    positions=[
        Position(symbol='AAPL', quantity=100, average_cost=150.0, current_price=145.0)
    ],
    timestamp=datetime.now()
)

# Check status
print(f"Trading allowed: {status.trading_allowed}")
print(f"New positions allowed: {status.new_positions_allowed}")
print(f"Position increases allowed: {status.position_increases_allowed}")
print(f"Emergency level: {status.level.value}")

# Triggered breakers
for breaker in status.active_breakers:
    print(f"Breaker: {breaker.breaker_type.value}")
    print(f"Reason: {breaker.reason}")
    print(f"Cooldown until: {breaker.cooldown_until}")

# Manual controls
if crisis_detected:
    emergency_controller.panic_button()  # Immediate halt

if system_failure:
    emergency_controller.activate_kill_switch("Database connection lost")

# Resume after review
if status.in_cooldown:
    print(f"Cooldown ends: {status.cooldown_until}")
else:
    success = emergency_controller.request_resume(
        approved_by="Risk Manager",
        reason="Conditions stabilized, reviewed and approved",
        timestamp=datetime.now()
    )
    print(f"Resume approved: {success}")
```

**Configuration**:
```python
EmergencyController(
    max_drawdown_pct=0.20,           # 20% max portfolio drawdown
    critical_drawdown_pct=0.15,      # 15% triggers critical alert
    max_daily_loss_pct=0.05,         # 5% max daily loss
    max_position_loss_pct=0.10,      # 10% max loss on single position
    volatility_threshold=2.5,        # 2.5x normal volatility
    cooldown_minutes=30,             # 30-minute cooldown after trip
    auto_resume_enabled=False,       # Manual approval required
    require_manual_review=True,      # Require explicit resume call
    max_daily_breaker_trips=3        # Max 3 trips per breaker per day
)
```

**Key Methods**:
- `check_emergency_conditions()`: Regular status check
- `panic_button()`: Immediate emergency halt
- `activate_kill_switch(reason)`: System-level shutdown
- `request_resume(approved_by, reason)`: Manual resume after review
- `reset_breaker(breaker_type)`: Reset specific breaker
- `get_active_breakers()`: List currently triggered breakers

---

## 🔧 Configuration Guide

### Conservative Profile (Low Risk)

**For**: Live trading, smaller accounts, lower risk tolerance

```python
# Risk Manager - Conservative
risk_manager = RiskManager(
    initial_capital=100000.0,
    max_positions=8,                # Max 8 concurrent positions
    max_position_pct=0.01,          # 1% max per position
    max_drawdown_pct=0.10,          # 10% max drawdown
    daily_loss_limit_pct=0.02,      # 2% daily loss limit
    max_leverage=1.0,               # No leverage
    concentration_limit=0.25        # 25% max in single position
)

# Position Sizer - Conservative (using Factory)
position_sizer = PositionSizerFactory.create(
    'risk_based',
    capital=100000.0,
    risk_per_trade=0.005,           # 0.5% risk per trade
    max_position_pct=0.01           # 1% max position size
)

# Drawdown Monitor - Conservative
drawdown_monitor = DrawdownMonitor(
    initial_equity=100000.0,
    max_drawdown_pct=0.10,          # 10% max drawdown
    daily_loss_limit_pct=0.02,      # 2% daily loss
    weekly_loss_limit_pct=0.05,     # 5% weekly loss
    scale_positions_on_drawdown=True,
    minor_drawdown_threshold=0.03,  # 3% minor
    moderate_drawdown_threshold=0.05, # 5% moderate
    severe_drawdown_threshold=0.08  # 8% severe
)

# Emergency Controller - Conservative
emergency_controller = EmergencyController(
    max_drawdown_pct=0.10,          # 10% max drawdown
    critical_drawdown_pct=0.08,     # 8% critical level
    max_daily_loss_pct=0.02,        # 2% max daily loss
    max_position_loss_pct=0.05,     # 5% max single position loss
    cooldown_minutes=60,            # 1-hour cooldown
    auto_resume_enabled=False       # Manual approval required
)
```

### Moderate Profile (Balanced)

**For**: Paper trading validation, medium accounts, moderate risk

```python
# Risk Manager - Moderate
risk_manager = RiskManager(
    initial_capital=100000.0,
    max_positions=10,               # Max 10 concurrent positions
    max_position_pct=0.02,          # 2% max per position
    max_drawdown_pct=0.20,          # 20% max drawdown
    daily_loss_limit_pct=0.03,      # 3% daily loss limit
    max_leverage=1.5,               # 1.5x leverage allowed
    concentration_limit=0.30        # 30% max in single position
)

# Position Sizer - Moderate (using Factory)
position_sizer = PositionSizerFactory.create(
    'volatility_adjusted',
    capital=100000.0,
    risk_per_trade=0.01,            # 1% risk per trade
    max_position_pct=0.02,          # 2% max position size
    target_volatility=0.15          # 15% target volatility
)

# Drawdown Monitor - Moderate
drawdown_monitor = DrawdownMonitor(
    initial_equity=100000.0,
    max_drawdown_pct=0.20,          # 20% max drawdown
    daily_loss_limit_pct=0.03,      # 3% daily loss
    weekly_loss_limit_pct=0.10,     # 10% weekly loss
    scale_positions_on_drawdown=True,
    minor_drawdown_threshold=0.05,  # 5% minor
    moderate_drawdown_threshold=0.10, # 10% moderate
    severe_drawdown_threshold=0.15  # 15% severe
)

# Emergency Controller - Moderate
emergency_controller = EmergencyController(
    max_drawdown_pct=0.20,          # 20% max drawdown
    critical_drawdown_pct=0.15,     # 15% critical level
    max_daily_loss_pct=0.03,        # 3% max daily loss
    max_position_loss_pct=0.10,     # 10% max single position loss
    cooldown_minutes=30,            # 30-min cooldown
    auto_resume_enabled=False       # Manual approval required
)
```

### Aggressive Profile (High Risk)

**For**: Testing only, larger accounts, higher risk tolerance

```python
# Risk Manager - Aggressive
risk_manager = RiskManager(
    initial_capital=100000.0,
    max_positions=15,               # Max 15 concurrent positions
    max_position_pct=0.03,          # 3% max per position
    max_drawdown_pct=0.30,          # 30% max drawdown
    daily_loss_limit_pct=0.05,      # 5% daily loss limit
    max_leverage=2.0,               # 2x leverage allowed
    concentration_limit=0.40        # 40% max in single position
)

# Position Sizer - Aggressive (using Factory)
position_sizer = PositionSizerFactory.create(
    'kelly',
    capital=100000.0,
    win_rate=0.55,                  # 55% win rate
    avg_win=0.02,                   # 2% avg win
    avg_loss=0.01,                  # 1% avg loss
    kelly_fraction=0.5,             # Use 1/2 Kelly
    max_position_pct=0.03           # 3% max position size
)

# Drawdown Monitor - Aggressive
drawdown_monitor = DrawdownMonitor(
    initial_equity=100000.0,
    max_drawdown_pct=0.30,          # 30% max drawdown
    daily_loss_limit_pct=0.05,      # 5% daily loss
    weekly_loss_limit_pct=0.15,     # 15% weekly loss
    scale_positions_on_drawdown=True,
    minor_drawdown_threshold=0.08,  # 8% minor
    moderate_drawdown_threshold=0.15, # 15% moderate
    severe_drawdown_threshold=0.22  # 22% severe
)

# Emergency Controller - Aggressive
emergency_controller = EmergencyController(
    max_drawdown_pct=0.30,          # 30% max drawdown
    critical_drawdown_pct=0.25,     # 25% critical level
    max_daily_loss_pct=0.05,        # 5% max daily loss
    max_position_loss_pct=0.15,     # 15% max single position loss
    cooldown_minutes=15,            # 15-min cooldown
    auto_resume_enabled=False       # Manual approval required
)
```

**⚠️ Warning**: Aggressive settings significantly increase risk. Only use for testing or if you fully understand the implications.

---

## 🔗 Integration Examples

### Example 1: Complete Trade Workflow

```python
from datetime import datetime
from risk import (
    RiskManager, PositionSizerFactory, DrawdownMonitor,
    CorrelationAnalyzer, RiskMonitor, EmergencyController,
    Position, PositionInfo
)

class TradingBot:
    def __init__(self):
        # Initialize all risk components with actual APIs
        self.risk_manager = RiskManager(
            initial_capital=100000.0,
            max_positions=10,
            max_position_pct=0.02,
            max_drawdown_pct=0.20,
            daily_loss_limit_pct=0.03,
            max_leverage=1.5,
            concentration_limit=0.30
        )
        
        # Use factory to create position sizer
        self.position_sizer = PositionSizerFactory.create(
            'volatility_adjusted',
            capital=100000.0,
            risk_per_trade=0.01,
            max_position_pct=0.02,
            target_volatility=0.15
        )
        
        self.drawdown_monitor = DrawdownMonitor(
            initial_equity=100000.0,
            max_drawdown_pct=0.20,
            daily_loss_limit_pct=0.03,
            weekly_loss_limit_pct=0.10,
            scale_positions_on_drawdown=True
        )
        
        self.correlation_analyzer = CorrelationAnalyzer(
            concentration_threshold=0.25,
            high_correlation_threshold=0.8,
            max_sector_concentration=0.50
        )
        
        self.risk_monitor = RiskMonitor(
            risk_manager=self.risk_manager,
            drawdown_monitor=self.drawdown_monitor,
            correlation_analyzer=self.correlation_analyzer
        )
        
        self.emergency_controller = EmergencyController(
            max_drawdown_pct=0.20,
            critical_drawdown_pct=0.15,
            max_daily_loss_pct=0.03,
            cooldown_minutes=30
        )
        
        self.account_equity = 100000.0
        self.daily_starting_equity = 100000.0
        self.starting_equity = 100000.0
        self.peak_equity = 100000.0
        self.positions_dict = {}  # symbol -> Position
    
    def evaluate_trade(self, symbol, price, stop_loss, volatility):
        """Complete trade evaluation with all risk checks."""
        
        timestamp = datetime.now()
        
        # 1. Check emergency conditions first
        positions_list = [Position(
            symbol=s,
            quantity=p.quantity,
            average_cost=p.average_cost,
            current_price=p.current_price
        ) for s, p in self.positions_dict.items()]
        
        emergency_status = self.emergency_controller.check_emergency_conditions(
            current_equity=self.account_equity,
            starting_equity=self.starting_equity,
            daily_starting_equity=self.daily_starting_equity,
            peak_equity=self.peak_equity,
            positions=positions_list,
            timestamp=timestamp
        )
        
        if not emergency_status.trading_allowed:
            return {
                'allowed': False,
                'reason': f'Emergency level: {emergency_status.level.value}',
                'emergency': True
            }
        
        # 2. Check drawdown status
        dd_metrics = self.drawdown_monitor.update(
            current_equity=self.account_equity,
            current_date=timestamp
        )
        
        if dd_metrics.is_trading_halted:
            return {
                'allowed': False,
                'reason': f'Trading halted: {dd_metrics.halt_reason}',
                'drawdown': True
            }
        
        # 3. Calculate position size (accounting for drawdown scaling)
        risk_amount = abs(price - stop_loss)
        base_size = self.position_sizer.calculate(
            price=price,
            risk_per_share=risk_amount,
            volatility=volatility,
            current_equity=self.account_equity
        )
        
        # Apply drawdown scaling
        position_size = int(base_size * dd_metrics.position_scale_factor)
        
        # 4. Validate with risk manager
        allowed, reason = self.risk_manager.check_trade_risk(
            symbol=symbol,
            side='BUY',
            quantity=position_size,
            price=price,
            positions=self.positions_dict
        )
        
        if not allowed:
            return {
                'allowed': False,
                'reason': reason,
                'risk_manager': True
            }
        
        # 5. Check overall risk health
        position_info_list = [
            PositionInfo(
                symbol=s,
                quantity=p.quantity,
                market_value=p.quantity * p.current_price,
                weight=(p.quantity * p.current_price) / self.account_equity
            ) for s, p in self.positions_dict.items()
        ]
        
        risk_status = self.risk_monitor.check_all_risks(
            current_equity=self.account_equity,
            positions=position_info_list,
            returns_data=None,  # Optional: pass historical returns
            timestamp=timestamp
        )
        
        # Alert on critical issues
        if risk_status.has_critical_issues():
            critical = risk_status.get_critical_alerts()
            print(f"⚠️  {len(critical)} critical alerts active:")
            for alert in critical:
                print(f"   - {alert.message}")
        
        # Trade approved
        return {
            'allowed': True,
            'position_size': position_size,
            'health_score': risk_status.health_score,
            'health_status': risk_status.overall_health,
            'active_alerts': len(risk_status.active_alerts),
            'position_scale_factor': dd_metrics.position_scale_factor
        }
    
    def execute_trade(self, symbol, price, stop_loss, volatility):
        """Execute trade with full risk management."""
        
        # Evaluate trade
        result = self.evaluate_trade(symbol, price, stop_loss, volatility)
        
        if not result['allowed']:
            print(f"❌ Trade rejected: {result['reason']}")
            return False
        
        # Execute trade (your broker API call here)
        position_size = result['position_size']
        print(f"✅ Executing trade: {symbol} x {position_size} @ ${price}")
        
        # Update positions
        self.positions[symbol] = {
            'shares': position_size,
            'entry_price': price,
            'stop_loss': stop_loss,
            'current_price': price
        }
        
        # Update risk tracking
        self.risk_manager.update(
            current_positions=self.positions,
            account_equity=self.account_equity,
            timestamp=datetime.now()
        )
        
        return True
```

### Example 2: Real-Time Monitoring Dashboard

```python
def display_risk_dashboard(risk_monitor, emergency_controller, account_equity):
    """Generate real-time risk dashboard."""
    
    dashboard = risk_monitor.get_dashboard_data()
    emergency_summary = emergency_controller.get_emergency_summary()
    
    print("\n" + "="*60)
    print("RISK MANAGEMENT DASHBOARD")
    print("="*60)
    
    # Overall Health
    print(f"\n📊 Overall Health: {dashboard['overall_health']}")
    print(f"   Score: {dashboard['health_score']}/100")
    
    # Account Status
    print(f"\n💰 Account Status:")
    print(f"   Equity: ${account_equity:,.2f}")
    print(f"   Drawdown: {dashboard['drawdown_metrics']['current_drawdown_pct']:.2%}")
    
    # Risk Metrics
    print(f"\n⚠️  Risk Metrics:")
    print(f"   Portfolio Heat: {dashboard['risk_metrics']['current_heat']:.2%} / "
          f"{dashboard['risk_metrics']['max_heat']:.2%}")
    print(f"   Daily Loss: {dashboard['risk_metrics']['daily_loss_pct']:.2%}")
    print(f"   Open Positions: {dashboard['risk_metrics']['position_count']}")
    
    # Alerts
    if dashboard['active_alerts']:
        print(f"\n🚨 Active Alerts ({len(dashboard['active_alerts'])}):")
        for alert in dashboard['active_alerts'][:5]:  # Show top 5
            print(f"   [{alert['level']}] {alert['message']}")
    
    # Emergency Status
    print(f"\n🚨 Emergency Status: {emergency_summary['current_level']}")
    if emergency_summary['active_breakers']:
        print(f"   Active Breakers: {', '.join(emergency_summary['active_breakers'])}")
    
    # Permissions
    perms = emergency_summary['permissions']
    print(f"\n🔒 Trading Permissions:")
    print(f"   Can Trade: {'✅' if perms['can_trade'] else '❌'}")
    print(f"   Can Open New: {'✅' if perms['can_open_new'] else '❌'}")
    print(f"   Can Increase: {'✅' if perms['can_increase_positions'] else '❌'}")
    
    print("\n" + "="*60 + "\n")
```

---

## 🧪 Testing

### Running Validation Tests

Each component has comprehensive validation tests:

```bash
# Test individual components
python test_risk_manager.py
python test_position_sizer.py
python test_drawdown_monitor.py
python test_correlation.py
python test_monitoring_simple.py
python test_emergency_controls.py

# Run integration tests
python test_risk_integration.py
```

### Integration Test Suite

See `test_risk_integration.py` for comprehensive end-to-end tests covering:
- Full trade workflow with all components
- Emergency scenario handling
- Drawdown protection activation
- Correlation-based trade rejection
- Recovery protocols
- Dashboard and monitoring

---

## 🐛 Troubleshooting

### Common Issues

**Issue**: "Trade rejected: Portfolio heat exceeded"
- **Cause**: Total risk across all positions exceeds `max_portfolio_heat`
- **Solution**: Close some positions or reduce position sizes
- **Check**: `risk_manager.get_remaining_capacity()`

**Issue**: "Cannot open new positions - drawdown protection active"
- **Cause**: Drawdown exceeds `protection_threshold`
- **Solution**: Wait for equity to recover above `recovery_threshold`
- **Check**: `drawdown_monitor.get_current_status()`

**Issue**: "High correlation with existing positions"
- **Cause**: New position would increase portfolio correlation above `max_correlation`
- **Solution**: Choose uncorrelated assets or close correlated positions
- **Check**: `correlation_analyzer.get_correlated_positions(symbol, threshold)`

**Issue**: "Emergency level: SHUTDOWN"
- **Cause**: Maximum drawdown exceeded or emergency stop activated
- **Solution**: Wait for cooldown period, then request manual resume
- **Check**: `emergency_controller.get_emergency_summary()`

**Issue**: Health score very low (<50)
- **Cause**: Multiple risk factors elevated (heat, drawdown, poor diversification)
- **Solution**: Review active alerts, reduce positions, improve diversification
- **Check**: `risk_monitor.get_dashboard_data()`

### Debug Mode

Enable detailed logging:

```python
import logging

logging.basicConfig(level=logging.DEBUG)

# Now all risk components will log detailed information
risk_manager = RiskManager(...)
```

### Performance Issues

If updates are slow:
- Reduce correlation `window` size (default 60)
- Increase `min_periods` for correlation (default 20)
- Reduce alert `cooldown_minutes` if getting too many alerts
- Use `get_remaining_capacity()` before validation to pre-filter trades

---

## 📈 Best Practices

### 1. Start Conservative

Begin with conservative settings and gradually increase risk as you validate system behavior:

```python
# Week 1: Very conservative
max_position_size = 0.005  # 0.5%
max_portfolio_heat = 0.02  # 2%

# Week 2: Still conservative
max_position_size = 0.01   # 1%
max_portfolio_heat = 0.04  # 4%

# Month 1: Moderate
max_position_size = 0.02   # 2%
max_portfolio_heat = 0.06  # 6%
```

### 2. Always Use Emergency Controls

Never trade without emergency controls:

```python
# ALWAYS check emergency status before trades
emergency_status = emergency_controller.check_emergency_conditions(...)
if not emergency_status.can_trade:
    return  # Don't trade during emergencies
```

### 3. Monitor Health Score

Track health score over time:

```python
# Aim for health score > 70
risk_status = risk_monitor.check_all_risks(...)

if risk_status.health_score < 50:
    # Take corrective action
    reduce_positions()
    
if risk_status.health_score < 30:
    # Emergency action
    close_all_positions()
```

### 4. Respect Drawdown Protection

Don't override drawdown protection:

```python
# WRONG - Don't do this
if not drawdown_monitor.can_open_position():
    # DON'T bypass protection
    pass  # ❌
    
# CORRECT
if not drawdown_monitor.can_open_position():
    return  # ✅ Respect the protection
```

### 5. Regular Correlation Updates

Update correlation regularly (at least daily):

```python
# Daily update
correlation_analyzer.update(
    positions=current_positions,
    returns=returns_series,  # Last 60+ days
    timestamp=datetime.now()
)
```

### 6. Test Before Live Trading

Always test in paper trading first:

```python
# Paper trading - more aggressive for testing
paper_risk_manager = RiskManager(
    max_portfolio_heat=0.08,
    max_position_size=0.03
)

# Live trading - conservative
live_risk_manager = RiskManager(
    max_portfolio_heat=0.04,
    max_position_size=0.01
)
```

### 7. Review Alerts Daily

Check active alerts at least once per day:

```python
# Daily review
risk_status = risk_monitor.check_all_risks(...)

for alert in risk_status.active_alerts:
    log_alert_to_file(alert)  # Keep records
    
    if alert.level == AlertLevel.CRITICAL:
        send_notification(alert)  # Get notified
```

### 8. Plan for Recovery

Have a recovery plan before emergencies happen:

```python
# Document your recovery process
recovery_plan = """
1. When emergency triggered:
   - Review positions immediately
   - Close losing positions first
   - Reduce portfolio heat below 50%

2. After cooldown period:
   - Review what triggered emergency
   - Verify market conditions stable
   - Request manual resume if approved

3. Post-emergency:
   - Start with reduced position sizes
   - Monitor health score closely
   - Gradually return to normal operation
"""
```

---

## 🔄 Maintenance

### Daily Tasks

- [ ] Review risk dashboard
- [ ] Check active alerts
- [ ] Verify health score > 70
- [ ] Review emergency status
- [ ] Update correlation metrics

### Weekly Tasks

- [ ] Analyze drawdown history
- [ ] Review circuit breaker trips
- [ ] Check position concentration
- [ ] Verify sector exposure
- [ ] Review rejected trades

### Monthly Tasks

- [ ] Analyze risk-adjusted returns
- [ ] Review and adjust risk limits
- [ ] Evaluate position sizing effectiveness
- [ ] Update correlation thresholds
- [ ] Backtest recent performance

---

## 📝 API Reference

### Complete API documentation available in individual module docstrings:

- `risk_manager.py` - RiskManager API
- `position_sizer.py` - PositionSizer API
- `drawdown_monitor.py` - DrawdownMonitor API
- `correlation.py` - CorrelationAnalyzer API
- `monitoring.py` - RiskMonitor API
- `emergency_controls.py` - EmergencyController API

Use Python's built-in help:

```python
from risk import RiskManager
help(RiskManager)
help(RiskManager.validate_trade)
```

---

## 🎓 Week 3 Implementation Timeline

- **Day 1**: Enhanced RiskManager - Core risk engine ✅
- **Day 2**: Position Sizing - Multiple sizing algorithms ✅
- **Day 3**: Drawdown Protection - Real-time drawdown monitoring ✅
- **Day 4**: Correlation Analysis - Portfolio diversification ✅
- **Day 5**: Real-Time Monitoring - Alert system and health scoring ✅
- **Day 6**: Emergency Controls - Circuit breakers and safety mechanisms ✅
- **Day 7**: Documentation & Integration - Complete system documentation ✅

---

## 📞 Support

For issues or questions:
1. Review this README
2. Check component docstrings
3. Review validation tests for usage examples
4. Check troubleshooting section

---

## ⚖️ License

This risk management system is part of the TWS Robot trading bot project.

---

## ⚠️ Disclaimer

**Risk Warning**: Trading involves substantial risk and is not suitable for every investor. This risk management system helps reduce risk but cannot eliminate it entirely. Past performance is not indicative of future results. Always start with paper trading and thoroughly test before risking real capital.

---

**Week 3 Complete** - Full risk management system ready for production use.
