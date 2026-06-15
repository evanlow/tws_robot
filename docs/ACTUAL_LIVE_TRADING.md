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
- Only visible when:
  - Account context is Live
  - Trading cycle is Single Trade
  - All readiness gates pass
- Requires explicit multi-step confirmation (see below).
- The frontend sends `dry_run: false` only through this path.
- Dashboard status chip shows: **LIVE SINGLE AUTONOMOUS ON**
- Outcome labels: `LIVE_ORDER_SUBMITTED` / `LIVE_ORDER_REJECTED` / `NO_TRADE`

## Actual Live Trading Confirmation Flow

The operator must provide **all** of the following in the confirmation modal:

1. **Detected live account ID** — typed exactly (compared case-insensitively).
2. **Operator identifier** — a non-empty name identifying who authorized the trade.
3. **Confirmation phrase** — must be typed exactly: `ENABLE ACTUAL LIVE TRADING`
4. **Risk acknowledgement** — checkbox confirming real money is at risk.

Only after all four fields validate does the frontend submit to the backend.

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

### Executor Wiring

The actual-live path constructs:

1. **`TwsTradingAdapter(environment='live', port=<detected_port>)`** — a proper
   live adapter implementing the required contract (`buy`/`sell`/`close_position`/
   `get_all_positions`/`environment`/`port`).

2. **`OrderExecutor(...)`** with:
   - `is_live_mode=True`
   - `require_confirmation=False` — the dashboard confirmation replaces terminal `input()`
   - `dry_run=False`
   - `live_trading_enabled=True`
   - `live_confirmation=LiveTradingConfirmation(...)` — validated per-session token
   - `expected_account_id=<typed_account_id>`
   - `limit_orders_only=True`

The backend does **NOT** use `svc._tws_bridge` as the adapter; it constructs
a dedicated `TwsTradingAdapter` instance with the correct environment/port.

The adapter's `connect_and_run()` method is called before any order execution.
If TWS/Gateway is not available or the adapter cannot reach the ready state,
the endpoint returns HTTP 503 with a clear error message rather than letting
the UI imply "Actual Live Trading" is ready.

### Request-Scoped Executor

The actual-live executor is **request-scoped** — it is NOT stored globally.
This prevents dry-run/actual-live bleed-through: a later dry-run activation
can never accidentally reuse a non-dry-run executor from a previous actual-live
session.

The adapter is disconnected in a `finally` block after every actual-live request.

### Executor/Runner Construction Order

The actual-live path follows a strict construction order:

1. Validate all confirmation fields
2. Build `LiveTradingConfirmation`
3. Build and **connect** `TwsTradingAdapter`
4. Build `OrderExecutor` with the connected adapter
5. Build `AutonomousLiveRunner` with the executor already attached
6. Evaluate gates
7. Run once

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
- Max open live autonomous trades not exceeded (v1: max 1)
- Max live trades per day not exceeded (v1: max 1)
- Limit orders only
- Buy-shares-only (v1 restriction)
- Risk manager passes
- Portfolio reconciliation passes
- Order sanity checks pass

## v1 Conservative Restrictions

- **Single Trade only** — continuous actual-live trading is not supported.
- **Buy shares only** — no short, options, or spread orders.
- **Limit orders only** — MARKET orders are always rejected.
- **Max 1 open autonomous live trade** at a time.
- **Max 1 live autonomous entry per day** by default.

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

## v1 Single-Trade Lifecycle

In v1, actual-live mode uses a conservative **entry-only** single-trade lifecycle:

- **ALL outcomes turn mode OFF**, including successful entry submission.
- After a successful entry (`executed`), mode turns OFF with status
  "Entry Submitted". The operator must manage the exit manually (via the
  dashboard's manual exit controls or directly through TWS).
- Non-executed outcomes also turn mode OFF:
  - `no_trade` — no qualifying candidates
  - `rejected` — gate or risk rejection
  - `engine_rejected` — engine-level rejection
  - `execution_failed` — order execution failure
  - `account_id_mismatch` — account verification failure
  - Any exception during the lifecycle run

### Why v1 is entry-only

The actual-live executor is **request-scoped** — it is built, used, and
disconnected within a single HTTP request to prevent dry-run/actual-live
bleed-through. This means no persisted actual-live executor exists for
subsequent exit evaluation calls.

If mode were left ON after entry, `/live/evaluate-exits` would silently
fall back to a dry-run executor (since `_build_live_runner()` always builds
`dry_run=True` by default). The exit manager accepts `OrderStatus.DRY_RUN`
as success, which would mark actual-live trades `EXIT_PENDING` without a
real exit order — a dangerous bleed-through.

To prevent this, v1 turns mode OFF after every outcome and the exit
endpoint includes a fail-closed guard that rejects exit evaluation when
open actual-live trades exist in the store without a connected non-dry-run
executor.

### Fail-closed exit guard

The `/live/evaluate-exits` endpoint protects against dry-run bleed-through
in two scenarios:

**Scenario 1: Mode left ON with `dry_run=False`** (shouldn't happen in v1,
but guarded):

1. Detect `state.is_on and not state.dry_run` (actual-live mode).
2. Return HTTP 400 with `outcome: "NO_EXIT"` if no real executor exists.

**Scenario 2: Mode OFF but open actual-live trades in store** (normal v1
state after entry-only):

1. Check the live trade store for open trades with `dry_run=False` in notes.
2. If any exist and no non-dry-run executor is available, return HTTP 400
   with `outcome: "NO_EXIT"` — the trade must be exited manually.
3. If a globally stored executor exists but has `dry_run=True`, also reject
   with 400 (prevents dry-run executor from marking actual-live trades
   `EXIT_PENDING`).

Dry-run trades (`dry_run=True` in notes) and states with no open
actual-live trades proceed normally.

This is intentionally conservative: the system fails closed rather than
risking uncontrolled dry-run behavior on actual-live trades.

## Frontend Order ID Display

The frontend reads the `submitted_order_id` field from the response payload,
falling back to `trade.entry_order_id` and then `trade.order_id` for backward
compatibility.
