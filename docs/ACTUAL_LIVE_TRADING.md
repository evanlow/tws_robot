# Actual Live Trading — Dashboard Guide

## Overview

The Autonomous Trading dashboard supports three distinct execution modes:

| Mode | Description | Orders to TWS? |
|------|-------------|-----------------|
| **Paper Mode** | Paper (simulated) execution only. | No — paper adapter only |
| **Live Dry-Run** | Live-account rehearsal. Full lifecycle runs but no order leaves to TWS. | No |
| **Actual Live Trading** | Real live autonomous orders submitted to TWS after all safety gates pass. | **Yes — real money at risk** |

## Mode Distinction

### Paper Mode
- Activated when the connected account is a Paper account.
- Uses the "Activate Autonomous Mode" button.
- All trades are simulated via the paper adapter.

### Live Dry-Run
- Activated when the connected account is Live.
- Uses the "Activate Live Dry-Run" button (the primary activation button when live).
- The frontend sends `dry_run: true`.
- The full lifecycle runs (gates, signal evaluation, risk checks) but no order is submitted to TWS.
- Dashboard status chip shows: **LIVE DRY-RUN ON**
- Outcome label: `LIVE_DRY_RUN_PREVIEW_ONLY`

### Actual Live Trading
- Activated via the separate **"🚨 Actual Live Trading"** button (red, visually distinct).
- Visible when:
  - Account context is Live
  - All readiness gates pass
  - For **Continuous Trading** cycle: `AUTONOMOUS_LIVE_CONTINUOUS_ENABLED=true` gate must also pass
- Requires explicit multi-step confirmation (see below).
- The frontend sends `dry_run: false` only through this path.
- Dashboard status chip:
  - Single Trade: **LIVE SINGLE AUTONOMOUS ON**
  - Continuous Trading: **LIVE CONTINUOUS AUTONOMOUS ON**
- Outcome labels: `LIVE_ORDER_SUBMITTED` / `LIVE_ORDER_REJECTED` / `NO_TRADE`

#### Single Trade actual-live
- One entry cycle is executed; bracket exits (target + stop) are submitted atomically.
- After entry, Autonomous Mode stays ON until the bracket child fills, then turns OFF.
- Conservative caps: `max_open_live_trades=1`, `max_live_trades_per_day=1` (hardcoded).

#### Continuous Trading actual-live
- Same as single trade but after the bracket child fills, the lifecycle advancer
  automatically starts the next cycle when gates still pass.
- Requires `AUTONOMOUS_LIVE_CONTINUOUS_ENABLED=true` **and**
  `AUTONOMOUS_MAX_LIVE_TRADES_PER_DAY` > 1 (backend rejects activation if the daily
  cap is still at the default of 1, making continuous impossible).
- Each subsequent cycle rebuilds a verified actual-live `OrderExecutor` using the
  current `TWSBridge`; if this fails (disconnected, wrong environment, account
  mismatch), the system **fails closed** and turns Autonomous Mode OFF.

## Actual Live Trading Confirmation Flow

The operator must provide **all** of the following in the confirmation modal:

1. **Detected live account ID** — typed exactly (compared case-insensitively).
2. **Operator identifier** — a non-empty name identifying who authorized the trade.
3. **Confirmation phrase** — must be typed exactly: `ENABLE ACTUAL LIVE TRADING`
4. **Risk acknowledgement** — checkbox confirming real money is at risk.

The modal title reflects the selected trading cycle:

- **Actual Live Single Trade** — single entry, mode turns OFF after bracket fills.
- **Actual Live Continuous Trading** — additional warning explains that further actual-live
  cycles may start automatically after each bracket fill.

Only after all four fields validate does the frontend submit to the backend.

## Required `.env` Switches

| Variable | Required for | Value |
|----------|-------------|-------|
| `AUTONOMOUS_LIVE_ENABLED` | All actual-live | `true` |
| `AUTONOMOUS_LIVE_CONTINUOUS_ENABLED` | Continuous actual-live | `true` |
| `AUTONOMOUS_MAX_LIVE_TRADES_PER_DAY` | Continuous actual-live | > 1 (e.g. `3`) |
| `AUTONOMOUS_MAX_OPEN_LIVE_TRADES` | All actual-live | Conservative int (default: `1`) |
| `AUTONOMOUS_LIVE_DRY_RUN` | Must be absent/false for actual-live | `false` |

## Backend Architecture

### Endpoint

```
POST /api/autonomous/live/actual-live/activate
```

### Request Body

```json
{
  "confirm": true,
  "account_mode": "live",
  "trading_cycle": "single_trade",
  "expected_account_id": "U1234567",
  "confirmed_by": "Operator Name",
  "confirmation_phrase": "ENABLE ACTUAL LIVE TRADING",
  "acknowledge_real_money_risk": true
}
```

Use `"trading_cycle": "continuous"` for continuous actual-live activation.

### Executor Wiring

The actual-live path constructs a verified `OrderExecutor` via
`_build_actual_live_executor()`, which:

1. Checks `svc.connected` is truthy.
2. Checks `svc.connection_env == 'live'`.
3. Checks detected account ID matches `expected_account_id`.
4. Checks `svc.tws_bridge` is present and connected.
5. Builds **`OrderExecutor(...)`** with:
   - `is_live_mode=True`
   - `require_confirmation=False` — the dashboard confirmation replaces terminal `input()`
   - `dry_run=False`
   - `live_trading_enabled=True`
   - `live_confirmation=LiveTradingConfirmation(...)` — validated per-session token
   - `expected_account_id=<typed_account_id>`
   - `limit_orders_only=live_config.live_limit_orders_only`

This helper is reused by both the initial activation request and subsequent
continuous cycles in `_maybe_advance_live_lifecycle()`.

### Request-Scoped Executor

The actual-live executor is **request-scoped** — it is NOT stored globally.
This prevents dry-run/actual-live bleed-through: a later dry-run activation
can never accidentally reuse a non-dry-run executor from a previous actual-live
session.

### Subsequent Continuous Cycles

After a bracket child fills, `_maybe_advance_live_lifecycle()` is called by
`/live/status` polls. When `state.dry_run is False` (actual-live), the next
cycle calls `_build_actual_live_executor()` again to rebuild a fresh verified
executor. If this fails for any reason, the system **fails closed**: Autonomous
Mode is turned OFF with a clear audit log entry rather than falling back to a
dry-run or no-adapter executor.

### Executor/Runner Construction Order

The actual-live path follows a strict construction order:

1. Validate all confirmation fields
2. Build `LiveTradingConfirmation`
3. Build actual-live `OrderExecutor` via `_build_actual_live_executor()` (verifies
   connection, environment, account ID, and bridge availability)
4. Build `AutonomousLiveRunner` with the executor already attached
5. Evaluate gates
6. Run once

This ensures the runner always has the correct executor at construction time
(not a stale/default one injected later).

### No Terminal `input()` Blocking

The `OrderExecutor` is constructed with `require_confirmation=False` for the
dashboard-triggered actual-live path. The dashboard multi-step confirmation
(account ID + operator + phrase + risk ack) serves as the explicit operator
confirmation, so the backend does not call `_get_user_confirmation()` which
uses `input()` (unsuitable for Flask/web server processes).

## Safety Gates (all must pass)

- IBKR connected
- Connected account is live
- Detected live account ID matches expected account ID
- `AUTONOMOUS_LIVE_ENABLED=true`
- `AUTONOMOUS_LIVE_DRY_RUN=false` (set automatically by actual-live path)
- Emergency stop inactive
- Signal provider ready
- Deployable cash above configured minimum
- Max open live autonomous trades not exceeded
- Max live trades per day not exceeded
- Limit orders only
- Buy-shares-only restriction
- Risk manager passes
- Portfolio reconciliation passes
- Order sanity checks pass
- *(Continuous only)* `AUTONOMOUS_LIVE_CONTINUOUS_ENABLED=true`
- *(Continuous only)* `AUTONOMOUS_MAX_LIVE_TRADES_PER_DAY > 1`

## Conservative Restrictions

- **Buy shares only** — no short, options, or spread orders.
- **Limit orders only** — MARKET orders are always rejected.
- **Single Trade**: `max_open_live_trades=1`, `max_live_trades_per_day=1` (hardcoded).
- **Continuous Trading**: explicit operator-configured caps required; the backend
  rejects activation if `AUTONOMOUS_MAX_LIVE_TRADES_PER_DAY <= 1`.

## Audit Trail

Every activation attempt is logged with:

- `dry_run` vs `actual_live` flag
- Detected account ID
- Expected/typed account ID
- Confirmed-by operator
- Trading cycle
- All gate results
- Final decision
- Order ID (if submitted)
- Rejection reason (if blocked)

## Outcome Labels

The dashboard shows a clear final outcome from the `outcome` field in the API response:

| Outcome | Meaning |
|---------|---------|
| `LIVE_DRY_RUN_PREVIEW_ONLY` | Dry-run path — no TWS order submitted |
| `LIVE_ORDER_SUBMITTED` | Actual live order submitted — order ID displayed |
| `LIVE_ORDER_REJECTED` | Order rejected by a safety gate — reason displayed |
| `NO_TRADE` | No qualifying candidates found — no action taken |

## Single-Trade Lifecycle

1. Entry submitted with bracket (BUY LMT + SELL LMT target + SELL STP stop).
2. Autonomous Mode stays ON while bracket is active.
3. Once bracket child fills, lifecycle advancer detects all trades closed.
4. Mode turns OFF automatically.

## Continuous Trading Lifecycle

1. First entry submitted with bracket (same as single-trade).
2. Autonomous Mode stays ON.
3. Once bracket child fills, `_maybe_advance_live_lifecycle()` detects all trades closed.
4. A new `_build_actual_live_executor()` call verifies connection, environment, account ID,
   and bridge. If this fails, mode turns OFF (fail-closed).
5. The next cycle's runner uses the freshly built executor. Step 2 repeats.
6. Mode turns OFF when `AUTONOMOUS_MAX_LIVE_TRADES_PER_DAY` is exhausted, the SPY gate
   fails, or any unhandled error occurs.

### Operator responsibilities for Continuous Trading actual-live

- Set `AUTONOMOUS_MAX_LIVE_TRADES_PER_DAY` to a deliberately conservative cap.
- Monitor the dashboard; use the emergency stop if anything is unexpected.
- Understand that each bracket fill may immediately trigger another entry if
  gates pass.
- No background loop exists; advancement happens only on `/live/status` polls
  or `/live/evaluate-exits` calls.

## Fail-Closed Exit Guard

The `/live/evaluate-exits` endpoint protects against dry-run bleed-through:

**Scenario: Mode ON with `dry_run=False`** (actual-live mode):

1. Detect `state.is_on and not state.dry_run`.
2. Return HTTP 400 with `outcome: "NO_EXIT"` if no real executor exists.

Dry-run trades and states with no open actual-live trades proceed normally.

This is intentionally conservative: the system fails closed rather than
risking uncontrolled dry-run behavior on actual-live trades.

## Frontend Order ID Display

The frontend reads the `submitted_order_id` field from the response payload,
falling back to `trade.entry_order_id` and then `trade.order_id` for backward
compatibility.
