# Live Trading Safety - CRITICAL GUIDE

**⚠️ READ THIS BEFORE TRADING WITH REAL MONEY ⚠️**

## Table of Contents
1. [Paper Trading is Your Simulation Mode](#paper-trading-is-your-simulation-mode)
2. [Multi-Layer Safety Architecture](#multi-layer-safety-architecture)
3. [Pre-Flight Checklist](#pre-flight-checklist)
4. [Risk Controls](#risk-controls)
5. [Emergency Procedures](#emergency-procedures)
6. [Order Execution Flow](#order-execution-flow)
7. [Common Mistakes to Avoid](#common-mistakes-to-avoid)

---

## Paper Trading is Your Simulation Mode

**IBKR's paper trading IS the "simulation mode":**
- Paper trading uses real-time market data
- Paper trading uses fake money (no financial risk)
- Paper trading behaves like live trading (realistic fills, latency)

**You CANNOT run both modes simultaneously:**
- TWS runs either Paper (port 7497) OR Live (port 7496)
- You must restart TWS to switch modes
- Your strategy code works identically in both modes

**Testing workflow:**
```
1. Test in Paper Trading (days/weeks) → Verify strategy works
2. Test in Live Trading (small positions) → Verify execution works
3. Scale up gradually → Monitor closely
```

---

## Multi-Layer Safety Architecture

Every order must pass **6 mandatory checks** before reaching TWS:

### Layer 1: Emergency Stop
- File: `EMERGENCY_STOP`
- If this file exists, **ALL orders are blocked**
- Create this file to immediately halt trading
- Check frequency: **Before every order**

### Layer 2: Signal Validation
- Symbol format (max 5 characters)
- Signal type (BUY/SELL/CLOSE only)
- Quantity > 0
- Price validation (if limit order)

### Layer 3: Risk Manager Validation
Checks from `RiskManager.check_trade_risk()`:
- **Position limit**: Max 4 concurrent positions
- **Position size**: Max 25% of equity per position
- **Drawdown limit**: Stop trading if down 20% from peak
- **Daily loss limit**: Stop trading if down 5% today
- **Emergency stop**: Blocks all trades if enabled

### Layer 4: Portfolio Reconciliation
- Compares strategy's position view vs TWS reality
- **BLOCKS order if TWS has positions we don't know about**
- Tolerates 5-share discrepancy (rounding)
- Prevents state desynchronization

### Layer 5: Order Sanity Checks
- Price > 0 (if specified)
- Price not > total equity (obvious error)
- Order cost < 50% of equity (single order limit)
- Estimated value reasonable

### Layer 6: Live Mode Confirmation
- **Only in live mode with --confirm-live flag**
- Displays order details (symbol, quantity, price, value)
- Requires explicit "yes" response
- User can cancel with "no" or Ctrl+C

---

## Pre-Flight Checklist

Before starting live trading, verify:

### Technical Setup
- [ ] TWS running in correct mode (paper = 7497, live = 7496)
- [ ] Account has sufficient buying power
- [ ] Internet connection stable
- [ ] System time synchronized (important for order timestamps)
- [ ] Logs directory exists and writable

### Risk Configuration
- [ ] `RiskManager` configured with appropriate limits:
  ```python
  risk_manager = RiskManager(
      max_positions=4,           # Conservative for start
      max_position_pct=0.20,     # 20% of equity max per position
      max_drawdown_pct=0.15,     # Stop at 15% drawdown
      daily_loss_limit_pct=0.03, # Stop at 3% daily loss
      emergency_stop_enabled=True
  )
  ```

### Strategy Validation
- [ ] Strategy tested in paper trading for at least 1 week
- [ ] Backtest results reviewed (Sharpe > 1.5, drawdown < 20%)
- [ ] Order frequency understood (not too aggressive)
- [ ] Position sizing appropriate for account size

### Emergency Preparedness
- [ ] Know how to create EMERGENCY_STOP file:
  ```bash
  # Windows
  echo. > EMERGENCY_STOP
  
  # Linux/Mac
  touch EMERGENCY_STOP
  ```
- [ ] TWS order cancellation procedure known
- [ ] Contact info for IBKR support saved
- [ ] Phone nearby for manual intervention

---

## Risk Controls

### Position Limits
```python
max_positions = 4          # Total concurrent positions
max_position_pct = 0.25    # 25% max per position
```

**Why this matters:**
- 4 positions × 25% = 100% max exposure (fully invested)
- Diversification across 4 symbols reduces single-stock risk
- Prevents over-concentration

### Drawdown Control
```python
max_drawdown_pct = 0.20    # Stop at 20% drawdown
```

**How it works:**
- Tracks highest equity (peak)
- If current equity < peak * 0.80, **stops all new trades**
- Existing positions can still be closed
- Prevents catastrophic losses

### Daily Loss Limit
```python
daily_loss_limit_pct = 0.05  # 5% daily loss limit
```

**Why this matters:**
- Limits damage from bad days
- Resets at midnight
- Prevents revenge trading (trying to recover losses)

### Emergency Stop
```python
emergency_stop_enabled = True
```

**How to trigger:**
1. Create file `EMERGENCY_STOP` in project directory
2. All new orders immediately blocked
3. Monitor existing positions manually in TWS
4. Delete file to resume trading

---

## Emergency Procedures

### Scenario 1: Strategy Misbehaving
**Symptoms:**
- Too many orders
- Unexpected positions
- Rapid losses

**Actions:**
1. **Immediately create EMERGENCY_STOP file** (blocks new orders)
2. Open TWS and review open orders
3. Cancel any unwanted orders in TWS
4. Close unwanted positions manually if needed
5. Stop the `run_live.py` process
6. Review logs in `logs/tws_robot_YYYYMMDD.log`
7. Review order audit trail in `logs/order_audit_YYYYMMDD.log`

### Scenario 2: Market Conditions Changed
**Symptoms:**
- High volatility
- News event
- Strategy drawdown approaching limit

**Actions:**
1. Create EMERGENCY_STOP file (prevents new positions)
2. Let existing positions close naturally OR
3. Manually close positions in TWS if urgent
4. Wait for market to stabilize
5. Review strategy performance
6. Adjust risk limits if needed
7. Delete EMERGENCY_STOP when ready to resume

### Scenario 3: Technical Issues
**Symptoms:**
- Lost TWS connection
- System crash
- Internet outage

**Actions:**
1. **Priority: Check TWS for open positions/orders**
2. Cancel any orphaned orders
3. Close positions if you can't monitor them
4. Do NOT restart `run_live.py` until issue resolved
5. Verify TWS connection stable
6. Check logs for what happened
7. Resume with caution

---

## Order Execution Flow

**Complete flow from signal to execution:**

```
┌─────────────┐
│ Strategy    │  Generates signal (BUY AAPL 100 shares)
│ on_bar()    │
└──────┬──────┘
       │
       v
┌──────────────────────┐
│ OrderExecutor        │
│ execute_signal()     │
└──────────────────────┘
       │
       v
┌──────────────────────┐
│ CHECK 1:             │  EMERGENCY_STOP file exists?
│ Emergency Stop       │  → YES: BLOCK ORDER ❌
└──────┬───────────────┘  → NO: Continue ✓
       │
       v
┌──────────────────────┐
│ CHECK 2:             │  Symbol valid? Signal type valid?
│ Signal Validation    │  → NO: REJECT ❌
└──────┬───────────────┘  → YES: Continue ✓
       │
       v
┌──────────────────────┐
│ CHECK 3:             │  Position limits? Drawdown? Daily loss?
│ Risk Manager         │  → FAIL: BLOCK ORDER ❌
└──────┬───────────────┘  → PASS: Continue ✓
       │
       v
┌──────────────────────┐
│ CHECK 4:             │  Strategy positions match TWS?
│ Portfolio Reconcile  │  → NO: REJECT ❌
└──────┬───────────────┘  → YES: Continue ✓
       │
       v
┌──────────────────────┐
│ CHECK 5:             │  Price reasonable? Quantity sane?
│ Sanity Checks        │  → NO: REJECT ❌
└──────┬───────────────┘  → YES: Continue ✓
       │
       v
┌──────────────────────┐
│ CHECK 6:             │  (Live mode only)
│ User Confirmation    │  Display order, prompt for "yes"
└──────┬───────────────┘  → "no": CANCEL ❌
       │                   → "yes": Continue ✓
       v
┌──────────────────────┐
│ PaperTradingAdapter  │  Converts to TWS order
│ .buy() / .sell()     │
└──────┬───────────────┘
       │
       v
┌──────────────────────┐
│ TWS API              │  Places order on exchange
│ placeOrder()         │
└──────────────────────┘
       │
       v
   ✅ ORDER SUBMITTED
   (Logged to order_audit_YYYYMMDD.log)
```

**Key points:**
- **6 checks, all mandatory**
- **Any failure = order blocked**
- **No bypasses or overrides**
- **Full audit trail**

---

## Common Mistakes to Avoid

### Mistake 1: Skipping Paper Trading
❌ **DON'T:** Test strategy once in backtest, then go live
✅ **DO:** Test in paper trading for at least 1 week minimum

**Why:**
- Backtest uses perfect hindsight data
- Paper trading reveals execution issues (slippage, fill delays)
- Paper trading tests risk controls in real-time

### Mistake 2: Using Live Mode Without Understanding TWS
❌ **DON'T:** Connect to live TWS (port 7496) until you understand how it works
✅ **DO:** Master paper trading first, then switch to live with small positions

**Why:**
- TWS has quirks (order types, fill behavior)
- Live mode has real financial consequences
- Can't undo mistakes with real money

### Mistake 3: Not Monitoring First Live Trade
❌ **DON'T:** Start live trading and walk away
✅ **DO:** Watch your first 10+ live trades closely

**Why:**
- Verify strategy behaves as expected
- Catch execution issues early
- Understand your system's actual behavior

### Mistake 4: Aggressive Position Sizing
❌ **DON'T:** Use 50%+ of equity per position initially
✅ **DO:** Start with 10-20% max per position

**Why:**
- Limits damage from strategy errors
- Allows multiple positions for diversification
- Reduces emotional stress

### Mistake 5: No Emergency Plan
❌ **DON'T:** Assume nothing will go wrong
✅ **DO:** Have EMERGENCY_STOP procedure ready before trading

**Why:**
- Systems fail (bugs, connection loss, TWS crash)
- Markets surprise (flash crashes, halts)
- You need instant "STOP" button

### Mistake 6: Ignoring Risk Limits
❌ **DON'T:** Override risk checks "just this once"
✅ **DO:** Respect risk limits always, adjust limits if needed

**Why:**
- Risk limits protect your capital
- "Just this once" becomes a habit
- Drawdown cascades quickly without limits

### Mistake 7: Running Multiple Strategies Without Testing
❌ **DON'T:** Run 5 strategies simultaneously on first day
✅ **DO:** Start with ONE strategy, add more gradually

**Why:**
- Multiple strategies = multiple risk sources
- Hard to debug which strategy caused issue
- Position limits apply across all strategies

---

## Safety Features Summary

### What We Have ✅
- **6-layer order validation** (emergency stop, signal validation, risk checks, portfolio reconciliation, sanity checks, user confirmation)
- **Risk limits enforcement** (position limits, drawdown control, daily loss limits)
- **Emergency stop file** (instant halt mechanism)
- **Order audit trail** (every order logged with timestamp, status, reason)
- **Portfolio reconciliation** (catches state desynchronization)
- **Live mode confirmation** (explicit user approval per order in live mode)

### What We Don't Have (Yet) ⚠️
- Real-time position tracking from TWS (we query on-demand)
- Automatic stop-loss orders (must be added to strategy)
- Email/SMS alerts for important events
- Web dashboard for monitoring
- Historical performance tracking in database
- Multi-strategy coordination

---

## Final Checklist Before Going Live

Print this and check off each item:

**Account Setup:**
- [ ] IBKR account approved for live trading
- [ ] Sufficient capital deposited (recommend $10,000+ for stocks)
- [ ] Account permissions include desired asset types
- [ ] TWS installed and configured

**Testing Completed:**
- [ ] Strategy backtested (Sharpe > 1.5, Drawdown < 20%)
- [ ] Strategy paper traded for 1+ weeks successfully
- [ ] All tests pass (pytest tests/ -v shows 100% pass rate)
- [ ] Reviewed logs from paper trading runs

**Risk Configuration:**
- [ ] RiskManager limits set conservatively
- [ ] Emergency stop procedure tested (create EMERGENCY_STOP file)
- [ ] Position sizing appropriate for account (<25% per position)
- [ ] Understand maximum possible loss scenarios

**System Ready:**
- [ ] Virtual environment activated
- [ ] All dependencies installed (pip install -r requirements.txt)
- [ ] TWS running in LIVE mode (port 7496)
- [ ] Logs directory exists
- [ ] System time correct (important for timestamps)

**You Are Ready:**
- [ ] Read this entire document
- [ ] Understand every safety check
- [ ] Know how to stop trading immediately
- [ ] Phone nearby for emergencies
- [ ] Will monitor first 10 trades closely
- [ ] Will start with small position sizes
- [ ] Have realistic expectations (strategies can lose money)

**Now you can run:**
```bash
python run_live.py --strategy bollinger --initial-capital 10000 --confirm-live
```

**Monitor for:**
- Orders being placed as expected
- Risk limits working correctly
- No unexpected positions
- Reasonable fill prices

---

## Support Resources

**When Things Go Wrong:**
1. **Immediate:** Create EMERGENCY_STOP file
2. **Check TWS:** Review positions/orders in TWS directly
3. **Review Logs:** `logs/tws_robot_YYYYMMDD.log` and `logs/order_audit_YYYYMMDD.log`
4. **IBKR Support:** 1-877-442-2757 (US) for account issues

**For Strategy Issues:**
- Review backtest results: `reports/backtest_STRATEGY_YYYYMMDD_HHMMSS.html`
- Check risk manager stats in logs
- Review WEEK4_DOCUMENTATION.md for strategy details

**Remember:**
- Paper trading is free, use it liberally
- Start small in live trading
- Risk limits are your friend
- When in doubt, stop trading and analyze

---

**⚠️ FINAL WARNING ⚠️**

Live trading involves real financial risk. You can lose money.

No strategy is guaranteed profitable. Past performance (backtest or paper trading) does not guarantee future results.

This software is provided as-is without warranty. Use at your own risk.

**By using this system for live trading, you acknowledge:**
- You understand how it works
- You've tested it thoroughly in paper trading
- You accept full responsibility for any losses
- You will not trade more than you can afford to lose

---

*Last Updated: January 24, 2026*
*Document Version: 1.0*
*Part of: TWS Robot Live Trading Phase 1*
