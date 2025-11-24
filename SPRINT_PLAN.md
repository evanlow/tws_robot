# Sprint Plan: Paper Trading Integration
**Date:** November 24, 2025  
**Sprint Duration:** 3 Sprints (10 days → completed in 8 days!)  
**Project Phase:** Week 1-2 of 7-Week Plan (COMPLETE)  

---

## 🎯 Vision & Principles

### Core Vision
Transform tws_robot into a **versatile quantitative trading platform** with equal emphasis on:
1. **Infrastructure** - Robust, scalable, production-ready systems
2. **Strategy Development** - Rapid innovation and testing
3. **Live Trading** - Safe, controlled deployment with mandatory validation

### Mandatory Workflow
```
┌──────────────┐    ┌──────────────┐    ┌──────────────┐    ┌──────────────┐
│  Backtest    │───▶│  Paper Trade │───▶│  Validation  │───▶│  Live Trade  │
│  (Required)  │    │  (Required)  │    │  (Required)  │    │  (Approved)  │
└──────────────┘    └──────────────┘    └──────────────┘    └──────────────┘
   138 tests           Min 30 days        Sharpe >1.0         Manual gate
   passing             real-time          Max DD <10%         + checklist
```

### Prime Directive Compliance
- ✅ 100% test pass rate before AND after changes (ALL tests, no exceptions)
- ✅ Verify baseline → Make change → Verify again
- ✅ Document test count in all commits
- ✅ No exceptions, no shortcuts
- ✅ Pre-existing failures must be fixed BEFORE starting new work
- ✅ "It was already broken" is NOT a valid excuse

---

## 📊 Current Status (November 24, 2025)

### Completed ✅
- **Backtest Engine:** 138/138 tests passing (100%)
- **Strategy Templates:** MA Cross, Mean Reversion, Momentum
- **Risk Profiles:** Conservative, Moderate, Aggressive
- **TWS Client:** Paper/live configs with market status checks
- **Prime Directive:** Enhanced with Sprint 3 lessons (dataclasses+enums, TDD, statistical analysis)
- **Module Cleanup:** Single authoritative backtest/ module
- **SPRINT 1 COMPLETE (Days 1-4):** 231/231 tests passing (100%) ✅
  - Task 1: Strategy Lifecycle (29 tests, commit f701d37)
  - Task 2: Paper Trading Adapter (32 tests, commit a3a3ff3)
  - Task 3: Real-time Market Data Pipeline (17 tests, commit cb1274d)
  - Task 3.1: Fix Pre-existing Test Failures (2 tests fixed, commit fdf2ced)
  - Task 4: Paper Trading Monitor (28 tests, commit d9f3c86)
  - Task 5: Integration Testing (26 tests, commit 1f1b846)
- **SPRINT 2 COMPLETE (Days 5-7):** 393/393 tests passing (100%) ✅
  - Task 1: Real-time Risk Monitor (28 tests, commit ea33654)
  - Task 2: Paper Trading Metrics Tracker (34 tests, commit cf9006a)
  - Task 3: Validation Criteria Enforcer (35 tests, commit aa6f3a1)
  - Task 4: Strategy Promotion Workflow (27 tests, commit 208a298)
  - Task 5: Validation Dashboard Enhancement (38 tests, commit fba239b)
- **SPRINT 3 COMPLETE (Day 8):** 532/532 tests passing (100%) ✅
  - Task 1: Config Hot-Reload (35 tests, commit c9b5cbb)
  - Task 2: Multi-Strategy Orchestration (35 tests, commit c9b5cbb)
  - Task 3: Strategy Comparison Dashboard (34 tests, commit 2e009ab)
  - Task 4: Performance Attribution (35 tests, commit b24c48f)
  - Task 5: Strategy Health Monitoring (35 tests, commit 0f45bc7)

### In Progress 🔄
- **Sprint 4 Planning:** Next phase determination (Integration vs Advanced Features)

### Blockers ❌
- None identified

---

## 🎯 Sprint Goals & Timeline

### Sprint 1: Paper Trading Foundation (Days 1-4) ✅ COMPLETE
**Goal:** Build the bridge from backtesting to paper trading

**Deliverables:**
- [x] Strategy lifecycle state machine
- [x] Paper trading adapter for TWS client
- [x] Real-time market data pipeline
- [x] Paper trading monitor dashboard
- [x] Integration tests (maintain 100% pass rate)

**Success Criteria:**
- ✅ Run MA Cross strategy on paper account
- ✅ Real-time position tracking working
- ✅ Orders execute through TWS paper account
- ✅ All 205 baseline tests still passing (100%)
- ✅ New integration tests 26/26 passing (100%)

### Sprint 2: Risk & Validation Framework (Days 5-7) ✅ COMPLETE
**Goal:** Implement paper trading validation and risk controls

**Deliverables:**
- [x] Risk profiles integrated with live execution ✅
- [x] Real-time risk monitoring and enforcement ✅
- [x] Paper trading validation metrics tracker ✅
- [x] Validation criteria enforcer (ValidationEnforcer class) ✅
- [x] Strategy promotion workflow and checklist ✅
- [x] Automated validation dashboard ✅

**Success Criteria:**
- ✅ Risk limits enforced in real-time (pre & post trade checks)
- ✅ Paper trading metrics tracked (Sharpe, DD, win rate, profit factor, consecutive losses)
- ✅ Promotion workflow prevents premature live deployment (3 gates enforced)
- ✅ Emergency stop functionality tested (integrated with lifecycle)
- ✅ All tests passing with risk integration (393/393 = 100%)

**Completion Summary:**
- **Date Completed:** November 24, 2025
- **Tests Added:** 162 (28+34+35+27+38)
- **Code Added:** 3,667 lines (2,310 production + 1,357 tests)
- **Velocity:** 54 tests/day (64% increase over Sprint 1)
- **Test Pass Rate:** 100% maintained throughout
- **Documentation:** SPRINT2_COMPLETE.md created
- **Prime Directive Updates:** 8 new lessons added

### Sprint 3: Strategy Development Pipeline (Days 8-10) ✅ COMPLETE
**Goal:** Enable multi-strategy concurrent execution and dynamic management

**Deliverables:**
- [x] Hot-reload strategy parameters (without restart) ✅
- [x] Strategy comparison dashboard (side-by-side metrics) ✅
- [x] Multi-strategy concurrent execution (orchestration) ✅
- [x] Performance attribution system (per-strategy tracking) ✅
- [x] Strategy health monitoring (real-time health scores) ✅
- [x] Strategy allocation management (capital distribution) ✅

**Success Criteria:**
- ✅ 3+ strategies running concurrently on paper
- ✅ Parameter changes without restart (hot-reload working)
- ✅ Side-by-side strategy comparison (comparison dashboard)
- ✅ Attribution tracking per strategy (P&L, trades, metrics)
- ✅ All tests passing with multi-strategy support (532/532 = 100%)
- ✅ Dynamic allocation working (rebalance without restart)

**Actual Results:**
- **Tests Added:** 174 tests (35+35+34+35+35)
- **Code Added:** ~4,200 lines (2,600 production + 1,600 tests)
- **Duration:** 1 day (Nov 24, 2025) - **3x faster than planned!**
- **Achieved Velocity:** 87 tests/day (61% increase over Sprint 2)

**Completion Summary:**
- **Date Completed:** November 24, 2025
- **Tests Added:** 174 (35+35+34+35+35)
- **Code Added:** 4,200 lines (2,600 production + 1,600 tests)
- **Velocity:** 87 tests/day (61% increase over Sprint 2, 164% over Sprint 1)
- **Test Pass Rate:** 100% maintained throughout (393→428→463→497→532)
- **Documentation:** SPRINT3_COMPLETE.md created
- **Prime Directive Updates:** 10 new lessons added
- **Key Achievements:** TDD approach, dataclass+enum architecture, statistical degradation detection

### Sprint 4: Integration & Deployment Phase (Days 9-11)
**Status:** IN PROGRESS (Started Nov 24, 2025)  
**Decision:** Option A selected - Option B features deferred for post-deployment
**Goal:** Connect all Sprint 1-3 components into production-ready system

**Deliverables:**
1. **End-to-End Integration Testing** (30-40 tests)
   - [ ] Full workflow validation (paper → validated → live transitions)
   - [ ] Strategy lifecycle testing (initialization → execution → shutdown)
   - [ ] Multi-component integration (orchestrator + risk + monitoring)
   - [ ] Error handling and recovery scenarios
   - [ ] Data pipeline integrity validation

2. **Production Deployment Configuration** (30-40 tests)
   - [ ] Environment configuration management
   - [ ] Secrets and credentials handling
   - [ ] Connection pooling and management
   - [ ] Production safety checks and guards
   - [ ] Automated deployment scripts

3. **Real-Time Monitoring Dashboards** (30-40 tests)
   - [ ] Live strategy monitoring interface
   - [ ] Performance tracking dashboard
   - [ ] Alert and notification systems
   - [ ] Health check endpoints
   - [ ] Metrics collection and display

4. **Comprehensive Documentation** (20-30 tests)
   - [ ] API documentation (all modules)
   - [ ] Deployment guides (step-by-step)
   - [ ] Operation manuals (daily usage)
   - [ ] Troubleshooting guides (common issues)
   - [ ] Architecture diagrams (system overview)

**Success Criteria:**
- ✅ All 120-150 integration tests passing
- ✅ Production deployment fully automated
- ✅ Monitoring dashboards operational
- ✅ Documentation complete and reviewed
- ✅ End-to-end workflows validated
- ✅ Zero warnings maintained
- ✅ 100% test pass rate

**Estimated Effort:**
- **Tests to Add:** 120-150 tests
- **Code to Add:** 3,500-4,000 lines (2,000 production + 1,500-2,000 tests)
- **Duration:** 2-3 days
- **Target Velocity:** 60-75 tests/day

**Future Enhancements (Option B - Post-Sprint 4):**
Deferred for implementation after production validation:
- Market regime detection (trend/range/volatile identification)
- Dynamic position sizing based on volatility and regime
- Advanced order types (trailing stops, bracket orders, OCO)
- Execution quality tracking and slippage analysis
- Portfolio optimization (mean-variance, risk parity)
- Correlation-based position limits

---

## 📋 Sprint 1 Detailed Backlog

### Task 1: Strategy Lifecycle State Machine (Est: 1-2 hours)
**Priority:** Critical  
**Dependencies:** None

**Implementation:**
```python
# File: strategy/lifecycle.py

States:
- BACKTEST: Strategy in backtest phase (testing on historical data)
- PAPER: Running on paper trading account
- VALIDATED: Paper trading passed validation criteria
- LIVE_APPROVED: Manual approval granted for live trading
- LIVE_ACTIVE: Running on live account
- PAUSED: Temporarily stopped
- RETIRED: Permanently stopped

Transitions:
- BACKTEST → PAPER: All tests passing
- PAPER → VALIDATED: 30+ days, Sharpe >1.0, MaxDD <10%, Win Rate >50%
- VALIDATED → LIVE_APPROVED: Manual approval + checklist
- LIVE_APPROVED → LIVE_ACTIVE: Final confirmation
- Any → PAUSED: Manual or automated stop
- Any → RETIRED: Permanent deactivation
```

**Storage:** SQLite database (strategy_state table)

**Tests Required:**
- State transition validation
- Gating logic enforcement
- Persistence and recovery

---

### Task 2: Paper Trading Adapter (Est: 3-4 hours)
**Priority:** Critical  
**Dependencies:** Task 1

**Implementation:**
```python
# File: execution/paper_adapter.py

Class: PaperTradingAdapter
- Wraps TWS client for strategy use
- Implements Strategy.buy() and Strategy.sell() interface
- Tracks positions in real-time
- Converts between backtest API and TWS API

Features:
- Order execution with TWS paper account
- Position tracking and reconciliation
- Commission simulation (match backtest assumptions)
- Order status monitoring
- Fill confirmation and callbacks
```

**Integration Points:**
- backtest.strategy.Strategy → execution adapter
- core.tws_client.py → TWS API calls
- strategy_templates.py strategies → execution

**Tests Required:**
- Order execution (market, limit, stop)
- Position tracking accuracy
- Commission calculation
- Error handling (connection loss, rejected orders)

---

### Task 3: Real-time Market Data Pipeline (Est: 2-3 hours)
**Priority:** Critical  
**Dependencies:** None

**Implementation:**
```python
# File: data/realtime_pipeline.py

Class: RealtimeDataManager
- Stream market data from TWS
- Convert to backtest.data.MarketData format
- Buffer and distribute to strategies
- Handle multiple symbols simultaneously

Features:
- TWS market data subscription
- Data normalization (TWS format → MarketData format)
- Multi-strategy distribution
- Data quality monitoring
- Reconnection handling
```

**Compatibility:**
- Must produce backtest.data.MarketData objects
- Must work with existing Strategy.on_bar() interface
- Must handle multiple strategies subscribing to same symbols

**Tests Required:**
- Data conversion accuracy
- Multi-subscriber handling
- Connection resilience
- Data quality validation

---

### Task 4: Paper Trading Monitor (Est: 2-3 hours)
**Priority:** High  
**Dependencies:** Task 2, Task 3

**Implementation:**
```python
# File: monitoring/paper_monitor.py

Display Components:
1. Strategy Status Panel
   - Strategy name, state, runtime
   - Current positions
   - P&L (session, total)
   
2. Risk Metrics Panel
   - Portfolio value
   - Margin usage
   - Max drawdown
   - Risk limit utilization
   
3. Order Activity Panel
   - Recent orders (last 20)
   - Order status
   - Fill prices
   
4. Performance Summary
   - Total return %
   - Sharpe ratio (if enough data)
   - Win rate
   - Total trades
```

**Display Format:** Terminal-based (Rich library) for Sprint 1  
**Future:** Web dashboard (Sprint 3 or later)

**Tests Required:**
- Display accuracy
- Real-time updates
- Error handling (missing data)

---

### Task 5: Integration Testing (Est: 2-3 hours)
**Priority:** Critical  
**Dependencies:** All above tasks

**Test Scenarios:**
1. **End-to-End Paper Trading**
   - Deploy MA Cross strategy from backtest to paper
   - Verify orders execute
   - Verify positions tracked
   - Verify P&L calculated

2. **Multi-Symbol Handling**
   - Strategy with 2+ symbols
   - Verify data distribution
   - Verify order routing

3. **Risk Limit Enforcement**
   - Trigger position limit
   - Verify order blocked
   - Verify alert generated

4. **Connection Resilience**
   - Simulate TWS disconnect
   - Verify reconnection
   - Verify state preservation

5. **Prime Directive Compliance**
   - Run full baseline test suite
   - Run new integration tests
   - Verify 100% pass rate

**Test Files:**
- `tests/test_paper_trading_integration.py`
- `tests/test_realtime_data_pipeline.py`
- `tests/test_strategy_lifecycle.py`

---

## 📋 Sprint 2 Detailed Backlog

### Task 1: Real-time Risk Monitor Integration (Est: 2-3 hours)
**Priority:** Critical  
**Dependencies:** Sprint 1 Task 4 (PaperMonitor)

**Implementation:**
```python
# File: execution/risk_monitor.py

Class: RealTimeRiskMonitor
- Monitor positions against RiskProfile limits
- Calculate portfolio risk metrics in real-time
- Enforce position size limits
- Track drawdown and margin usage
- Generate risk alerts

Features:
- Position-level risk checks (before order placement)
- Portfolio-level risk aggregation
- Real-time P&L and drawdown tracking
- Risk limit breach detection
- Integration with PaperTradingAdapter
```

**Integration Points:**
- `backtest/profiles.py` RiskProfile → Risk limits
- `execution/paper_adapter.py` → Pre-order risk checks
- `monitoring/paper_monitor.py` → Risk display
- `strategy/lifecycle.py` → Auto-pause on breach

**Tests Required:**
- Position size limit enforcement
- Portfolio risk calculation
- Drawdown tracking accuracy
- Breach detection and alerts
- Integration with adapter (order rejection)

---

### Task 2: Paper Trading Metrics Tracker (Est: 2-3 hours)
**Priority:** Critical  
**Dependencies:** Sprint 1 Task 2 (PaperTradingAdapter)

**Implementation:**
```python
# File: strategy/metrics_tracker.py

Class: PaperMetricsTracker
- Track strategy performance metrics over time
- Calculate validation criteria (Sharpe, win rate, etc.)
- Store time-series data (daily snapshots)
- Generate validation reports

Metrics Tracked:
- Days running (calendar days in PAPER state)
- Total trades executed
- Win rate (winning trades / total trades)
- Sharpe ratio (rolling calculation)
- Maximum drawdown (peak-to-trough)
- Profit factor (gross profit / gross loss)
- Consecutive losses (current streak)
- Average win/loss size
```

**Storage:** 
- SQLite: `strategy_metrics` table
- Daily snapshots: `strategy_snapshots` table

**Integration Points:**
- `execution/paper_adapter.py` → Trade execution data
- `strategy/lifecycle.py` → Metrics for validation
- `monitoring/paper_monitor.py` → Display metrics

**Tests Required:**
- Metric calculation accuracy
- Time-series data integrity
- Sharpe ratio calculation (rolling window)
- Drawdown calculation
- Win rate and profit factor

---

### Task 3: Validation Criteria Enforcer (Est: 2 hours)
**Priority:** Critical  
**Dependencies:** Task 2 (MetricsTracker)

**Implementation:**
```python
# File: strategy/validation.py

Class: ValidationEnforcer
- Check if strategy meets validation criteria
- Prevent premature promotion to VALIDATED state
- Generate validation reports with pass/fail reasons
- Track validation progress over time

Validation Checks:
1. Minimum trading days (30+)
2. Minimum trades (20+)
3. Sharpe ratio (>1.0)
4. Maximum drawdown (<10%)
5. Win rate (>50%)
6. Profit factor (>1.5)
7. Consecutive losses (<5)

Report Format:
- Pass/Fail status per criterion
- Current value vs. required value
- Days until minimum trading period
- Recommendation (ready/not ready)
```

**Integration Points:**
- `strategy/lifecycle.py` → PAPER → VALIDATED transition
- `strategy/metrics_tracker.py` → Current metrics
- `monitoring/paper_monitor.py` → Display validation status

**Tests Required:**
- Each validation criterion individually
- Combined validation logic
- Edge cases (exactly at threshold)
- Report generation

---

### Task 4: Strategy Promotion Workflow (Est: 2-3 hours)
**Priority:** High  
**Dependencies:** Task 3 (ValidationEnforcer)

**Implementation:**
```python
# File: strategy/promotion.py

Class: PromotionWorkflow
- Implement multi-gate approval process
- Enforce validation checklist
- Require manual approval at each gate
- Document approval trail

Workflow States:
1. PAPER: Running on paper account
2. VALIDATION_PENDING: Criteria met, awaiting review
3. VALIDATED: Automated validation passed
4. APPROVAL_PENDING: Awaiting manual approval
5. LIVE_APPROVED: Approved for live trading
6. LIVE_ACTIVE: Running on live account

Manual Gates:
- Gate 1: PAPER → VALIDATED (automated checks + manual review)
- Gate 2: VALIDATED → LIVE_APPROVED (manual approval + checklist)
- Gate 3: LIVE_APPROVED → LIVE_ACTIVE (final confirmation)

Checklist (Gate 2):
- [ ] Strategy code reviewed
- [ ] Risk parameters verified
- [ ] Position sizing confirmed
- [ ] Emergency procedures tested
- [ ] Monitoring alerts configured
- [ ] Historical performance reviewed
- [ ] Market conditions assessed
```

**Storage:**
- SQLite: `approval_history` table
- Fields: strategy_name, gate, approved_by, approved_at, notes

**Integration Points:**
- `strategy/lifecycle.py` → State transitions
- `strategy/validation.py` → Automated checks
- UI (future): Manual approval interface

**Tests Required:**
- Workflow state transitions
- Checklist enforcement
- Approval trail persistence
- Rollback capability

---

### Task 5: Validation Dashboard Enhancement (Est: 2 hours)
**Priority:** Medium  
**Dependencies:** Task 2, Task 3, Task 4

**Implementation:**
```python
# File: monitoring/validation_monitor.py

Extend PaperMonitor with:

5. Validation Status Panel
   - Validation criteria progress bars
   - Pass/Fail indicators per criterion
   - Days until minimum trading period
   - Promotion workflow state
   
6. Performance Charts (Terminal-based)
   - Equity curve (simplified sparkline)
   - Drawdown chart
   - Win/loss distribution
   
7. Alerts Panel
   - Risk limit breaches
   - Validation milestones reached
   - Manual actions required
```

**Display Updates:**
- Real-time validation progress
- Color-coded status (green=pass, yellow=pending, red=fail)
- Countdown to validation eligibility
- Next action required

**Integration Points:**
- `monitoring/paper_monitor.py` → Additional panels
- `strategy/metrics_tracker.py` → Metrics data
- `strategy/validation.py` → Validation status
- `execution/risk_monitor.py` → Risk alerts

**Tests Required:**
- Display accuracy
- Real-time updates
- Alert visibility
- Edge cases (no data, errors)

---

## 🎯 Success Metrics

### Technical Metrics
```yaml
Prime Directive:
  - Baseline tests: 138/138 passing (100%)
  - Integration tests: >90% coverage
  - No regression in existing functionality

Performance:
  - Strategy deployment: <60 seconds (backtest → paper)
  - Order execution: <200ms (signal → TWS order)
  - Data latency: <100ms (TWS → strategy)

Reliability:
  - Connection recovery: <10 seconds
  - State persistence: 100% (no data loss)
  - Error handling: All edge cases covered
```

### Functional Metrics
```yaml
Paper Trading:
  - MA Cross strategy running: ✅
  - Real-time position tracking: ✅
  - Paper P&L calculation: ✅
  - Risk limit enforcement: ✅
  - Start/stop controls: ✅

Strategy Lifecycle:
  - State transitions working: ✅
  - Gating logic enforced: ✅
  - Persistence working: ✅
```

### Business Metrics
```yaml
Deployment:
  - Backtest → Paper: Automated
  - Manual steps: <5 minutes
  - Rollback capability: <2 minutes

Risk Management:
  - Position limits: Enforced
  - Drawdown limits: Enforced
  - Emergency stop: <5 seconds
```

---

## 🛡️ Risk Management

### Paper Trading Validation Criteria
**Minimum Requirements (30+ days):**
```python
{
    "min_days": 30,
    "min_trades": 20,
    "sharpe_ratio": 1.0,
    "max_drawdown": 0.10,  # 10%
    "win_rate": 0.50,      # 50%
    "profit_factor": 1.5,
    "consecutive_losses": 5  # Max allowed
}
```

### Live Trading Gate
**Checklist Before Live Approval:**
- [ ] 30+ days paper trading completed
- [ ] All validation metrics met
- [ ] Strategy code reviewed
- [ ] Risk parameters verified
- [ ] Emergency procedures tested
- [ ] Position sizing confirmed
- [ ] Manual approval documented
- [ ] Monitoring alerts configured

### Emergency Procedures
```python
EMERGENCY_STOP:
  - Trigger: Manual or automated (DD >15%)
  - Action: Close all positions immediately
  - Notification: Email + SMS + Dashboard alert
  - Cooldown: 24 hours before restart allowed

POSITION_LIMIT_BREACH:
  - Trigger: Position exceeds risk limit
  - Action: Reject new orders, alert operator
  - Resolution: Manual review required

CONNECTION_LOSS:
  - Trigger: TWS connection lost >30 seconds
  - Action: Pause strategies, attempt reconnect
  - Resolution: Auto-resume on reconnect or manual review
```

---

## 📊 Progress Tracking

### Sprint 1 Progress (Update Daily)
**Day 1:**
- [x] Task 1: Strategy lifecycle state machine (29 tests, f701d37)
- [x] Task 2: Paper trading adapter (32 tests, a3a3ff3)
- [x] Task 3: Real-time data pipeline (17 tests, cb1274d)

**Day 2:**
- [ ] Task 2: Paper trading adapter (completed)
- [ ] Task 3: Real-time data pipeline

**Day 3:**
- [x] Task 4: Paper trading monitor (28 tests, d9f3c86)
- [ ] Task 5: Integration testing (started)

**Day 4:**
- [ ] Task 5: Integration testing (completed)
- [ ] Sprint 1 retrospective
- [ ] Deploy to paper account

### Blockers & Issues
**None yet** - Update as they arise

### Decisions & Rationale
**November 22, 2025:**
- Use SQLite for Sprint 1 (rapid development)
- Terminal-based monitor (defer web dashboard)
- Focus on MA Cross strategy first (simplest template)

---

## 🔄 Sprint Ceremonies

### Daily Stand-up (Virtual)
**Format:**
1. What was completed yesterday?
2. What will be completed today?
3. Any blockers?

### Sprint Review (End of Sprint 1)
**Agenda:**
1. Demo: MA Cross running on paper account
2. Metrics review: Tests passing, coverage, performance
3. Lessons learned
4. Sprint 2 planning

### Retrospective
**Questions:**
1. What went well?
2. What could be improved?
3. Action items for next sprint

---

## 📋 Sprint 3 Detailed Backlog

### Task 1: Strategy Configuration Hot-Reload (Est: 3-4 hours)
**Priority:** Critical  
**Dependencies:** Sprint 1 (lifecycle), Sprint 2 (metrics tracker)

**Implementation:**
```python
# File: strategies/config/config_watcher.py

Class: ConfigWatcher
- Monitor strategy config files for changes
- Detect file modifications (polling or file system events)
- Validate new configuration before applying
- Notify strategy instances of config updates
- Rollback on validation failure

# File: strategies/config/config_loader.py

Class: ConfigLoader
- Load strategy parameters from YAML/JSON files
- Validate parameter types and ranges
- Merge with defaults
- Version tracking for config changes

# Integration with existing Strategy base class:
Strategy.update_parameters(new_params)
```

**Configuration Format:**
```yaml
# config/strategies/ma_cross_conservative.yaml
strategy:
  name: MA_Cross_Conservative
  type: MovingAverageCross
  parameters:
    fast_period: 10
    slow_period: 20
    symbols:
      - AAPL
      - MSFT
    risk_profile: Conservative
  allocation: 0.33  # 33% of capital
  
# Config versioning
version: 1.2
last_updated: 2025-11-24T10:30:00
```

**Hot-Reload Features:**
- File system watcher (detect changes within 1 second)
- Parameter validation (type checking, range checking)
- Graceful parameter update (mid-session, no restart)
- Rollback on failure (revert to previous config)
- Config change audit trail (who changed what when)

**Tests Required:**
- Config file loading and validation
- Parameter update without restart
- Invalid config rejection
- Rollback on error
- Multiple strategy hot-reload
- File watcher responsiveness
- Integration with strategy lifecycle

**Estimated Tests:** 25-30

---

### Task 2: Multi-Strategy Orchestration (Est: 4-5 hours)
**Priority:** Critical  
**Dependencies:** Task 1, Sprint 1 (paper adapter)

**Implementation:**
```python
# File: strategies/strategy_orchestrator.py

Class: StrategyOrchestrator
- Manage multiple strategies simultaneously
- Coordinate market data distribution
- Aggregate signals from all strategies
- Enforce portfolio-level constraints
- Handle strategy lifecycle events
- Capital allocation management

Features:
- Register/unregister strategies dynamically
- Distribute market data to active strategies
- Collect and prioritize signals
- Detect signal conflicts (same symbol, opposite directions)
- Apply portfolio-level risk limits
- Track per-strategy attribution
```

**Orchestration Logic:**
```python
class StrategyOrchestrator:
    def __init__(self, risk_manager, paper_adapter):
        self.strategies = {}  # name -> Strategy instance
        self.allocations = {}  # name -> allocation %
        self.active = {}  # name -> active status
        
    def register_strategy(self, strategy, allocation):
        """Add strategy with capital allocation"""
        
    def on_market_data(self, market_data):
        """Distribute data to all active strategies"""
        for strategy in self.active_strategies:
            signals = strategy.generate_signals(market_data)
            self.process_signals(strategy.name, signals)
            
    def process_signals(self, strategy_name, signals):
        """Handle signals with attribution and risk checks"""
        for signal in signals:
            # Check portfolio risk limits
            # Check strategy allocation remaining
            # Execute if approved
            # Track attribution
            
    def rebalance_allocations(self, new_allocations):
        """Update capital allocations without restart"""
```

**Signal Conflict Resolution:**
```python
Conflict Resolution Rules:
1. Same symbol, same direction → Aggregate (sum quantities)
2. Same symbol, opposite directions → Higher priority wins
3. Portfolio heat exceeded → Reject all signals
4. Strategy allocation exhausted → Reject strategy signals
```

**Tests Required:**
- Multi-strategy registration
- Market data distribution
- Signal aggregation
- Conflict resolution
- Portfolio constraint enforcement
- Dynamic allocation rebalancing
- Strategy add/remove without restart
- Attribution tracking

**Estimated Tests:** 30-35

---

### Task 3: Strategy Comparison Dashboard (Est: 3-4 hours)
**Priority:** High  
**Dependencies:** Task 2, Sprint 2 (metrics tracker, validation monitor)

**Implementation:**
```python
# File: monitoring/strategy_comparator.py

Class: StrategyComparator
- Display multiple strategies side-by-side
- Compare performance metrics
- Visualize relative performance
- Highlight best/worst performers
- Show allocation and utilization

# File: monitoring/comparison_dashboard.py

Class: ComparisonDashboard
- Terminal-based comparison view
- Real-time updates
- Sortable by any metric
- Color-coded performance
- Sparklines for trend comparison
```

**Dashboard Layout:**
```
╔══════════════════════════════════════════════════════════════════╗
║              Strategy Comparison Dashboard                       ║
║                     Live: 3 Active Strategies                    ║
╠══════════════════════════════════════════════════════════════════╣
║ Strategy            Alloc  Status  P&L      Sharpe  DD     Trades║
║──────────────────────────────────────────────────────────────────║
║ MA_Cross_Cons       33%    PAPER   +$2.5k   1.4    -3%    45    ║
║   Equity: ▁▂▃▄▅▆▇█  Capital: $33k  Win%: 62%  PF: 2.1           ║
║──────────────────────────────────────────────────────────────────║
║ MeanRev_Mod         33%    PAPER   +$1.8k   1.2    -5%    38    ║
║   Equity: ▁▃▅▄▅▇▆█  Capital: $33k  Win%: 58%  PF: 1.8           ║
║──────────────────────────────────────────────────────────────────║
║ Momentum_Agg        34%    PAPER   +$3.2k   1.6    -7%    52    ║
║   Equity: ▁▂▄▆█▇▆▇  Capital: $34k  Win%: 54%  PF: 2.4           ║
╠══════════════════════════════════════════════════════════════════╣
║ Portfolio Total              P&L: +$7.5k  Sharpe: 1.5  DD: -4%  ║
║   Equity: ▁▂▃▄▅▆▇█  Value: $107.5k  Win%: 58%  Trades: 135     ║
╠══════════════════════════════════════════════════════────════════╣
║ Performance Ranking:                                             ║
║   1. 🥇 Momentum_Agg   (+3.2%)  Best Sharpe: 1.6               ║
║   2. 🥈 MA_Cross_Cons  (+2.5%)  Best Win Rate: 62%             ║
║   3. 🥉 MeanRev_Mod    (+1.8%)  Lowest DD: -3%                 ║
╠══════════════════════════════════════════════════════════════════╣
║ Correlation Matrix:                                              ║
║              MA_Cross  MeanRev  Momentum                         ║
║   MA_Cross      1.00     0.45     0.62                          ║
║   MeanRev       0.45     1.00     0.38                          ║
║   Momentum      0.62     0.38     1.00                          ║
╠══════════════════════════════════════════════════════════════════╣
║ [S]ort  [F]ilter  [D]etails  [R]efresh  [Q]uit                  ║
╚══════════════════════════════════════════════════════════════════╝
```

**Comparison Features:**
- Side-by-side metrics display
- Sortable by any column
- Color-coded performance (green/yellow/red)
- Sparklines for visual comparison
- Correlation matrix
- Performance ranking
- Drill-down to strategy details
- Export comparison report

**Tests Required:**
- Multi-strategy display
- Metric calculation and comparison
- Sorting functionality
- Color coding logic
- Sparkline generation
- Correlation calculation
- Real-time updates
- Layout rendering

**Estimated Tests:** 25-30

---

### Task 4: Performance Attribution System (Est: 3-4 hours)
**Priority:** High  
**Dependencies:** Task 2, Sprint 2 (metrics tracker)

**Implementation:**
```python
# File: monitoring/attribution.py

Class: PerformanceAttribution
- Track P&L per strategy
- Track trades per strategy
- Track risk contribution per strategy
- Calculate strategy-level metrics
- Generate attribution reports

Attribution Metrics:
- Absolute P&L contribution
- Risk-adjusted P&L (Sharpe contribution)
- Trade count contribution
- Win rate by strategy
- Drawdown contribution
- Capital utilization by strategy
```

**Attribution Tracking:**
```python
class AttributionTracker:
    def record_trade(self, strategy_name, trade):
        """Record trade with strategy attribution"""
        
    def record_pnl(self, strategy_name, pnl, timestamp):
        """Record P&L with timestamp"""
        
    def get_strategy_metrics(self, strategy_name):
        """Get all metrics for specific strategy"""
        
    def get_portfolio_breakdown(self):
        """Get attribution breakdown across all strategies"""
        
    def generate_attribution_report(self, start_date, end_date):
        """Detailed attribution report for period"""
```

**Database Schema:**
```sql
CREATE TABLE strategy_attribution (
    id INTEGER PRIMARY KEY,
    strategy_name TEXT,
    timestamp DATETIME,
    trade_id INTEGER,
    pnl REAL,
    symbol TEXT,
    quantity INTEGER,
    FOREIGN KEY (trade_id) REFERENCES strategy_trades(id)
);

CREATE TABLE strategy_daily_attribution (
    id INTEGER PRIMARY KEY,
    strategy_name TEXT,
    date DATE,
    daily_pnl REAL,
    cumulative_pnl REAL,
    trade_count INTEGER,
    win_count INTEGER,
    sharpe_contribution REAL,
    UNIQUE(strategy_name, date)
);
```

**Attribution Report:**
```
╔══════════════════════════════════════════════════════════════╗
║         Performance Attribution Report                       ║
║         Period: Nov 1-24, 2025 (24 days)                    ║
╠══════════════════════════════════════════════════════════════╣
║ Strategy           P&L      % Total  Sharpe  Trades  Win%  ║
║──────────────────────────────────────────────────────────────║
║ Momentum_Agg      $3,200    42.7%    1.6     52      54%   ║
║ MA_Cross_Cons     $2,500    33.3%    1.4     45      62%   ║
║ MeanRev_Mod       $1,800    24.0%    1.2     38      58%   ║
║──────────────────────────────────────────────────────────────║
║ Portfolio Total   $7,500    100.0%   1.5     135     58%   ║
╠══════════════════════════════════════════════════════════════╣
║ Risk-Adjusted Performance:                                  ║
║   Sharpe-weighted: Momentum_Agg contributes 45% of value   ║
║   Best risk/return: MA_Cross_Cons (lowest DD, good return)║
╠══════════════════════════════════════════════════════════════╣
║ Recommendations:                                             ║
║   • Consider increasing Momentum_Agg allocation (strong)    ║
║   • MeanRev_Mod underperforming - review parameters        ║
║   • MA_Cross_Cons: Excellent risk control, keep current    ║
╚══════════════════════════════════════════════════════════════╝
```

**Tests Required:**
- Trade attribution recording
- P&L calculation per strategy
- Daily attribution aggregation
- Portfolio breakdown calculation
- Report generation
- Time period filtering
- Database persistence
- Integration with orchestrator

**Estimated Tests:** 20-25

---

### Task 5: Strategy Health Monitoring (Est: 2-3 hours)
**Priority:** Medium  
**Dependencies:** Task 2, Task 4, Sprint 2 (risk monitor, validation)

**Implementation:**
```python
# File: monitoring/strategy_health.py

Class: StrategyHealthMonitor
- Calculate per-strategy health scores
- Monitor strategy vitals in real-time
- Detect strategy degradation
- Generate health alerts
- Recommend actions (pause, parameter adjustment)

Health Score Components:
1. Recent performance (30% weight)
   - Last 10 trades P&L trend
   - Recent win rate
2. Risk metrics (30% weight)
   - Current drawdown
   - Volatility of returns
3. Execution quality (20% weight)
   - Fill quality
   - Slippage vs expected
4. Consistency (20% weight)
   - Consecutive losses
   - Performance stability
```

**Health Monitoring:**
```python
class StrategyHealthMonitor:
    def calculate_health_score(self, strategy_name):
        """Calculate 0-100 health score"""
        
    def check_vital_signs(self, strategy_name):
        """Check critical health indicators"""
        
    def detect_degradation(self, strategy_name):
        """Detect performance degradation"""
        
    def generate_health_alert(self, strategy_name, issue):
        """Create health alert with severity"""
        
    def recommend_action(self, strategy_name, health_score):
        """Recommend action based on health"""
```

**Health Alerts:**
```
Health Score Ranges:
90-100: Excellent (✅ green) - No action needed
70-89:  Good (✅ green) - Monitor
50-69:  Fair (⚠ yellow) - Review parameters
30-49:  Poor (⚠ orange) - Consider pausing
0-29:   Critical (❌ red) - Pause immediately

Alert Types:
- DEGRADATION: Performance declining over time
- HIGH_DD: Drawdown exceeding threshold
- CONSECUTIVE_LOSSES: Too many losses in a row
- LOW_WIN_RATE: Win rate below acceptable
- EXECUTION_ISSUES: Slippage or fill problems
```

**Integration with Dashboard:**
```
╔══════════════════════════════════════════════════════╗
║           Strategy Health Dashboard                  ║
╠══════════════════════════════════════════════════════╣
║ Strategy: MA_Cross_Conservative                      ║
║ Health Score: 87/100 ✅ GOOD                         ║
║──────────────────────────────────────────────────────║
║ Recent Performance:    ████████░░ 85/100            ║
║ Risk Metrics:          █████████░ 90/100            ║
║ Execution Quality:     ████████░░ 88/100            ║
║ Consistency:           ███████░░░ 82/100            ║
║──────────────────────────────────────────────────────║
║ Vital Signs:                                         ║
║   ✓ Last 10 trades: 7 wins, 3 losses               ║
║   ✓ Current DD: -3.2% (within limit)               ║
║   ✓ Win rate: 62% (above target)                   ║
║   ⚠ Consecutive wins: 0 (just had loss)            ║
║──────────────────────────────────────────────────────║
║ Recommendation: CONTINUE - Strategy healthy         ║
╚══════════════════════════════════════════════════════╝
```

**Tests Required:**
- Health score calculation
- Component scoring (performance, risk, execution, consistency)
- Degradation detection
- Alert generation
- Action recommendations
- Integration with orchestrator
- Real-time updates

**Estimated Tests:** 20-25

---

### Sprint 3 Testing Strategy

**Unit Tests (50-60 tests):**
- Config loading and validation
- Parameter hot-reload
- Signal aggregation and conflict resolution
- Attribution calculation
- Health score calculation

**Integration Tests (40-50 tests):**
- Multi-strategy orchestration
- End-to-end hot-reload
- Dashboard rendering with real data
- Attribution tracking across strategies
- Health monitoring integration

**System Tests (20-30 tests):**
- 3+ strategies running concurrently
- Dynamic allocation rebalancing
- Config changes without restart
- Complete attribution chain
- Dashboard with all features

**Total Sprint 3 Target:** 120-150 tests

---

## 📚 Reference Documents

### Existing Documentation
- `PROJECT_PLAN.md` - 7-week master plan
- `PRIME_DIRECTIVE.md` - Development guidelines (updated with Sprint 2 lessons)
- `SPRINT2_COMPLETE.md` - Sprint 2 completion summary
- `WEEK4_DOCUMENTATION.md` - Backtest system docs
- `README.md` - Project overview

### New Documentation (Create During Sprint)
- `docs/PAPER_TRADING.md` - Paper trading guide
- `docs/STRATEGY_LIFECYCLE.md` - Lifecycle documentation
- `docs/DEPLOYMENT.md` - Deployment procedures

---

## 🎓 Lessons from Previous Sprints

### Week 4 Day 4 (Module Cleanup)
**What went well:**
- Systematic verification at each step
- Clear commit messages with test counts
- Git history preservation
- Prime Directive compliance

**Applied to this sprint:**
- Test-first approach for all new features
- Incremental integration (task by task)
- Clear documentation of decisions
- Verify → Change → Verify pattern

---

## ✅ Definition of Done

### Task Level
- [ ] Implementation complete and tested
- [ ] Unit tests written and passing
- [ ] Integration tests passing
- [ ] Code reviewed (self-review minimum)
- [ ] Documentation updated
- [ ] No TODOs or FIXMEs left

### Sprint Level
- [ ] All sprint backlog items complete
- [ ] Baseline tests: 138/138 passing
- [ ] Integration tests: >90% coverage
- [ ] Success criteria met
- [ ] Demo prepared
- [ ] Documentation complete
- [ ] Sprint retrospective complete
- [ ] Code committed with clear messages

### Story Level (Paper Trading Integration)
- [ ] All 3 sprints complete
- [ ] Strategy running on paper account
- [ ] Validation framework working
- [ ] Multi-strategy support verified
- [ ] Production-ready (Week 7 standards)

---

## 🚀 Getting Started

### Pre-Sprint Setup
```bash
# Verify environment
cd c:\Users\Evan\Documents\Projects\ibkr\tws_robot
.\Scripts\Activate.ps1

# Verify baseline
python -m pytest test_backtest_engine.py test_backtest_data.py test_profiles.py test_profile_comparison.py test_strategy_templates.py --tb=no -q

# Expected: 138 passed

# Create new branch for sprint work
git checkout -b feature/paper-trading-integration

# Ready to start!
```

### First Task
Start with Task 1: Strategy Lifecycle State Machine
- Create `strategy/lifecycle.py`
- Implement state enum and transitions
- Add persistence layer (SQLite)
- Write unit tests
- Verify baseline tests still pass

---

**Let's build a world-class trading platform! 🚀**
