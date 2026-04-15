# TWS Robot Documentation

**Complete documentation for the Interactive Brokers TWS Robot trading system.**

---

## Quick Start

```bash
# Activate environment
.\venv\Scripts\Activate.ps1  # Windows
source venv/bin/activate       # Mac/Linux

# Launch the web dashboard (recommended)
python scripts/run_web.py
# Open: http://127.0.0.1:5000

# Run tests (Prime Directive: 100% pass rate)
pytest -v

# Check coverage
pytest --cov
```

---

## 📚 Documentation Index

### For New Users — Start Here

- **[Getting Started (30 min)](GETTING_STARTED_30MIN.md)** - Complete beginner tutorial ⭐
- **[User Guide](USER_GUIDE.md)** - Strategies, risk management, weekly routines
- **[Quick Reference](QUICK_REFERENCE.md)** - Commands cheat sheet and emergency procedures
- **[Examples Guide](EXAMPLES_GUIDE.md)** - What each example script does

### Architecture

Comprehensive system design documentation:

- **[System Overview](architecture/overview.md)** - High-level architecture, components, and data flow
- **[Risk Controls](architecture/risk-controls.md)** - Risk management system, position sizing, circuit breakers
- **[Event Flow](architecture/event-flow.md)** - Event bus architecture and communication patterns
- **[Strategy Lifecycle](architecture/strategy-lifecycle.md)** - Strategy state machine and lifecycle management

### Architecture Decision Records (ADRs)

Key design decisions with rationale:

- **[ADR-001: Event Bus Architecture](decisions/001-event-bus-architecture.md)** - Why event-driven design
- **[ADR-002: Paper Trading Approach](decisions/002-paper-trading-approach.md)** - Validation gate before live trading
- **[ADR-003: Risk Parameter Choices](decisions/003-risk-parameter-choices.md)** - How risk limits were selected
- **[ADR-004: State Machine Design](decisions/004-state-machine-design.md)** - Strategy lifecycle state machine

### Runbooks

Practical guides for common tasks:

- **[Adding a New Strategy](runbooks/adding-new-strategy.md)** - Complete workflow from development to live trading
- **[Debugging Strategies](runbooks/debugging-strategies.md)** - Systematic debugging procedures and tools
- **[Emergency Procedures](runbooks/emergency-procedures.md)** - Critical incident response (⚠️ READ BEFORE TRADING)

### Developer Guides

- **[API Reference](API_REFERENCE.md)** - Developer API documentation
- **[Contributing](CONTRIBUTING.md)** - How to contribute
- **[Technical Specs](TECHNICAL_SPECS.md)** - Architecture details
- **[Testing Guide](TESTING.md)** - Testing documentation, Prime Directive, coverage goals

### Operations

- **[Deployment Guide](DEPLOYMENT_GUIDE.md)** - Production setup and 30-day validation
- **[Local Deployment](LOCAL_DEPLOYMENT.md)** - Local development setup with web UI
- **[Live Trading Safety](LIVE_TRADING_SAFETY.md)** - Critical safety guide for live trading

---

## 🎯 System Components

### Core Components

| Component | Description | Coverage |
|-----------|-------------|----------|
| **Event Bus** | Central communication hub | 84% |
| **Strategy Lifecycle** | State machine for strategies | 97% |
| **Risk Monitor** | Real-time risk controls | 99% |
| **Metrics Tracker** | Performance and monitoring | 99% |
| **Order Manager** | Order execution and tracking | 95% |

### Trading Strategies

| Strategy | Description | Status |
|----------|-------------|--------|
| **Bollinger Bands** | Mean reversion strategy | ✅ Production |
| **Moving Average** | Trend following | ✅ Production |
| **Momentum** | Momentum-based trading | 🧪 Testing |

### Risk Management

- **Position Sizing:** Kelly Criterion (half-Kelly for safety)
- **Daily Loss Limit:** 2% of account value
- **Max Position Size:** 5% of account value
- **Max Drawdown:** 15% circuit breaker
- **Emergency Controls:** Automatic shutdown on violations

---

## 🚀 Getting Started

### 1. Installation

```bash
# Clone repository
git clone <repository-url>
cd tws_robot

# Create virtual environment
python -m venv venv

# Activate environment
.\venv\Scripts\Activate.ps1  # Windows PowerShell
source venv/bin/activate       # Mac/Linux

# Install dependencies
pip install -r requirements.txt
```

### 2. Launch the Web Dashboard

```bash
python scripts/run_web.py
# Open http://127.0.0.1:5000 in your browser
```

The web dashboard is the primary interface for TWS Robot. From there you can:
- Monitor connection status, equity, and P&L
- Manage and run trading strategies
- Execute backtests and review results
- Monitor risk levels and emergency stop

### 3. Configuration

```bash
# Copy the example configuration
cp .env.example .env
# Edit .env with your Interactive Brokers details
```

```env
# Paper trading settings
TRADING_ENV=paper
PAPER_HOST=127.0.0.1
PAPER_PORT=7497              # Paper trading port
PAPER_ACCOUNT=YOUR_PAPER_ID  # Your paper account ID

# Live trading settings
LIVE_HOST=127.0.0.1
LIVE_PORT=7496               # Live trading port
LIVE_ACCOUNT=YOUR_LIVE_ID    # Your live account ID
```

### 4. Run Tests

```bash
# All tests must pass (Prime Directive)
pytest -v
```

---

## 📊 Current Status

### Test Coverage

```
Current: 690 tests passing (100% pass rate)
Overall Coverage: 44%
Critical Modules: 84-99%
```

**Coverage by Module:**

| Module | Coverage | Status |
|--------|----------|--------|
| Event Bus | 84% | 🟡 Good |
| Strategy Lifecycle | 97% | 🟢 Excellent |
| Risk Monitor | 99% | 🟢 Excellent |
| Metrics Tracker | 99% | 🟢 Excellent |
| Bollinger Bands | 95% | 🟢 Excellent |
| Strategy Registry | 100% | 🟢 Excellent |

### Recent Changes

See [SPRINT4_COMPLETE.md](../SPRINT4_COMPLETE.md) for latest updates.

---

## 🛡️ Prime Directive

> **All tests must pass. Zero failures. Zero warnings.**

This is our #1 rule. Before any commit:

```bash
pytest -v
```

**Expected:** `===== 690 passed in X.XXs =====`

**Not acceptable:**
- Any failures
- Any warnings
- Skipped tests (unless explicitly marked)

See [Testing Guide](TESTING.md) for full details.

---

## 🎓 Learning Path

### New Users

1. Launch the web dashboard: `python scripts/run_web.py`
2. Read [Getting Started (30 min)](GETTING_STARTED_30MIN.md)
3. Read [User Guide](USER_GUIDE.md) for strategy details
4. Run your first backtest: `python scripts/quick_start.py`
5. Read [Adding a New Strategy](runbooks/adding-new-strategy.md)

### Developers

1. Read all Architecture docs
2. Review all ADRs
3. Understand [Event Flow](architecture/event-flow.md)
4. Study [Strategy Lifecycle](architecture/strategy-lifecycle.md)
5. Practice with [Debugging Strategies](runbooks/debugging-strategies.md)

### Production Operators

1. **MUST READ:** [Emergency Procedures](runbooks/emergency-procedures.md)
2. Review [Risk Controls](architecture/risk-controls.md)
3. Understand [Paper Trading Approach](decisions/002-paper-trading-approach.md)
4. Keep emergency shutdown script handy
5. Practice emergency procedures monthly

---

## ⚠️ Safety Checklist

Before trading live:

- [ ] All tests passing (100%)
- [ ] Backtested with historical data
- [ ] 30+ days paper trading validation
- [ ] Sharpe ratio > 1.5
- [ ] Max drawdown < 15%
- [ ] Risk controls tested
- [ ] Emergency procedures reviewed
- [ ] Monitoring alerts configured
- [ ] Emergency shutdown script ready
- [ ] TWS connection stable

**Never skip the paper trading validation gate.**

See [Paper Trading Approach ADR](decisions/002-paper-trading-approach.md).

---

## 📁 Project Structure

```
tws_robot/
├── web/                        # ⭐ Web dashboard (primary UI)
│   ├── routes/                #   One Blueprint per page
│   ├── templates/             #   Jinja2 HTML templates
│   └── static/                #   CSS, JavaScript assets
├── docs/                       # ← You are here
│   ├── README.md              # This file
│   ├── USER_GUIDE.md          # User guide
│   ├── TESTING.md             # Testing guide
│   ├── architecture/          # System design docs
│   ├── decisions/             # ADRs
│   └── runbooks/              # Operational guides
├── scripts/                   # CLI utilities (run_web.py, etc.)
├── strategies/                # Trading strategies
│   ├── base_strategy.py       # Base class
│   ├── bollinger_bands.py     # BB strategy
│   └── strategy_registry.py   # Strategy management
├── risk/                      # Risk management
│   ├── risk_monitor.py        # Real-time monitoring
│   ├── position_sizer.py      # Position sizing
│   └── drawdown_control.py    # Drawdown management
├── execution/                 # Order execution
│   ├── order_manager.py       # Order management
│   └── paper_adapter.py       # Paper trading
├── backtest/                  # Backtesting engine
│   ├── engine.py              # Backtest runner
│   ├── data_manager.py        # Data handling
│   └── performance.py         # Performance analytics
├── monitoring/                # Monitoring and metrics
│   ├── metrics_tracker.py     # Metrics collection
│   └── event_bus.py           # Event system
├── examples/                  # Example scripts
├── tests/                     # Test suite
├── requirements.txt           # Dependencies
└── pytest.ini                 # Test configuration
```

---

## 🔧 Common Tasks

### Add New Strategy

See [Adding a New Strategy](runbooks/adding-new-strategy.md) runbook.

**Quick steps:**
1. Create strategy class
2. Write unit tests
3. Backtest validation
4. Paper trading (30 days)
5. Validation & promotion
6. Live deployment

### Debug Issue

See [Debugging Strategies](runbooks/debugging-strategies.md) runbook.

**Quick debugging:**
```python
# Enable debug logging
import logging
logging.basicConfig(level=logging.DEBUG)
strategy.logger.setLevel(logging.DEBUG)

# Inspect state
from runbooks.debugging_tools import StrategyInspector
inspector = StrategyInspector(strategy)
inspector.print_full_state()
```

### Handle Emergency

See [Emergency Procedures](runbooks/emergency-procedures.md) runbook.

**Quick emergency stop (web dashboard):**
Click the 🚨 **EMERGENCY STOP** button in the top status bar of the web dashboard.

**Quick emergency stop (terminal):**
```bash
# Press Ctrl+C to stop the running application
# Or close TWS/IB Gateway to disconnect all API clients
```

---

## 📞 Support

### Internal Resources

- **Documentation:** This `docs/` directory
- **Examples:** `example_*.py` files in root
- **Tests:** `tests/` directory for working examples

### External Resources

- **Interactive Brokers TWS API:** [Official Documentation](https://interactivebrokers.github.io/tws-api/)
- **pytest:** [Documentation](https://docs.pytest.org/)
- **Python:** [Python 3.12 Documentation](https://docs.python.org/3.12/)

### Emergency

- **IB Support:** 877-442-2757
- **Emergency Stop (web):** Click 🚨 EMERGENCY STOP in the dashboard top bar
- **Emergency Stop (terminal):** Press Ctrl+C or close TWS

---

## 📈 Roadmap

**Planned:**
- Additional strategy implementations
- Enhanced monitoring dashboard
- Distributed backtesting
- Machine learning integration
- Multi-account support

---

## 📝 Contributing

### Before Committing

1. Run all tests: `pytest -v`
2. Check coverage: `pytest --cov`
3. Verify Prime Directive: 100% pass rate
4. Update documentation if needed
5. Add/update tests for new code

### Documentation Standards

- Use Markdown format
- Include code examples
- Add Mermaid diagrams for architecture
- Keep ADRs for design decisions
- Update this README's index

---

## 📜 License

[Your License Here]

---

## 🙏 Acknowledgments

- Interactive Brokers for TWS API
- Python testing community for pytest
- All contributors to this project

---

**Last Updated:** April 2026  
**Prime Directive:** ✅ Maintained

