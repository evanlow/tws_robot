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
11. [Order Management](#11-order-management)
12. [Command-Line Tools](#12-command-line-tools)
13. [Your Weekly Routine](#13-your-weekly-routine)
14. [Troubleshooting](#14-troubleshooting)
15. [Frequently Asked Questions](#15-frequently-asked-questions)

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
| `TWS_ADMIN_PASSWORD` | `changeme` | Web dashboard login password |
| `SECRET_KEY` | *(random)* | Flask session secret — **change in production** |
| `OPENAI_API_KEY` | *(unset)* | Your OpenAI API key — required to enable AI features |
| `OPENAI_MODEL` | `gpt-4o` | OpenAI model used for AI chat and insights |
| `LOGIN_DISABLED` | *(unset)* | Set to `true` to bypass auth in local development |

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

## 11. Order Management

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

## 12. Command-Line Tools

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

## 13. Your Weekly Routine

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

## 14. Troubleshooting

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

## 15. Frequently Asked Questions

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
