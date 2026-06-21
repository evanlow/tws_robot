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
| Controlled assisted-live basket | Partial | Basket-level risk allocation is implemented, but broker lifecycle/protection/recovery phases are still required before this becomes preferred live mode |
| Continuous live mode | Pending | Requires operational robustness phases below |
| Automatic capital scaling | Pending | Must wait for promotion gates and evidence review |

## 3. Continuous-live readiness roadmap

| Phase | Work item | Status | Target PR |
|---:|---|---|---|
| 1 | Basket-level risk allocation | Done | Current PR continuing #161 |
| 2 | Broker order lifecycle state machine | Done | Current PR continuing #161 |
| 3 | Broker-side protective stop / bracket verification | Done | Current PR continuing #161 |
| 4 | Idempotency and duplicate-order prevention | Planned | Next implementation PR |
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

Status: Done in current PR; pending merge

Target outcome:

- Basket mode becomes risk-budgeted, not merely notional-budgeted.
- Total planned stop-risk across all basket legs stays within a shared basket risk budget.

Checklist:

- [x] Add `BasketRiskAllocator`.
- [x] Add basket risk config fields.
- [x] Compute planned risk dollars per leg.
- [x] Allocate shared basket risk budget across selected legs.
- [x] Resize or reject legs that exceed allocated risk budget.
- [x] Add basket-level diagnostics.
- [x] Add evidence fields for basket risk.
- [x] Add tests.
- [x] Update docs.

Implementation notes:

- Added `autonomous/basket_risk_allocator.py`.
- Added `basket_risk_allocator_enabled`, `max_basket_risk_equity_pct`,
  `basket_risk_allocation_mode`, and `basket_min_leg_risk_dollars` config.
- `BasketPlanner` still applies sector and notional caps, then applies the
  shared stop-risk budget.
- The allocator supports `BUY_SHARES` legs with valid stops, can reduce
  quantity, can reject over-risk legs, and cannot increase exposure.
- `BasketPlan.to_dict()` includes `risk_allocation` diagnostics for evidence
  and operator review.

Test evidence:

- Passed: `.venv\Scripts\python.exe -m pytest tests/test_basket_planner.py tests/test_autonomous_engine_basket.py tests/test_config.py --basetemp=.pytest-tmp`
- Initial run without `--basetemp=.pytest-tmp` failed before executing tests
  because Windows denied access to `AppData\Local\Temp\pytest-of-evanl`.
- Full suite: `.venv\Scripts\python.exe -m pytest --basetemp=.pytest-tmp`
  completed with `2799 passed`, `18 skipped`, and `6 failed`. The failures
  were existing autonomous/live-runner expectation issues outside the basket
  risk allocation path:
  `tests/test_autonomous_engine.py::test_recommend_only_never_places_orders`,
  `tests/test_autonomous_live_runner.py::test_live_runner_config_defaults`,
  `tests/test_autonomous_live_runner.py::test_live_runner_config_from_env_defaults`,
  `tests/test_autonomous_live_runner.py::test_record_trade_persists_bracket_child_ids`,
  `tests/test_autonomous_live_runner.py::test_synthesized_stop_when_plan_lacks_stop_price`,
  and
  `tests/test_live_dry_run_guard.py::test_live_dry_run_with_no_adapter_reaches_dry_run_result`.

Smoke-test evidence:

- Passed: `.venv\Scripts\python.exe tests/run_all_smoke.py --basetemp=.pytest-tmp`
  (`473 passed`). The command exited 0; it printed a non-failing sparkline
  fallback message after pytest completed.

Known limitations and manual checks:

- Equal-risk allocation only.
- Non-`BUY_SHARES` basket legs are rejected by the allocator because they do not
  have planned per-share stop-risk.
- Broker lifecycle state, broker-side protection verification, and idempotency
  are now implemented later in this PR. Restart recovery, quote freshness,
  broker-fill ingestion, and a continuous supervisor remain future phases
  before unattended continuous live operation.
- Human review should confirm the default basket risk budget is suitable before
  assisted-live basket use.

### Phase 2 — Broker order lifecycle state machine

Status: Done in current PR; pending merge

Checklist:

- [x] Add lifecycle state model.
- [x] Persist lifecycle events.
- [x] Track submitted, filled, rejected, closed, and recovery states.
- [x] Add recovery states.
- [x] Add lifecycle diagnostics to live runner output.
- [x] Add tests for state transitions.

Implementation notes:

- Added `autonomous/order_lifecycle.py` with `OrderLifecycleState`,
  `OrderLifecycleEvent`, and append-only `OrderLifecycleStore`.
- Added `order_lifecycle_store_path` to `AutonomousLiveRunnerConfig`.
- `AutonomousLiveRunner` and the basket live-runner patch now write lifecycle
  events around the existing `OrderExecutor` path.
- Submitted entry orders emit `PLANNED` then `SUBMITTED`.
- Bracket child orders emit `TARGET_PENDING` or
  `PROTECTIVE_STOP_PENDING`.
- Rejected orders emit `REJECTED`.
- Bracket target/stop fills emit child `FILLED` and parent `CLOSED`.
- Stale open trades whose broker position is no longer present emit
  `ORPHANED_ORDER`.
- Broker-side protection verification is implemented separately in Phase 3.

Test evidence:

- Passed: `.venv\Scripts\python.exe -m pytest tests/test_order_lifecycle.py --basetemp=.pytest-tmp -q`
  (`4 passed`).
- Passed: `.venv\Scripts\python.exe -m pytest tests/test_order_lifecycle.py tests/test_basket_planner.py tests/test_autonomous_engine_basket.py tests/test_config.py --basetemp=.pytest-tmp -q`
  (`49 passed`).
- Passed: `.venv\Scripts\python.exe -m pytest tests/test_portfolio_analysis.py::TestPortfolioPersistence --basetemp=.pytest-tmp -q`
  (`9 passed`).
- Passed: `.venv\Scripts\python.exe tests/run_all_smoke.py --basetemp=.pytest-tmp`
  (`473 passed`).

Known limitations and manual checks:

- Lifecycle recording is file-backed JSONL and does not yet reconcile entry
  order acknowledgement callbacks into `ACKNOWLEDGED`.
- Partial-fill state is modeled but not yet automatically ingested; automatic
  fill ingestion remains Phase 6.

### Phase 3 — Broker-side protective stop / bracket verification

Status: Done in current PR; pending merge

Checklist:

- [x] Verify broker acknowledgement of protective stop/bracket orders.
- [x] Confirm protective quantity matches filled quantity.
- [x] Mark trade protected only after verification.
- [x] Block new entries when protection is missing.
- [x] Add recovery state for unprotected live position.

Implementation notes:

- Added `autonomous/protection_verifier.py` with broker open-order snapshot
  normalisation and protection verification.
- Added `require_broker_protection_confirmation` to
  `AutonomousLiveRunnerConfig`; it defaults to `True` and can be overridden by
  `AUTONOMOUS_REQUIRE_BROKER_PROTECTION_CONFIRMATION`.
- `AutonomousLiveRunner.evaluate_gates()` verifies every open non-dry-run
  autonomous live trade before allowing another entry.
- Missing or unverifiable protection records `RECOVERY_REQUIRED` in the
  lifecycle store and blocks new entries while the trade remains open.
- Confirmed broker-visible stop/bracket protection records
  `PROTECTIVE_STOP_CONFIRMED`.
- `TWSBridge` now maintains broker-visible open-order snapshots from
  `openOrder` and `orderStatus`, exposed through
  `get_open_order_snapshots()`.

Test evidence:

- Passed: `.venv\Scripts\python.exe -m pytest tests/test_order_lifecycle.py tests/test_tws_bridge.py::TestBridgeOpenOrderSnapshots --basetemp=.pytest-tmp -q`
  (`8 passed`).
- Passed: `.venv\Scripts\python.exe tests/run_all_smoke.py --basetemp=.pytest-tmp`
  (`473 passed`).

Known limitations and manual checks:

- The verifier is read-only; it does not submit replacement stops when
  protection is missing.
- Partial-fill quantity is inferred from the broker position snapshot when
  present; automatic fill ingestion and child-order resizing remain future
  phases.
- If broker open-order snapshots are unavailable while an open live trade
  exists, the system fails closed and requires operator recovery.

### Phase 4 — Idempotency and duplicate-order prevention

Status: Done in current PR; pending merge

Checklist:

- [x] Add run/decision/basket/leg identifiers.
- [x] Add idempotency lock store.
- [x] Block duplicate signal/basket-leg submission.
- [x] Handle restart after submission but before evidence write.
- [x] Add stale-lock inspection/clear path.

Implementation notes:

- Added `autonomous/idempotency.py` with append-only JSONL replay of
  `IN_FLIGHT`, `SUBMITTED`, and `CLEARED` lock states.
- Added `idempotency_store_path`, `idempotency_stale_minutes`, and
  `allow_duplicate_symbol_live_entries` to `AutonomousLiveRunnerConfig`.
  Duplicate symbol live entries remain blocked by default.
- The base live runner and basket live-runner patch acquire a symbol/action
  lock before broker submission for non-dry-run live entries.
- Existing open autonomous trades for the same symbol fail closed with
  `duplicate_order_blocked` unless explicitly allowed.
- Active idempotency locks fail closed with `duplicate_order_blocked` and
  write `DUPLICATE_ORDER_BLOCKED` lifecycle diagnostics.
- Basket execution preflights all legs before submission so duplicate symbols
  or active locks cannot produce a partial basket submit.
- Submitted orders mark locks `SUBMITTED` with broker order and autonomous
  trade IDs; executor failures, rejections, and lifecycle write failures clear
  in-flight locks.
- Readiness reconciliation clears locks only after the local autonomous trade
  is terminal. Operators can inspect stale locks and explicitly clear a lock
  through runner helpers.

Test evidence:

- Passed: `.venv\Scripts\python.exe -m pytest tests/test_idempotency.py tests/test_order_lifecycle.py tests/test_autonomous_live_runner_basket.py --basetemp=.pytest-tmp -q`
  (`15 passed`).

Smoke-test evidence:

- Passed: `.venv\Scripts\python.exe -m pytest tests/test_safety_regression.py tests/test_web_api.py tests/test_portfolio_analysis.py tests/test_auth.py tests/test_config_security.py tests/test_order_executor.py tests/test_tws_bridge.py tests/test_fx_research.py --basetemp=.pytest-tmp --no-cov -vv --tb=short -o faulthandler_timeout=60`
  (`473 passed`).

Known limitations and manual checks:

- Stale locks are surfaced for operator inspection and manual clear; they are
  not auto-cleared solely because they are old.
- The idempotency key intentionally blocks by symbol/action for live entries,
  not just by exact signal timestamp, to avoid duplicate exposure after a
  restart window.
- Quote freshness, automatic fill ingestion, and continuous supervisor
  recovery are still future phases.

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
