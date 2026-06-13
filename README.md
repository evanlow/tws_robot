# TWS Robot - Autonomous Trading System

[![CI](https://github.com/evanlow/tws_robot/actions/workflows/ci.yml/badge.svg)](https://github.com/evanlow/tws_robot/actions/workflows/ci.yml)

**Autonomous stock trading with a safety-first architecture — scan, rank, plan, and execute trades automatically.**

TWS Robot is an **autonomous trading system** that scans the S&P 500 universe, ranks candidates using technical analysis, builds trade plans, and executes them on your Interactive Brokers paper account — all with multiple layers of safety gates. Start in recommend-only mode to review what the system would trade, then graduate to paper execution when you're confident in the pipeline.

---

## ⚠️ Risk Warning

TWS Robot is experimental open-source software for use with Interactive Brokers TWS / IB Gateway. It is provided as-is, without warranties. Trading involves substantial risk, including loss of capital. Use paper trading first. You are solely responsible for all trading decisions, orders, and losses. See [`DISCLAIMER.md`](DISCLAIMER.md).

---

## 🤖 Autonomous Trading — The Core Feature

TWS Robot's primary capability is its **autonomous trading pipeline** — a fully automated system that finds, evaluates, and executes trades without manual intervention.

### How It Works

```
┌──────────┬──────────┬──────────┬─────────────┬────────────────┐
│  Scanner  │  Ranker  │ Planner  │   Engine    │    Adapter     │
│           │          │          │  (Gating)   │  (Execution)   │
│  S&P 500  │ Hard     │ BUY_     │ Cash check  │ Paper adapter  │
│  universe │ filters  │ SHARES   │ Risk check  │ Live adapter   │
│  +        │ Scoring  │   or     │ Daily limit │   (future)     │
│  Signal   │ Ranking  │ SHORT_   │ Emergency   │                │
│  provider │          │ PUT      │   stop gate │                │
└──────────┴──────────┴──────────┴─────────────┴────────────────┘
```

| Stage | What It Does |
|-------|-------------|
| **Scanner** | Scans the S&P 500 universe using the `TechnicalAnalysisSignalProvider` to identify candidates with actionable signals. |
| **Ranker** | Applies hard filters (signal strength, volume, trend, earnings proximity, concentration limits), then scores and sorts survivors. |
| **Planner** | Builds a `TradePlan` — either `BUY_SHARES` (limit order) or `SELL_CASH_SECURED_PUT` (if option data is available) — with exact quantities, limit price, target, and stop. |
| **Engine** | Validates against safety gates: emergency stop, daily trade limit, deployable cash, equity checks, and the optional RiskManager. |
| **Adapter** | In Paper Execute mode, sends the order to your IBKR paper account. In Recommend-Only mode, returns the plan without executing. |

### Operating Modes

| Mode | Orders Placed? | Description |
|------|---------------|-------------|
| **Recommend Only** (default) | ❌ Never | Runs the full pipeline and returns a trade plan for your review. Safe to run anytime. |
| **Paper Execute** | ✅ Paper only | Executes trades on your IBKR paper account. Requires active paper connection. |
| **Assisted Live** | ✅ Live (opt-in) | Live execution requires explicit config flag + caller confirmation. Not exposed via HTTP. |

### Safety Architecture

Multiple independent layers must all pass before any order is placed:

1. **Emergency Stop** — A single `EMERGENCY_STOP` file halts the system instantly
2. **Runner Gates** — Connection verified, paper adapter ready, trade limits enforced
3. **Engine Validation** — Deployable cash sufficient, position sizing within limits, risk manager approval
4. **Mode Gate** — Recommend-Only never executes; Paper requires paper connection; Live requires explicit opt-in + confirmation
5. **Audit Trail** — Every decision (including rejections) written to append-only JSONL log

### Autonomous Dashboard

The web dashboard provides a dedicated **Autonomous Trading** page where you can:
- **Scan Universe** — Run a full recommend-only pass and see ranked candidates with rejection reasons
- **Propose Trade** — Run the full pipeline and review the trade plan before execution
- **Execute Paper Trade** — Submit the proposed trade to your paper account
- **Paper Robot Runner** — Continuous autonomous trading loop (configurable interval)
- **Exit Manager** — Monitors open positions for take-profit, stop-loss, and max holding duration

---

## 🎯 Additional Features

### Web Dashboard
- 🌐 **Point-and-click interface** for managing everything from your browser
- 📊 **Real-time positions and P&L** tracking
- 🧪 **Backtesting** — Test strategies on historical data before risking money
- 🛡️ **Risk monitoring** with emergency stop button always visible
- 📈 **Performance tracking** — Sharpe ratio, win rate, drawdown metrics

### Strategy Backtesting
- 📊 Moving Average, Mean Reversion, and Momentum strategy templates
- ⚡ Paper trading validation with real-time data
- 🔧 Risk profiles: Conservative, Balanced, Aggressive

### Portfolio Analysis
- 🏢 Company name display (supports international stocks: HK, JP, UK, AU, etc.)
- 📰 AI Market Outlook with session recap and actionable recommendations
- 🎯 AI Portfolio Intelligence — auto-detect strategies from positions (covered calls, spreads, iron condors)
- 🧠 Account Intelligence modules — health scoring, cash management, risk analysis, performance benchmarking

### For Developers
- 🏗️ Event-driven architecture with modular components
- 🧬 Extensible framework — build custom signal providers and strategies
- 📊 Comprehensive backtesting with realistic market simulation
- 🔧 Full control over risk profiles, position sizing, and execution logic

---

## ⚡ Quick Start (5 Minutes)

> **Prerequisites:** For **paper or live trading**, you need [Interactive Brokers TWS](https://www.interactivebrokers.com/en/trading/tws.php) (or IB Gateway) running with API access enabled. Backtesting works without TWS. See the **[TWS Connection Guide](docs/TWS_CONNECTION_GUIDE.md)** for complete setup instructions.

### 1. Install TWS Robot

```bash
# Clone and set up
git clone https://github.com/evanlow/tws_robot.git
cd tws_robot

# Create virtual environment
python -m venv venv

# Activate it (choose your platform)
.\venv\Scripts\Activate.ps1  # Windows PowerShell
source venv/bin/activate        # Mac/Linux

# Install dependencies
pip install -r requirements.txt
```

### 2. Launch the Web Dashboard (Recommended)

The easiest way to use TWS Robot is through the **web dashboard** — no terminal expertise needed:

```bash
# Start the web dashboard
python scripts/run_web.py

# Then open your browser to: http://127.0.0.1:5000
```

From the dashboard you can:
- 🤖 **Autonomous Trading** - Scan, propose, and execute trades automatically
- 📊 **View positions and P&L** on the Dashboard page
- 🧪 **Run backtests** from the Backtest page
- 🛡️ **Monitor risk** on the Risk page
- ⚙️ **Configure settings** on the Settings page
- 🚨 **Emergency stop** with one click from the top bar

> **🔐 Authentication:** The dashboard requires login. Default credentials are `admin` / `changeme`. See [Authentication](#-authentication) below to configure.

### 3. Or Use the Command Line

If you prefer working in a terminal:

**New to algo trading? Start here:**
```bash
# Interactive guide to choose a strategy for your stock
python scripts/strategy_selector.py
```

**Want to see if a strategy works? Try this:**
```bash
# Test Moving Average strategy on historical data
python scripts/quick_start.py
```

> 💡 **Note:** Quick start examples use **backtest strategies** (Moving Average, Mean Reversion, Momentum) for historical testing. For **live/paper trading**, see the Bollinger Bands strategy in `strategies/` folder.

**Ready to explore? Check these out:**
```bash
# Compare Conservative vs. Aggressive risk profiles
python examples/example_profile_comparison.py

# Test all three strategies (MA, Mean Reversion, Momentum)
python examples/example_strategy_templates.py
```

### 3. Understand the Workflow

```mermaid
graph LR
    A[🤖 Autonomous Scan] --> B[📊 Review Recommendations]
    B --> C{Confident?}
    C -->|No| D[🔧 Adjust Config]
    D --> A
    C -->|Yes| E[📄 Paper Execute]
    E --> F{30+ Days Good?}
    F -->|No| D
    F -->|Yes| G[💰 Assisted Live]
    
    style A fill:#e1f5ff
    style B fill:#fff3cd
    style E fill:#d4edda
    style G fill:#f8d7da
```

**Start in recommend-only mode.** Review several cycles of recommendations before enabling paper execution.

### 4. Learn More

📖 **[Read the User Guide](docs/USER_GUIDE.md)** - Everything you need to know to use TWS Robot effectively
- Understand what each strategy does and when to use it
- Learn about risk management and position sizing
- Get a realistic weekly trading routine
- Know when to stop trading a strategy

---

## 📁 Project Structure

Understanding the codebase:

```
tws_robot/
├── autonomous/            # ⭐ Autonomous trading engine (core feature)
│   ├── autonomous_engine.py  # Top-level orchestrator
│   ├── candidate_scanner.py  # S&P 500 universe scanning
│   ├── candidate_ranker.py   # Signal filtering and scoring
│   ├── trade_planner.py      # Trade plan generation (shares/puts)
│   ├── signal_provider.py    # Signal provider interface
│   ├── exit_manager.py       # Automated exit management
│   ├── autonomous_runner.py  # Paper trading runner loop
│   └── audit.py              # JSONL audit logging
├── web/                   # Web dashboard (primary user interface)
│   ├── routes/               # One Blueprint per menu section
│   ├── templates/            # Jinja2 HTML templates
│   └── static/               # CSS, JavaScript assets
├── backtest/              # Historical testing engine
│   ├── strategy_templates.py  # Pre-built strategies (MA, MeanReversion, Momentum)
│   ├── engine.py             # Backtesting engine
│   └── profiles.py           # Risk profiles (Conservative, Moderate, Aggressive)
├── strategies/            # Live trading strategies
├── risk/                  # Risk management system
│   ├── risk_manager.py       # Position sizing, drawdown control
│   └── position_sizer.py     # Calculate position sizes
├── core/                  # Infrastructure
│   ├── event_bus.py          # Event-driven architecture
│   └── ...                   # Other core components
├── execution/             # Order execution and TWS integration
├── monitoring/            # Performance tracking
├── scripts/               # Command-line utilities (run_web.py, quick_start.py, etc.)
├── examples/              # Self-contained demonstration scripts
└── docs/                  # Documentation
```

**🎯 Quick Navigation:**
- **Autonomous trading?** → `autonomous/autonomous_engine.py` or web dashboard Autonomous Trading page
- **Want to use the dashboard?** → `python scripts/run_web.py` then open http://127.0.0.1:5000
- **Want to backtest?** → `backtest/strategy_templates.py`
- **Need risk controls?** → `risk/risk_manager.py`
- **Building custom signal provider?** → `autonomous/signal_provider.py`

---

## ❓ Frequently Asked Questions

### Can I use this for live trading right now?
The autonomous trading engine supports **paper execution** out of the box — it will scan, rank, plan, and execute trades on your IBKR paper account. Live execution (`assisted_live` mode) exists but is intentionally disabled by default and not exposed via HTTP endpoints. Start with recommend-only mode, graduate to paper, and paper trade for at least 30 days before considering live.

### Which strategy should I start with?
1. **Autonomous trading?** Open the web dashboard → Autonomous Trading page → click "Scan Universe" to see what the system recommends
2. **Manual backtesting?** Run `python scripts/strategy_selector.py` for guided selection
3. **Want to compare?** Backtest all strategies: `python examples/example_strategy_templates.py`

### Do I need Interactive Brokers TWS running?
- **For backtesting:** No, works offline with historical data
- **For paper trading:** Yes, need TWS Paper Trading mode (port 7497)
- **For live trading:** Yes, need TWS with live account (port 7496)
- **Setup guide:** See the **[TWS Connection Guide](docs/TWS_CONNECTION_GUIDE.md)** for step-by-step instructions

### How much capital do I need?
- **Backtesting:** $0 (simulated)
- **Paper trading:** $0 (simulated TWS account)
- **Live trading:** Minimum $10,000 recommended for proper diversification

### Is this beginner-friendly?
**Absolutely!** TWS Robot includes a **web dashboard** that you can access in your browser — no terminal experience required.  
**Backtesting:** Yes! The web dashboard lets you run backtests with a few clicks  
**Live trading:** Intermediate+ (requires understanding of trading, risk management, TWS setup)

### What if I get errors?
1. Check you're in the project directory and venv is activated
2. Verify dependencies installed: `pip install -r requirements.txt`
3. For TWS connection issues, see [Troubleshooting](#-troubleshooting) below
4. See [Debugging Guide](docs/runbooks/debugging-strategies.md) for detailed help

---

## 🔧 Troubleshooting

### "ModuleNotFoundError: No module named 'backtest'"
```bash
# Ensure you're in the project directory
cd tws_robot

# Activate virtual environment
.\venv\Scripts\Activate.ps1  # Windows
source venv/bin/activate      # Mac/Linux

# Install dependencies
pip install -r requirements.txt
```

### "Connection refused" when running check_account.py
- Ensure TWS or IB Gateway is running
- Check TWS API settings enabled: **Edit → Global Configuration → API → Settings**
  - Enable ActiveX and Socket Clients
  - Trusted IP addresses: 127.0.0.1
- Paper trading uses port **7497**, live uses port **7496**

### "No data available" during backtest
```bash
# Download historical data first
python scripts/download_real_data.py AAPL MSFT GOOGL
```

### Tests failing
```bash
# Clear test cache and rerun
pytest --cache-clear

# Run specific test file
pytest test_backtest_engine.py -v
```

**More help:**
- [Debugging Strategies Guide](docs/runbooks/debugging-strategies.md)
- [Emergency Procedures](docs/runbooks/emergency-procedures.md)
- [Architecture Documentation](docs/architecture/overview.md)

---

## 📚 Documentation Index

**Getting Started:**
- ⭐ **[Your First 30 Minutes](docs/GETTING_STARTED_30MIN.md) - Complete beginner tutorial**
- [README](README.md) - Quick start and overview (you are here)
- [User Guide](docs/USER_GUIDE.md) - Learn strategies and workflows
- [Autonomous Trading (USER_GUIDE §11)](docs/USER_GUIDE.md#11-autonomous-trading) - Full autonomous pipeline documentation
- [Examples Guide](docs/EXAMPLES_GUIDE.md) - Working code examples
- [Quick Reference](docs/QUICK_REFERENCE.md) - Commands and configs cheat sheet

**Development:**
- [API Reference](docs/API_REFERENCE.md) - Complete developer API documentation
- [Web API Reference](docs/WEB_API_REFERENCE.md) - REST API for web dashboard
- [Contributing Guide](docs/CONTRIBUTING.md) - How to contribute
- [Technical Specs](docs/TECHNICAL_SPECS.md) - Architecture details
- [Architecture Docs](docs/architecture/overview.md) - System design
- [Adding New Strategy](docs/runbooks/adding-new-strategy.md) - Development guide
- [Prime Directive](prime_directive.md) - Development philosophy

**Operations:**
- [Deployment Guide](docs/DEPLOYMENT_GUIDE.md) - Production setup
- [Local Deployment](docs/LOCAL_DEPLOYMENT.md) - Local development setup
- [Emergency Procedures](docs/runbooks/emergency-procedures.md) - Crisis management
- [Debugging Guide](docs/runbooks/debugging-strategies.md) - Troubleshooting

---
## 📊 Performance Benchmarks

**Test Environment:** Windows 11, Python 3.12.10, 2500+ tests passing

### Strategy Backtest Performance (2022-2023)

| Strategy | Symbol | Total Return | Sharpe Ratio | Max Drawdown | Win Rate |
|----------|--------|--------------|--------------|--------------|----------|
| Moving Average | AAPL | +18.7% | 1.52 | -8.1% | 56.7% |
| Mean Reversion | KO | +12.3% | 1.38 | -6.5% | 62.1% |
| Momentum | NVDA | +31.2% | 1.71 | -12.3% | 51.3% |

**Benchmark:** S&P 500 buy-and-hold returned +15.2% over same period.

### System Performance

- **Backtest Speed:** 2 years of daily data processed in ~8 seconds
- **Data Processing:** 500+ bars/second
- **Test Suite:** All 2500+ tests complete in ~140 seconds
- **Memory Usage:** ~500MB for typical backtest
- **Order Execution:** < 100ms latency to TWS (paper/live)

### Risk Management

- **Position Sizing:** Dynamic based on volatility and account equity
- **Risk Per Trade:** 1-2% of account by default
- **Correlation Analysis:** Multi-asset portfolio risk checking
- **Emergency Stop:** Automatic portfolio halt at -5% daily loss

*Note: Past performance does not guarantee future results. All figures are from backtests on historical data.*

---
## 🎓 What You'll Learn

### Module 1: Autonomous Trading Basics
- Understand the scan → rank → plan → execute pipeline
- Run in recommend-only mode and review trade proposals
- Read the audit log to understand why candidates were selected or rejected

### Module 2: Paper Execution
- Connect to Interactive Brokers paper account
- Enable paper execute mode and run autonomous cycles
- Use the Paper Robot Runner for continuous operation
- Monitor the Exit Manager handling take-profit and stop-loss

### Module 3: Risk Management
- Set position sizes based on account size
- Configure daily trade limits and max open positions
- Use the emergency stop mechanism
- Understand the multi-layer safety architecture

### Module 4: Advanced Configuration
- Build custom signal providers
- Configure symbol whitelists/blacklists
- Tune ranker scoring parameters
- Review and adjust trade planner settings

**Full learning path in [USER_GUIDE.md](docs/USER_GUIDE.md)**

---

## 🏆 Built-In Strategies

**Primary: Autonomous Trading Pipeline** — The autonomous engine uses the `TechnicalAnalysisSignalProvider` to scan the S&P 500 and automatically identify, rank, and execute trades. This is the recommended way to trade with TWS Robot.

**Backtesting strategies** (for historical analysis only):

| Strategy | Best For | When to Use | Example Stocks |
|----------|----------|-------------|----------------|
| **Moving Average Crossover** | Trending markets | Stock has clear up/down movements | AAPL, MSFT, NVDA |
| **Mean Reversion** | Range-bound markets | Stock bounces around stable average | KO, PG, JNJ |
| **Momentum** | High-growth stocks | Stock shows strong trends | TSLA, growth stocks |

> **Note:** The backtest strategies above are for historical testing and learning. For automated trading, use the Autonomous Trading pipeline.

---

## 🛡️ Safety & Risk Management

### Built-In Protections
- ✅ **Paper trading first** - Test with fake money before risking real capital
- ✅ **Position limits** - Never risk more than configured percentage per trade
- ✅ **Circuit breakers** - Auto-shutdown on excessive losses (2% daily, 15% total)
- ✅ **Market hours checks** - Warns about after-hours trading
- ✅ **Confirmation prompts** - Extra confirmation for live trading

### Risk Profiles

Choose your comfort level:
- **Conservative** - 2-3% per trade, tight stops, retirement accounts
- **Balanced** - 5% per trade, moderate stops, active traders  
- **Aggressive** - 10% per trade, wide stops, experienced traders

---

## 🔧 Advanced Features

**Autonomous trading pipeline:**
- S&P 500 universe scanning with technical analysis signals
- Multi-factor candidate ranking with hard filters
- Automatic trade plan generation (shares or cash-secured puts)
- Paper Robot Runner for continuous autonomous execution
- Exit Manager with take-profit, stop-loss, and max holding duration
- Full audit trail of every decision in JSONL format

**Professional-grade backtesting:**
- Realistic market simulation with slippage and commissions
- Performance analytics (Sharpe, Sortino, Calmar ratios)
- Trade-by-trade analysis and visualization

**Web dashboard (built-in):**
- Autonomous Trading page with scan, propose, and execute controls
- Real-time position and P&L tracking
- Backtest execution from the browser
- Risk monitoring and emergency stop

---

## 📚 Documentation & Guides

**Start Here:** Your complete guide to TWS Robot documentation.

### 🎯 For New Users - Start Here

| Guide | When to Use | What You'll Learn |
|-------|-------------|-------------------|
| **[Web Dashboard](scripts/run_web.py)** | Right now! | Launch `python scripts/run_web.py` and open http://127.0.0.1:5000 |
| **[USER_GUIDE.md](docs/USER_GUIDE.md)** | Your first 30 minutes | Complete walkthrough: strategies, risk management, weekly routine, realistic expectations |
| **[QUICK_REFERENCE.md](docs/QUICK_REFERENCE.md)** | Daily commands | Cheat sheet: common commands, quick metrics guide, emergency procedures |
| **[Quick Start Script](scripts/quick_start.py)** | From the terminal | Run your first backtest in 5 minutes |

### 📖 Understanding What You Have

| Guide | When to Use | What You'll Learn |
|-------|-------------|-------------------|
| **[EXAMPLES_GUIDE.md](docs/EXAMPLES_GUIDE.md)** | Before running any example | What each example script does, expected output, common issues |
| **[PROJECT_PLAN.md](docs/PROJECT_PLAN.md)** | Understanding architecture | System design, component overview, development guidelines |

### 🔧 For Active Trading

| Guide | When to Use | What You'll Learn |
|-------|-------------|-------------------|
| **[Autonomous Trading (USER_GUIDE §11)](docs/USER_GUIDE.md#11-autonomous-trading)** | Using autonomous mode | Pipeline, safety gates, operating modes, dashboard controls |
| **[Web Dashboard](/)**  | Every trading session | Real-time positions, P&L, strategy status, risk monitoring |
| **[check_account.py](scripts/check_account.py)** | Terminal account check | Current account status, positions, P&L, margin health |
| **[market_status.py](scripts/market_status.py)** | Before placing trades | Is the market open? Safe to trade? |

### 🚀 For Developers

| Guide | When to Use | What You'll Learn |
|-------|-------------|-------------------|
| **[prime_directive.md](prime_directive.md)** | Before coding anything | Development standards, testing requirements, code quality rules |
| **[TECHNICAL_SPECS.md](docs/TECHNICAL_SPECS.md)** | Building features | API references, class structures, integration patterns |
| **[docs/](docs/)** | Deep dives | Architecture details, runbooks, troubleshooting guides |

### 📊 Understanding Results

| Guide | When to Use | What You'll Learn |
|-------|-------------|-------------------|
| **[Metrics in USER_GUIDE](docs/USER_GUIDE.md#understanding-your-results)** | After every backtest | What Sharpe ratio, drawdown, win rate mean |
| **[Risk Management in USER_GUIDE](docs/USER_GUIDE.md#risk-management)** | Setting up strategies | Position sizing, stop losses, circuit breakers |

### 🆘 When Things Go Wrong

| Guide | When to Use | What You'll Find |
|-------|-------------|------------------|
| **[QUICK_REFERENCE.md](docs/QUICK_REFERENCE.md#troubleshooting)** | Quick fixes | Common errors and fast solutions |
| **[Emergency Procedures](docs/QUICK_REFERENCE.md#emergency-commands)** | System acting weird | How to stop everything NOW |
| **[docs/runbooks/debugging-strategies.md](docs/runbooks/debugging-strategies.md)** | Strategy not working | Step-by-step debugging process |

### 📚 Documentation Reading Order

**If you're brand new:**
1. **This README** (you are here!) → Get the big picture
2. **[USER_GUIDE.md](docs/USER_GUIDE.md)** → Learn strategies and risk management
3. **[QUICK_REFERENCE.md](docs/QUICK_REFERENCE.md)** → Bookmark for daily use
4. **[EXAMPLES_GUIDE.md](docs/EXAMPLES_GUIDE.md)** → Before running examples

**If you want to trade today:**
1. **[Web Dashboard](scripts/run_web.py)** → Run `python scripts/run_web.py` and open http://127.0.0.1:5000
2. **Autonomous Trading page** → Click "Scan Universe" to see recommendations
3. **[USER_GUIDE §11](docs/USER_GUIDE.md#11-autonomous-trading)** → Full autonomous trading documentation
4. **[QUICK_REFERENCE.md](docs/QUICK_REFERENCE.md)** → Commands you need

**If you're a developer:**
1. **[prime_directive.md](prime_directive.md)** → MUST READ before coding
2. **[PROJECT_PLAN.md](docs/PROJECT_PLAN.md)** → Understand architecture
3. **[TECHNICAL_SPECS.md](docs/TECHNICAL_SPECS.md)** → API references
4. **[docs/](docs/)** → Deep technical docs

---

## 🚨 Critical Information

### Realistic Expectations
- ✅ Good strategy: 10-20% annual return
- ✅ Great strategy: 20-30% annual return  
- ❌ Claiming 50%+: Probably too risky or unrealistic

**Remember:** S&P 500 averages ~10% per year. Beating that consistently is success!

### The Golden Rules
1. **ALWAYS backtest first** - If it didn't work historically, it won't work now
2. **ALWAYS paper trade 30+ days** - Prove it works in real-time
3. **NEVER risk more than 1-2% per trade** - Survive being wrong 20+ times
4. **NEVER set-and-forget** - Check your system daily
5. **STOP if strategy fails** - 5+ consecutive losses or 10% drawdown = stop and reassess

---

## 🔧 Environment-Based Configuration

**Web dashboard for easy management:**
- Launch with `python scripts/run_web.py` and access at http://127.0.0.1:5000
- Manage strategies, run backtests, and monitor risk from your browser
- Connect/disconnect from TWS directly via the Settings page
- Emergency stop button always visible in the top bar

**Supports both paper and live trading:**
- Configuration via `.env` files for security
- Easy switching between environments
- Separate settings for paper/live accounts

**Market Status Integration:**
- Real-time US stock market status checking
- Automatic warnings for after-hours trading
- Safety prompts for live trading during market closures

**TWS Integration:**
- Real-time market data streaming
- Historical data collection
- Account balance and portfolio monitoring
- Order execution capabilities

---

## 🚀 Installation & Setup

### Prerequisites

1. **Interactive Brokers Account** - Paper or live trading account (only needed for paper/live trading, not for backtesting)
2. **TWS or IB Gateway** - Download from Interactive Brokers website (only needed for paper/live trading)
3. **Python 3.8+** - With pip package manager

### Step-by-Step Installation

**1. Clone the repository:**
```bash
git clone https://github.com/evanlow/tws_robot.git
cd tws_robot
```

**2. Create virtual environment:**
```bash
python -m venv venv
```

**3. Activate virtual environment:**
```bash
# Windows PowerShell
.\venv\Scripts\Activate.ps1

# macOS/Linux
source venv/bin/activate
```

**4. Install dependencies:**
```bash
pip install -r requirements.txt
```

**5. Configure your account:**
```bash
cp .env.example .env
# Edit .env with your Interactive Brokers details
```

### Interactive Brokers Setup

**Enable API Access in TWS:**
1. Open TWS or IB Gateway
2. Go to: File → Global Configuration → API → Settings
3. Enable "Enable ActiveX and Socket Clients"
4. Set Socket Port:
   - Paper trading: `7497`
   - Live trading: `7496`
5. Add `127.0.0.1` to trusted IPs if prompted

---

## 🎮 Usage Examples

### Web Dashboard (Easiest — Recommended for Most Users)

```bash
# Start the web dashboard
python scripts/run_web.py

# Open in your browser: http://127.0.0.1:5000
# Optional: specify host/port
python scripts/run_web.py --host 0.0.0.0 --port 8080 --debug
```

From the web dashboard you can manage everything visually:
- **Autonomous Trading** — Scan universe, propose trades, execute on paper, run continuous robot
- **Dashboard** — Connection status, equity, P&L at a glance
- **Backtest** — Run backtests and review results
- **Positions** — View open positions and trade history
- **Risk** — Monitor risk levels and circuit breaker status
- **Logs** — Browse application logs in real time
- **Settings** — Configure TWS connection and trading parameters

### Command-Line Backtesting

```bash
# Interactive guide for first-time users
python scripts/quick_start.py

# Find the right strategy for your stock
python scripts/strategy_selector.py

# Compare risk profiles (Conservative vs. Aggressive)
python examples/example_profile_comparison.py

# Test all three strategies on historical data
python examples/example_strategy_templates.py
```

### Paper Trading (Recommended Before Live)

```bash
# Start paper trading with default settings
python tws_client.py --env paper --timeout 30

# Show current configuration
python tws_client.py --show-config

# Skip market status check (for after-hours testing)
python tws_client.py --env paper --skip-market-check
```

### Live Trading (Use With Caution!)

```bash
# Live trading requires explicit confirmation
python tws_client.py --env live --timeout 60

# Check market status before trading
python scripts/market_status.py
```

### Command Line Options

| Option | Description |
|--------|-------------|
| `--env, -e` | Trading environment: `paper` or `live` |
| `--timeout, -t` | Set timeout in seconds (default: no timeout) |
| `--show-config` | Display current configuration and exit |
| `--skip-market-check` | Skip market status verification |
| `--no-timeout` | Run without timeout |
| `--help, -h` | Show help message |

---

## 📊 Understanding Your Results

### Key Metrics Explained

**Total Return**
- Your profit/loss percentage over the test period
- Compare to S&P 500 (~10% annually) as benchmark

**Sharpe Ratio** (Risk-adjusted return)
- `> 2.0` = Excellent  
- `> 1.0` = Good
- `> 0.5` = Fair
- `< 0.5` = Poor (too much risk)

**Max Drawdown** (Worst loss from peak)
- `< 10%` = Low risk
- `10-20%` = Moderate risk
- `> 20%` = High risk (be careful!)

**Win Rate** (Percentage of winning trades)
- `> 60%` = Great
- `> 50%` = Good (more wins than losses)
- `< 40%` = Concerning (review strategy)

---

## Project Structure

```
tws_robot/
├── autonomous/          # ⭐ Autonomous trading engine (core feature)
│   ├── autonomous_engine.py  # Top-level pipeline orchestrator
│   ├── candidate_scanner.py  # S&P 500 universe scanning
│   ├── candidate_ranker.py   # Hard filters + scoring
│   ├── trade_planner.py      # BUY_SHARES / SHORT_PUT planning
│   ├── signal_provider.py    # Signal provider interface
│   ├── exit_manager.py       # TP/SL/duration exit logic
│   ├── autonomous_runner.py  # Paper runner loop
│   └── audit.py              # JSONL decision audit log
├── web/                 # Flask web UI (primary user interface)
│   ├── app.py           #   Application entry point
│   ├── routes/          #   One Blueprint per menu section
│   ├── templates/       #   Jinja2 HTML templates
│   └── static/          #   CSS, JavaScript assets
├── backtest/            # Backtesting engine, data manager, analytics, profiles
├── config/              # Environment & broker configuration
│   ├── env_config.py    #   Loads & validates .env at runtime
│   ├── paper.py         #   Paper trading defaults (port 7497)
│   └── live.py          #   Live trading defaults (port 7496)
├── core/                # Event bus, TWS connection, order management
├── data/                # SQLite databases, data models, real-time pipeline
├── deployment_scripts/  # Startup / backup scripts
├── docs/                # All project documentation
│   ├── architecture/    #   System design overviews
│   ├── decisions/       #   Architectural decision records (ADRs)
│   ├── runbooks/        #   Operational runbooks
│   └── sprints/         #   Sprint & week-by-week progress logs
├── examples/            # Self-contained demonstration scripts
├── execution/           # Order executor, market data feed, paper adapter
├── ibapi/               # Interactive Brokers Python API (vendored)
├── monitoring/          # Paper trading monitor, validation monitor
├── reports/             # Generated backtest chart images
├── risk/                # Risk manager, position sizer, drawdown control
├── scripts/             # Command-line utilities and entry points
│   ├── run_web.py       #   Start the Flask web UI
│   ├── quick_start.py   #   Your first backtest (5 min)
│   ├── run_live.py      #   Launch paper / live trading session
│   ├── check_account.py #   Account balance, positions, P&L
│   ├── market_status.py #   Is the US market open?
│   └── ...
├── strategies/          # Live-trading strategies, configs
├── strategy/            # Strategy lifecycle, metrics, promotion, validation
├── tests/               # Full test suite (mirrors source structure)
├── .env.example         # Configuration template
├── prime_directive.md   # Development standards & safety rules
├── pytest.ini           # Test discovery & coverage config
├── requirements.txt     # Python dependencies
├── README.md            # This file
└── tws_robot_spec.md    # Full application specification
```

## Safety & Security

⚠️ **Important Security Notes**:

- **Never commit `.env` file** - Contains sensitive account information
- **Use paper trading first** - Test strategies before going live
- **Monitor live trades** - Always supervise automated trading
- **Market hours awareness** - System warns about after-hours trading

## 🔐 Authentication

The web dashboard is protected by login authentication. All routes (pages and APIs) require a valid session. CSRF protection is enabled for all state-changing requests, including cookie-authenticated API calls.

### Default Credentials

| Setting | Default |
|---------|---------|
| Username | `admin` |
| Password | _must be configured_ |

**⚠️** In normal deployments you must set `TWS_ADMIN_PASSWORD` or `TWS_ADMIN_PASSWORD_HASH`. The insecure `changeme` fallback is only allowed when `TESTING`, `DEBUG`, or `ALLOW_DEFAULT_PASSWORD=true` is enabled.

### Configuration

Set credentials in your `.env` file:

```bash
TWS_ADMIN_USERNAME=admin
TWS_ADMIN_PASSWORD=your-secure-password
```

### Disable Authentication (Local Dev Only)

For local-only development on `127.0.0.1`, you can disable authentication:

```bash
LOGIN_DISABLED=true
```

### Security Details

- **Session-based auth** using Flask-Login with secure cookies.
- **CSRF protection** via Flask-WTF on all POST/PUT/DELETE requests, including `/api/*`; the web client sends the token in an `X-CSRFToken` header for JavaScript requests.
- **API routes** return `401 JSON` responses when unauthenticated.
- **Page routes** redirect to the login page when the session is missing or expired.

## TWS Setup

1. **Start TWS or IB Gateway**
2. **Enable API connections**:
   - File → Global Configuration → API → Settings
   - Enable "Enable ActiveX and Socket Clients"
   - Set Socket Port: 7497 (paper) or 7496 (live)
3. **Add trusted IPs**: Add `127.0.0.1` if needed

## Error Codes

Common TWS error codes you might see:

- **2104**: Market data farm connection OK (informational)
- **2106**: HMDS data farm connection OK (informational)  
- **2158**: Security definition data farm connection OK (informational)
- **2108**: Unable to subscribe to market data (normal during off-hours)

## Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## License

This project is for educational purposes only. Please ensure you understand the risks of automated trading and comply with all applicable regulations.

## Disclaimer

**⚠️ Trading Risk Warning**: 
- Automated trading involves substantial risk of loss
- Past performance does not guarantee future results
- Only trade with money you can afford to lose
- Always test strategies in paper trading first
- Monitor your automated systems at all times

The authors are not responsible for any financial losses incurred through the use of this software.

## 🆘 Getting Help

### Common Questions

**"How much money can I make?"**
- Realistic: 10-30% annually with good strategies
- Anything claiming 50%+ is likely too risky
- Goal: Beat S&P 500's ~10% average consistently

**"Which strategy should I use?"**
- Start with Moving Average Crossover (simplest)
- Run `python scripts/strategy_selector.py` for personalized recommendations
- Test multiple strategies to find what works for you

**"How much money do I need?"**
- Paper trading: $0 (fake money)
- Live trading: $5,000-$10,000 minimum recommended
- Need enough to diversify and cover commissions

**"What if my strategy stops working?"**
- Normal! Markets change and strategies fail
- Stop trading if: 2 months of losses, 10% drawdown, or 5+ consecutive losses
- Re-test on recent data and adjust or switch strategies

### Support Resources

📖 **Read First:**
- [USER_GUIDE.md](docs/USER_GUIDE.md) - Complete trader's guide
- [Technical Docs](docs/) - Architecture and API reference
- [Runbooks](docs/runbooks/) - Common tasks and troubleshooting

🐛 **Found a Bug?**
1. Check existing [Issues](https://github.com/evanlow/tws_robot/issues)
2. Create new issue with:
   - What you were trying to do
   - What happened vs. what you expected
   - Error messages and logs
   - Your configuration (hide sensitive data!)

💡 **Have a Suggestion?**
We love feature requests! Open an issue with the "enhancement" label.

---

## 🎯 Your TWS Robot Journey

### Module 1: Learn & Test
- [ ] Launch the web dashboard: `python scripts/run_web.py`
- [ ] Run `python scripts/quick_start.py` for your first backtest
- [ ] Test strategies with `python examples/example_strategy_templates.py`
- [ ] Use `python scripts/strategy_selector.py` to find your strategy
- [ ] Read [USER_GUIDE.md](docs/USER_GUIDE.md) completely

### Module 2: Paper Trade
- [ ] Connect to IB paper account
- [ ] Run chosen strategy for 30 days minimum
- [ ] Track daily performance
- [ ] Verify risk controls work correctly

### Module 3: Evaluate Results
- [ ] Did you beat buy-and-hold?
- [ ] Is Sharpe ratio > 1.0?
- [ ] Is max drawdown acceptable?
- [ ] Ready to go live? Start small!

### Going Live (If Ready)
- [ ] Start with 25% of intended capital
- [ ] Use 1% position sizes initially
- [ ] Monitor daily for first month
- [ ] Scale up gradually if successful

**Remember:** Most traders fail. Go slow, test thoroughly, and never risk money you can't afford to lose.

---

**Happy Trading! 📈**