# Configuration Guide

This document is the canonical reference for runtime configuration in TWS Robot.
It focuses on environment variables and `.env` settings that are read by the
current codebase.

If a value here conflicts with an example elsewhere, trust the code-backed
default documented here and treat the older example as drift until updated.

## Scope

This guide covers:

- Environment variables loaded from `.env` or the process environment
- Default values used by the current codebase
- Safety impact for paper/live/autonomous trading
- High-level configuration topics that affect operator behavior

This guide does not try to document internal `current_app.config[...]` test or
injection hooks. Those are application wiring points, not operator-facing
environment settings.

Last reviewed against code: 2026-06-26.

## Configuration Flow

Primary sources and precedence:

1. The web app loads `.env` with `load_dotenv(override=True)` in normal runs.
2. Code reads environment variables with safe defaults when keys are unset.
3. Some CLI paths still allow explicit flags such as `--env paper|live`.
4. Tests and advanced integrations may override behavior through Flask config.

## Quick Start

1. Copy `.env.example` to `.env`.
2. Fill in broker account IDs and any credentials you actually use.
3. Keep live trading disabled unless you explicitly intend to enable it.
4. Restart the web server after editing `.env`.

Recommended minimum local setup:

```dotenv
TRADING_ENV=paper
PAPER_HOST=127.0.0.1
PAPER_PORT=7497
PAPER_CLIENT_ID=0
PAPER_ACCOUNT=YOUR_PAPER_ACCOUNT_ID

TWS_ADMIN_USERNAME=admin
TWS_ADMIN_PASSWORD=change-me
SECRET_KEY=replace-with-a-random-secret
```

## Safety Notes

- `LIVE_ACCOUNT` is required when `TRADING_ENV=live`.
- Live autonomous mode is opt-in and gated by multiple explicit switches.
- `ALLOW_YAHOO_FOR_LIVE_TRADING` should remain `false` for live execution.
- In production, set a strong `SECRET_KEY` and do not rely on default auth.
- Do not commit `.env` files, API keys, passwords, or account identifiers.

## Environment Variable Reference

### Core Broker Connection

| Variable | Default | Required | Notes |
|---|---:|---|---|
| `TRADING_ENV` | `paper` | No | Default broker environment. CLI `--env` can override this. |
| `PAPER_HOST` | `127.0.0.1` | No | TWS/IB Gateway host for paper trading. |
| `PAPER_PORT` | `7497` | No | Standard paper API port. |
| `PAPER_CLIENT_ID` | `0` | No | Paper-mode IBKR client ID. |
| `PAPER_ACCOUNT` | `DU2746208` | No | Paper account ID fallback used if not overridden. |
| `LIVE_HOST` | `127.0.0.1` | No | TWS/IB Gateway host for live trading. |
| `LIVE_PORT` | `7496` | No | Standard live API port. |
| `LIVE_CLIENT_ID` | `1` | No | Live-mode IBKR client ID. |
| `LIVE_ACCOUNT` | none | Yes for live | Must be set for live trading. |

### Web, Auth, and Application Security

| Variable | Default | Required | Notes |
|---|---:|---|---|
| `TWS_ADMIN_USERNAME` | `admin` | No | Dashboard login username. |
| `TWS_ADMIN_PASSWORD` | none | One of password or hash | Plain-text dashboard password; hashed at startup if used. |
| `TWS_ADMIN_PASSWORD_HASH` | none | One of password or hash | Preferred over plain-text password when both are present. |
| `ALLOW_DEFAULT_PASSWORD` | `false` | No | Only for local dev/testing when default `changeme` fallback is tolerated. |
| `LOGIN_DISABLED` | `false` | No | Bypasses auth for local development only. |
| `SECRET_KEY` | generated fallback | Yes for production | Flask session secret. Must be strong and explicit in production. |
| `ENVIRONMENT` | unset | No | Set to `production` to enforce stricter security checks. |
| `DISCLAIMER_ACCEPTANCE_FILE` | `disclaimer_acceptance.json` | No | Path to disclaimer acceptance record. |
| `EMERGENCY_STOP_FILE` | `EMERGENCY_STOP` in project root | No | Presence of this file halts automated trading fail-closed. |
| `STRATEGY_DB_PATH` | `strategy_lifecycle.db` near project root | No | Strategy lifecycle SQLite database path. |

### AI Configuration

| Variable | Default | Required | Notes |
|---|---:|---|---|
| `OPENAI_API_KEY` | none | No | When set, AI is auto-enabled unless explicitly disabled. |
| `OPENAI_MODEL` | `gpt-4o` | No | Model name used by the AI client. |
| `AI_ENABLED` | auto | No | Explicit `true`/`false` override for AI enablement. |

### Database

| Variable | Default | Required | Notes |
|---|---:|---|---|
| `DATABASE_URL` | `sqlite:///tws_robot.db` | No | SQLAlchemy connection string. PostgreSQL/MySQL use pooled connections; SQLite is fallback. |

### FX Research Module

| Variable | Default | Required | Notes |
|---|---:|---|---|
| `FX_DATA_MODE` | `not_configured` | No | Allowed: `not_configured`, `demo`, `live_research`. |
| `FX_PROVIDER` | `yfinance` | No | Currently only `yfinance` is supported. |
| `FX_PROVIDER_TIMEOUT_SECONDS` | `10` | No | Provider HTTP timeout in seconds. |

### Cash Availability and Reserve Logic

These settings affect deployable cash calculations and should be reviewed
carefully before enabling any autonomous mode.

| Variable | Default | Required | Notes |
|---|---:|---|---|
| `CASH_RESERVE_MODE` | `gross_assignment` | No | Allowed: `gross_assignment`, `net_premium`, `broker_margin`. |
| `CASH_ACCOUNT_BASE_CURRENCY` | `USD` | No | Base currency assumption used when standardizing deployable cash. |
| `MANUAL_CASH_BUFFER_PCT` | `0.10` | No | Fractional cash buffer, e.g. `0.10` = 10%. |
| `MANUAL_CASH_BUFFER_AMOUNT` | `0` | No | Fixed buffer amount; larger of pct/fixed applies. |
| `OPTION_CONTRACT_MULTIPLIER_DEFAULT` | `100` | No | Fallback shares-per-contract value. |

### Autonomous Paper Runner

| Variable | Default | Required | Notes |
|---|---:|---|---|
| `AUTONOMOUS_RUNNER_ENABLED` | `false` | No | Enables the autonomous paper runner. Safe default is off. |

### Autonomous Live Runner Safety

These are the highest-sensitivity settings in the repository.

| Variable | Default | Required | Notes |
|---|---:|---|---|
| `AUTONOMOUS_LIVE_ENABLED` | `false` | No | Master switch for live autonomous mode. |
| `AUTONOMOUS_LIVE_CONTINUOUS_ENABLED` | `false` | No | Additional gate for repeated live cycles. |
| `AUTONOMOUS_MAX_DEPLOYABLE_CASH_PCT` | `0.005` | No | Per-trade live cap as a fraction of deployable cash. |
| `AUTONOMOUS_MIN_DEPLOYABLE_CASH` | `1000.0` | No | Refuses live trading below this deployable cash floor. |
| `AUTONOMOUS_MAX_OPEN_LIVE_TRADES` | `1` | No | Concurrent open live autonomous trades. |
| `AUTONOMOUS_MAX_LIVE_TRADES_PER_DAY` | `1` | No | Daily live autonomous entry cap. |
| `AUTONOMOUS_LIVE_LIMIT_ORDERS_ONLY` | `true` | No | Market orders are refused when true. |
| `AUTONOMOUS_LIVE_REQUIRE_ACCOUNT_CONFIRMATION` | `true` | No | Caller must confirm expected live account ID. |
| `AUTONOMOUS_REQUIRE_PLAN_STOP_FOR_LIVE` | `true` | No | Prefer planner-provided stop price for live entries. |
| `AUTONOMOUS_REQUIRE_BROKER_PROTECTION_CONFIRMATION` | `true` | No | New live entries require broker-visible protection on existing autonomous positions. |
| `AUTONOMOUS_ALLOW_DUPLICATE_SYMBOL_LIVE_ENTRIES` | `false` | No | Blocks duplicate live entries per symbol when false. |
| `AUTONOMOUS_LIVE_DRY_RUN` | `false` | No | Rehearses live lifecycle without sending orders when true. |
| `AUTONOMOUS_DEFAULT_STOP_PCT` | `0.05` | No | Fallback stop distance when no live stop price is available. |
| `AUTONOMOUS_ORDER_LIFECYCLE_STORE_PATH` | `logs/autonomous_order_lifecycle.jsonl` | No | Append-only live order lifecycle log. |
| `AUTONOMOUS_IDEMPOTENCY_STORE_PATH` | `logs/autonomous_idempotency.jsonl` | No | Append-only idempotency lock store. |
| `AUTONOMOUS_IDEMPOTENCY_STALE_MINUTES` | `120` | No | Stale-lock threshold for idempotency helpers. |
| `LIVE_MARKET_DATA_PROVIDER` | `ibkr` | No | Must remain `ibkr` for live autonomous execution. |
| `ALLOW_YAHOO_FOR_LIVE_TRADING` | `false` | No | Should remain false for live execution safety. |
| `MAX_LIVE_QUOTE_AGE_SECONDS` | `5.0` | No | Diagnostic freshness threshold exposed in live-market-data status. |

### Autonomous Engine, Sizing, and Exit Planning

| Variable | Default | Required | Notes |
|---|---:|---|---|
| `AUTONOMOUS_MAX_NEW_POSITION_PCT` | `0.10` | No | Shared fallback cap for deployable-cash and equity sizing when more specific caps are unset. |
| `AUTONOMOUS_MAX_POSITION_DEPLOYABLE_CASH_PCT` | unset | No | More specific deployable-cash cap; falls back to `AUTONOMOUS_MAX_NEW_POSITION_PCT`. |
| `AUTONOMOUS_MAX_POSITION_EQUITY_PCT` | unset | No | More specific equity cap; falls back to `AUTONOMOUS_MAX_NEW_POSITION_PCT`. |
| `AUTONOMOUS_EXIT_TARGET_MODE` | `resistance` | No | Allowed: `resistance`, `percent`, `adr_intraday`. |
| `AUTONOMOUS_TAKE_PROFIT_PCT` | `0.08` | No | Fixed percentage target and fallback target mode input. |
| `AUTONOMOUS_ADR_LOOKBACK_DAYS` | `0` | No | ADR lookback used by ADR-based exit targeting. `.env.example` suggests `14` as a practical operator override. |
| `AUTONOMOUS_ADR_TARGET_FRACTION` | `0.50` | No | ADR fraction used for target distance. |
| `AUTONOMOUS_ADR_MAX_TARGET_PCT` | `0.03` | No | Upper cap for ADR-derived target move. |
| `AUTONOMOUS_ADR_MIN_TARGET_PCT` | `0.005` | No | Lower floor for ADR-derived target move. |
| `AUTONOMOUS_ADR_RESPECT_RESISTANCE_CAP` | `true` | No | Caps ADR target at resistance when configured. |
| `AUTONOMOUS_MIN_PROFIT_THRESHOLD_USD` | `100.0` | No | Profit threshold used by runner exit logic. |
| `AUTONOMOUS_LIFECYCLE_INTERVAL_SECONDS` | `60` | No | Background lifecycle re-evaluation interval. |

### Commission-Aware Minimum Profitability Gate

| Variable | Default | Required | Notes |
|---|---:|---|---|
| `AUTONOMOUS_COMMISSION_AWARE_SIZING_ENABLED` | `false` | No | Rejects uneconomic trades after commission estimates when enabled. |
| `AUTONOMOUS_ESTIMATED_COMMISSION_PER_ORDER` | `1.0` | No | Flat estimated commission per order leg. |
| `AUTONOMOUS_MIN_NET_PROFIT_USD` | `0.0` | No | Minimum expected net profit after commission. |
| `AUTONOMOUS_MIN_NET_PROFIT_PCT_OF_TRADE` | `0.0` | No | Minimum expected net profit as fraction of trade notional. |

## Template-Only or Legacy Keys

The following keys appear in `.env.example`, local `.env` files, or older docs,
but are not currently consumed as authoritative runtime environment toggles by
the code paths reviewed for this guide:

| Variable | Current status |
|---|---|
| `LOG_LEVEL` | Mentioned in templates/docs, but not read by a central runtime config loader in the current code path review. |
| `ENABLE_CASH_AVAILABILITY_GUARD` | Documented in templates/docs, but no direct environment read was found in the current runtime path review. |
| `BLOCK_AUTOMATED_TRADING_IF_UNCOVERED_SHORT_CALL` | Documented in templates/docs, but no direct environment read was found in the current runtime path review. |
| `BLOCK_AUTOMATED_TRADING_IF_DEPLOYABLE_CASH_NEGATIVE` | Documented in templates/docs, but no direct environment read was found in the current runtime path review. |

Treat these as documentation/template drift until the code is updated to read
them explicitly or the templates are simplified.

## Code-Only Configuration Topics

Some autonomous behavior is configurable in Python dataclasses and route wiring,
but is not currently exposed as environment variables. At the time of writing,
examples include:

- VIX market-regime guard thresholds and size multipliers
- Some execution-quality and market-data health guard thresholds
- Basket-planning and evidence-sizer tuning fields

Those settings still matter, but they are code-default configuration rather
than operator-facing `.env` configuration today.

## Related Documents

- [README.md](../README.md)
- [USER_GUIDE.md](USER_GUIDE.md)
- [ACTUAL_LIVE_TRADING.md](ACTUAL_LIVE_TRADING.md)
- [AUTONOMOUS_TRADING_SYSTEM_SPEC.md](AUTONOMOUS_TRADING_SYSTEM_SPEC.md)
- [TWS_CONNECTION_GUIDE.md](TWS_CONNECTION_GUIDE.md)
