# Live Trading Features - Development Strategy

> ⚠️ **HISTORICAL DOCUMENT — MOST FEATURES BELOW HAVE BEEN IMPLEMENTED**
>
> This strategy document was written in January 2026 during the planning phase. Since then, the majority of the features described have been fully implemented and tested:
>
> - ✅ **Phase 1 MVP**: `scripts/run_live.py` launcher, `MarketDataFeed`, `OrderExecutor`, safety checks — all implemented
> - ✅ **Phase 2 Robustness**: Auto-reconnection, state persistence via database, order status tracking — implemented
> - ✅ **Phase 3 Safety**: Emergency controls (3-level system with circuit breakers), daily loss limits, pre-flight checks, position limits — implemented
> - ✅ **Phase 4 Multi-Strategy**: `StrategyOrchestrator` with signal aggregation, conflict resolution, allocation management — implemented
> - ✅ **Phase 5 Monitoring**: Web dashboard with real-time positions, P&L, risk monitoring, logs, AI assistant — implemented
> - ⬚ **Phase 6 More Strategies**: Only Bollinger Bands is live-ready; MA Cross, Mean Reversion, Momentum remain backtest-only
>
> **For current documentation, see:**
> - [User Guide](USER_GUIDE.md) — How to use TWS Robot
> - [Live Trading Safety](LIVE_TRADING_SAFETY.md) — Critical safety guide
> - [Local Deployment](LOCAL_DEPLOYMENT.md) — Paper trading and live deployment
> - [TWS Connection Guide](TWS_CONNECTION_GUIDE.md) — Connecting to IBKR

**Original Status:** Planning Phase (January 2026) — **Most items now complete**  
**Date:** January 24, 2026  
**Purpose:** Define the roadmap for live trading capabilities

---

## 📊 Current State Assessment

### ✅ What Exists (Implemented & Tested)

**Core Infrastructure:**
- ✅ **TWS Connection Client** (`tws_client.py`) - Connects to IBKR, loads portfolio, monitors account
- ✅ **Paper Trading Adapter** (`execution/paper_adapter.py`) - Bridges strategies to TWS API
- ✅ **Strategy Framework** (`strategies/base_strategy.py`) - Base class for all strategies
- ✅ **Signal System** (`strategies/signal.py`) - Signal types, strength, validation
- ✅ **Strategy Orchestrator** (`strategies/strategy_orchestrator.py`) - Multi-strategy coordination
- ✅ **Risk Management** (`risk/`) - Position sizing, drawdown control, correlation analysis
- ✅ **Real-time Monitoring** (`risk/monitoring.py`) - Health checks, alerts, dashboards

**Live Trading Strategy:**
- ✅ **Bollinger Bands** (`strategies/bollinger_bands.py`) - Production-ready for paper/live

**Backtest Strategies** (Not live-ready):
- ⚠️ Moving Average Crossover (`backtest/strategy_templates.py`)
- ⚠️ Mean Reversion (`backtest/strategy_templates.py`)
- ⚠️ Momentum (`backtest/strategy_templates.py`)

### ❌ What's Missing (Critical Gaps)

**1. Live Trading Launcher**
- ❌ No script to run `BollingerBands` with `PaperTradingAdapter`
- ❌ No integration between `tws_client.py` (connection) and `strategies/` (trading logic)
- ❌ No command like `python run_live.py --strategy bollinger_bands --env paper`

**2. Strategy-to-TWS Integration**
- ❌ `tws_client.py` only monitors - doesn't execute strategy signals
- ❌ No bridge connecting `BollingerBandsStrategy.on_bar()` → `PaperTradingAdapter.place_order()` → TWS API
- ❌ No real-time market data feed to strategy

**3. Live Strategy Lifecycle**
- ❌ No start/stop mechanism for live strategies
- ❌ No graceful shutdown handling
- ❌ No state persistence (what if process crashes?)
- ❌ No reconnection logic for TWS disconnects

**4. Order Execution Pipeline**
- ❌ Strategy generates signals, but who converts them to orders?
- ❌ No order validation before sending to TWS
- ❌ No order status tracking (pending, filled, rejected)
- ❌ No position reconciliation (strategy thinks 100 shares, TWS says 90)

**5. Safety & Controls**
- ❌ No emergency stop button
- ❌ No max daily loss enforcement
- ❌ No pre-flight checks (market open? account has cash? position limits?)
- ❌ No audit trail of orders placed

**6. Data Feed**
- ❌ `tws_client.py` subscribes to market data but doesn't forward it to strategies
- ❌ No real-time bar construction (5-min bars, 15-min bars)
- ❌ No data buffering/caching

**7. Documentation**
- ❌ No "Live Trading Guide" explaining the full workflow
- ❌ No runbook for "How to Run Bollinger Bands Live"
- ❌ No troubleshooting guide for live trading issues

---

## 🎯 Development Priorities

### **Phase 1: MVP Live Trading (Highest Priority)** ⭐
**Goal:** Get `BollingerBands` strategy running in paper trading with real-time data

**Deliverables:**
1. **`run_live.py` - Main Live Trading Launcher**
   ```python
   # Usage:
   python run_live.py --strategy bollinger_bands --env paper --symbols AAPL,MSFT
   ```
   
   **Responsibilities:**
   - Connect to TWS via `PaperTradingAdapter`
   - Load and start `BollingerBandsStrategy`
   - Subscribe to real-time market data
   - Feed data to strategy
   - Convert strategy signals → TWS orders
   - Monitor positions and P&L
   - Handle graceful shutdown

2. **Real-time Data Feed Pipeline**
   - `MarketDataFeed` class that:
     - Requests real-time bars from TWS
     - Constructs 5-minute bars
     - Calls `strategy.on_bar(bar_data)`
   - Buffer management for historical context
   
3. **Signal-to-Order Bridge**
   - `OrderExecutor` class that:
     - Receives signals from strategy
     - Validates against risk limits
     - Converts to TWS order format
     - Submits via `PaperTradingAdapter`
     - Tracks order status
   
4. **Basic Safety Checks**
   - Market hours check (don't trade when closed)
   - Account balance check (enough cash?)
   - Position limits check (not over-leveraged?)
   - Emergency stop file (`touch STOP` to halt trading)

**Files to Create:**
- `run_live.py` - Main launcher
- `execution/market_data_feed.py` - Real-time data pipeline
- `execution/order_executor.py` - Signal → Order conversion
- `execution/safety_checks.py` - Pre-trade validation

**Files to Modify:**
- `tws_client.py` - Refactor to be importable, not just standalone
- `strategies/bollinger_bands.py` - Add real-time data handling (if needed)

**Estimated Effort:** 3-4 days (24-32 hours)

---

### **Phase 2: Robustness & Reliability**
**Goal:** Make live trading production-ready

**Deliverables:**
1. **State Persistence**
   - Save strategy state to disk every 5 minutes
   - Restore state on restart
   - Track open positions, pending orders

2. **Reconnection Logic**
   - Detect TWS disconnects
   - Auto-reconnect with exponential backoff
   - Reconcile positions after reconnect

3. **Order Status Tracking**
   - Monitor order lifecycle (submitted → filled/rejected)
   - Handle partial fills
   - Update strategy position on fills

4. **Position Reconciliation**
   - Compare strategy positions vs TWS positions
   - Alert on mismatch
   - Auto-correct if within tolerance

5. **Enhanced Logging**
   - Log every order (symbol, quantity, price, reason)
   - Log every fill
   - Separate log file per day
   - Structured logging (JSON format)

**Files to Create:**
- `execution/state_manager.py` - State persistence
- `execution/reconnection_handler.py` - TWS reconnect logic
- `execution/position_reconciler.py` - Position sync
- `execution/audit_logger.py` - Structured audit trail

**Estimated Effort:** 2-3 days (16-24 hours)

---

### **Phase 3: Safety & Controls**
**Goal:** Prevent catastrophic losses

**Deliverables:**
1. **Emergency Controls**
   - Stop file monitoring (`if exists(STOP): halt()`)
   - Keyboard interrupt handling (Ctrl+C = graceful shutdown)
   - Kill switch API endpoint (POST /emergency_stop)

2. **Daily Loss Limits**
   - Track daily P&L
   - Halt trading at -5% daily loss
   - Resume next day automatically
   - Send email alert on breach

3. **Pre-Flight Checklist**
   - ✅ TWS connected?
   - ✅ Market open?
   - ✅ Account has buying power?
   - ✅ No overnight positions (if day-trading)?
   - ✅ Risk limits configured?
   
4. **Position Limits**
   - Max position size per symbol
   - Max portfolio heat
   - Max correlation exposure
   - Enforce before placing orders

**Files to Create:**
- `execution/emergency_controls.py` - Stop mechanisms
- `execution/daily_loss_monitor.py` - P&L tracking
- `execution/preflight_checks.py` - Startup validation
- `execution/position_limits.py` - Position constraints

**Estimated Effort:** 2 days (16 hours)

---

### **Phase 4: Multi-Strategy Support**
**Goal:** Run multiple strategies simultaneously

**Deliverables:**
1. **Strategy Orchestrator Integration**
   - Use existing `StrategyOrchestrator`
   - Register multiple strategies with capital allocation
   - Aggregate signals from all strategies
   - Resolve conflicts (Strategy A says buy, Strategy B says sell)

2. **Portfolio-Level Risk**
   - Total portfolio heat calculation
   - Correlation-based position sizing
   - Diversification enforcement

3. **Per-Strategy Accounting**
   - Track P&L per strategy
   - Attribute performance to strategy
   - Report strategy rankings

**Files to Modify:**
- `run_live.py` - Support multiple strategies
- `strategies/strategy_orchestrator.py` - Add real-time mode

**Estimated Effort:** 1-2 days (8-16 hours)

---

### **Phase 5: Monitoring & Observability**
**Goal:** Know what's happening at all times

**Deliverables:**
1. **Real-time Dashboard**
   - Current positions
   - Today's P&L
   - Open orders
   - Recent signals
   - Health status

2. **Alerting**
   - Email alerts on:
     - Order rejections
     - Risk limit breaches
     - Connection issues
     - Unexpected behavior
   
3. **Performance Reporting**
   - Daily summary email
   - Weekly performance report
   - Monthly strategy comparison

**Files to Create:**
- `monitoring/live_dashboard.py` - Real-time web dashboard
- `monitoring/alert_manager.py` - Alert routing
- `monitoring/performance_reporter.py` - Scheduled reports

**Estimated Effort:** 3 days (24 hours)

---

### **Phase 6: More Live Strategies**
**Goal:** Convert backtest strategies to live trading

**Deliverables:**
1. **Moving Average Crossover** (Live)
   - Migrate from `backtest/strategy_templates.py`
   - Add real-time data handling
   - Test in paper trading for 30 days

2. **Mean Reversion** (Live)
   - Migrate from backtest
   - Adapt for real-time data
   - Paper trade validation

3. **Momentum** (Live)
   - Migrate from backtest
   - Real-time implementation
   - Paper trade validation

**Files to Create:**
- `strategies/moving_average_live.py`
- `strategies/mean_reversion_live.py`
- `strategies/momentum_live.py`

**Estimated Effort:** 2-3 days per strategy (16-24 hours each)

---

## 🗓️ Proposed Timeline

| Phase | Duration | Priority | Status |
|-------|----------|----------|--------|
| **Phase 1: MVP** | 3-4 days | 🔴 Critical | Not Started |
| **Phase 2: Robustness** | 2-3 days | 🔴 Critical | Not Started |
| **Phase 3: Safety** | 2 days | 🟠 High | Not Started |
| **Phase 4: Multi-Strategy** | 1-2 days | 🟡 Medium | Not Started |
| **Phase 5: Monitoring** | 3 days | 🟡 Medium | Not Started |
| **Phase 6: More Strategies** | 2-3 days each | 🟢 Low | Not Started |

**Total Estimated Time:** 13-17 days (104-136 hours)

**Recommendation:** Start with Phase 1 (MVP), validate in paper trading for 30 days, then proceed to Phase 2.

---

## 📐 Architecture Proposal

### Current Architecture (Backtest)
```
Historical Data → BacktestEngine → Strategy.on_bar() → Simulated Orders → Results
```

### Proposed Architecture (Live)
```
TWS API (Market Data)
    ↓
MarketDataFeed (constructs bars)
    ↓
Strategy.on_bar() (Bollinger Bands)
    ↓
Signal (BUY/SELL/CLOSE)
    ↓
OrderExecutor (validate + convert)
    ↓
PaperTradingAdapter (TWS API calls)
    ↓
TWS (executes orders)
    ↓
Order Fills → Update Strategy Positions
```

### Key Components

**1. MarketDataFeed**
```python
class MarketDataFeed:
    def __init__(self, tws_adapter, symbols, bar_size='5 min'):
        self.tws_adapter = tws_adapter
        self.symbols = symbols
        self.bar_size = bar_size
        self.bar_buffers = {}  # symbol -> list of ticks
    
    def start(self):
        """Subscribe to real-time data"""
        for symbol in self.symbols:
            self.tws_adapter.subscribe_market_data(symbol)
    
    def on_tick(self, symbol, tick):
        """Called when tick arrives from TWS"""
        self.bar_buffers[symbol].append(tick)
        
        # Check if 5-minute bar complete
        if self._is_bar_complete(symbol):
            bar = self._construct_bar(symbol)
            self._notify_subscribers(symbol, bar)
```

**2. OrderExecutor**
```python
class OrderExecutor:
    def __init__(self, tws_adapter, risk_manager):
        self.tws_adapter = tws_adapter
        self.risk_manager = risk_manager
    
    def execute_signal(self, strategy_name, signal):
        """Convert signal to order and execute"""
        
        # Validate signal
        if not signal.is_valid():
            return OrderResult.rejected("Invalid signal")
        
        # Check risk limits
        if not self.risk_manager.check_trade_risk(signal):
            return OrderResult.rejected("Risk limit exceeded")
        
        # Convert to TWS order
        order = self._signal_to_order(signal)
        
        # Submit to TWS
        order_id = self.tws_adapter.place_order(order)
        
        return OrderResult.submitted(order_id)
```

**3. run_live.py (Main Entry Point)**
```python
def main():
    # 1. Parse arguments
    args = parse_args()  # --strategy, --env, --symbols
    
    # 2. Connect to TWS
    tws_adapter = PaperTradingAdapter(
        host='127.0.0.1',
        port=7497 if args.env == 'paper' else 7496
    )
    tws_adapter.connect_and_run()
    
    # 3. Initialize components
    market_feed = MarketDataFeed(tws_adapter, args.symbols)
    risk_manager = RiskManager(initial_capital=100000)
    order_executor = OrderExecutor(tws_adapter, risk_manager)
    
    # 4. Load strategy
    strategy = load_strategy(args.strategy, symbols=args.symbols)
    
    # 5. Connect signal handler
    strategy.on_signal = lambda sig: order_executor.execute_signal(args.strategy, sig)
    
    # 6. Start market feed
    market_feed.subscribe(lambda sym, bar: strategy.on_bar(bar))
    market_feed.start()
    
    # 7. Run until stopped
    print("Live trading started. Press Ctrl+C to stop.")
    wait_for_shutdown()
    
    # 8. Graceful shutdown
    strategy.stop()
    tws_adapter.disconnect()
```

---

## 🔑 Key Design Decisions

### Decision 1: Reuse `PaperTradingAdapter` or Create New Client?
**Recommendation:** Reuse `PaperTradingAdapter`
- ✅ Already implements order placement
- ✅ Already tracks positions
- ✅ Tested with TWS API
- ❌ Name is confusing for live trading (rename to `TWSAdapter`?)

**Action:** Rename `PaperTradingAdapter` → `TWSAdapter`, support both paper and live

---

### Decision 2: Real-time Bars vs Tick Data?
**Recommendation:** Real-time Bars (via `reqRealTimeBars`)
- ✅ TWS provides 5-second bars natively
- ✅ Matches backtest bar structure
- ✅ Simpler than constructing from ticks
- ❌ 5-second is shortest interval (not tick-level)

**Action:** Use `reqRealTimeBars` with 5-second bars, aggregate to strategy timeframe

---

### Decision 3: Single-Process or Multi-Process?
**Recommendation:** Single-process for MVP, multi-process later
- ✅ Simpler to debug
- ✅ Easier state management
- ❌ Not scalable to many strategies
- ❌ One strategy crash kills all

**Action:** Phase 1 = single-process, Phase 4 = evaluate multi-process

---

### Decision 4: State Storage - JSON or Database?
**Recommendation:** JSON files for MVP, PostgreSQL later
- ✅ Simple to implement
- ✅ Human-readable
- ✅ No database setup
- ❌ Not concurrent-safe
- ❌ No query capability

**Action:** Phase 1 = JSON in `state/` folder, Phase 5 = add PostgreSQL option

---

## 📝 Documentation Plan

Once Phase 1 MVP is complete, create:

1. **LIVE_TRADING_GUIDE.md**
   - What is live trading in TWS Robot?
   - How `run_live.py` works
   - How to run Bollinger Bands in paper trading
   - How to monitor live trading
   - How to stop gracefully
   - What happens when things go wrong

2. **Update USER_GUIDE.md**
   - Add "Live Trading Workflow" section
   - Explain connection → data feed → signals → orders → fills
   - Add troubleshooting for live trading

3. **Update README.md**
   - Add live trading quick start example
   - Update architecture diagram

4. **Create LIVE_TRADING_RUNBOOK.md**
   - Daily startup procedure
   - Pre-market checklist
   - Monitoring during trading hours
   - End-of-day shutdown
   - Weekly reconciliation
   - Emergency procedures

---

## ⚠️ Risks & Mitigation

| Risk | Impact | Probability | Mitigation |
|------|--------|-------------|------------|
| Order gets stuck in pending state | Medium | Medium | Timeout + retry logic |
| TWS disconnects mid-trade | High | Low | Reconnection + position reconciliation |
| Strategy crashes | High | Medium | Try-catch + alert + graceful degradation |
| Market data feed stops | High | Low | Heartbeat monitoring + reconnect |
| Accidental live trading (meant paper) | Critical | Low | Require explicit `--confirm-live` flag |
| Over-leveraging | Critical | Medium | Pre-trade position limits |
| Daily loss exceeds limit | High | Medium | Real-time P&L monitoring + circuit breaker |

---

## 🎯 Success Criteria

**Phase 1 MVP is successful when:**
- [ ] Can run `python run_live.py --strategy bollinger_bands --env paper --symbols AAPL`
- [ ] Strategy receives real-time 5-minute bars from TWS
- [ ] Strategy generates signals (BUY/SELL)
- [ ] Signals are converted to orders and sent to TWS
- [ ] Orders are filled by TWS
- [ ] Positions are tracked accurately
- [ ] Can gracefully shutdown with Ctrl+C
- [ ] Runs for 8 hours without crashing
- [ ] Handles market close gracefully

**Phase 2 Robustness is successful when:**
- [ ] Survives TWS disconnect/reconnect
- [ ] Restores state after process restart
- [ ] Reconciles positions after restart
- [ ] Runs for 30 days without manual intervention

**Phase 3 Safety is successful when:**
- [ ] Emergency stop file halts trading instantly
- [ ] Daily loss limit enforced
- [ ] Pre-flight checks prevent invalid trading
- [ ] Audit trail shows every order placed

---

## 🚦 Go/No-Go Decision Points

**Before starting Phase 1:**
- [ ] Confirm `PaperTradingAdapter` works with TWS paper account
- [ ] Confirm `BollingerBandsStrategy` generates valid signals
- [ ] Confirm team has time for 3-4 days of development

**Before starting Phase 2:**
- [ ] Phase 1 MVP runs successfully for 5+ trading days
- [ ] No critical bugs in Phase 1
- [ ] Paper trading P&L matches expectations

**Before enabling live trading:**
- [ ] Paper trading validated for 30+ days
- [ ] All safety controls tested
- [ ] Emergency procedures documented
- [ ] Team comfortable with risk

---

## 📞 Next Steps

**Immediate Actions:**
1. Review this strategy with team
2. Confirm Phase 1 priorities
3. Allocate 3-4 days for Phase 1 development
4. Create GitHub issues for Phase 1 tasks:
   - Issue #1: Create `run_live.py` launcher
   - Issue #2: Create `MarketDataFeed` class
   - Issue #3: Create `OrderExecutor` class
   - Issue #4: Add safety checks
   - Issue #5: Integration testing

**Questions to Answer:**
1. Do we refactor `tws_client.py` or start fresh with `run_live.py`?
2. Should we rename `PaperTradingAdapter` to `TWSAdapter` now or later?
3. What's the minimum viable safety checks for Phase 1?
4. Do we need email alerts in Phase 1 or can it wait for Phase 5?

---

**Status:** Ready for team review and approval  
**Next Review:** After Phase 1 completion  
**Owner:** Development Team
