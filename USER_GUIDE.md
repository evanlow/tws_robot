# TWS Robot — User Guide

> ⚠️ **Risk Warning:** TWS Robot is experimental open-source software. Trading involves substantial risk, including loss of capital. Always paper trade first. You are solely responsible for all trading decisions and losses. See [`DISCLAIMER.md`](DISCLAIMER.md).

---

## Table of Contents

1. [What is TWS Robot?](#1-what-is-tws-robot)
2. [Installation & Setup](#2-installation--setup)
3. [Configuration](#3-configuration)
4. [Authentication](#4-authentication)
5. [The Web Dashboard](#5-the-web-dashboard)
   - [Dashboard (Home)](#51-dashboard-home)
   - [Strategies](#52-strategies)
   - [Positions](#53-positions)
   - [Backtest](#54-backtest)
   - [Risk](#55-risk)
   - [Events & Logs](#56-events--logs)
   - [Account Intelligence](#57-account-intelligence)
   - [AI Features](#58-ai-features)
   - [FX Research](#59-fx-research)
   - [Settings](#510-settings)
6. [Backtesting](#6-backtesting)
7. [Paper Trading](#7-paper-trading)
8. [Live Trading](#8-live-trading)
9. [Strategies Reference](#9-strategies-reference)
10. [Risk Management](#10-risk-management)
11. [Autonomous Trading](#11-autonomous-trading)
    - [Overview](#111-overview)
    - [How the Pipeline Works](#112-how-the-pipeline-works)
    - [Operating Modes](#113-operating-modes)
    - [Safety Architecture](#114-safety-architecture)
    - [Prerequisites](#115-prerequisites)
    - [Quick Start: Your First Autonomous Paper Trade](#116-quick-start-your-first-autonomous-paper-trade)
    - [Configuration Reference](#117-configuration-reference)
    - [Signal Providers & Candidate Ranking](#118-signal-providers--candidate-ranking)
    - [Trade Planning](#119-trade-planning)
    - [Trade Lifecycle & Exit Management](#1110-trade-lifecycle--exit-management)
    - [The Autonomous Trading Dashboard](#1111-the-autonomous-trading-dashboard)
    - [REST API Reference](#1112-rest-api-reference)
    - [The Audit Log](#1113-the-audit-log)
    - [Progressing to Live Execution](#1114-progressing-to-live-execution)
    - [Troubleshooting](#1115-troubleshooting)
    - [Frequently Asked Questions](#1116-frequently-asked-questions)
12. [Order Management](#12-order-management)
13. [Command-Line Tools](#13-command-line-tools)
14. [Your Weekly Routine](#14-your-weekly-routine)
15. [Troubleshooting](#15-troubleshooting)
16. [Frequently Asked Questions](#16-frequently-asked-questions)

---

## 1. What is TWS Robot?

TWS Robot is a Python-based automated trading platform that connects to your **Interactive Brokers** account via the official `ibapi` library. It lets you:

- **Test** trading strategies on historical data (backtesting) — no broker required
- **Validate** strategies with real-time data on a simulated account (paper trading)
- **Deploy** strategies against a real account (live trading)

The recommended workflow is always:

```
Historical Data → Backtest → Paper Trade → Live Trade
```

**Never skip a step.** A strategy that looks great in backtests must also prove itself in paper trading before you risk real capital.

### Who is TWS Robot for?

| User | What You Can Do |
|------|----------------|
| **New to algo trading** | Use the web dashboard, run pre-built strategies, backtest without any coding |
| **Active traders** | Automate execution, compare strategies, monitor performance in real time |
| **Quant developers** | Build custom strategies on the event-driven framework, extend any module |

---

## 2. Installation & Setup

### Prerequisites

- Python 3.12 or newer
- For **paper or live trading**: Interactive Brokers TWS or IB Gateway running with API access enabled (see [TWS Connection Guide](docs/TWS_CONNECTION_GUIDE.md))
- For **backtesting only**: no broker connection needed

### Install TWS Robot

```bash
# 1. Clone the repository
git clone https://github.com/evanlow/tws_robot.git
cd tws_robot

# 2. Create and activate a virtual environment
python -m venv venv

# Windows PowerShell
.\venv\Scripts\Activate.ps1

# macOS / Linux
source venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt
```

### First Launch

```bash
# Start the web dashboard
python scripts/run_web.py
```

Open your browser to **http://127.0.0.1:5000**. Log in with the default credentials (`admin` / `changeme`) and you are ready to go.

---

## 3. Configuration

All configuration lives in a `.env` file in the project root. Copy the provided template to get started:

```bash
cp .env.example .env
```

Then open `.env` in any text editor and fill in your values:

| Variable | Default | Description |
|----------|---------|-------------|
| `TRADING_ENV` | `paper` | `paper` or `live` — which account to use by default |
| `PAPER_HOST` | `127.0.0.1` | Host where TWS is running (paper account) |
| `PAPER_PORT` | `7497` | TWS API port for paper trading |
| `PAPER_CLIENT_ID` | `0` | Client ID sent to TWS (paper) |
| `PAPER_ACCOUNT` | *(your ID)* | Your IB paper account number |
| `LIVE_HOST` | `127.0.0.1` | Host where TWS is running (live account) |
| `LIVE_PORT` | `7496` | TWS API port for live trading |
| `LIVE_CLIENT_ID` | `1` | Client ID sent to TWS (live) |
| `LIVE_ACCOUNT` | *(your ID)* | Your IB live account number |
| `LOG_LEVEL` | `INFO` | Logging verbosity (`DEBUG`, `INFO`, `WARNING`, `ERROR`) |
| `TWS_ADMIN_USERNAME` | `admin` | Web dashboard login username |
| `TWS_ADMIN_PASSWORD` | `changeme` | Web dashboard login password (plain-text; hashed at startup) |
| `TWS_ADMIN_PASSWORD_HASH` | *(unset)* | Pre-hashed bcrypt/PBKDF2 password — takes priority over `TWS_ADMIN_PASSWORD` |
| `ALLOW_DEFAULT_PASSWORD` | `false` | Set to `true` in local dev to suppress the insecure-default-password warning |
| `SECRET_KEY` | *(random)* | Flask session secret — **change in production** |
| `OPENAI_API_KEY` | *(unset)* | Your OpenAI API key — required to enable AI features |
| `OPENAI_MODEL` | `gpt-4o` | OpenAI model used for AI chat and insights |
| `AI_ENABLED` | *(auto)* | Explicitly force AI on (`true`) or off (`false`); defaults to enabled when `OPENAI_API_KEY` is set |
| `LOGIN_DISABLED` | *(unset)* | Set to `true` to bypass auth in local development |
| `ENVIRONMENT` | *(unset)* | Set to `production` to enforce strict security checks (e.g. `SECRET_KEY` required) |
| `AUTONOMOUS_RUNNER_ENABLED` | `false` | Set to `true` to allow the autonomous paper-trading runner to open/close positions automatically |
| `DATABASE_URL` | *(SQLite)* | SQLAlchemy connection string; defaults to a local SQLite file when unset |
| `FX_DATA_MODE` | `not_configured` | FX research data source: `not_configured`, `demo`, or `live_research` |
| `FX_PROVIDER` | `yfinance` | FX data provider library (currently only `yfinance` is supported) |
| `FX_PROVIDER_TIMEOUT_SECONDS` | `10` | HTTP timeout in seconds for FX provider requests |
| `EMERGENCY_STOP_FILE` | `EMERGENCY_STOP` | Path to the emergency-stop sentinel file; trading halts when this file exists |
| `DISCLAIMER_ACCEPTANCE_FILE` | `disclaimer_acceptance.json` | Path to the disclaimer acceptance record |
| `STRATEGY_DB_PATH` | `strategy_lifecycle.db` | Path to the strategy lifecycle SQLite database |
| `CASH_RESERVE_MODE` | `gross_assignment` | Cash reserve calculation method: `gross_assignment`, `net_premium`, or `broker_margin` |
| `MANUAL_CASH_BUFFER_PCT` | `0.05` | Fraction of cash balance kept as an untouched buffer (e.g. `0.10` = 10 %) |
| `MANUAL_CASH_BUFFER_AMOUNT` | `0` | Fixed dollar amount kept as an untouched buffer (larger of this or `MANUAL_CASH_BUFFER_PCT` applies) |
| `OPTION_CONTRACT_MULTIPLIER_DEFAULT` | `100` | Default option-contract multiplier when not available from position data |
| `ENABLE_CASH_AVAILABILITY_GUARD` | `true` | Enable the deployable-cash safety guard |
| `BLOCK_AUTOMATED_TRADING_IF_UNCOVERED_SHORT_CALL` | `true` | Block automated trades when an uncovered short call is detected |
| `BLOCK_AUTOMATED_TRADING_IF_DEPLOYABLE_CASH_NEGATIVE` | `true` | Block automated trades when deployable cash is negative |

> 💡 **Tip:** Never commit your `.env` file to version control. It is already in `.gitignore`.

### Environment-Specific Config Files

| File | Purpose |
|------|---------|
| `config/paper.py` | Paper trading defaults (port 7497) |
| `config/live.py` | Live trading defaults with extra safety guards (port 7496) |
| `config/env_config.py` | Loads and validates all environment variables at startup |

---

## 4. Authentication

The web dashboard requires you to log in before you can access any page.

- **Default username:** `admin`
- **Default password:** `changeme`

**To change your credentials**, add these lines to your `.env` file:

```
TWS_ADMIN_USERNAME=yourname
TWS_ADMIN_PASSWORD=a-strong-password
```

Restart the dashboard after editing `.env`.

> ⚠️ **Security:** Change the default password before exposing the dashboard to any network. In production, also set a strong `SECRET_KEY` and remove `LOGIN_DISABLED` if it was set.

### CSRF Protection

All state-changing requests (POST, DELETE, etc.) from the web UI include a CSRF token automatically. This is handled by `web/static/js/main.js` and the `csrf-token` meta tag in each page — you do not need to do anything.

---

## 5. The Web Dashboard

Start the dashboard:

```bash
python scripts/run_web.py
# Open: http://127.0.0.1:5000
```

The top navigation bar is always visible and shows:

- **Connection status** — whether TWS is connected and which environment (paper/live)
- **Account equity** and **daily P&L**
- **Risk level** indicator
- 🚨 **Emergency Stop button** — one click halts all trading immediately

### 5.1 Dashboard (Home)

**URL:** `/`

The landing page gives you an at-a-glance view of your trading system:

| Section | What You See |
|---------|-------------|
| **Connection Status** | Whether the system is connected to TWS, current environment |
| **Portfolio Summary** | Total equity, unrealised P&L, daily P&L, buying power |
| **Active Strategies** | Cards for each registered strategy with live position rows and quick start/stop controls |
| **Recent Trades** | Last 10 executed trades |
| **Active Alerts** | Up to 10 recent risk or system alerts |
| **Market Overview** | Multi-region market status (US, EU, Asia) refreshed automatically |
| **Portfolio Analysis** | Allocation chart, concentration metrics, drawdown indicator, and rebalancing suggestions |

> 💡 **Tip:** The Dashboard is read-only. Use the **Strategies** page to start or stop strategies, and the **Positions** page to manage open trades.

---

### 5.2 Strategies

**URL:** `/strategies`

Manage all trading strategies from one page.

**What you can do:**

- **View** all registered strategies and their current status (running / stopped / error)
- **Start / Stop** any strategy with a single click
- **Inspect live positions** for each strategy's configured symbols
- **AI Insight card** — if AI is enabled, each strategy card shows an auto-generated summary with confidence score and next-action recommendations; otherwise the card shows "AI not enabled"

**Strategy card details:**

Each card shows:
- Strategy name, status, and configured symbols
- Live position rows (entry price, current price, unrealised P&L per symbol)
- Quick start/stop toggle button

---

### 5.3 Positions

**URL:** `/positions`

Shows all **open positions** currently held in the broker account.

| Column | Meaning |
|--------|---------|
| Symbol | Ticker (e.g. `AAPL`) — displayed as full company name where available |
| Quantity | Number of shares (positive = long, negative = short) |
| Avg Cost | Average entry price per share |
| Market Value | Current total market value |
| Unrealised P&L | Profit or loss on the open position |
| Realised P&L | Profit or loss on closed trades today |

**Order history** is also shown below the open positions — every order that has been recorded, submitted, filled, or cancelled.

---

### 5.4 Backtest

**URL:** `/backtest`

Run historical simulations on any of the built-in strategies without connecting to TWS.

**To run a backtest:**

1. Select a **strategy** (Moving Average Crossover, Mean Reversion, or Momentum)
2. Enter the **ticker symbol** (e.g. `AAPL`)
3. Choose a **date range**
4. Select a **risk profile** (Conservative, Balanced, or Aggressive)
5. Click **Run Backtest**

**Results shown:**

| Metric | What It Means |
|--------|--------------|
| Total Return | Overall % gain or loss over the test period |
| Annualised Return | Return scaled to a one-year equivalent |
| Sharpe Ratio | Risk-adjusted return (higher is better; >1.0 is good) |
| Sortino Ratio | Like Sharpe, but only penalises downside volatility |
| Calmar Ratio | Return divided by maximum drawdown |
| Max Drawdown | Largest peak-to-trough decline during the test |
| Win Rate | % of trades that were profitable |
| Number of Trades | Total trades executed over the period |

The page also displays an **equity curve chart** and a trade-by-trade breakdown so you can see exactly when the strategy entered and exited positions.

> 💡 **Need historical data?** Run `python scripts/download_real_data.py AAPL MSFT GOOGL` to download OHLCV data for the symbols you want to backtest.

---

### 5.5 Risk

**URL:** `/risk`

Monitor and control your risk exposure.

**What you can see:**

| Section | Description |
|---------|------------|
| **Drawdown Gauge** | Current drawdown vs. your warning (−2%) and emergency (−5% daily / −15% total) thresholds |
| **Risk Profile** | Currently active profile (Conservative / Balanced / Aggressive) with position size and stop-loss settings |
| **Circuit Breaker Status** | Whether any automatic trading halt is in force |
| **Correlation Heatmap** | Cross-asset correlation across open positions to detect over-concentration |
| **VaR Summary** | Real-time Value at Risk estimate for the portfolio |

**Emergency Stop** is also available on this page (as well as always visible in the top bar).

---

### 5.6 Events & Logs

**URL:** `/logs`

Live log stream of all application events via Server-Sent Events (SSE).

- **Application logs** — INFO/WARNING/ERROR messages from all modules
- **Prime Directive violations** — any rule violations recorded in `prime_directive_violations.log`

Logs auto-scroll as new events arrive. Use the filter controls to narrow down by level or module.

---

### 5.7 Account Intelligence

**URL:** `/account-intelligence`

An advanced analytics dashboard with eight modules, all loaded client-side via the `/api/intelligence/*` endpoints:

| Module | What It Analyses |
|--------|-----------------|
| **Account Health** | Composite health score, margin usage, diversification metrics |
| **Cash Management** | Cash reserve vs. target, idle cash detection, cash flow forecast |
| **Opportunity Detector** | Sector gaps in your portfolio, rebalancing suggestions, dividend screening |
| **Performance Benchmarking** | Your return vs. SPY / QQQ / IWM; alpha, beta, and fee tracking |
| **Risk Intelligence** | Monte Carlo simulation (10 000 scenarios), stress tests, liquidity analysis |
| **Report Generator** | Automated daily/weekly/monthly performance reports with threshold alerts |
| **Multi-Account Manager** | Aggregate view across accounts, cross-account risk, duplicate position detection |
| **Execution Quality** | Fill quality, slippage tracking, order rejection monitoring |

Each module card loads independently — if the broker is not connected, the module shows its best estimate from cached data.

---

### 5.8 AI Features

AI features require `OPENAI_API_KEY` to be set in your `.env` file.

#### AI Chat

**URL:** `/ai/chat`

A dedicated chat interface backed by the OpenAI API. The assistant has full context of your live trading state (positions, strategies, risk summary) injected into every request so you can ask questions like:

- *"What is my largest position and how is it performing?"*
- *"Should I add more exposure to tech given my current allocation?"*
- *"What are the risks of running a Bollinger Bands strategy in this market?"*

Chat history is stored in memory for the current session (up to 50 messages). To clear it, click **Clear History** or send `DELETE /ai/chat/history`.

#### Portfolio Insights (AI Strategy Deduction)

**URL:** `/portfolio-analysis`

AI analyses your open positions and automatically detects the option or equity strategies you are running:

- Covered calls, protective puts, collars
- Bull/bear spreads, iron condors, straddles, strangles
- Profit targets, stop losses, and risk metrics per inferred strategy
- Confidence scores and narrative insights explaining what each position means and what to do next

#### AI Strategy Assistant

Available on the **Strategies** page — provides per-strategy AI summaries that auto-load when AI is enabled.

---

### 5.9 FX Research

**URL:** `/fx`

A **read-only** research dashboard for SGD foreign-exchange signals. No order execution.

Displays:
- Signal bias (Long SGD / Short SGD / Neutral) per currency pair
- Market-watch table with rate snapshots and trend indicators
- Research notes and links

> This section uses demo/mock data by default and is intended for research and monitoring only.

---

### 5.10 Settings

**URL:** `/settings`

Configure the TWS connection and application behaviour:

| Setting | Description |
|---------|-------------|
| TWS Host | IP address of the machine running TWS (usually `127.0.0.1`) |
| TWS Port | API port — `7497` for paper, `7496` for live |
| Client ID | Unique integer ID sent to TWS for this connection |
| Environment Toggle | Switch between paper and live mode |
| Rate Limits | Max requests per second to avoid exceeding IB API limits |

Changes take effect when you reconnect to TWS (click **Reconnect** on the Dashboard, or restart the server).

---

## 6. Backtesting

Backtesting lets you simulate a strategy on historical price data to see how it would have performed — without risking any money.

### Running a Backtest from the Web Dashboard

1. Go to **Backtest** in the navigation bar
2. Select strategy, symbol, date range, and risk profile
3. Click **Run Backtest**
4. Review the equity curve, metrics table, and trade log

### Running a Backtest from the Command Line

```bash
# Quick 5-minute demo (Moving Average on AAPL)
python scripts/quick_start.py

# Full backtest with charts and detailed output
python examples/example_backtest_complete.py

# Compare all three built-in strategies side by side
python examples/example_strategy_templates.py

# Compare Conservative vs. Aggressive risk profiles
python examples/example_profile_comparison.py
```

### Downloading Historical Data

Backtests read local OHLCV files. Download data before running a test:

```bash
python scripts/download_real_data.py AAPL MSFT GOOGL NVDA
```

Data is stored in the `data/` directory and reused automatically.

### Interpreting Results

| Metric | Healthy Range | Watch Out If… |
|--------|--------------|---------------|
| Sharpe Ratio | > 1.0 | < 0.5 — poor risk-adjusted return |
| Max Drawdown | < −10% | Worse than −20% — too volatile |
| Win Rate | > 50% | Below 40% consistently |
| Total Return | > 0% and beats S&P | Negative, or far below benchmark |

**Reference benchmarks (2022–2023 backtests):**

| Strategy | Symbol | Total Return | Sharpe | Max Drawdown | Win Rate |
|----------|--------|-------------|--------|-------------|----------|
| Moving Average | AAPL | +18.7% | 1.52 | −8.1% | 56.7% |
| Mean Reversion | KO | +12.3% | 1.38 | −6.5% | 62.1% |
| Momentum | NVDA | +31.2% | 1.71 | −12.3% | 51.3% |

*S&P 500 buy-and-hold returned +15.2% over the same period.*

> ⚠️ Past performance does not guarantee future results.

---

## 7. Paper Trading

Paper trading runs your strategy with **real-time market data** against a simulated Interactive Brokers account. It behaves exactly like live trading except no real money moves.

### Prerequisites

- Interactive Brokers TWS or IB Gateway running in **Paper Trading** mode
- API access enabled in TWS: *Edit → Global Configuration → API → Settings*
  - ✅ Enable ActiveX and Socket Clients
  - ✅ Trusted IP: `127.0.0.1`
- `.env` configured with your paper account details and `TRADING_ENV=paper`

### Starting Paper Trading

**From the web dashboard:**
1. Go to **Settings** and confirm Port = `7497` and Environment = `paper`
2. Go to **Strategies** and click **Start** on the Bollinger Bands strategy
3. Monitor results on the **Dashboard** and **Positions** pages

**From the command line:**
```bash
python scripts/run_live.py --env paper
```

### What to Monitor

- **Daily P&L** — is the strategy making or losing simulated money?
- **Win rate** — are more than half of trades profitable?
- **Max drawdown** — does the strategy ever lose 10%+ in a single run?
- **Consistency** — are results stable week over week, or wildly variable?

### Paper Trading Minimum Duration

Run paper trading for **at least 30 days** before considering live deployment. Markets go through cycles — a strategy that only works in trending markets will fail in choppy conditions.

---

## 8. Live Trading

> ⚠️ **Real money is at risk.** Only proceed after sustained paper trading success and with capital you can afford to lose.

### Prerequisites

- Successful paper trading for ≥30 days with consistent positive results
- Interactive Brokers TWS running in **Live** mode (port 7496)
- At least $10,000 in your live account (recommended for adequate diversification)
- `.env` configured with `TRADING_ENV=live` and your live account number

### Starting Live Trading

**From the web dashboard:**
1. Go to **Settings** and switch Environment to `live`
2. Confirm Port = `7496`
3. Go to **Strategies** and click **Start**
4. You will see a **confirmation prompt** — live trading requires explicit acknowledgement

**From the command line:**
```bash
python scripts/run_live.py --env live
```

### Emergency Stop

If anything looks wrong, hit the red **Emergency Stop** button visible in the top bar of every page. This immediately:
1. Halts all strategy execution
2. Cancels pending orders (where possible)
3. Optionally flattens open positions

You can also trigger it from the Risk page or via the API: `POST /api/emergency/stop`.

---

## 9. Strategies Reference

### Backtest-Only Strategies

These three strategies are available for historical testing. They are not wired for live order placement.

#### Moving Average Crossover

| | |
|---|---|
| **Best for** | Trending markets, blue-chip stocks (AAPL, MSFT, NVDA) |
| **Avoid** | Choppy, sideways-moving stocks |
| **Signal: BUY** | Fast MA (20-day) crosses above slow MA (50-day) |
| **Signal: SELL** | Fast MA crosses below slow MA |

```python
from backtest.strategy_templates import MovingAverageCrossStrategy, MACrossConfig
from backtest.strategy import StrategyConfig

config = StrategyConfig(initial_capital=10000)
ma_config = MACrossConfig(fast_period=20, slow_period=50)
strategy = MovingAverageCrossStrategy(config, ma_config)
```

#### Mean Reversion

| | |
|---|---|
| **Best for** | Stable, range-bound stocks (KO, PG, JNJ, utilities) |
| **Avoid** | Trending or breakout stocks |
| **Signal: BUY** | Price drops > 2 standard deviations below its moving average |
| **Signal: SELL** | Price returns to the mean |

```python
from backtest.strategy_templates import MeanReversionStrategy

config = StrategyConfig(initial_capital=10000)
strategy = MeanReversionStrategy(config)
```

#### Momentum

| | |
|---|---|
| **Best for** | High-growth / volatile stocks (TSLA, NVDA) |
| **Avoid** | Declining or choppy markets |
| **Signal: BUY** | Strong positive rate-of-change, accelerating |
| **Signal: SELL** | Momentum slows or turns negative |

```python
from backtest.strategy_templates import MomentumStrategy

config = StrategyConfig(initial_capital=10000)
strategy = MomentumStrategy(config)
```

### Live / Paper Trading Strategy

#### Bollinger Bands Mean Reversion

The only production-ready strategy for paper and live trading.

| | |
|---|---|
| **Location** | `strategies/bollinger_bands.py` |
| **Indicator** | 20-period SMA ± 2.0 standard deviations |
| **Signal: Long** | Price crosses below the lower band (oversold) |
| **Signal: Short** | Price crosses above the upper band (overbought) |
| **Exit** | Price returns to the middle band (SMA) |
| **Stop loss** | 2% from entry price |

### Strategy Selection Guide

Not sure which strategy to use?

| Market Condition | Recommended Strategy |
|-----------------|---------------------|
| Clear uptrend or downtrend | Moving Average Crossover |
| Sideways / range-bound | Mean Reversion |
| Strong momentum / high growth | Momentum |
| Real-time paper/live trading | Bollinger Bands |

Or use the interactive selector:

```bash
python scripts/strategy_selector.py
```

### Adding Custom Strategies

For developers who want to build their own strategy, see [`docs/runbooks/adding-new-strategy.md`](docs/runbooks/adding-new-strategy.md).

---

## 10. Risk Management

TWS Robot enforces safety at multiple layers so a single bad trade cannot destroy your account.

### Risk Profiles

Choose your comfort level at startup or from the Risk page:

| Profile | Position Size per Trade | Stop Loss | Best For |
|---------|------------------------|-----------|----------|
| **Conservative** | 2–3% of account | Tight (~5%) | Retirement accounts, low risk tolerance |
| **Balanced** | ~5% of account | Moderate (~10%) | Active traders, moderate risk |
| **Aggressive** | ~10% of account | Wide (~15%) | Experienced traders, high risk tolerance |

```python
from backtest.profiles import create_conservative_profile, create_balanced_profile, create_aggressive_profile

profile = create_conservative_profile()   # safest
profile = create_balanced_profile()       # default
profile = create_aggressive_profile()     # highest risk
```

### Circuit Breakers

TWS Robot **automatically stops all trading** if:

| Threshold | Trigger | Action |
|-----------|---------|--------|
| Daily loss ≥ −2% | Warning level | Alert displayed; trading continues |
| Daily loss ≥ −5% | Emergency level | All trading halted immediately |
| Total drawdown ≥ −15% | Emergency level | All trading halted immediately |

You must manually re-enable trading after an emergency stop by clicking **Resume** on the Risk page (or via `POST /api/emergency/reset`).

### Position Sizing

Position size is calculated dynamically based on:
- Your current account equity
- Per-trade volatility of the instrument
- Your chosen risk profile

The default is **1–2% of account equity per trade**, consistent with professional risk management standards.

### Pre-Trade Checks

Every order — whether generated by a strategy or submitted manually — passes through:
1. Position limit check (is this too large?)
2. Risk threshold check (is the portfolio already too exposed?)
3. Emergency stop gate (is the system halted?)
4. Account data readiness check (is equity data loaded?)

If any check fails, the order is rejected with an explanatory error message.

---

## 10.1 Cash Availability & Deployable Capital

TWS Robot estimates **deployable cash** — the portion of your account balance that is genuinely available for new trades, after setting aside capital already committed to open obligations.

> This is labelled *TWS Robot estimated* throughout the UI. It is **not** an official broker margin figure. Broker margin rules may differ.

### Why broker buying power is not enough

Interactive Brokers reports a `BuyingPower` figure that may include margin headroom. However, some of your cash is already implicitly committed:

- **Cash-secured short puts** — if assigned, you must buy the underlying at the strike price. That notional obligation should be reserved.
- **Defined-risk spreads** — only the maximum loss (spread width × contracts × multiplier) needs to be reserved, not the full assignment value.
- **Covered calls** — do not consume cash, but the underlying shares are "committed" and may be called away.
- **Pending open orders** — a buy order sitting in the market has not yet consumed cash but will do so if filled.
- **Multi-currency positions** — SGD or HKD cash is not freely interchangeable with USD without explicit FX conversion.

### Deployable cash formula

```
deployable_cash = max(
    0,
    cash_balance
    − reserved_for_short_puts
    − reserved_for_defined_risk_spreads
    − reserved_for_pending_orders
    − manual_cash_buffer
    − margin_safety_buffer
)
```

### Cash Availability API

The full analysis is available via the REST API:

```http
GET /api/account/cash-availability
```

See [docs/WEB_API_REFERENCE.md](docs/WEB_API_REFERENCE.md#get-apiaccountcash-availability) for the complete response schema.

### Configuration

Add these keys to your `.env` file to customize behaviour:

| Variable | Default | Description |
|----------|---------|-------------|
| `CASH_RESERVE_MODE` | `gross_assignment` | Reserve mode: `gross_assignment`, `net_premium`, or `broker_margin` |
| `MANUAL_CASH_BUFFER_PCT` | `0.10` | Fraction of cash balance to keep untouched (e.g. `0.10` = 10%) |
| `MANUAL_CASH_BUFFER_AMOUNT` | `0` | Fixed dollar amount to keep untouched (larger of the two is used) |
| `OPTION_CONTRACT_MULTIPLIER_DEFAULT` | `100` | Multiplier when not available from position data |
| `ENABLE_CASH_AVAILABILITY_GUARD` | `true` | Enable/disable the deployable-cash safety gate |
| `BLOCK_AUTOMATED_TRADING_IF_UNCOVERED_SHORT_CALL` | `true` | Block automated recommendations when uncovered short calls exist |
| `BLOCK_AUTOMATED_TRADING_IF_DEPLOYABLE_CASH_NEGATIVE` | `true` | Block automated recommendations when deployable cash ≤ 0 |

### Warnings

| Warning | Meaning |
|---------|---------|
| ⚠ Deployable cash ≤ 0 | All cash is reserved; no capital available for new trades |
| ⚠ Cash balance < reserved cash | Obligations exceed your current cash balance |
| 🔴 Uncovered short call risk | One or more short calls are not covered by shares or long calls |
| 🔴 Short stock risk | Short stock positions may increase margin requirements |
| ⚠ High margin usage | Less than 10% excess liquidity remaining |
| ⚠ Multi-currency risk | Multiple currency cash balances detected; USD deployable cash may be overstated |

---

## 11. Autonomous Trading

> ⚠️ **Risk Warning:** Autonomous trading places real orders without moment-to-moment human oversight. Always paper trade first. Validate extensively before considering live execution. You are solely responsible for all outcomes. See [`DISCLAIMER.md`](DISCLAIMER.md) and [`prime_directive.md`](prime_directive.md).

---

### 11.1 Overview

TWS Robot's **Autonomous Trading** module lets the system scan the S&P 500 universe, identify high-quality oversold candidates, size a trade against your available cash, and optionally submit that order to your paper (or live) Interactive Brokers account — all without you clicking a button for each trade.

The module is built around **safety-first defaults**:

- Every setting starts in a conservative, non-executing mode.
- Live execution is **disabled by default** and requires explicit configuration changes.
- A single file (`EMERGENCY_STOP`) halts the system instantly at any time.
- Every decision — including rejections — is written to an append-only audit log so you can replay exactly what the system did and why.
- The system never guesses at prices: if a live price is unavailable, exit orders are not placed rather than using a stale estimate.

Think of Autonomous Trading as a tireless analyst that runs the same disciplined checklist every time, then either presents its recommendation to you (Recommend-Only mode) or executes it on your paper account (Paper Execute mode).

---

### 11.2 How the Pipeline Works

Every autonomous cycle follows the same five-stage pipeline:

```
┌────────────────────────────────────────────────────────────────┐
│                      AUTONOMOUS CYCLE                          │
├──────────┬──────────┬──────────┬─────────────┬────────────────┤
│  Scanner  │  Ranker  │ Planner  │   Engine    │    Adapter     │
│           │          │          │  (Gating)   │  (Execution)   │
│  S&P 500  │ Hard     │ BUY_     │ Cash check  │ Paper adapter  │
│  universe │ filters  │ SHARES   │ Risk check  │ Live adapter   │
│  +        │ Scoring  │   or     │ Daily limit │   (future)     │
│  Signal   │ Ranking  │ SHORT_   │ Emergency   │                │
│  provider │          │ PUT      │   stop gate │                │
└──────────┴──────────┴──────────┴─────────────┴────────────────┘
```

| Stage | What Happens |
|-------|-------------|
| **Scanner** | Iterates over the configured stock universe (default: S&P 500). For each symbol, calls the active `SignalProvider` to retrieve a `CandidateSignal`. Symbols without a signal are skipped. |
| **Ranker** | Applies hard filters (signal strength, label, volume, trend, earnings proximity, concentration limits). Surviving candidates are scored and sorted — the one closest to support with the most room to resistance and the highest strength score wins. |
| **Planner** | Given the top-ranked candidate plus your deployable cash, decides between `BUY_SHARES` (limit order for shares) and `SELL_CASH_SECURED_PUT` (cash-secured put, if option chain data is available and strike is at-or-below support). Produces a `TradePlan` with exact quantities, limit price, target, and stop. |
| **Engine** | Validates the `TradePlan` against safety gates: emergency stop, daily trade limit, account equity checks, and the optional `RiskManager`. Returns a structured `AutonomousDecision` (approved or rejected with reasons). |
| **Adapter** | In `PAPER_EXECUTE` mode, sends the order to the paper account via `AutonomousPaperAdapter`. In `RECOMMEND_ONLY` mode, the adapter is never called — the decision is returned as a recommendation only. |

The **ExitManager** runs as a separate pass over open autonomous trades. It checks each open position against take-profit, stop-loss, maximum holding duration, and the emergency stop, and submits a paper SELL order when exit conditions are met.

---

### 11.3 Operating Modes

The autonomous engine has three operating modes. Switch between them in the dashboard or via the API.

| Mode | What the Engine Does | Orders Placed? |
|------|---------------------|---------------|
| `recommend_only` | Runs the full pipeline and returns a `TradePlan`, but never calls the execution adapter. Safe to run at any time. | ❌ Never |
| `paper_execute` | Runs the full pipeline **and** sends limit orders to your IBKR paper account via `AutonomousPaperAdapter`. Requires an active paper connection. | ✅ Paper only |
| `assisted_live` | May submit to your live account, **but only** when `allow_live_execution = True` is set in config **and** the API call explicitly passes `confirm = True`. | ✅ Live (opt-in) |

**Start with `recommend_only`.** Review several cycles of recommendations before ever enabling paper execution. Paper trade for at least 30 days before considering `assisted_live`.

---

### 11.4 Safety Architecture

Multiple independent layers protect against unintended trading. All of them must pass before an order is placed:

```
Layer 1 — Emergency stop file
  └─ If EMERGENCY_STOP file exists on disk → halt immediately, no orders

Layer 2 — Runner gates (paper runner only)
  ├─ runner_enabled must be True
  ├─ Must be connected to IBKR paper account (not live)
  ├─ Paper adapter must report ready
  ├─ Signal provider must be ready
  ├─ open_autonomous_trades < max_open_autonomous_trades
  └─ daily_trade_count < max_trades_per_day

Layer 3 — Engine validation
  ├─ Deployable cash >= min_deployable_cash
  ├─ Trade size <= max_new_position_pct * equity
  ├─ Candidate passed all ranker hard filters
  └─ Optional RiskManager check

Layer 4 — Mode gate
  ├─ RECOMMEND_ONLY → never executes
  ├─ PAPER_EXECUTE  → paper adapter only, never live
  └─ ASSISTED_LIVE  → requires allow_live_execution=True AND confirm=True
```

**Emergency Stop** is always available:
- Click the red **Emergency Stop** button from any page in the dashboard.
- Touch `EMERGENCY_STOP` file: `touch EMERGENCY_STOP` (or delete it to re-enable).
- Call the API: `POST /api/autonomous/emergency-stop`.
- Call the shared endpoint: `POST /api/emergency/stop`.

The autonomous engine checks for this file at the start of every cycle and the exit manager checks it before evaluating every open trade. The moment the file exists, no new orders are placed and no exits are submitted.

---

### 11.5 Prerequisites

Before running autonomous trading in any mode:

| Requirement | Needed For |
|-------------|-----------|
| TWS Robot fully installed and running (`python scripts/run_web.py`) | All modes |
| Interactive Brokers TWS open and connected | Paper and live modes |
| TWS Paper account connected (port `7497`) | `paper_execute` mode |
| `AUTONOMOUS_RUNNER_ENABLED=true` in `.env` (or set in app config) | `paper_execute` mode |
| Sustained paper trading success over 30+ days | Live mode only |
| `allow_live_execution = True` explicitly set in config | Live mode only |
| Minimum $1,000 deployable cash (configurable) | Paper and live modes |

> **Check your prerequisites from the dashboard:** navigate to **Autonomous Trading** → **Status**. The readiness panel shows a green ✅ or red ❌ for every gate with a plain-English explanation for any failures.

---

### 11.6 Quick Start: Your First Autonomous Paper Trade

This walkthrough gets you to your first recommended trade in about 10 minutes using `recommend_only` mode (no orders placed).

#### Step 1 — Start the dashboard

```bash
python scripts/run_web.py
```

Navigate to **http://127.0.0.1:5000** and log in.

#### Step 2 — Connect to your paper account

In TWS, switch to **Paper Trading** mode (port `7497`). In the TWS Robot dashboard, go to **Settings** → set Environment to `paper` and Port to `7497`. Click **Save & Reconnect**.

#### Step 3 — Open the Autonomous Trading page

Click **Autonomous Trading** in the left navigation. You will see the **Status** panel showing current configuration and readiness gates.

#### Step 4 — Run a scan

Click **Scan Universe**. The engine queries the S&P 500 screener for `Strong(100) / Confirmed Rebound` signals, applies the ranker, and returns a list of candidates. No order is placed. Review the candidates, their scores, and why others were rejected.

#### Step 5 — Get a full proposal

Click **Propose Trade**. This runs the full pipeline including the trade planner and produces a concrete `TradePlan` — symbol, action, quantity, limit price, take-profit target, and stop-loss — based on your current deployable cash.

Review the plan carefully. The plan is a recommendation only; nothing has been submitted to your broker.

#### Step 6 — Enable paper execution (optional)

When you are comfortable with the recommendations after several cycles:

1. Add `AUTONOMOUS_RUNNER_ENABLED=true` to your `.env` file and restart the web server.
2. On the **Autonomous Trading** dashboard, confirm all readiness gates are green.
3. Click **Execute Paper Trade**. The system calls `POST /api/autonomous/runner/run-once-paper`, which places a limit order on your IBKR paper account after passing all readiness gates.
4. Monitor the trade on the **Autonomous Trades** panel — status will progress from `OPEN` through to `CLOSED` as the exit manager evaluates your position each cycle.

---

### 11.7 Configuration Reference

#### Core Engine Configuration (`AutonomousTradingConfig`)

These settings control the trading engine's behaviour. They can be supplied as JSON overrides to the API endpoints (see [§11.12](#1112-rest-api-reference)).

| Parameter | Default | Description |
|-----------|---------|-------------|
| `mode` | `recommend_only` | Operating mode: `recommend_only`, `paper_execute`, or `assisted_live` |
| `allow_live_execution` | `false` | Master switch for live order submission. Must be `true` before `assisted_live` mode can place orders. |
| `require_user_confirmation` | `true` | When `true`, `assisted_live` calls must pass `confirm: true` in the request body |
| `max_trades_per_day` | `1` | Maximum number of new autonomous positions opened per calendar day (enforced via the audit log, persists across restarts) |
| `max_new_position_pct` | `0.10` | Maximum fraction of account equity for any single new position (e.g. `0.10` = 10%) |
| `min_deployable_cash` | `1000.0` | Minimum deployable cash (USD) required before any trade is proposed |
| `min_signal_strength` | `100` | Minimum `strength_score` a candidate must carry to pass the ranker |
| `required_signal_label` | `Confirmed Rebound` | The exact signal label required; currently only `Confirmed Rebound` qualifies |
| `stock_universe` | `sp500` | Universe scanned by the candidate scanner |
| `prefer_cash_secured_put` | `true` | Prefer a cash-secured short put over buying shares when option chain data is available |
| `allow_share_buy` | `true` | Allow `BUY_SHARES` trade type |
| `allow_short_put` | `true` | Allow `SELL_CASH_SECURED_PUT` trade type |
| `avoid_earnings_within_days` | `7` | Reject candidates whose earnings date is within this many days (in either direction) |
| `use_limit_orders_only` | `true` | Always use limit orders; market orders are never placed |
| `emergency_stop_file` | `EMERGENCY_STOP` | Path to the emergency stop sentinel file |
| `audit_log_dir` | `logs` | Directory for JSONL audit log files |
| `symbol_whitelist` | `null` | When set, only these symbols are eligible (list of tickers) |
| `symbol_blacklist` | `[]` | Symbols permanently excluded from autonomous trading |

#### Runner Configuration (`AutonomousRunnerConfig`)

These settings control the paper-only runner that wraps the engine with additional safety gates.

| Parameter | Default | Environment Variable | Description |
|-----------|---------|---------------------|-------------|
| `runner_enabled` | `false` | `AUTONOMOUS_RUNNER_ENABLED` | Master on/off switch. Set `true` to allow paper execution. |
| `paper_only` | `true` | — | Runner refuses to act unless connected to the IBKR paper account. |
| `buy_shares_only` | `true` | — | Only `BUY_SHARES` trades are eligible in the current paper MVP. |
| `max_new_trades_per_run` | `1` | — | Maximum new trades a single `run_once` call may open |
| `max_open_autonomous_trades` | `1` | — | Maximum number of simultaneously open autonomous positions |
| `max_holding_days` | `5` | — | Automatically exit a position after this many calendar days |
| `run_during_market_hours_only` | `true` | — | Reserved for future enforcement of market-hours guard |
| `avoid_first_minutes_after_open` | `15` | — | Reserved: minutes after market open to skip |
| `avoid_last_minutes_before_close` | `15` | — | Reserved: minutes before market close to skip |
| `trade_store_path` | `logs/autonomous_trades.jsonl` | — | Path to the trade lifecycle store (JSONL) |

**To enable paper execution**, add this to your `.env`:

```bash
AUTONOMOUS_RUNNER_ENABLED=true
```

Restart the web server for the change to take effect. All other defaults remain safely conservative.

---

### 11.8 Signal Providers & Candidate Ranking

#### What is a Signal Provider?

The engine does not perform technical analysis itself — it delegates that to a pluggable `SignalProvider`. This separation means:

- The engine's safety logic, ranking, and planning can be tested in isolation.
- You can swap in a different analysis engine without touching the orchestration code.
- The same analysis that powers the **S&P 500 Screener** page is reused for autonomous candidate generation.

#### The Production Provider: `TechnicalAnalysisSignalProvider`

When the S&P 500 screener service is active, the autonomous engine automatically uses `TechnicalAnalysisSignalProvider`. This provider maps screener rows to `CandidateSignal` objects using the following rules:

| Condition | Meaning |
|-----------|---------|
| `momentum_label == "Confirmed Rebound"` | Price is above the 5-day SMA with two consecutive higher closes — an early-stage recovery signal |
| `quality_label == "Strong"` | The stock passed the fundamentals-based quality threshold in the screener |
| Both conditions met → `strength_score = 100` | Qualifies as a `Strong(100) / Confirmed Rebound` candidate |
| Either condition missing → `strength_score = 0` | Rejected by the ranker's `min_signal_strength` filter |

> **Dashboard indicator:** The Status panel shows `TechnicalAnalysisSignalProvider` when the production provider is active. If it shows `StaticSignalProvider` with a ⚠ warning, the screener service is not reachable and all scan/propose calls will return `no_candidate` until it is available.

#### Candidate Ranking

After the scanner collects signals, the **Ranker** applies filters and scoring:

**Hard filters (must all pass):**
1. `strength_score >= min_signal_strength` (default: 100)
2. `signal_label == required_signal_label` (default: `"Confirmed Rebound"`)
3. `volume_ok == True` — sufficient trading volume
4. `trend_ok == True` — price is in an acceptable trend context
5. No earnings within `avoid_earnings_within_days` (default: 7 days)
6. Existing position in the symbol is not already at `max_new_position_pct` of equity

**Scoring (higher = better rank):**

| Component | Weight | Rule |
|-----------|--------|------|
| Signal strength | Dominant | `score = strength_score` (base) |
| Proximity to support | Up to +0.20 | Price closer to support = higher score; price at or below support scores maximum |
| Room to resistance | Up to +0.30 | Larger gap between current price and resistance = higher score |

Rejected candidates and their rejection reasons are visible in the **Audit Log** and on the dashboard's **Rejected Candidates** panel — useful for understanding what the engine considered and why it passed.

---

### 11.9 Trade Planning

The **TradePlanner** converts the top-ranked candidate plus your deployable cash into a concrete `TradePlan`. It never places orders; it purely calculates what to do and exposes that as a data structure.

#### Trade Types

| Trade Type | When Used | Requirements |
|-----------|-----------|-------------|
| `SELL_CASH_SECURED_PUT` | Preferred when `prefer_cash_secured_put=True` and option chain data is available | Strike must be ≤ support price; deployable cash ≥ `strike × 100 × contracts` |
| `BUY_SHARES` | Default fallback; also used when no option chain data is available or CSP conditions aren't met | Deployable cash ≥ `quantity × limit_price` |

#### What a `TradePlan` Contains

| Field | Description |
|-------|-------------|
| `symbol` | Ticker (e.g. `AAPL`) |
| `trade_type` | `BUY_SHARES` or `SELL_CASH_SECURED_PUT` |
| `action` | `BUY` (shares) or `SELL` (short put) |
| `quantity` | Number of shares (for `BUY_SHARES`) |
| `limit_price` | Limit order price — never a market order |
| `target_price` | Take-profit price target |
| `stop_price` | Stop-loss price level |
| `required_cash` | Cash that must be available before the order can proceed |
| `contracts` | Number of option contracts (for `SELL_CASH_SECURED_PUT`) |
| `strike` | Option strike price (for `SELL_CASH_SECURED_PUT`) |
| `expiry` | Option expiry date (for `SELL_CASH_SECURED_PUT`) |
| `reason` | Human-readable explanation of why this plan was chosen |
| `risk_notes` | List of risk considerations |
| `exit_plan` | Plain-English description of the exit strategy |

#### Position Sizing

For `BUY_SHARES`, the quantity is sized so that `quantity × limit_price` does not exceed:

```
min(deployable_cash, max_new_position_pct × equity)
```

This ensures no single autonomous trade consumes more than the configured fraction of your account equity, regardless of how much cash is available.

---

### 11.10 Trade Lifecycle & Exit Management

#### Trade States

Every autonomous paper trade flows through these states:

```
  OPEN ──→ EXIT_PENDING ──→ CLOSED
   │                           ↑
   └─────────────────────────→ FAILED
```

| State | Meaning |
|-------|---------|
| `OPEN` | Entry order placed; position is open and being monitored by the exit manager |
| `EXIT_PENDING` | Exit order submitted; waiting for fill confirmation |
| `CLOSED` | Exit filled; trade complete (realised P&L available) |
| `FAILED` | Entry or exit order encountered an unrecoverable error |

#### Exit Conditions (checked by `AutonomousExitManager`)

The exit manager evaluates every `OPEN` trade on each cycle. It will submit a paper SELL limit order when any of these conditions is met:

| Exit Type | Trigger | Priority |
|-----------|---------|----------|
| `TAKE_PROFIT` | `current_price >= target_price` | Checked first |
| `STOP_LOSS` | `current_price <= stop_price` | Checked second |
| `TIME_EXIT` | Position has been open for ≥ `max_holding_days` calendar days | Checked third |
| `RISK_EXIT` | Emergency stop file exists **or** the `RiskManager` raises a risk flag | Checked fourth |

**Important safety rule:** The exit manager **never guesses prices**. If a live price is unavailable for any reason (including during a `RISK_EXIT`), the trade stays `OPEN` and a `NO_PRICE_AVAILABLE` note is written to the audit log. The exit will be attempted again on the next cycle when live data is available.

#### The Trade Store

All autonomous paper trades are persisted to `logs/autonomous_trades.jsonl`. This is an append-only JSONL file where:

- An `"op": "OPEN"` line records the full trade snapshot when entered.
- `"op": "UPDATE"` lines record each state change (filled price, exit reason, realised P&L, etc.).

On restart, the runner replays this log to reconstruct the full current state of open trades — daily trade limits and open position counts survive restarts.

To view all trades:

```http
GET /api/autonomous/trades
```

---

### 11.11 The Autonomous Trading Dashboard

Navigate to **Autonomous Trading** in the left navigation bar to access the full dashboard. It has four panels:

#### Status Panel

Shows a real-time snapshot of the system's readiness:

| Indicator | Green ✅ | Red ❌ |
|-----------|---------|-------|
| Connected | IBKR connection is active | Not connected |
| Paper Mode | Connected to paper account | Connected to live, or not connected |
| Paper Adapter Ready | Adapter wired and operational | Adapter not available |
| Signal Provider Ready | Production `TechnicalAnalysisSignalProvider` active | Using stub `StaticSignalProvider` |
| Emergency Stop | Not active | `EMERGENCY_STOP` file exists |
| Runner Enabled | `runner_enabled = True` | Runner disabled in config |
| Open Trades | Below `max_open_autonomous_trades` | At or above limit |

A single ❌ gate prevents paper execution from proceeding. The reasons list tells you exactly what to fix.

#### Scan & Propose Panel

| Button | What Happens |
|--------|-------------|
| **Scan Universe** | Runs the scanner and ranker; returns ranked candidates and rejected symbols with reasons. No trade planned, no order placed. |
| **Propose Trade** | Runs the full pipeline (scan → rank → plan); returns a complete `TradePlan`. No order placed. |
| **Execute Paper Trade** | Runs the full pipeline and submits the order to your IBKR paper account. Requires all readiness gates to be green and `runner_enabled = True`. |

#### Open Trades Panel

Displays all trades currently in `OPEN` or `EXIT_PENDING` state:

| Column | Description |
|--------|-------------|
| Symbol | Ticker |
| Entry | Entry limit price and time |
| Type | `BUY_SHARES` or `SELL_CASH_SECURED_PUT` |
| Target / Stop | Take-profit and stop-loss levels |
| Status | `OPEN` or `EXIT_PENDING` |
| Days Held | Days since entry |

#### Audit Log Panel

Shows the last 50 entries from the daily JSONL audit log. Each entry records the full decision context: which candidate was selected, why others were rejected, what plan was produced, and whether execution succeeded.

---

### 11.12 REST API Reference

All autonomous endpoints are under `/api/autonomous/`. They require authentication (same cookie or token used by the rest of the dashboard).

#### `GET /api/autonomous/status`

Returns the current configuration, emergency stop state, signal provider status, and paper adapter readiness.

```json
{
  "config": { "mode": "recommend_only", "max_trades_per_day": 1, "..." : "..." },
  "emergency_stop_file_exists": false,
  "paper_adapter_configured": true,
  "connected": true,
  "connection_env": "paper",
  "signal_provider": "TechnicalAnalysisSignalProvider",
  "signal_provider_ready": true
}
```

#### `POST /api/autonomous/scan`

Runs the scanner and ranker (no trade planning, no order). Returns candidates and rejections.

**Request body (all optional):**
```json
{
  "config_overrides": {
    "min_signal_strength": 100,
    "required_signal_label": "Confirmed Rebound"
  }
}
```

**Response:**
```json
{
  "status": "ok",
  "candidates": [
    { "symbol": "AAPL", "score": 100.25, "strength_score": 100, "signal_label": "Confirmed Rebound" }
  ],
  "rejected": [
    { "symbol": "TSLA", "reason": "earnings within 7 days" }
  ]
}
```

#### `POST /api/autonomous/propose`

Runs the full pipeline in `recommend_only` mode — returns a complete `TradePlan` without placing any order.

**Request body (all optional):**
```json
{ "config_overrides": { "max_new_position_pct": 0.08 } }
```

**Response:**
```json
{
  "status": "proposed",
  "decision": {
    "status": "recommended",
    "candidate": { "symbol": "AAPL", "last_price": 182.50 },
    "plan": {
      "symbol": "AAPL",
      "trade_type": "BUY_SHARES",
      "action": "BUY",
      "quantity": 54,
      "limit_price": 182.00,
      "target_price": 196.00,
      "stop_price": 170.00,
      "required_cash": 9828.00
    }
  }
}
```

#### `POST /api/autonomous/execute-paper`

Runs the engine directly in `paper_execute` mode — hardcoded; the mode cannot be overridden. Submits a limit order to the IBKR paper account via the configured `AutonomousPaperAdapter`. This endpoint bypasses the runner's readiness gates (see `runner/run-once-paper` below for the fully-gated version).

Requires an active paper connection and a configured paper adapter. Returns `EXECUTION_FAILED` (not an HTTP error) if the adapter is absent.

```json
POST /api/autonomous/execute-paper
{ "confirm": true }
```

#### `POST /api/autonomous/runner/run-once-paper`

Runs one full paper-autonomous cycle through the `AutonomousPaperRunner` — the **recommended endpoint** for paper execution. Enforces all readiness gates (connection, paper mode, runner enabled, open-trade limit, daily trade limit) before calling the engine. Records the trade in the trade store on success.

Requires:
- `AUTONOMOUS_RUNNER_ENABLED=true`
- Active paper connection (port `7497`)

**Response (success):**
```json
{
  "status": "executed",
  "trade": {
    "autonomous_trade_id": "abc123",
    "symbol": "AAPL",
    "status": "OPEN",
    "entry_order_id": 42,
    "entry_limit_price": 182.00,
    "quantity": 54
  }
}
```

**Response (gate failure):**
```json
{
  "status": "rejected",
  "rejection_reason": "not_paper_mode",
  "gates": {
    "connected": true,
    "paper_mode": false,
    "reasons": ["Not connected to paper account"]
  }
}
```

#### `POST /api/autonomous/emergency-stop`

Creates the `EMERGENCY_STOP` sentinel file. Takes effect immediately for all subsequent engine and exit-manager calls.

```json
{ "status": "emergency_stop_activated" }
```

#### `GET /api/autonomous/audit`

Returns up to the last 200 entries (default 20; pass `?limit=N`) from today's audit log file, in reverse-chronological order. Each entry is a full decision record. Read-only.

#### `GET /api/autonomous/runner/trades`

Returns all autonomous trades replayed from the trade store, grouped by status.

```json
{
  "open": [ { "autonomous_trade_id": "abc123", "symbol": "AAPL", "status": "OPEN", "..." : "..." } ],
  "exit_pending": [],
  "closed": [ { "autonomous_trade_id": "def456", "symbol": "MSFT", "status": "CLOSED", "realised_pnl": 320.00, "exit_reason": "TAKE_PROFIT" } ],
  "counts": { "open": 1, "exit_pending": 0, "closed": 1, "total": 2 }
}
```

#### `POST /api/autonomous/runner/evaluate-exits`

Manually triggers the exit manager to evaluate all open trades. Returns a list of `ExitDecision` objects — one per open trade, whether or not an exit was submitted.

```json
{
  "decisions": [
    { "autonomous_trade_id": "abc123", "symbol": "AAPL", "decision": "NO_EXIT", "reason": "price 185.00 below target 196.00" }
  ],
  "count": 1
}
```

#### `GET /api/autonomous/runner/status`

Returns the runner's readiness gates snapshot — useful for programmatic health checks.

#### Allowed `config_overrides` Fields

Only the following fields are accepted in request bodies to prevent privilege escalation:

| Field | Type | Notes |
|-------|------|-------|
| `mode` | string | `"recommend_only"`, `"paper_execute"`, `"assisted_live"` |
| `allow_live_execution` | boolean | Must also have backend config enabled |
| `require_user_confirmation` | boolean | |
| `max_trades_per_day` | integer | |
| `max_new_position_pct` | float | Must be in (0, 1] |
| `min_deployable_cash` | float | |
| `min_signal_strength` | integer | |
| `required_signal_label` | string | |

The `emergency_stop_file` and `audit_log_dir` paths are **never** overridable from the request body.

---

### 11.13 The Audit Log

Every autonomous cycle appends one JSON line to a daily log file:

```
logs/autonomous_trading_YYYYMMDD.jsonl
```

Each line contains a full decision record regardless of outcome — executed trades **and** every rejection are recorded. Example entry:

```json
{
  "timestamp": "2025-11-15T09:32:11.042Z",
  "config": { "mode": "paper_execute", "max_trades_per_day": 1 },
  "decision": {
    "status": "paper_executed",
    "candidate": { "symbol": "AAPL", "strength_score": 100, "signal_label": "Confirmed Rebound" },
    "plan": { "trade_type": "BUY_SHARES", "quantity": 54, "limit_price": 182.00 },
    "execution_result": { "order_id": 42, "status": "submitted" }
  },
  "rejected_candidates": [
    { "symbol": "TSLA", "reason": "earnings within 7 days" },
    { "symbol": "NVDA", "reason": "symbol already over-concentrated in portfolio" }
  ]
}
```

**Why the audit log matters:**

- The engine counts executions from the audit log to enforce `max_trades_per_day` **across process restarts** — if you restart the server mid-day, the daily limit is preserved.
- Missing or unreadable audit log files are treated as zero (the engine never refuses to start because a log is unavailable).
- Logs rotate daily. Older files accumulate in the `logs/` directory and can be archived or deleted as needed.

To view recent audit log entries from the dashboard, open the **Audit Log** panel on the Autonomous Trading page. To query via the API: `GET /api/autonomous/audit`.

---

### 11.14 Progressing to Live Execution

> ⚠️ **Live trading puts real money at risk. This section is for experienced users only. Paper trade extensively before proceeding.**

Live execution via `assisted_live` mode has multiple independent safeguards that must all be satisfied simultaneously. There is no single toggle that "enables live trading."

#### Checklist Before Considering Live Execution

- [ ] **Paper trade success:** Run in `paper_execute` mode for at least 30 consecutive trading days with net-positive results
- [ ] **Manual review:** Review every audit log entry from your paper period. Understand every rejection and every exit reason.
- [ ] **Drawdown test:** Confirm the autonomous strategy stayed within acceptable drawdown during your paper period (check the Risk page)
- [ ] **Emergency stop test:** Deliberately trigger and clear the emergency stop at least once to confirm you can halt the system
- [ ] **Capital adequacy:** Ensure your live account has sufficient capital for the `max_new_position_pct` limit to leave meaningful room for diversification
- [ ] **Understand exit timing:** The exit manager only runs when you call it (no automatic background scheduler by default). Decide how often you will trigger it.

#### Enabling Live Execution

**Step 1 — Set backend config:**

In your `.env`:
```bash
AUTONOMOUS_RUNNER_ENABLED=true
```

In `config/live.py` or your Flask app config, set:
```python
autonomous_engine_config = {
    "mode": "assisted_live",
    "allow_live_execution": True,
    "require_user_confirmation": True,   # keep True
    "max_trades_per_day": 1,
    "max_new_position_pct": 0.10,
}
```

**Step 2 — Connect to the live account:**

Switch TWS to Live mode (port `7496`). In the dashboard Settings, set Environment to `live` and Port to `7496`.

**Step 3 — Execute with explicit confirmation:**

Live execution via `assisted_live` mode is invoked programmatically through the engine (the `/api/autonomous/execute-paper` endpoint is hardcoded to `paper_execute` mode and cannot run live trades). Use the engine directly in application code with:

```python
from autonomous.autonomous_config import AutonomousMode, AutonomousTradingConfig
from autonomous.autonomous_engine import AutonomousTradingEngine

config = AutonomousTradingConfig(
    mode=AutonomousMode.ASSISTED_LIVE,
    allow_live_execution=True,
    require_user_confirmation=True,
)
engine = AutonomousTradingEngine(config=config, ...)
decision = engine.run_once(confirm=True)   # confirm=True required
```

Without `confirm=True`, the engine returns `rejected` even in `assisted_live` mode.

**Step 4 — Monitor closely:**

- Check the audit log after every execution
- Verify orders appear in your IBKR account immediately
- Have the emergency stop one click away at all times

---

### 11.15 Troubleshooting

#### "All gates show green but Execute Paper Trade returns `runner_disabled`"

The runner requires `AUTONOMOUS_RUNNER_ENABLED=true` in the environment. Check your `.env` file and restart the web server.

```bash
grep AUTONOMOUS_RUNNER_ENABLED .env   # should output: AUTONOMOUS_RUNNER_ENABLED=true
python scripts/run_web.py
```

#### "Scan returns `no_candidate` every time"

The signal provider is returning no qualifying signals. Check:

1. **Status panel:** Is `signal_provider_ready: true`? If not, the `StaticSignalProvider` stub is active — the S&P 500 screener service is not available.
2. **Screener page:** Open the S&P 500 Screener page. If it shows no `Strong` / `Confirmed Rebound` rows, there are genuinely no qualifying candidates today.
3. **Signal threshold:** Your `min_signal_strength` may be too high. The default is `100`, which only accepts the `Strong(100) / Confirmed Rebound` label.
4. **Universe connectivity:** Run `python scripts/connection_test.py` to verify the IBKR connection is live.

#### "Emergency stop is active but I did not trigger it"

The `EMERGENCY_STOP` file may have been created by the risk monitoring system or a previous manual stop. Check and remove it:

```bash
ls -la EMERGENCY_STOP         # confirm it exists
cat EMERGENCY_STOP            # read any message written to it
rm EMERGENCY_STOP             # remove to re-enable
```

Then call `GET /api/autonomous/status` to confirm `emergency_stop_file_exists: false`.

#### "Paper adapter not ready"

This means either:

1. You are not connected to the IBKR paper account (check that TWS is in Paper mode on port `7497`).
2. TWS Robot is connected but the paper adapter failed to initialise — check the web server logs for a Python traceback.

#### "Trade stuck in `EXIT_PENDING` for a long time"

`EXIT_PENDING` means the exit order was submitted but a fill confirmation has not been received. This can happen when:

- The limit price is away from the market (common for limit sells above the current price).
- The paper account simulation has not matched the order yet.

Check the **Positions** page for the exit order status. You can also cancel the pending exit order and let the exit manager re-evaluate on the next cycle.

#### "Audit log is empty"

If no cycles have been run today, the daily log file does not exist (it is created on the first write). Run a scan or propose call to generate the first entry.

---

### 11.16 Frequently Asked Questions

**Q: Is autonomous trading the same as "set it and forget it"?**

**A:** No. TWS Robot's autonomous module is a decision-support tool that requires active oversight. There is no background scheduler that triggers automatically — you (or a cron job you set up) must call `run_once` or use the dashboard button. This is intentional: the system is designed to remove execution friction, not human judgment.

**Q: How many trades will it place per day?**

**A:** At most `max_trades_per_day` (default: 1). The daily count persists across server restarts via the audit log. On days when the scanner finds no qualifying candidates, no trade is placed and the engine returns `no_candidate`.

**Q: What happens if I have no deployable cash?**

**A:** The engine returns `insufficient_cash` and records the rejection in the audit log. No order is placed. See [§10.1 Cash Availability](#101-cash-availability--deployable-capital) for how to interpret your deployable cash figure.

**Q: Can I run it on non-S&P 500 stocks?**

**A:** The `stock_universe` config currently only supports `sp500`. Support for other universes (e.g. STI, HKEX) is planned. You can use the `symbol_whitelist` option to restrict the scan to a custom subset of the S&P 500.

**Q: What if my put gets assigned?**

**A:** Assignment of a `SELL_CASH_SECURED_PUT` position is handled outside the autonomous module at this stage — it results in a long stock position in your IBKR account that you would manage manually. The trade store records the original put entry; no automatic management of an assigned position is currently implemented.

**Q: Can I use it with a margin account?**

**A:** The cash sizing logic (`required_cash = strike × 100 × contracts` for puts; `quantity × limit_price` for shares) assumes cash collateralisation, not margin. Using margin could lead to larger positions than intended. Ensure your `max_new_position_pct` limit reflects your actual risk appetite.

**Q: How do I add my own signal provider?**

**A:** Create a class implementing the `SignalProvider` protocol (a single `analyze(symbol: str) -> Optional[CandidateSignal]` method), then register it in your Flask app config:

```python
app.config["autonomous_signal_provider"] = MyCustomProvider()
```

The engine will use your provider instead of `TechnicalAnalysisSignalProvider`.

**Q: Can I back-test the autonomous strategy?**

**A:** Not directly via the Autonomous Trading module — the engine is designed for live/paper execution. However, you can replay your audit logs to analyse past decisions, or wire the technical analysis signal conditions into the main **Backtest** module to simulate the `Strong(100) / Confirmed Rebound` entry criteria historically.

---

## 12. Order Management

### Viewing Orders

Open the **Positions** page to see the full order history, including status for each order:

| Status | Meaning |
|--------|---------|
| `RECORDED` | Order captured locally, not yet sent to broker |
| `SUBMITTED` | Order forwarded to Interactive Brokers |
| `FILLED` | Order fully executed |
| `CANCELLED` | Order cancelled (by you or the system) |
| `REJECTED` | Broker or pre-trade check rejected the order |

### Cancelling an Order

From the Positions page, click **Cancel** next to any open order. Alternatively, use the API:

```
DELETE /api/orders/<order_id>
```

**Cancellation behaviour:**

| Order Type | What Happens |
|-----------|-------------|
| `local_only` (no broker ID) | Marked `CANCELLED` locally; a `warning` field explains no broker action was taken |
| `broker` order (has broker ID) | Cancel request forwarded to TWS via `TWSBridge.cancel_order()`; status becomes `cancel_requested` |
| Terminal status (FILLED / CANCELLED / REJECTED) | Returns HTTP 409 Conflict — nothing to cancel |

### Manual Order Recording

You can record a manual order through the API (local-only, not sent to broker):

```
POST /api/orders/
{
    "symbol": "AAPL",
    "action": "BUY",
    "quantity": 10,
    "order_type": "MARKET",
    "limit_price": null
}
```

The order passes through the same risk and emergency-stop gates as strategy-generated orders.

---

## 13. Command-Line Tools

All scripts live in the `scripts/` directory. Run them from the project root with your virtual environment activated.

| Script | What It Does |
|--------|-------------|
| `python scripts/run_web.py` | Start the Flask web dashboard (http://127.0.0.1:5000) |
| `python scripts/quick_start.py` | Run a Moving Average backtest in ~5 minutes |
| `python scripts/strategy_selector.py` | Interactive guide to pick the right strategy |
| `python scripts/run_live.py` | Launch a paper or live trading session |
| `python scripts/check_account.py` | Show account balance, positions, and P&L (needs TWS) |
| `python scripts/market_status.py` | Report whether the market is currently open |
| `python scripts/download_real_data.py AAPL MSFT` | Download historical OHLCV data for given symbols |
| `python scripts/connection_test.py` | Test the TWS API connection |
| `python scripts/init_database.py` | Initialise the local SQLite database |

### Example Scripts

| Script | What It Shows |
|--------|--------------|
| `python examples/example_strategy_templates.py` | All three backtest strategies in action |
| `python examples/example_profile_comparison.py` | Conservative vs. Aggressive risk profile comparison |

### `tws_client.py` Direct Options

```bash
python tws_client.py                      # Run with default environment (from .env)
python tws_client.py --env paper          # Paper trading
python tws_client.py --env live           # Live trading
python tws_client.py --show-config        # Print current configuration
python tws_client.py --timeout 60         # Run for 60 seconds then exit
python tws_client.py --skip-market-check  # Skip market hours check
```

---

## 14. Your Weekly Routine

### Daily (5 minutes)

1. Glance at the **Dashboard** — confirm the system is connected and running
2. Check **Daily P&L** in the status bar
3. Scan for any **Alerts** at the bottom of the Dashboard

### Weekly (15–20 minutes)

**Monday morning:**
1. Open the dashboard: `python scripts/run_web.py` → http://127.0.0.1:5000
2. Review last week's performance on the **Dashboard** page
3. Check the **Risk** page — is drawdown within comfortable limits?
4. Look at the **Positions** page — any stale or oversized positions?

**End of week:**
1. Review the **Events & Logs** page for any warnings or errors you may have missed
2. Check the **Account Intelligence** page for cash management and opportunity alerts

### Monthly (30–60 minutes)

1. Run fresh backtests from the **Backtest** page on recent data
2. Compare strategy performance vs. buy-and-hold (benchmark)
3. Decide: keep running, adjust parameters, or pause the strategy
4. Review the **Performance Benchmarking** module in Account Intelligence

### When to Stop a Strategy

Stop using a strategy (or pause it for review) if you observe:
- ❌ 5 or more consecutive losing trades
- ❌ Drawdown exceeding 10% of your account
- ❌ Win rate drops below 40% over a 30-day window
- ❌ Sharpe ratio falls below 0.5
- ❌ The strategy keeps losing money for 2 consecutive months

When in doubt, stop first and investigate.

---

## 15. Troubleshooting

### "ModuleNotFoundError: No module named 'backtest'"

```bash
# Make sure you're in the project directory
cd tws_robot

# Activate the virtual environment
.\venv\Scripts\Activate.ps1    # Windows
source venv/bin/activate        # macOS / Linux

# Reinstall dependencies
pip install -r requirements.txt
```

### "Connection refused" when connecting to TWS

1. Ensure TWS or IB Gateway is **running and logged in**
2. Enable the API in TWS: *Edit → Global Configuration → API → Settings*
   - ✅ Enable ActiveX and Socket Clients
   - ✅ Add `127.0.0.1` to Trusted IP addresses
3. Confirm you are using the correct port:
   - Paper trading: **7497**
   - Live trading: **7496**
4. Check `.env` matches the settings above

### "No data available" during backtest

```bash
# Download data for the symbols you want to test
python scripts/download_real_data.py AAPL MSFT GOOGL
```

### Web dashboard shows blank pages or 500 errors

1. Check the terminal where `run_web.py` is running for error messages
2. Increase log verbosity: set `LOG_LEVEL=DEBUG` in `.env`
3. Go to **Events & Logs** in the dashboard for real-time log output

### AI features not working

1. Make sure `OPENAI_API_KEY` is set in `.env` with a valid key
2. Restart the web server after editing `.env`
3. The AI Chat page will display "AI not enabled" if the key is missing or invalid

### Tests failing

```bash
# Clear cache and rerun all tests
python -m pytest --cache-clear

# Run a specific test file with verbose output
python -m pytest tests/test_backtest_engine.py -v

# Run only the web API tests
python -m pytest tests/test_web_api.py -v
```

More help:
- [Debugging Strategies Guide](docs/runbooks/debugging-strategies.md)
- [Emergency Procedures](docs/runbooks/emergency-procedures.md)
- [TWS Connection Guide](docs/TWS_CONNECTION_GUIDE.md)

---

## 16. Frequently Asked Questions

### Do I need to know how to code?

**No.** The web dashboard lets you run backtests, manage strategies, monitor positions, and view analytics entirely from your browser. No terminal experience is required after the one-time installation.

For power users, all features are also accessible via command-line scripts and a REST API.

### Do I need Interactive Brokers?

- **Backtesting:** No broker connection needed — runs entirely offline on historical data
- **Paper trading:** Yes — TWS Paper Trading mode (port 7497)
- **Live trading:** Yes — TWS with a funded live account (port 7496)

See the [TWS Connection Guide](docs/TWS_CONNECTION_GUIDE.md) for step-by-step setup.

### How much capital do I need?

| Mode | Minimum |
|------|---------|
| Backtesting | $0 (simulated) |
| Paper trading | $0 (simulated account) |
| Live trading | $10,000 recommended |

The $10,000 minimum for live trading allows proper diversification across 2–3 positions while keeping commissions manageable.

### Which strategy should I start with?

1. **Completely new to algo trading?** Run `python scripts/strategy_selector.py` for a guided recommendation
2. **Want proven results?** Backtest all strategies: `python examples/example_strategy_templates.py`
3. **Ready to trade live?** Use **Bollinger Bands** with the **Conservative** risk profile

### Can I run multiple strategies at once?

Yes. In fact, running complementary strategies reduces reliance on any single approach:

- Moving Average Crossover works well in trending markets
- Mean Reversion works well in choppy, range-bound markets
- Running both means at least one is likely working at any given time

### How do I add my own strategy?

See [`docs/runbooks/adding-new-strategy.md`](docs/runbooks/adding-new-strategy.md) for a full walkthrough. In brief:
1. Create a new class in `strategies/` that inherits from the base strategy class
2. Implement `generate_signals()` and `on_bar()` methods
3. Register it in `strategies/strategy_registry.py`
4. Add a corresponding backtest template in `backtest/strategy_templates.py` if needed

### What are realistic return expectations?

| Performance Level | Annual Return |
|------------------|--------------|
| S&P 500 buy-and-hold average | ~10% |
| Good algorithmic strategy | 10–20% |
| Great algorithmic strategy | 20–30% |
| **Be very cautious above** | **30%+** |

The goal is **consistent, risk-adjusted returns** — not maximum returns. A strategy with a 15% return and a Sharpe ratio of 1.5 is far better than one with 25% returns and a Sharpe ratio of 0.4.

### What happens if I lose internet connection during live trading?

TWS Robot communicates with IB's TWS desktop application, which runs locally on your machine. A brief internet outage will not affect orders already submitted to Interactive Brokers' servers. However, new signals will not be generated until the connection is restored. The system logs a connection error and retries automatically.

---

## Additional Resources

| Document | Purpose |
|----------|---------|
| [README.md](README.md) | Quick start and project overview |
| [docs/GETTING_STARTED_30MIN.md](docs/GETTING_STARTED_30MIN.md) | Complete beginner tutorial (30 minutes) |
| [docs/TWS_CONNECTION_GUIDE.md](docs/TWS_CONNECTION_GUIDE.md) | Step-by-step TWS setup guide |
| [docs/QUICK_REFERENCE.md](docs/QUICK_REFERENCE.md) | Commands and config cheat sheet |
| [docs/API_REFERENCE.md](docs/API_REFERENCE.md) | Developer API documentation |
| [docs/WEB_API_REFERENCE.md](docs/WEB_API_REFERENCE.md) | REST API reference for the web dashboard |
| [docs/CONTRIBUTING.md](docs/CONTRIBUTING.md) | How to contribute to TWS Robot |
| [docs/runbooks/debugging-strategies.md](docs/runbooks/debugging-strategies.md) | Troubleshooting guide |
| [docs/runbooks/emergency-procedures.md](docs/runbooks/emergency-procedures.md) | Crisis management procedures |
| [prime_directive.md](prime_directive.md) | Development standards and safety rules |
| [DISCLAIMER.md](DISCLAIMER.md) | Full risk and legal disclaimer |

---

*TWS Robot is experimental open-source software provided as-is, without warranties. Always paper trade first. Never trade with money you cannot afford to lose.*
