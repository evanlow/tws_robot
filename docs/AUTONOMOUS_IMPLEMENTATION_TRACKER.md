# Autonomous Trading Implementation Tracker

This tracker records what has been implemented, what is pending, and which PRs delivered each capability.

It complements `docs/AUTONOMOUS_TRADING_SYSTEM_SPEC.md`.

Legend:

| Status | Meaning |
|---|---|
| Done | Implemented and merged |
| Partial | Implemented in part, or implemented but needs hardening |
| Pending | Not yet implemented |
| Planned | Accepted roadmap item, not yet started |

## 1. Completed trading-intelligence tranche

| Area | Status | PR / Notes |
|---|---|---|
| Evidence foundation | Done | PR #162 |
| Decision evidence records | Done | PR #162 |
| Evidence API / recent evidence view | Done | PR #162 |
| Support/resistance enrichment | Done | PR #163 |
| Assisted-live valid stop requirement | Done | PR #163 |
| VIX / market-regime guard | Done | PR #160 |
| Market-regime size multiplier | Done | PR #160 |
| Opt-in basket planner | Done | PR #164 |
| Basket selected/trade_plans output | Done | PR #164 |
| Paper basket execution | Done | PR #164 |
| Assisted-live basket support | Partial | PR #164; works through live-runner path but needs basket-level risk allocator and stronger broker lifecycle before continuous live |
| Risk-per-trade sizing | Done | PR #165 |
| Volatility sizing | Done | PR #165 |
| Binding sizing cap diagnostics | Done | PR #165 |
| Feature builder | Done | PR #166 |
| Rule-based edge estimator | Done | PR #166 |
| Expected-R ranking | Done | PR #166 |
| Fractional edge / fractional-Kelly-style sizing | Done | PR #167; implemented as `FractionalEdgeSizer`, not literal `KellySizer` |
| Drawdown governor | Done | PR #167 |
| Execution quality guard | Done | PR #168; pre-submission only |
| Strategy-arm learning | Done | PR #169 |
| Validation framework | Done | PR #169 |
| Realized outcome reconciliation | Done | PR #170 |
| Slippage / commission / partial-fill outcome fields | Done | PR #170 |
| Strategy equity curve | Done | PR #171 |
| Daily/weekly/monthly lifecycle loss limits | Done | PR #171 |
| Sector regime context | Done | PR #172 |
| Time-of-day regime context | Done | PR #172 |
| Chronological validation report | Done | PR #172 |
| Formal system specification | In review | PR #173 |

## 2. Current operating readiness

| Capability | Status | Notes |
|---|---|---|
| Recommend-only autonomous analysis | Done | Safe default |
| Paper execution | Done | Suitable for evidence collection |
| Controlled assisted-live single trade | Partial | Feasible with conservative caps and all live gates passing |
| Controlled assisted-live basket | Partial | Feasible but should wait for basket-level risk allocation before becoming preferred live mode |
| Continuous live mode | Pending | Requires operational robustness phases below |
| Automatic capital scaling | Pending | Must wait for promotion gates and evidence review |

## 3. Continuous-live readiness roadmap

| Phase | Work item | Status | Target PR |
|---:|---|---|---|
| 1 | Basket-level risk allocation | Pending | Next implementation PR |
| 2 | Broker order lifecycle state machine | Planned | TBD |
| 3 | Broker-side protective stop / bracket verification | Planned | TBD |
| 4 | Idempotency and duplicate-order prevention | Planned | TBD |
| 5 | Quote freshness and market-data health guard | Planned | TBD |
| 6 | Automatic broker-fill ingestion | Planned | TBD |
| 7 | Continuous-run supervisor | Planned | TBD |
| 8 | Restart recovery and broker reconciliation | Planned | TBD |
| 9 | Enhanced emergency stop operations | Planned | TBD |
| 10 | Control tower dashboard/API | Planned | TBD |
| 11 | Replay / chaos testing harness | Planned | TBD |
| 12 | Capital ramp and promotion gates | Planned | TBD |

## 4. Phase detail tracker

### Phase 1 — Basket-level risk allocation

Status: Pending

Target outcome:

- Basket mode becomes risk-budgeted, not merely notional-budgeted.
- Total planned stop-risk across all basket legs stays within a shared basket risk budget.

Checklist:

- [ ] Add `BasketRiskAllocator`.
- [ ] Add basket risk config fields.
- [ ] Compute planned risk dollars per leg.
- [ ] Allocate shared basket risk budget across selected legs.
- [ ] Resize or reject legs that exceed allocated risk budget.
- [ ] Add basket-level diagnostics.
- [ ] Add evidence fields for basket risk.
- [ ] Add tests.
- [ ] Update docs.

### Phase 2 — Broker order lifecycle state machine

Status: Planned

Checklist:

- [ ] Add lifecycle state model.
- [ ] Persist lifecycle events.
- [ ] Track submitted, acknowledged, partial, filled, cancelled, rejected, closed, reconciled states.
- [ ] Add recovery states.
- [ ] Add lifecycle diagnostics to live runner output.
- [ ] Add tests for state transitions.

### Phase 3 — Broker-side protective stop / bracket verification

Status: Planned

Checklist:

- [ ] Verify broker acknowledgement of protective stop/bracket orders.
- [ ] Confirm protective quantity matches filled quantity.
- [ ] Mark trade protected only after verification.
- [ ] Block new entries when protection is missing.
- [ ] Add recovery state for unprotected live position.

### Phase 4 — Idempotency and duplicate-order prevention

Status: Planned

Checklist:

- [ ] Add run/decision/basket/leg identifiers.
- [ ] Add idempotency lock store.
- [ ] Block duplicate signal/basket-leg submission.
- [ ] Handle restart after submission but before evidence write.
- [ ] Add stale-lock inspection/clear path.

### Phase 5 — Quote freshness and market-data health guard

Status: Planned

Checklist:

- [ ] Track bid/ask/last timestamps.
- [ ] Block stale quote in live mode.
- [ ] Add feed-health diagnostics.
- [ ] Add live-mode missing bid/ask block option.
- [ ] Add tests for stale and missing quotes.

### Phase 6 — Automatic broker-fill ingestion

Status: Planned

Checklist:

- [ ] Consume broker execution/fill events.
- [ ] Capture execution ID, order ID, symbol, side, quantity, price, commission, timestamp.
- [ ] Update trade store automatically.
- [ ] Update lifecycle state.
- [ ] Emit outcome evidence when trade closes.
- [ ] Add tests for full and partial fills.

### Phase 7 — Continuous-run supervisor

Status: Planned

Checklist:

- [ ] Add supervisor module.
- [ ] Prevent overlapping runs.
- [ ] Maintain heartbeat.
- [ ] Pause on serious errors.
- [ ] Pause on broker disconnect.
- [ ] Pause on unreconciled lifecycle state.
- [ ] Pause on risk-lifecycle breach.

### Phase 8 — Restart recovery and broker reconciliation

Status: Planned

Checklist:

- [ ] Reconcile local trade store against broker positions.
- [ ] Reconcile local order records against broker open orders.
- [ ] Reconcile recent broker executions.
- [ ] Classify startup state: `SAFE_TO_TRADE`, `SAFE_TO_MONITOR_ONLY`, `RECOVERY_REQUIRED`, `MANUAL_INTERVENTION_REQUIRED`.
- [ ] Block trading when recovery is required.

### Phase 9 — Enhanced emergency stop operations

Status: Planned

Checklist:

- [ ] Keep current emergency stop as new-entry blocker.
- [ ] Add supervisor pause integration.
- [ ] Add optional pending-entry cancellation.
- [ ] Preserve protective exits unless panic flatten is explicitly requested.
- [ ] Add audited reset.
- [ ] Add dashboard/API visibility.

### Phase 10 — Control tower dashboard/API

Status: Planned

Checklist:

- [ ] Expose autonomous mode and enabled state.
- [ ] Expose heartbeat.
- [ ] Expose IBKR connection and account state.
- [ ] Expose market-data health.
- [ ] Expose cash/deployable cash.
- [ ] Expose open autonomous trades and orders.
- [ ] Expose basket risk usage.
- [ ] Expose confirmed protection state.
- [ ] Expose risk lifecycle state.
- [ ] Expose emergency stop status.

### Phase 11 — Replay / chaos testing harness

Status: Planned

Checklist:

- [ ] Add simulated broker fixtures.
- [ ] Simulate normal fill.
- [ ] Simulate partial fill.
- [ ] Simulate order rejection.
- [ ] Simulate broker disconnect.
- [ ] Simulate stale quote.
- [ ] Simulate restart after submission.
- [ ] Simulate restart after fill before evidence write.
- [ ] Simulate unconfirmed protective stop.
- [ ] Verify no duplicate exposure.

### Phase 12 — Capital ramp and promotion gates

Status: Planned

Checklist:

- [ ] Define capital levels.
- [ ] Generate promotion report.
- [ ] Require operator approval.
- [ ] Allow demotion after drawdown/fault.
- [ ] Track live/paper consistency.
- [ ] Prevent automatic capital scaling.

## 5. Maintenance rules

Future PRs should update this tracker when they complete a phase or checklist item.

A PR that implements a roadmap phase should update:

- the phase status;
- completed checklist items;
- PR number / notes;
- any new limitations discovered.

If implementation diverges from the spec, update both the spec and this tracker in the same PR or in a documentation follow-up PR.
