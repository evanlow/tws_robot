# Sprint Plan: Paper Trading Integration
**Date:** November 22, 2025  
**Sprint Duration:** 3 Sprints (10 days)  
**Project Phase:** Week 1-2 of 7-Week Plan  

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
- ✅ 100% test pass rate before AND after changes
- ✅ Verify baseline → Make change → Verify again
- ✅ Document test count in all commits
- ✅ No exceptions, no shortcuts

---

## 📊 Current Status (November 22, 2025)

### Completed ✅
- **Backtest Engine:** 138/138 tests passing (100%)
- **Strategy Templates:** MA Cross, Mean Reversion, Momentum
- **Risk Profiles:** Conservative, Moderate, Aggressive
- **TWS Client:** Paper/live configs with market status checks
- **Prime Directive:** Enhanced with systematic deletion protocol
- **Module Cleanup:** Single authoritative backtest/ module
- **Sprint 1 Task 1:** Strategy Lifecycle (29 tests, commit f701d37)
- **Sprint 1 Task 2:** Paper Trading Adapter (32 tests, commit a3a3ff3)

### In Progress 🔄
- **Sprint 1 Task 3:** Real-time Market Data Pipeline

### Blockers ❌
- None identified

---

## 🎯 Sprint Goals & Timeline

### Sprint 1: Paper Trading Foundation (Days 1-4)
**Goal:** Build the bridge from backtesting to paper trading

**Deliverables:**
- [x] Strategy lifecycle state machine
- [x] Paper trading adapter for TWS client
- [ ] Real-time market data pipeline
- [ ] Paper trading monitor dashboard
- [ ] Integration tests (maintain 100% pass rate)

**Success Criteria:**
- ✅ Run MA Cross strategy on paper account
- ✅ Real-time position tracking working
- ✅ Orders execute through TWS paper account
- ✅ All 138 baseline tests still passing
- ✅ New integration tests >90% coverage

### Sprint 2: Risk & Validation Framework (Days 5-7)
**Goal:** Implement paper trading validation and risk controls

**Deliverables:**
- [ ] Risk profiles integrated with live execution
- [ ] Real-time risk monitoring and enforcement
- [ ] Paper trading validation metrics tracker
- [ ] Strategy promotion workflow and checklist
- [ ] Automated validation dashboard

**Success Criteria:**
- ✅ Risk limits enforced in real-time
- ✅ Paper trading metrics tracked (Sharpe, DD, win rate)
- ✅ Promotion workflow prevents premature live deployment
- ✅ Emergency stop functionality tested
- ✅ All tests passing with risk integration

### Sprint 3: Strategy Development Pipeline (Days 8-10)
**Goal:** Enable multi-strategy concurrent execution

**Deliverables:**
- [ ] Hot-reload strategy parameters
- [ ] Strategy comparison dashboard
- [ ] Multi-strategy concurrent execution
- [ ] Performance attribution system
- [ ] Strategy health monitoring

**Success Criteria:**
- ✅ 3+ strategies running concurrently on paper
- ✅ Parameter changes without restart
- ✅ Side-by-side strategy comparison
- ✅ Attribution tracking per strategy
- ✅ All tests passing with multi-strategy support

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
- [x] Task 1: Strategy lifecycle state machine (29 tests)
- [x] Task 2: Paper trading adapter (32 tests)
- [ ] Task 3: Real-time data pipeline (in progress)

**Day 2:**
- [ ] Task 2: Paper trading adapter (completed)
- [ ] Task 3: Real-time data pipeline

**Day 3:**
- [ ] Task 4: Paper trading monitor
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

## 📚 Reference Documents

### Existing Documentation
- `PROJECT_PLAN.md` - 7-week master plan
- `PRIME_DIRECTIVE.md` - Development guidelines
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
