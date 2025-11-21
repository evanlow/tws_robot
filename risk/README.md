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
from risk import (
    RiskManager, PositionSizer, DrawdownMonitor,
    CorrelationAnalyzer, RiskMonitor, EmergencyController
)

# Initialize core components
risk_manager = RiskManager(
    max_portfolio_heat=0.06,      # 6% max total risk
    max_position_size=0.02,       # 2% per position
    max_daily_loss=0.03,          # 3% daily loss limit
    max_sector_concentration=0.30  # 30% per sector
)

position_sizer = PositionSizer(
    default_method='volatility',
    max_leverage=2.0
)

drawdown_monitor = DrawdownMonitor(
    protection_threshold=0.10,     # Enter protection at 10% DD
    max_drawdown=0.20,            # Hard stop at 20% DD
    recovery_threshold=0.05        # Exit protection at 5% DD
)

correlation_analyzer = CorrelationAnalyzer(
    window=60,                     # 60-period rolling window
    max_correlation=0.70,          # Max 0.70 correlation
    max_concentration=0.40         # Max 40% in one position
)

risk_monitor = RiskMonitor(
    risk_manager=risk_manager,
    drawdown_monitor=drawdown_monitor,
    correlation_analyzer=correlation_analyzer
)

emergency_controller = EmergencyController(
    max_drawdown_pct=0.20,        # 20% max drawdown
    max_daily_loss_pct=0.05,      # 5% max daily loss
    cooldown_minutes=30,          # 30-min cooldown after emergency
    require_manual_review=True    # Require approval to resume
)
```

### Basic Usage

```python
# 1. Calculate position size
position_size = position_sizer.calculate_size(
    symbol='AAPL',
    price=150.0,
    stop_loss=145.0,
    account_equity=100000.0,
    method='volatility',
    volatility=0.02
)

# 2. Validate with risk manager
validation = risk_manager.validate_trade(
    symbol='AAPL',
    shares=position_size,
    price=150.0,
    side='BUY',
    current_positions=positions,
    account_equity=100000.0
)

if not validation['allowed']:
    print(f"Trade rejected: {validation['reason']}")
    return

# 3. Check emergency conditions
emergency_status = emergency_controller.check_emergency_conditions(
    current_equity=100000.0,
    starting_equity=100000.0,
    daily_starting_equity=100000.0,
    peak_equity=105000.0,
    positions=positions,
    timestamp=datetime.now()
)

if not emergency_status.can_trade:
    print(f"Trading blocked: {emergency_status.level}")
    return

# 4. Execute trade
# ... your trade execution code ...

# 5. Update risk tracking
risk_manager.update(
    current_positions=positions,
    account_equity=100000.0,
    timestamp=datetime.now()
)

drawdown_monitor.update(
    current_equity=100000.0,
    timestamp=datetime.now()
)

# 6. Monitor overall health
risk_status = risk_monitor.check_all_risks(
    equity=100000.0,
    positions=positions,
    returns=returns_series,
    timestamp=datetime.now()
)

print(f"Health Score: {risk_status.health_score}/100")
for alert in risk_status.active_alerts:
    print(f"[{alert.level}] {alert.message}")
```

---

## 📚 Component Documentation

### 1. RiskManager

**Purpose**: Core risk management engine that enforces position limits, portfolio heat, and daily loss limits.

**Key Methods**:
- `validate_trade()` - Validates if a trade meets risk limits
- `update()` - Updates current risk metrics
- `can_open_new_position()` - Checks if new positions are allowed
- `get_remaining_capacity()` - Returns available risk capacity
- `check_sector_limit()` - Validates sector concentration

**Configuration**:
```python
RiskManager(
    max_portfolio_heat=0.06,        # Max 6% total portfolio risk
    max_position_size=0.02,         # Max 2% per position
    max_daily_loss=0.03,            # Max 3% daily loss
    max_correlated_risk=0.08,       # Max 8% correlated positions
    max_sector_concentration=0.30,  # Max 30% per sector
    position_limit=10               # Max 10 positions
)
```

**See Also**: [API Reference](#api-reference) for complete method documentation.

---

### 2. PositionSizer

**Purpose**: Calculate optimal position sizes using various algorithms based on risk tolerance and market conditions.

**Sizing Methods**:

1. **Fixed Fractional** - Fixed percentage of capital
   ```python
   size = position_sizer.calculate_size(
       symbol='AAPL', price=150.0, stop_loss=145.0,
       account_equity=100000.0, method='fixed_fractional',
       risk_per_trade=0.01  # 1% risk
   )
   ```

2. **Kelly Criterion** - Optimal sizing based on win rate and profit factor
   ```python
   size = position_sizer.calculate_size(
       symbol='AAPL', price=150.0, stop_loss=145.0,
       account_equity=100000.0, method='kelly',
       win_rate=0.55, profit_factor=1.8
   )
   ```

3. **Volatility-Based** - Size based on asset volatility
   ```python
   size = position_sizer.calculate_size(
       symbol='AAPL', price=150.0, stop_loss=145.0,
       account_equity=100000.0, method='volatility',
       volatility=0.02, target_volatility=0.15
   )
   ```

4. **ATR-Based** - Size using Average True Range
   ```python
   size = position_sizer.calculate_size(
       symbol='AAPL', price=150.0, stop_loss=145.0,
       account_equity=100000.0, method='atr',
       atr=2.5, atr_multiplier=2.0
   )
   ```

5. **Risk Parity** - Equal risk contribution across positions
   ```python
   size = position_sizer.calculate_size(
       symbol='AAPL', price=150.0, stop_loss=145.0,
       account_equity=100000.0, method='risk_parity',
       volatility=0.02, num_positions=5
   )
   ```

**Configuration**:
```python
PositionSizer(
    default_method='volatility',
    max_leverage=2.0,
    kelly_fraction=0.25  # Use 25% of full Kelly
)
```

---

### 3. DrawdownMonitor

**Purpose**: Track drawdowns in real-time and activate protection mode when thresholds are breached.

**Key Features**:
- Real-time drawdown calculation from peak equity
- Automatic protection mode activation
- Recovery protocols with hysteresis
- Historical drawdown tracking

**Protection Modes**:
- **NORMAL**: No drawdown restrictions
- **PROTECTION**: Reduce position sizing, close losing positions
- **MAXIMUM**: Hard stop - close all positions

**Usage**:
```python
# Update with current equity
status = drawdown_monitor.update(
    current_equity=95000.0,
    timestamp=datetime.now()
)

if status.protection_mode:
    print(f"Protection active: {status.current_drawdown_pct:.1%} drawdown")
    # Reduce position sizes or close positions

# Check if can open new positions
if not drawdown_monitor.can_open_position():
    print("Cannot open new positions - drawdown protection active")
```

**Configuration**:
```python
DrawdownMonitor(
    protection_threshold=0.10,   # Enter protection at 10% DD
    max_drawdown=0.20,          # Hard stop at 20% DD
    recovery_threshold=0.05,     # Exit protection at 5% DD
    lookback_days=90            # Track last 90 days
)
```

---

### 4. CorrelationAnalyzer

**Purpose**: Monitor portfolio diversification by tracking correlations, concentration, and sector exposure.

**Key Features**:
- Rolling correlation calculation across all positions
- Position concentration analysis
- Sector exposure tracking
- Diversification scoring
- Highly correlated position detection

**Usage**:
```python
# Update with current positions and returns
metrics = correlation_analyzer.update(
    positions=current_positions,
    returns=returns_series,
    timestamp=datetime.now()
)

# Check correlation before adding new position
correlated = correlation_analyzer.get_correlated_positions(
    symbol='AAPL',
    threshold=0.70
)

if correlated:
    print(f"Warning: High correlation with {correlated}")

# Check concentration
concentration = correlation_analyzer.get_concentration_metrics(
    positions=current_positions,
    account_equity=100000.0
)

print(f"Top 3 concentration: {concentration['top_3_concentration']:.1%}")
```

**Configuration**:
```python
CorrelationAnalyzer(
    window=60,                    # 60-period rolling window
    min_periods=20,               # Min 20 periods for calculation
    max_correlation=0.70,         # Flag correlations > 0.70
    max_concentration=0.40,       # Max 40% in single position
    max_sector_concentration=0.50 # Max 50% in single sector
)
```

---

### 5. RiskMonitor

**Purpose**: Integration hub that monitors all risk components in real-time and generates alerts.

**Alert Levels**:
- **INFO**: Informational notices
- **WARNING**: Attention required
- **CRITICAL**: Immediate action needed

**Alert Categories**:
- Position Size, Portfolio Risk, Drawdown, Correlation, Concentration, Sector Risk, Daily Loss

**Usage**:
```python
# Comprehensive risk check
risk_status = risk_monitor.check_all_risks(
    equity=100000.0,
    positions=current_positions,
    returns=returns_series,
    timestamp=datetime.now()
)

# Check overall health (0-100 score)
print(f"Health Score: {risk_status.health_score}/100")
print(f"Status: {risk_status.overall_health}")

# Review active alerts
for alert in risk_status.active_alerts:
    if alert.level == AlertLevel.CRITICAL:
        print(f"🚨 CRITICAL: {alert.message}")
    elif alert.level == AlertLevel.WARNING:
        print(f"⚠️  WARNING: {alert.message}")

# Get dashboard data for visualization
dashboard = risk_monitor.get_dashboard_data()
```

**Health Score Calculation**:
```
Score = 100
  - (portfolio_heat / max_heat * 20)
  - (daily_loss_pct * 400)
  - (drawdown_pct * 100)
  - (poor_diversification / 5)
  - (critical_alerts * 5)
```

**Configuration**:
```python
RiskMonitor(
    risk_manager=risk_manager,
    drawdown_monitor=drawdown_monitor,
    correlation_analyzer=correlation_analyzer,
    alert_cooldown_minutes=15  # Prevent alert spam
)
```

---

### 6. EmergencyController

**Purpose**: Provide circuit breaker protection and emergency controls for catastrophic scenarios.

**Emergency Levels**:
1. **NONE** - Normal operation
2. **WARNING** - Minor concern (10-12% drawdown)
3. **ALERT** - Elevated risk (12-15% drawdown)
4. **CRITICAL** - Circuit breaker triggered (15-20% drawdown)
5. **SHUTDOWN** - Maximum drawdown exceeded (>20% drawdown)

**Circuit Breakers**:

1. **Drawdown Breaker** - Trips on excessive drawdown
2. **Daily Loss Breaker** - Trips on daily loss limit
3. **Position Loss Breaker** - Trips on single position loss
4. **Volatility Breaker** - Trips on market volatility spike

**Key Features**:
- Automatic circuit breaker activation
- Kill switch for immediate shutdown
- Panic button for emergencies
- Cooldown periods (default 30 minutes)
- Manual approval required for resume
- Daily trip limits per breaker

**Usage**:
```python
# Regular emergency check
emergency_status = emergency_controller.check_emergency_conditions(
    current_equity=95000.0,
    starting_equity=100000.0,
    daily_starting_equity=98000.0,
    peak_equity=105000.0,
    positions=current_positions,
    timestamp=datetime.now()
)

if emergency_status.level >= EmergencyLevel.CRITICAL:
    print(f"🚨 EMERGENCY: {emergency_status.level}")
    # Close all positions, cancel orders

# Manual emergency stop
if market_crash_detected():
    emergency_controller.panic_button()

# Kill switch activation
if system_error():
    emergency_controller.activate_kill_switch("System error detected")

# Resume after cooldown
if emergency_status.in_cooldown:
    print(f"Cooldown ends: {emergency_status.cooldown_ends_at}")
else:
    success = emergency_controller.request_resume(
        approved_by="Risk Manager",
        reason="Market stabilized, ready to resume",
        timestamp=datetime.now()
    )
```

**Configuration**:
```python
EmergencyController(
    max_drawdown_pct=0.20,           # 20% max drawdown
    critical_drawdown_pct=0.15,      # 15% critical level
    max_daily_loss_pct=0.05,         # 5% max daily loss
    max_position_loss_pct=0.10,      # 10% max single position loss
    cooldown_minutes=30,             # 30-min cooldown
    auto_resume_enabled=False,       # Require manual approval
    require_manual_review=True       # Require review before resume
)
```

---

## 🔧 Configuration Guide

### Conservative Profile (Low Risk)

**For**: Live trading, smaller accounts, lower risk tolerance

```python
# Risk Manager - Conservative
risk_manager = RiskManager(
    max_portfolio_heat=0.04,        # 4% total risk
    max_position_size=0.01,         # 1% per position
    max_daily_loss=0.02,            # 2% daily loss limit
    max_sector_concentration=0.25,  # 25% per sector
    position_limit=8
)

# Position Sizer - Conservative
position_sizer = PositionSizer(
    default_method='fixed_fractional',
    max_leverage=1.0,               # No leverage
    kelly_fraction=0.125            # 1/8 Kelly
)

# Drawdown Monitor - Conservative
drawdown_monitor = DrawdownMonitor(
    protection_threshold=0.05,      # Enter protection at 5% DD
    max_drawdown=0.10,             # Hard stop at 10% DD
    recovery_threshold=0.03        # Exit protection at 3% DD
)

# Emergency Controller - Conservative
emergency_controller = EmergencyController(
    max_drawdown_pct=0.10,         # 10% max drawdown
    critical_drawdown_pct=0.08,    # 8% critical level
    max_daily_loss_pct=0.03,       # 3% max daily loss
    cooldown_minutes=60            # 1-hour cooldown
)
```

### Moderate Profile (Balanced)

**For**: Paper trading validation, medium accounts, moderate risk

```python
# Risk Manager - Moderate
risk_manager = RiskManager(
    max_portfolio_heat=0.06,        # 6% total risk
    max_position_size=0.02,         # 2% per position
    max_daily_loss=0.03,            # 3% daily loss limit
    max_sector_concentration=0.30,  # 30% per sector
    position_limit=10
)

# Position Sizer - Moderate
position_sizer = PositionSizer(
    default_method='volatility',
    max_leverage=1.5,
    kelly_fraction=0.25            # 1/4 Kelly
)

# Drawdown Monitor - Moderate
drawdown_monitor = DrawdownMonitor(
    protection_threshold=0.10,      # Enter protection at 10% DD
    max_drawdown=0.20,             # Hard stop at 20% DD
    recovery_threshold=0.05        # Exit protection at 5% DD
)

# Emergency Controller - Moderate
emergency_controller = EmergencyController(
    max_drawdown_pct=0.20,         # 20% max drawdown
    critical_drawdown_pct=0.15,    # 15% critical level
    max_daily_loss_pct=0.05,       # 5% max daily loss
    cooldown_minutes=30            # 30-min cooldown
)
```

### Aggressive Profile (High Risk)

**For**: Testing only, larger accounts, higher risk tolerance

```python
# Risk Manager - Aggressive
risk_manager = RiskManager(
    max_portfolio_heat=0.10,        # 10% total risk
    max_position_size=0.03,         # 3% per position
    max_daily_loss=0.05,            # 5% daily loss limit
    max_sector_concentration=0.40,  # 40% per sector
    position_limit=15
)

# Position Sizer - Aggressive
position_sizer = PositionSizer(
    default_method='kelly',
    max_leverage=2.0,
    kelly_fraction=0.5             # 1/2 Kelly
)

# Drawdown Monitor - Aggressive
drawdown_monitor = DrawdownMonitor(
    protection_threshold=0.15,      # Enter protection at 15% DD
    max_drawdown=0.30,             # Hard stop at 30% DD
    recovery_threshold=0.08        # Exit protection at 8% DD
)

# Emergency Controller - Aggressive
emergency_controller = EmergencyController(
    max_drawdown_pct=0.30,         # 30% max drawdown
    critical_drawdown_pct=0.25,    # 25% critical level
    max_daily_loss_pct=0.08,       # 8% max daily loss
    cooldown_minutes=15            # 15-min cooldown
)
```

**⚠️ Warning**: Aggressive settings significantly increase risk. Only use for testing or if you fully understand the implications.

---

## 🔗 Integration Examples

### Example 1: Complete Trade Workflow

```python
from datetime import datetime
from risk import (
    RiskManager, PositionSizer, DrawdownMonitor,
    CorrelationAnalyzer, RiskMonitor, EmergencyController
)

class TradingBot:
    def __init__(self):
        # Initialize all risk components
        self.risk_manager = RiskManager(
            max_portfolio_heat=0.06,
            max_position_size=0.02,
            max_daily_loss=0.03
        )
        
        self.position_sizer = PositionSizer(
            default_method='volatility',
            max_leverage=1.5
        )
        
        self.drawdown_monitor = DrawdownMonitor(
            protection_threshold=0.10,
            max_drawdown=0.20
        )
        
        self.correlation_analyzer = CorrelationAnalyzer(
            window=60,
            max_correlation=0.70
        )
        
        self.risk_monitor = RiskMonitor(
            risk_manager=self.risk_manager,
            drawdown_monitor=self.drawdown_monitor,
            correlation_analyzer=self.correlation_analyzer
        )
        
        self.emergency_controller = EmergencyController(
            max_drawdown_pct=0.20,
            max_daily_loss_pct=0.05
        )
        
        self.account_equity = 100000.0
        self.daily_starting_equity = 100000.0
        self.positions = {}
    
    def evaluate_trade(self, symbol, price, stop_loss, volatility):
        """Complete trade evaluation with all risk checks."""
        
        timestamp = datetime.now()
        
        # 1. Check emergency conditions first
        emergency_status = self.emergency_controller.check_emergency_conditions(
            current_equity=self.account_equity,
            starting_equity=100000.0,
            daily_starting_equity=self.daily_starting_equity,
            peak_equity=max(self.account_equity, 100000.0),
            positions=self.positions,
            timestamp=timestamp
        )
        
        if not emergency_status.can_trade:
            return {
                'allowed': False,
                'reason': f'Emergency level: {emergency_status.level}',
                'emergency': True
            }
        
        # 2. Check drawdown status
        dd_status = self.drawdown_monitor.update(
            current_equity=self.account_equity,
            timestamp=timestamp
        )
        
        if dd_status.protection_mode and not self.drawdown_monitor.can_open_position():
            return {
                'allowed': False,
                'reason': f'Drawdown protection active: {dd_status.current_drawdown_pct:.1%}',
                'drawdown': True
            }
        
        # 3. Check correlation
        correlated = self.correlation_analyzer.get_correlated_positions(
            symbol=symbol,
            threshold=0.70
        )
        
        if correlated:
            return {
                'allowed': False,
                'reason': f'High correlation with existing positions: {correlated}',
                'correlation': True
            }
        
        # 4. Calculate position size
        position_size = self.position_sizer.calculate_size(
            symbol=symbol,
            price=price,
            stop_loss=stop_loss,
            account_equity=self.account_equity,
            method='volatility',
            volatility=volatility
        )
        
        # 5. Validate with risk manager
        validation = self.risk_manager.validate_trade(
            symbol=symbol,
            shares=position_size,
            price=price,
            side='BUY',
            current_positions=self.positions,
            account_equity=self.account_equity
        )
        
        if not validation['allowed']:
            return validation
        
        # 6. Check overall risk health
        risk_status = self.risk_monitor.check_all_risks(
            equity=self.account_equity,
            positions=self.positions,
            returns=None,  # Would pass returns series here
            timestamp=timestamp
        )
        
        # Alert on critical issues
        critical_alerts = [a for a in risk_status.active_alerts 
                          if a.level == 'CRITICAL']
        
        if critical_alerts:
            print(f"⚠️  {len(critical_alerts)} critical alerts active")
            for alert in critical_alerts:
                print(f"   - {alert.message}")
        
        # Trade approved
        return {
            'allowed': True,
            'position_size': position_size,
            'health_score': risk_status.health_score,
            'active_alerts': len(risk_status.active_alerts)
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
