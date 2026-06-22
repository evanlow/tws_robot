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
| Evidence-learning performance metrics | Done | PR #183 |
| Evidence-learning setup registry | Done | PR #184 |
| Evidence-learning evidence calibrator | Done | PR #186 |
| Evidence-learning adaptive edge estimator | Done | Current PR |
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
| 1 | Basket-level risk allocation | Done | PR #175 |
| 2 | Broker order lifecycle state machine | Done | PR #175 |
| 3 | Broker-side protective stop / bracket verification | Done | PR #175 |
| 4 | Idempotency and duplicate-order prevention | Done | PR #175 |
| 5 | Quote freshness and market-data health guard | Done | PR #175 |
| 6 | Automatic broker-fill ingestion | Done | PR #175 |
| 7 | Continuous-run supervisor | Done | PR #175 |
| 8 | Restart recovery and broker reconciliation | Done | PR #176 |
| 9 | Enhanced emergency stop operations | Done | PR #178 |
| 10 | Control tower dashboard/API | Done | PR #180 |
| 11 | Replay / chaos testing harness | Done | PR #181 |
| 12 | Capital ramp and promotion gates | Done | PR #182 |

## 4. Phase detail tracker

### Phase 1 — Basket-level risk allocation

Status: Done in PR #175

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

Status: Done in PR #175

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

Status: Done in PR #175

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

Status: Done in PR #175

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
- Automatic fill ingestion and continuous supervisor recovery are still
  future phases.

### Phase 5 — Quote freshness and market-data health guard

Status: Done in PR #175

Checklist:

- [x] Track bid/ask/last timestamps.
- [x] Block stale quote in live mode.
- [x] Add feed-health diagnostics.
- [x] Add live-mode missing bid/ask block option.
- [x] Add tests for stale and missing quotes.

Implementation notes:

- Added `autonomous/market_data_health.py` with a source-agnostic
  `MarketDataHealthGuard` and serializable diagnostics.
- Added configurable guard settings to `AutonomousTradingConfig`.
- `TradePlanner` now runs market-data health before execution-quality
  checks, rejects assisted-live stale/degraded/closed-market plans, records
  rejection reasons, and attaches `market_data_health` to trade-plan output.
- `TechnicalAnalysisSignalProvider` maps bid/ask/last timestamps, feed
  status, feed-health, and market-open metadata into candidate extras when
  those fields are available.

Test evidence:

- Passed: `.venv\Scripts\python.exe -m pytest tests\test_market_data_health.py tests\test_trade_planner_execution_quality.py tests\test_trade_planner.py tests\test_technical_analysis_signal_provider.py tests\test_autonomous_engine_basket.py tests\test_order_lifecycle.py --basetemp=.pytest-tmp -q`
  (`57 passed`).

Smoke-test evidence:

- Passed: `.venv\Scripts\python.exe -m pytest tests/test_safety_regression.py tests/test_web_api.py tests/test_portfolio_analysis.py tests/test_auth.py tests/test_config_security.py tests/test_order_executor.py tests/test_tws_bridge.py tests/test_fx_research.py --basetemp=.pytest-tmp --no-cov -vv --tb=short -o faulthandler_timeout=60`
  (`473 passed`).

Known limitations and manual checks:

- Missing bid/ask blocking is configurable and defaults to non-blocking to
  preserve current assisted-live fixtures; operators can fail closed with
  `market_data_block_missing_bid_ask_live=True`.
- Missing quote timestamp blocking is configurable and defaults to
  non-blocking for compatibility with providers that do not yet publish
  quote timestamps.
- The guard is pre-submission only; it does not subscribe to market data or
  repair a degraded feed.
- Automatic fill ingestion remains Phase 6.

### Phase 6 — Automatic broker-fill ingestion

Status: Done in PR #175

Checklist:

- [x] Consume broker execution/fill events.
- [x] Capture execution ID, order ID, symbol, side, quantity, price, commission, timestamp.
- [x] Update trade store automatically.
- [x] Update lifecycle state.
- [x] Emit outcome evidence when trade closes.
- [x] Add tests for full and partial fills.

Implementation notes:

- Added `autonomous/broker_fill_ingestor.py` to normalize broker fill rows,
  merge repeated/enriched executions by execution ID, aggregate partial fills,
  update `TradeStore`, record lifecycle transitions, and emit outcome
  evidence for closed trades.
- Extended `AutonomousTrade` with persisted `entry_fills`, `exit_fills`, and
  `outcome_emitted` fields.
- Extended `TWSBridge` with `execDetails`, `commissionReport`, and
  `pop_broker_fill_events()` so IBKR execution and commission callbacks can be
  consumed without losing late commission reports.
- Wired `AutonomousLiveRunner` to optionally ingest broker fill events before
  readiness checks while retaining the existing filled-order-ID fallback.

Test evidence:

- Passed: `.venv\Scripts\python.exe -m pytest tests\test_broker_fill_ingestor.py tests\test_tws_bridge.py::TestBridgeBrokerFillEvents tests\test_autonomous_trade_store.py tests\test_order_lifecycle.py --basetemp=.pytest-tmp -q`
  (`22 passed`).

Smoke-test evidence:

- Passed: `.venv\Scripts\python.exe -m pytest tests/test_safety_regression.py tests/test_web_api.py tests/test_portfolio_analysis.py tests/test_auth.py tests/test_config_security.py tests/test_order_executor.py tests/test_tws_bridge.py tests/test_fx_research.py --basetemp=.pytest-tmp --no-cov -vv --tb=short -o faulthandler_timeout=60`
  (`476 passed`).

Known limitations and manual checks:

- The ingestor is accounting-only; it does not resize child orders after a
  partial fill and does not submit replacement protection.
- Outcome emission is append-only. If a broker reports commission after an
  outcome has already been emitted, the trade store can be enriched but the
  existing outcome record is not rewritten.
- Continuous supervisor recovery, restart chaos tests, and dashboard drilldown
  remain future phases.

### Phase 7 — Continuous-run supervisor

Status: Done in PR #175

Checklist:

- [x] Add supervisor module.
- [x] Prevent overlapping runs.
- [x] Maintain heartbeat.
- [x] Pause on serious errors.
- [x] Pause on broker disconnect.
- [x] Pause on unreconciled lifecycle state.
- [x] Pause on risk-lifecycle breach.

Implementation notes:

- Added `autonomous/continuous_supervisor.py` with non-overlap locking,
  cadence enforcement, heartbeat/status snapshots, pause/resume controls, and
  structured fault/result records.
- Wired the live lifecycle worker and `/api/autonomous/live/status`
  auto-advance path through the supervisor for continuous cycles.
- Supervisor status is exposed in `/api/autonomous/live/status` under
  `continuous_supervisor`.
- Continuous cycles pause fail-closed on broker disconnect, emergency stop,
  unreconciled protection/lifecycle state, failed live trades, risk lifecycle
  breach results, or tick exceptions.
- Fixed a continuous-cycle market-not-suitable halt path to format the runner
  result decision payload instead of referencing an undefined local variable.

Test evidence:

- Passed: `.venv\Scripts\python.exe -m pytest tests\test_continuous_supervisor.py tests\test_api_autonomous_live.py::TestLiveStatus tests\test_api_autonomous_live.py::TestLiveLifecycleTick --basetemp=.pytest-tmp -q`
  (`13 passed`).

Smoke-test evidence:

- Passed: `.venv\Scripts\python.exe -m pytest tests/test_safety_regression.py tests/test_web_api.py tests/test_portfolio_analysis.py tests/test_auth.py tests/test_config_security.py tests/test_order_executor.py tests/test_tws_bridge.py tests/test_fx_research.py --basetemp=.pytest-tmp --no-cov -vv --tb=short -o faulthandler_timeout=60`
  (`476 passed`).

Known limitations and manual checks:

- The supervisor is a coordinator only; it does not perform restart recovery,
  broker/local reconciliation, automatic replacement protection, order
  cancellation, or panic flattening.
- The existing lifecycle worker still owns background threading; the supervisor
  controls whether a continuous tick is allowed to run and why it pauses.
- Dedicated dashboard controls for supervisor pause/resume remain part of the
  future control tower phase.

### Phase 8 — Restart recovery and broker reconciliation

Status: Done in PR #176

Checklist:

- [x] Reconcile local trade store against broker positions.
- [x] Reconcile local order records against broker open orders.
- [x] Reconcile recent broker executions.
- [x] Classify startup state: `SAFE_TO_TRADE`, `SAFE_TO_MONITOR_ONLY`, `RECOVERY_REQUIRED`, `MANUAL_INTERVENTION_REQUIRED`.
- [x] Block trading when recovery is required.

Implementation notes:

- Added `autonomous/recovery_manager.py` with `RecoveryManager`,
  `RecoveryReport`, `RecoveryIssue`, and `RecoveryClassification`.
- `AutonomousLiveRunner.evaluate_gates()` now emits
  `recovery_classification`, `recovery_required`, and
  `recovery_diagnostics` in the readiness payload.
- The recovery manager compares local autonomous open trades with broker
  positions, broker-visible open orders, lifecycle current states, active
  idempotency locks, broker protection diagnostics, and deployable cash.
- Local/broker quantity mismatches, local open trades without broker
  positions, unmatched active broker BUY orders, stale/trade-less idempotency
  locks, missing broker-side protection, and recovery lifecycle states block
  new entries.
- Continuous supervisor fault inference now pauses on recovery-required
  readiness diagnostics.
- Recovery is read-only and defensive; it does not submit, cancel, replace,
  flatten, auto-clear locks, or enable live trading.

Test evidence:

- Passed: `.venv\Scripts\python.exe -m pytest tests\test_recovery_manager.py --basetemp=.pytest-tmp -q`
  (`7 passed`).
- Passed: `.venv\Scripts\python.exe -m pytest tests\test_recovery_manager.py tests\test_continuous_supervisor.py tests\test_order_lifecycle.py --basetemp=.pytest-tmp -q`
  (`26 passed`).
- Passed: `.venv\Scripts\python.exe -m pytest tests\test_api_autonomous_live.py::TestLiveStatus tests\test_api_autonomous_live.py::TestLiveLifecycleTick tests\test_recovery_manager.py --basetemp=.pytest-tmp -q`
  (`11 passed`).

Smoke-test evidence:

- Passed split smoke verification for the same smoke set used by PR #175:
  `.venv\Scripts\python.exe -m pytest tests/test_safety_regression.py tests/test_web_api.py --basetemp=.pytest-tmp --no-cov -q --tb=short -o faulthandler_timeout=60`
  (`203 passed`);
  `.venv\Scripts\python.exe -m pytest tests/test_portfolio_analysis.py tests/test_auth.py tests/test_config_security.py --basetemp=.pytest-tmp --no-cov -q --tb=short -o faulthandler_timeout=60`
  (`112 passed`);
  `.venv\Scripts\python.exe -m pytest tests/test_order_executor.py tests/test_tws_bridge.py tests/test_fx_research.py --basetemp=.pytest-tmp --no-cov -q --tb=short -o faulthandler_timeout=60`
  (`161 passed`). Total split smoke coverage: `476 passed`.
- A parallel smoke attempt using the same `.pytest-tmp` directory produced one
  SQLite temp-file setup error in `tests/test_portfolio_analysis.py`; rerunning
  the affected group by itself passed, so the error was treated as test
  orchestration contention rather than a product failure.

Known limitations and manual checks:

- Recovery classification is read-only; operator action is required to clear
  stale locks, resolve orphaned lifecycle states, or fix broker/local
  mismatches.
- It does not submit replacement stops, cancel pending orders, panic-flatten,
  or auto-resize child orders after partial fills.
- Recent execution reconciliation is supported by the recovery model, while
  the live runner currently relies on the Phase 6 broker-fill ingestor for
  execution snapshots before recovery classification.

### Phase 9 — Enhanced emergency stop operations

Status: Done in PR #178

Checklist:

- [x] Keep current emergency stop as new-entry blocker.
- [x] Add supervisor pause integration.
- [x] Add optional pending-entry cancellation.
- [x] Preserve protective exits unless panic flatten is explicitly requested.
- [x] Add audited reset.
- [x] Add dashboard/API visibility.

Implementation notes:

- Enhanced `POST /api/autonomous/emergency-stop` so it writes the autonomous
  emergency-stop marker, turns paper/live autonomous modes off, stops lifecycle
  workers, pauses the live continuous supervisor, and writes an autonomous
  audit event.
- Added optional `cancel_pending_entries=true` cleanup that forwards broker
  cancel requests for pending live autonomous entry order IDs only.  Paper
  entry order IDs are reported but not sent to the broker, and target/stop
  child order IDs are reported as preserved protective exits.
- Added `POST /api/autonomous/emergency-reset`, requiring `confirm=true`, to
  clear only an autonomous-owned marker, keep autonomous modes off, resume the
  supervisor only when it was paused by emergency stop, and write an audit
  event.  Global/manual emergency markers must be cleared through
  `/api/emergency/resume`.
- Added structured `emergency_stop` status to `/api/autonomous/status` and
  `/api/autonomous/live/status`, including marker state, manual reset
  requirement, shared risk-manager stop state, and the separation between
  Emergency Stop and Panic Flatten.

Test evidence:

- Passed: `.venv\Scripts\python.exe -m pytest tests\test_api_autonomous_live.py::TestAutonomousEmergencyStop --basetemp=.pytest-tmp -q`
  (`6 passed`).
- Passed: `.venv\Scripts\python.exe -m pytest tests\test_api_autonomous_live.py::TestLiveStatus tests\test_api_autonomous_live.py::TestLiveHalt tests\test_api_autonomous_live.py::TestAutonomousEmergencyStop tests\test_web_api.py::TestEmergencyAPI --basetemp=.pytest-tmp -q`
  (`18 passed`).

Smoke-test evidence:

- Passed split smoke verification:
  `.venv\Scripts\python.exe -m pytest tests/test_safety_regression.py tests/test_web_api.py --basetemp=.pytest-tmp --no-cov -q --tb=short -o faulthandler_timeout=60`
  (`203 passed`);
  `.venv\Scripts\python.exe -m pytest tests/test_portfolio_analysis.py tests/test_auth.py tests/test_config_security.py --basetemp=.pytest-tmp --no-cov -q --tb=short -o faulthandler_timeout=60`
  (`112 passed`);
  `.venv\Scripts\python.exe -m pytest tests/test_order_executor.py tests/test_tws_bridge.py tests/test_fx_research.py --basetemp=.pytest-tmp --no-cov -q --tb=short -o faulthandler_timeout=60`
  (`161 passed`). Total split smoke coverage: `476 passed`.
- The first smoke group printed a non-failing sparkline fallback message after
  pytest completed; the command exited 0.

Known limitations and manual checks:

- Bulk pending-entry cleanup forwards cancel requests for live entry order IDs
  only and does not mark trades terminal immediately; broker
  fill/reject/cancel reconciliation remains the source of truth.
- Panic Flatten remains a separate future explicit control and is not invoked
  by emergency stop or reset.
- Reset clears only autonomous-owned emergency-stop markers and resumes the
  supervisor only if the pause reason was emergency stop.  It does not clear
  global/manual emergency markers, reactivate paper/live autonomous mode, or
  enable live trading.

### Phase 10 — Control tower dashboard/API

Status: Done in PR #180

Checklist:

- [x] Expose autonomous mode and enabled state.
- [x] Expose heartbeat.
- [x] Expose IBKR connection and account state.
- [x] Expose market-data health.
- [x] Expose cash/deployable cash.
- [x] Expose open autonomous trades and orders.
- [x] Expose basket risk usage.
- [x] Expose confirmed protection state.
- [x] Expose risk lifecycle state.
- [x] Expose emergency stop status.

Implementation notes:

- Added `GET /api/autonomous/control-tower` as a consolidated operator
  snapshot for Phase 10 visibility.
- The payload includes paper/live autonomous mode state, enabled status,
  continuous-supervisor heartbeat, IBKR connection/account verification,
  passive live-readiness gates, market-data health diagnostics from recent
  evidence when present, cash/deployable-cash diagnostics, paper/live
  autonomous trade summaries, broker-visible open orders, append-only order
  lifecycle current states, latest basket risk usage from evidence, passive
  broker-protection diagnostics, recovery/risk lifecycle state, recent
  decisions, recent rejections, recent fills/outcomes, and structured
  emergency-stop status.
- The control-tower route is intentionally passive and does not call
  `AutonomousLiveRunner.evaluate_gates()`, because the live runner readiness
  evaluator ingests broker fills/rejections, reconciles stale positions,
  releases idempotency locks, and may write lifecycle diagnostics.
- The response includes explicit `safety_notes` and live-readiness
  `side_effects` markers confirming that the endpoint does not submit orders,
  cancel orders, flatten positions, write lifecycle events, or advance the
  autonomous lifecycle.

Test evidence:

- Passed: `.venv\Scripts\python.exe -m pytest tests\test_api_autonomous_live.py::TestControlTower --basetemp=.pytest-tmp -q`
  (`2 passed`).
- Passed: `.venv\Scripts\python.exe -m pytest tests\test_api_autonomous.py tests\test_api_autonomous_live.py::TestLiveStatus tests\test_api_autonomous_live.py::TestControlTower tests\test_api_autonomous_evidence.py tests\test_autonomous_dashboard.py --basetemp=.pytest-tmp -q`
  (`94 passed`).

Smoke-test evidence:

- Passed split smoke verification:
  `.venv\Scripts\python.exe -m pytest tests/test_safety_regression.py tests/test_web_api.py --basetemp=.pytest-tmp --no-cov -q --tb=short -o faulthandler_timeout=60`
  (`203 passed`);
  `.venv\Scripts\python.exe -m pytest tests/test_portfolio_analysis.py tests/test_auth.py tests/test_config_security.py --basetemp=.pytest-tmp --no-cov -q --tb=short -o faulthandler_timeout=60`
  (`112 passed`);
  `.venv\Scripts\python.exe -m pytest tests/test_order_executor.py tests/test_tws_bridge.py tests/test_fx_research.py --basetemp=.pytest-tmp --no-cov -q --tb=short -o faulthandler_timeout=60`
  (`161 passed`). Total split smoke coverage: `476 passed`.
- The first smoke group initially timed out after 240 seconds with no reported
  failures; rerunning the same group with a longer timeout passed.
- The second smoke group printed non-failing post-pytest database/cache fetch
  messages after pytest completed; the command exited 0.

Known limitations and manual checks:

- The first Phase 10 slice is API-first; it consolidates state for the
  existing dashboard/control-tower surface but does not redesign the browser UI.
- Passive readiness does not ingest fresh broker fills/rejections or release
  terminal idempotency locks; use `/api/autonomous/live/status` when explicit
  live-runner reconciliation is desired.
- Daily/weekly/monthly R remains available through existing outcome evidence
  and risk lifecycle records; this endpoint currently surfaces recent fills and
  risk/recovery state but does not compute a separate R-period summary table.

### Phase 11 — Replay / chaos testing harness

Status: Done in current PR; pending merge

Checklist:

- [x] Add simulated broker fixtures.
- [x] Simulate normal fill.
- [x] Simulate partial fill.
- [x] Simulate order rejection.
- [x] Simulate broker disconnect.
- [x] Simulate stale quote.
- [x] Simulate restart after submission.
- [x] Simulate restart after fill before evidence write.
- [x] Simulate basket with one failed leg.
- [x] Simulate stop hit.
- [x] Simulate target hit.
- [x] Simulate unconfirmed protective stop.
- [x] Verify no duplicate exposure.

Implementation notes:

- Added `autonomous/replay_engine.py` with `ReplayChaosHarness`,
  `SimulatedBroker`, replay scenario/step/result dataclasses, and
  `default_phase_11_scenarios()`.
- The harness is simulation-only. It never calls `OrderExecutor`, never
  submits or cancels broker orders, never flattens positions, and never changes
  live-mode activation or sizing behavior.
- Replay scenarios drive the existing safety components instead of parallel
  mock logic: `BrokerFillIngestor`, `OrderLifecycleStore`,
  `IdempotencyStore`, `ProtectionVerifier`, `RecoveryManager`,
  `MarketDataHealthGuard`, and `ContinuousSupervisor`.
- Each replay result records recovery classification, supervisor status,
  duplicate-exposure diagnostics, evidence-reconstructability diagnostics,
  broker snapshots, lifecycle states, and trade-store state.
- The default scenario set covers the current Phase 11 spec cases:
  normal fill, partial fill, order rejection, broker disconnect, stale quote,
  restart after submission, restart after fill before evidence write, basket
  with one failed leg, stop hit, target hit, and unconfirmed protective stop.

Test evidence:

- Passed: `.venv\Scripts\python.exe -m pytest tests\test_replay_engine.py --basetemp=.pytest-tmp -q`
  (`5 passed`).
- Passed: `.venv\Scripts\python.exe -m pytest tests\test_replay_engine.py tests\test_recovery_manager.py tests\test_order_lifecycle.py tests\test_broker_fill_ingestor.py tests\test_continuous_supervisor.py tests\test_market_data_health.py --basetemp=.pytest-tmp -q`
  (`42 passed`).

Smoke-test evidence:

- Passed split smoke verification:
  `.venv\Scripts\python.exe -m pytest tests/test_safety_regression.py tests/test_web_api.py --basetemp=.pytest-tmp --no-cov -q --tb=short -o faulthandler_timeout=60`
  (`203 passed`);
  `.venv\Scripts\python.exe -m pytest tests/test_portfolio_analysis.py tests/test_auth.py tests/test_config_security.py --basetemp=.pytest-tmp --no-cov -q --tb=short -o faulthandler_timeout=60`
  (`112 passed`);
  `.venv\Scripts\python.exe -m pytest tests/test_order_executor.py tests/test_tws_bridge.py tests/test_fx_research.py --basetemp=.pytest-tmp --no-cov -q --tb=short -o faulthandler_timeout=60`
  (`161 passed`). Total split smoke coverage: `476 passed`.

Known limitations and manual checks:

- This is a deterministic component/test harness, not a broker simulator UI or
  long-running market replay service.
- The harness does not submit replacement protection, cancel orders,
  panic-flatten, or auto-clear stale idempotency locks; those remain explicit
  operator/recovery actions.
- Scenario data is intentionally small and deterministic. Future phases can
  layer historical market-bar playback or randomized fault schedules on top of
  the same result model if needed.

### Phase 12 — Capital ramp and promotion gates

Status: Done in current PR

Checklist:

- [x] Define capital levels.
- [x] Generate promotion report.
- [x] Require operator approval.
- [x] Allow demotion after drawdown/fault.
- [x] Track live/paper consistency.
- [x] Prevent automatic capital scaling.

Implementation notes:

- Added `autonomous/capital_promotion.py` with fixed capital levels 0-6,
  `CapitalPromotionEvaluator`, threshold configuration, metrics dataclasses,
  paper/live consistency diagnostics, and promotion/hold/demotion report
  serialization.
- Reports include completed and recent trade counts, avg R, expected R, win
  rate, profit factor, rolling Sharpe, Sortino, max drawdown in R, slippage,
  partial-fill rate, operational incident count, stale-evidence age, paper/live
  counts, and approval/rejection/demotion reasons.
- The evaluator is advisory only. It never submits, cancels, replaces, or
  flattens orders; never mutates autonomous configuration; never enables live
  trading; and never changes capital caps automatically.
- Every report sets `operator_approval_required` to true and
  `automatic_capital_scaling_allowed` to false.

Test evidence:

- Passed: `.venv\Scripts\python.exe -m pytest tests\test_capital_promotion.py --basetemp=.pytest-tmp -q`
  (`6 passed`).
- Passed: `.venv\Scripts\python.exe -m pytest tests\test_capital_promotion.py tests\test_validation_framework.py tests\test_trade_evidence_store.py tests\test_risk_lifecycle.py --basetemp=.pytest-tmp -q`
  (`23 passed`).

Smoke-test evidence:

- Passed split smoke verification:
  `.venv\Scripts\python.exe -m pytest tests/test_safety_regression.py tests/test_web_api.py --basetemp=.pytest-tmp --no-cov -q --tb=short -o faulthandler_timeout=60`
  (`203 passed`);
  `.venv\Scripts\python.exe -m pytest tests/test_portfolio_analysis.py tests/test_auth.py tests/test_config_security.py --basetemp=.pytest-tmp --no-cov -q --tb=short -o faulthandler_timeout=60`
  (`112 passed`);
  `.venv\Scripts\python.exe -m pytest tests/test_order_executor.py tests/test_tws_bridge.py tests/test_fx_research.py --basetemp=.pytest-tmp --no-cov -q --tb=short -o faulthandler_timeout=60`
  (`161 passed`). Total split smoke coverage: `476 passed`.
- The second smoke group printed non-failing post-pytest database/cache fetch
  messages after pytest completed; the command exited 0.

Known limitations and manual checks:

- This phase does not add dashboard/API exposure for promotion reports; that
  remains part of EL8.
- The report consumes available realized outcome evidence and optional
  operational event records. It does not write approval history or apply
  operator approvals.

## 5. Maintenance rules

Future PRs should update this tracker when they complete a phase or checklist item.

A PR that implements a roadmap phase should update:

- the phase status;
- completed checklist items;
- PR number / notes;
- any new limitations discovered.

If implementation diverges from the spec, update both the spec and this tracker in the same PR or in a documentation follow-up PR.
