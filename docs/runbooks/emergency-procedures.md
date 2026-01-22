# Runbook: Emergency Procedures

## Overview

Critical procedures for handling emergency situations in the TWS Robot trading system.

**⚠️ READ THIS BEFORE TRADING LIVE**

## Emergency Contact Card

```
System: TWS Robot Trading Platform
Environment: [PAPER / LIVE]
Account: [IB Account Number]
Phone Support: IB 877-442-2757
Emergency Stop: [See Section 1]
```

## Priority Levels

| Level | Description | Response Time |
|-------|-------------|---------------|
| P0 | System threatening financial loss | IMMEDIATE |
| P1 | Trading impaired but protected | 5 minutes |
| P2 | Degraded performance | 30 minutes |
| P3 | Minor issue, no impact | Next day |

---

## P0: CRITICAL - Immediate Action Required

### 1. Emergency Shutdown (KILL SWITCH)

**When to Use:**
- Runaway trading detected
- Risk controls failing
- System behaving unexpectedly
- Catastrophic bug discovered

**Procedure:**

```python
# OPTION 1: Emergency shutdown script (FASTEST)
# Keep this script readily accessible

from strategies.strategy_registry import StrategyRegistry
from execution.order_manager import OrderManager

def emergency_shutdown():
    """
    EMERGENCY KILL SWITCH
    Stops all strategies and cancels all orders
    """
    print("🚨 EMERGENCY SHUTDOWN INITIATED 🚨")
    
    # 1. Stop all strategies
    registry = StrategyRegistry.get_instance()
    registry.stop_all()
    print("✓ All strategies stopped")
    
    # 2. Cancel all pending orders
    order_manager = OrderManager.get_instance()
    cancelled = order_manager.cancel_all_orders()
    print(f"✓ {len(cancelled)} orders cancelled")
    
    # 3. Disable trading
    risk_monitor = RiskMonitor.get_instance()
    risk_monitor.disable_trading("EMERGENCY_SHUTDOWN")
    print("✓ Trading disabled")
    
    # 4. Close event bus
    event_bus = EventBus.get_instance()
    event_bus.shutdown()
    print("✓ Event bus shut down")
    
    print("🚨 EMERGENCY SHUTDOWN COMPLETE 🚨")
    print("Review positions manually in TWS")

if __name__ == '__main__':
    emergency_shutdown()
```

**Save as:** `emergency_shutdown.py` in root directory

**Run:**
```bash
python emergency_shutdown.py
```

**OPTION 2: Manual TWS Shutdown**

1. Open TWS/IB Gateway
2. Go to **Account** → **Account Window**
3. Right-click strategy → **Cancel All Orders**
4. Manually close positions if needed
5. Exit TWS

**OPTION 3: Phone IB**

If system unresponsive:
- Call: 877-442-2757
- Say: "Emergency - Cancel all orders and close positions"
- Provide: Account number, authentication

### 2. Runaway Trading Detected

**Symptoms:**
- Excessive order submission (>10 per minute)
- Multiple positions in same symbol
- Position sizes exceeding limits
- Rapid repeated buy/sell cycles

**Immediate Actions:**

```python
# 1. STOP - Run emergency shutdown
python emergency_shutdown.py

# 2. CHECK - Review recent activity
from monitoring.metrics_tracker import MetricsTracker

tracker = MetricsTracker()
recent_trades = tracker.get_trades(last_n_minutes=5)
recent_orders = tracker.get_orders(last_n_minutes=5)

print(f"Trades (5 min): {len(recent_trades)}")
print(f"Orders (5 min): {len(recent_orders)}")

for trade in recent_trades:
    print(f"  {trade['timestamp']}: {trade['action']} {trade['quantity']} {trade['symbol']} @ ${trade['price']}")

# 3. ASSESS - Calculate damage
total_loss = sum(t['pnl'] for t in recent_trades)
print(f"Total P&L from incident: ${total_loss:,.2f}")

# 4. DOCUMENT - Save evidence
import json
from datetime import datetime

incident_report = {
    'timestamp': datetime.now().isoformat(),
    'type': 'runaway_trading',
    'trades': recent_trades,
    'orders': recent_orders,
    'total_pnl': total_loss
}

with open(f'incident_{datetime.now().strftime("%Y%m%d_%H%M%S")}.json', 'w') as f:
    json.dump(incident_report, f, indent=2)
```

**Root Cause Analysis:**
- Check strategy logic for infinite loops
- Review signal generation conditions
- Verify risk controls were called
- Check for race conditions

### 3. Risk Controls Failing

**Symptoms:**
- Position sizes exceed max_position_pct
- Daily loss exceeds max_daily_loss_pct
- Trading continues after circuit breaker should trigger

**Immediate Actions:**

```python
# 1. STOP IMMEDIATELY
python emergency_shutdown.py

# 2. VERIFY CURRENT STATE
from risk.risk_monitor import RiskMonitor

risk = RiskMonitor.get_instance()
state = risk.get_risk_state()

print("RISK STATE:")
print(f"  Account value: ${state['account_value']:,.2f}")
print(f"  Daily P&L: ${state['daily_pnl']:,.2f}")
print(f"  Daily loss %: {state['daily_pnl'] / state['account_value'] * 100:.2f}%")
print(f"  Max position: {state['max_position_size']}")
print(f"  Trading enabled: {state['trading_enabled']}")

# Check if limits breached
if abs(state['daily_pnl']) > state['account_value'] * 0.02:  # 2% daily limit
    print("⚠️ DAILY LOSS LIMIT BREACHED")

# 3. CHECK POSITIONS
from execution.order_manager import OrderManager

om = OrderManager.get_instance()
positions = om.get_all_positions()

print(f"\nCURRENT POSITIONS ({len(positions)}):")
for symbol, pos in positions.items():
    value = pos['quantity'] * pos['current_price']
    pct = value / state['account_value'] * 100
    print(f"  {symbol}: {pos['quantity']} shares, ${value:,.2f} ({pct:.1f}%)")
    
    if pct > 5.0:  # 5% position limit
        print(f"    ⚠️ EXCEEDS POSITION LIMIT")
```

**Fix Procedure:**

```python
# 1. Find the bug
# Check why risk controls didn't fire
# Common issues:
# - Risk monitor not subscribed to order events
# - Position size calculation bug
# - Stale account value

# 2. Add fail-safe checks
def order_with_failsafe(order):
    """Add manual risk check before every order"""
    # Check position size
    account_value = get_account_value()
    order_value = order['quantity'] * order['price']
    
    if order_value > account_value * 0.05:  # 5% limit
        raise ValueError(f"Order value ${order_value} exceeds 5% limit")
    
    # Check daily loss
    daily_pnl = get_daily_pnl()
    if abs(daily_pnl) > account_value * 0.02:  # 2% limit
        raise ValueError(f"Daily loss ${daily_pnl} exceeds 2% limit")
    
    # Submit order
    submit_order(order)

# 3. Test fix
# Run unit tests
pytest tests/test_risk_manager.py -v
pytest tests/test_emergency_controls.py -v

# 4. Verify in paper trading
# Don't go live until verified for 7+ days
```

### 4. Database Corruption

**Symptoms:**
- Strategy state not persisting
- Position data incorrect
- Historical data missing

**Immediate Actions:**

```python
# 1. STOP TRADING
python emergency_shutdown.py

# 2. BACKUP DATABASE
import shutil
from datetime import datetime

db_path = 'data/trading.db'
backup_path = f'data/trading_backup_{datetime.now().strftime("%Y%m%d_%H%M%S")}.db'

shutil.copy2(db_path, backup_path)
print(f"Database backed up to: {backup_path}")

# 3. CHECK INTEGRITY
import sqlite3

conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# Run integrity check
result = cursor.execute("PRAGMA integrity_check").fetchone()
print(f"Integrity check: {result[0]}")

if result[0] != 'ok':
    print("⚠️ DATABASE CORRUPTED")
    # Restore from backup
    shutil.copy2(backup_path, db_path)
    print("Restored from backup")

# 4. VERIFY CRITICAL TABLES
tables = ['strategies', 'positions', 'orders', 'trades']
for table in tables:
    count = cursor.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    print(f"{table}: {count} rows")

conn.close()
```

---

## P1: HIGH PRIORITY - Action Within 5 Minutes

### 5. TWS Connection Lost

**Symptoms:**
- No market data updates
- Orders not submitting
- Connection error messages

**Actions:**

```python
# 1. Check connection status
from core.connection import ConnectionManager

conn = ConnectionManager.get_instance()
print(f"Connected: {conn.is_connected()}")
print(f"Last heartbeat: {conn.last_heartbeat}")

# 2. Attempt reconnection
if not conn.is_connected():
    print("Attempting reconnection...")
    conn.reconnect()
    
    # Wait for connection
    import time
    for i in range(10):
        if conn.is_connected():
            print("✓ Reconnected")
            break
        time.sleep(1)
    else:
        print("❌ Reconnection failed")

# 3. If can't reconnect, check TWS
# - Is TWS running?
# - Is IB Gateway running?
# - Check TWS settings → API → Enable ActiveX and Socket Clients
# - Check port (7497 paper, 7496 live)
```

**Restart TWS:**

1. Close TWS/IB Gateway
2. Wait 30 seconds
3. Restart TWS/IB Gateway
4. Wait for login
5. Reconnect robot:
   ```python
   from core.connection import ConnectionManager
   conn = ConnectionManager.get_instance()
   conn.connect(host='127.0.0.1', port=7497)  # 7497 for paper
   ```

### 6. Incorrect Position Reported

**Symptoms:**
- System thinks position exists but TWS shows none
- Quantity mismatch between system and TWS
- Phantom positions

**Actions:**

```python
# 1. GET SYSTEM STATE
from execution.order_manager import OrderManager

om = OrderManager.get_instance()
system_positions = om.get_all_positions()

print("System positions:")
for symbol, pos in system_positions.items():
    print(f"  {symbol}: {pos['quantity']} @ ${pos['avg_price']}")

# 2. GET TWS STATE
# Manually check TWS Account window
# Compare with system state

# 3. RECONCILE
# If mismatch, trust TWS as source of truth
from execution.position_reconciler import PositionReconciler

reconciler = PositionReconciler()
reconciler.sync_with_tws()

# 4. VERIFY
system_positions_after = om.get_all_positions()
print("\nAfter reconciliation:")
for symbol, pos in system_positions_after.items():
    print(f"  {symbol}: {pos['quantity']} @ ${pos['avg_price']}")
```

### 7. Strategy Stuck in ERROR State

**Symptoms:**
- Strategy won't start
- Error state persists after restart
- Can't recover

**Actions:**

```python
# 1. CHECK ERROR DETAILS
from strategies.strategy_registry import StrategyRegistry

registry = StrategyRegistry.get_instance()
strategy = registry.get_strategy("StrategyName")

print(f"State: {strategy.state}")
metrics = strategy.get_metrics()
print(f"Errors: {metrics.get('errors', [])}")
print(f"Error count: {metrics.get('error_count', 0)}")

# 2. REVIEW LOGS
import re

with open('logs/strategy.log', 'r') as f:
    logs = f.readlines()

# Find errors for this strategy
strategy_errors = [line for line in logs if 'ERROR' in line and strategy.config.name in line]
for error in strategy_errors[-10:]:  # Last 10 errors
    print(error.strip())

# 3. FIX UNDERLYING ISSUE
# Based on error messages, fix the root cause

# 4. RESET STATE (after fixing)
strategy.state = StrategyState.STOPPED
strategy._error_count = 0

# 5. RESTART
strategy.start()
print(f"New state: {strategy.state}")
```

---

## P2: MEDIUM PRIORITY - Action Within 30 Minutes

### 8. Degraded Performance

**Symptoms:**
- Slow order execution
- Delayed market data
- High CPU/memory usage

**Actions:**

```python
# 1. CHECK SYSTEM RESOURCES
import psutil

print(f"CPU: {psutil.cpu_percent()}%")
print(f"Memory: {psutil.virtual_memory().percent}%")
print(f"Disk: {psutil.disk_usage('/').percent}%")

# 2. CHECK PROCESS
import os
process = psutil.Process(os.getpid())
print(f"\nProcess:")
print(f"  Memory: {process.memory_info().rss / 1024 / 1024:.1f} MB")
print(f"  Threads: {process.num_threads()}")
print(f"  CPU: {process.cpu_percent()}%")

# 3. PROFILE PERFORMANCE
# See debugging-strategies.md for profiling details

# 4. OPTIMIZE
# - Reduce indicator calculations
# - Limit history size
# - Check for memory leaks
```

### 9. Missing Data

**Symptoms:**
- Gaps in price history
- No data for certain symbols
- Historical data incomplete

**Actions:**

```python
# 1. CHECK DATA AVAILABILITY
from backtest.data_manager import DataManager

dm = DataManager()
for symbol in ['AAPL', 'MSFT', 'GOOGL']:
    data = dm.load_data(
        symbols=[symbol],
        start_date='2025-01-01',
        end_date='2025-01-15'
    )
    
    if symbol in data:
        bars = len(data[symbol])
        print(f"{symbol}: {bars} bars")
        
        if bars == 0:
            print(f"  ⚠️ NO DATA")
    else:
        print(f"{symbol}: NOT FOUND")

# 2. DOWNLOAD MISSING DATA
# Use download_real_data.py script
python download_real_data.py --symbol AAPL --start 2025-01-01 --end 2025-01-15

# 3. VERIFY DOWNLOAD
data = dm.load_data(symbols=['AAPL'], start_date='2025-01-01', end_date='2025-01-15')
print(f"Downloaded: {len(data['AAPL'])} bars")
```

---

## Post-Incident Procedures

### 1. Document Incident

**Template:**

```markdown
# Incident Report

**Date:** 2025-01-15  
**Time:** 14:30 EST  
**Severity:** P0  
**Status:** Resolved  

## Summary
Brief description of what happened.

## Timeline
- 14:30 - Issue detected
- 14:31 - Emergency shutdown executed
- 14:35 - Root cause identified
- 14:45 - Fix implemented
- 15:00 - Testing complete
- 15:15 - System restored

## Impact
- Financial: $X loss
- Trades affected: N trades
- Downtime: X minutes

## Root Cause
Detailed explanation of what caused the issue.

## Resolution
How the issue was fixed.

## Prevention
Steps taken to prevent recurrence:
1. Added validation check X
2. Improved monitoring for Y
3. Updated documentation

## Action Items
- [ ] Add unit test for this scenario
- [ ] Update emergency procedures
- [ ] Review similar code
```

### 2. Run Diagnostics

```bash
# Full system check
pytest -v                          # All tests must pass
pytest --cov                       # Check coverage
python -m pylint strategies/       # Code quality
python -m mypy strategies/         # Type checking
```

### 3. Paper Trading Validation

After any P0/P1 incident:

```python
# Mandatory paper trading before returning to live
strategy.transition_to_paper()

# Run for minimum 7 days
# Verify:
# - No recurrence of issue
# - All risk controls working
# - Performance acceptable

# Only then return to live
if validated_for_7_days:
    strategy.transition_to_live()
```

### 4. Update Documentation

- Add incident to ADR if design change needed
- Update runbooks with new procedures
- Document lessons learned

## Testing Emergency Procedures

**Practice emergency shutdown monthly:**

```python
# In paper trading environment
def test_emergency_shutdown():
    # 1. Start strategies
    registry.start_all()
    
    # 2. Generate some activity
    # ... submit orders, open positions
    
    # 3. Execute emergency shutdown
    emergency_shutdown()
    
    # 4. Verify
    assert all(s.state == StrategyState.STOPPED for s in registry.get_all())
    assert len(order_manager.get_open_orders()) == 0
    assert not risk_monitor.is_trading_enabled()
    
    print("✓ Emergency shutdown test passed")

# Run monthly
test_emergency_shutdown()
```

## Emergency Contacts

| Role | Name | Phone | Email |
|------|------|-------|-------|
| Primary | [Your Name] | [Phone] | [Email] |
| IB Support | - | 877-442-2757 | - |
| Technical | [Backup] | [Phone] | [Email] |

## Quick Reference

**Stop Everything:**
```bash
python emergency_shutdown.py
```

**Check System Status:**
```python
from monitoring.health_check import HealthChecker
HealthChecker().run_all_checks()
```

**Review Recent Activity:**
```python
from monitoring.metrics_tracker import MetricsTracker
MetricsTracker().print_summary(last_hours=1)
```

**Manual TWS Actions:**
1. Open TWS Account window
2. Cancel all orders: Right-click → Cancel All
3. Close positions: Right-click position → Close Position

---

**Remember:** When in doubt, STOP FIRST, investigate second.

## Further Reading

- [Debugging Strategies](debugging-strategies.md)
- [Risk Controls](../architecture/risk-controls.md)
- [Monitoring Guide](../architecture/monitoring.md)
