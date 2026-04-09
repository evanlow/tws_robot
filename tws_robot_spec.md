# TWS Robot — Application Specification

## What is TWS Robot?

TWS Robot is a Python-based automated trading platform that connects to Interactive Brokers' Trader Workstation (TWS) via the official `ibapi` library. Its purpose is to let traders go from an idea to a running automated strategy through three stages: **backtesting** on historical data, **paper trading** with real-time market data and simulated money, and finally **live trading** with real capital.

The system targets a spectrum of users — from newcomers learning algorithmic trading, to active traders who want to automate execution, to quantitative developers who want to build and run custom strategies on a production-grade framework.

---

## Core Workflow

```
Historical Data → Backtest → Paper Trade → Live Trade
```

1. **Backtest** — Validate a strategy against historical price data offline (no broker connection required).
2. **Paper Trade** — Run the strategy with real-time market data against a simulated Interactive Brokers account (TWS Paper Trading, port 7497).
3. **Live Trade** — Deploy the strategy against a real Interactive Brokers account (TWS Live, port 7496).

Users are explicitly encouraged never to skip stages.

---

## Architecture

The application is built around an **event-driven, modular architecture**:

- A central **Event Bus** decouples all components. Market data, signals, trade fills, and risk alerts are all published and consumed as typed events.
- Each subsystem is an independent module (`backtest/`, `strategies/`, `risk/`, `execution/`, `monitoring/`, `core/`) with clearly defined responsibilities.
- The original single-file `core/tws_client.py` (basic portfolio monitor) is the historical starting point; the v2 architecture replaces it with the full modular platform.
- One repository is sufficient — all components run on the same host and are tightly coupled. No SPA framework is needed; the web UI uses server-rendered Jinja2 templates.

### Repository Layout

```
tws_robot/
├── backtest/              # Backtesting engine, data manager, market simulator,
│                          #   performance analytics, risk profiles
├── config/                # Environment and broker configuration
│   ├── env_config.py      #   Loads & validates .env at runtime
│   ├── paper.py           #   Paper trading defaults (port 7497)
│   └── live.py            #   Live trading defaults with extra safety guards
├── core/                  # Event bus, TWS connection, order management,
│                          #   rate limiter, contract builder
│   └── tws_client.py      #   Original single-file client (historical reference)
├── data/                  # SQLite databases, historical OHLCV data,
│                          #   data models, real-time pipeline
├── deployment_scripts/    # Windows startup / backup scripts
├── docs/                  # All project documentation
│   ├── architecture/      #   System-design decision records
│   ├── decisions/         #   Architectural decision records (ADRs)
│   ├── runbooks/          #   Operational runbooks
│   └── sprints/           #   Sprint & week-by-week progress logs
├── examples/              # Self-contained demonstration scripts
├── execution/             # Order executor, market data feed,
│                          #   paper trading adapter, runtime risk monitor
├── ibapi/                 # Interactive Brokers Python API (vendored)
├── monitoring/            # Paper trading monitor, validation monitor
├── reports/               # Generated chart images from backtests
├── risk/                  # Risk manager, position sizer, drawdown control,
│                          #   correlation analyser, emergency controls
├── scripts/               # Command-line utilities and entry points
├── strategies/            # Live-trading strategies (Bollinger Bands),
│                          #   base class, signal types, config loader
├── strategy/              # Strategy lifecycle, metrics tracker,
│                          #   promotion flow, validation
├── tests/                 # Full test suite (mirrors source structure)
├── web/                   # Flask web UI
│   ├── app.py             #   Application entry point (flask --app web.app run)
│   ├── routes/            #   One Blueprint per menu section
│   │   ├── dashboard.py   #     GET /
│   │   ├── strategies.py  #     GET/POST /strategies
│   │   ├── backtest.py    #     GET/POST /backtest
│   │   ├── positions.py   #     GET /positions
│   │   ├── risk.py        #     GET /risk
│   │   ├── logs.py        #     GET /logs  (SSE stream)
│   │   └── settings.py    #     GET/POST /settings
│   ├── templates/         #   Jinja2 HTML templates
│   │   ├── base.html      #     Shared layout shell + navbar
│   │   └── <section>/     #     Per-section templates
│   └── static/            #   CSS, JavaScript, chart assets
│       ├── css/main.css
│       └── js/main.js
├── .env.example           # Environment variable template
├── .gitignore
├── prime_directive.md     # Development standards & safety rules
├── pytest.ini             # Test discovery & coverage configuration
├── README.md              # Project overview and quick-start
├── requirements.txt       # Python dependencies
└── tws_robot_spec.md      # This file — application specification
```

### Web UI — Menu Structure

| Route | Blueprint | Backend modules |
|-------|-----------|-----------------|
| `/` | `dashboard` | `monitoring/`, `core/connection.py` — TWS status, equity, P&L, active alerts |
| `/strategies` | `strategies` | `strategies/strategy_registry.py` — list, start/stop, parameter tuning |
| `/backtest` | `backtest` | `backtest/` — run configs, equity curve, drawdown, profile comparison |
| `/positions` | `positions` | `core/order_manager.py` — open positions, order history, emergency close |
| `/risk` | `risk` | `risk/` — drawdown gauges, correlation heatmap, profile switching |
| `/logs` | `logs` | Event bus SSE stream + `prime_directive_violations.log` |
| `/settings` | `settings` | TWS host/port/client-ID, paper↔live toggle, rate limits |

---

## Built-in Trading Strategies

### Backtest-only Strategies (`backtest/strategy_templates.py`)

These strategies are available for historical testing and are not wired for live order placement.

| Strategy | Logic | Best Market Condition |
|----------|-------|-----------------------|
| **Moving Average Crossover** | Buy on golden cross (fast MA > slow MA); sell on death cross | Trending markets |
| **Mean Reversion** | Buy when price drops below lower Bollinger Band; sell above upper band | Range-bound / stable stocks |
| **Momentum** | Enter in the direction of strong recent trends | High-growth / volatile stocks |

### Live / Paper Trading Strategy (`strategies/bollinger_bands.py`)

**Bollinger Bands Mean Reversion** — the one production-ready strategy for live and paper accounts.

- **Entry long**: price crosses below the lower Bollinger Band (oversold).
- **Entry short**: price crosses above the upper Bollinger Band (overbought).
- **Exit**: price returns to the middle band (SMA).
- **Stop loss**: 2% from entry price.
- Default parameters: 20-period SMA, 2.0 standard-deviation bands.

---

## Risk Management (`risk/`)

The risk system enforces safety at multiple layers:

| Feature | Detail |
|---------|--------|
| **Position sizing** | Dynamic, based on account equity and per-trade volatility; default 1–2% of account per trade |
| **Risk profiles** | Conservative (2–3%), Balanced (5%), Aggressive (10%) — user selects at startup |
| **Drawdown control** | Automatic circuit-breaker triggers at –2% daily loss (warning) and –5% daily / –15% total (emergency stop) |
| **Correlation analysis** | Checks cross-asset correlation to prevent over-concentration |
| **Emergency stop** | Immediately halts all trading and can flatten open positions |
| **VaR (Value at Risk)** | Real-time portfolio VaR calculation |
| **Pre-trade checks** | Every order is validated against position limits and risk thresholds before submission |

---

## Backtesting Engine (`backtest/`)

- Processes historical OHLCV bar data loaded from local files (downloaded via `download_real_data.py`).
- Simulates realistic execution with configurable **slippage** and **commissions**.
- Produces comprehensive performance reports:
  - Total return, annualised return
  - Sharpe ratio, Sortino ratio, Calmar ratio
  - Maximum drawdown
  - Win rate, trade-by-trade breakdown
- Supports **risk profile comparison** (Conservative vs. Balanced vs. Aggressive on the same strategy/data).
- Reported benchmark performance (2022–2023 backtests): Moving Average +18.7%, Mean Reversion +12.3%, Momentum +31.2% vs. S&P 500 +15.2%.
- Processing speed: ~500 bars/second, 2 years of daily data in ~8 seconds.

---

## Broker Integration (`core/`, `execution/`)

- Communicates with Interactive Brokers TWS via the official **`ibapi`** Python library.
- `TradeApp` (in `tws_client.py`) subclasses both `EWrapper` and `EClient` to handle bidirectional communication.
- Supports both **paper trading** (port 7497) and **live trading** (port 7496) modes, configured via `.env` / `config_paper.py` / `config_live.py`.
- A `RateLimiter` prevents exceeding IB API request limits.
- `ContractBuilder` constructs IB `Contract` objects for equities and other instrument types.
- Order execution latency to TWS: < 100ms (target).

---

## Monitoring & Observability (`monitoring/`, `strategies/`)

- Real-time position and P&L tracking.
- Health monitor checks strategy liveness and connection state.
- Performance attribution breaks down returns by strategy.
- Planned / partial: WebSocket-based dashboard (FastAPI) for browser-based real-time monitoring, email/SMS alerts.
- A complete **audit trail** of all orders and fills is stored in the database.

---

## Data Persistence

SQLite is used locally (`strategy_lifecycle.db`, `test.db`). The target schema (PostgreSQL for production) covers:

- `strategies` — strategy registry and status
- `orders` / `fills` — full order lifecycle
- `positions` / `portfolio_snapshots` — portfolio state over time
- `strategy_performance` — daily metrics per strategy
- `risk_events` — risk alerts and actions taken
- `market_data` — cached historical bars
- `audit_log` — change tracking across all tables

---

## Configuration

| File | Purpose |
|------|---------|
| `.env` (from `.env.example`) | Host, port, account credentials, mode (paper/live) |
| `config/paper.py` | Paper trading defaults (port 7497) |
| `config/live.py` | Live trading defaults with extra safety guards (port 7496) |
| `config/env_config.py` | Loads and validates environment variables at runtime |

---

## Key Entry Points

| Script | What it does |
|--------|-------------|
| `scripts/quick_start.py` | Runs a Moving Average backtest in ~5 minutes |
| `scripts/strategy_selector.py` | Interactive guide to choose the right strategy for a given stock |
| `scripts/run_live.py` | Launches a live or paper trading session |
| `scripts/run_web.py` | Starts the Flask web UI (default: http://127.0.0.1:5000) |
| `scripts/check_account.py` | Displays current account balance, positions, and P&L (requires TWS) |
| `scripts/market_status.py` | Reports whether the market is currently open |
| `scripts/download_real_data.py` | Downloads historical OHLCV data for given symbols |
| `examples/example_strategy_templates.py` | Demonstrates all three backtest strategies |
| `examples/example_profile_comparison.py` | Compares Conservative vs. Aggressive risk profiles side-by-side |

---

## Safety Philosophy

1. **Paper trade first** — all live features require an explicit mode flag.
2. **Confirmation prompts** before placing any real-money orders.
3. **Automatic circuit breakers** — the system halts itself before losses compound.
4. **Prime Directive** (`prime_directive.md`) — a documented development standard enforcing test coverage, code quality, and safety rules for every contribution.
5. **Minimum recommended capital** for live trading: $10,000 for adequate diversification.

---

## Technology Stack

| Component | Technology |
|-----------|-----------|
| Language | Python 3.12+ |
| Broker API | Interactive Brokers `ibapi` |
| Data / numerics | `pandas`, `numpy` |
| Database (local) | SQLite |
| Database (target) | PostgreSQL |
| Web UI | Flask + Jinja2 (server-rendered; no SPA framework) |
| Web API (planned) | FastAPI + WebSockets (real-time data feeds) |
| Testing | `pytest` (690+ tests) |
| Configuration | `.env` + `python-dotenv` |
