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
| Evidence-learning dashboard/API exposure | Done | PR #190; EL8 read-only setup performance, promotion, weak setup, and drift diagnostics exposed through evidence APIs and control tower |
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
| Commission-aware minimum profitability gate | Done | Issue #199; pre-submission gate rejects share buys whose expected net profit at target is below the configured minimum after estimated round-trip commission |
| Strategy-arm learning | Done | PR #169 |
| Evidence-learning performance metrics | Done | PR #183 |
| Evidence-learning setup registry | Done | PR #184 |
| Evidence-learning evidence calibrator | Done | PR #186 |
| Evidence-learning adaptive edge estimator | Done | PR #187 |
| Evidence-learning setup eligibility gate | Done | PR #188 |
| Evidence-learning evidence-aware sizing overlay | Done | PR #189 |
| Validation framework | Done | PR #169 |
| IBKR real-time market-data feed for assisted-live prices | In review | Issue #177; actual-live now requires healthy IBKR live quotes and rejects Yahoo/delayed/frozen feeds by default |
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

Status: Done in PR #182

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

- The report consumes available realized outcome evidence and optional
  operational event records. It does not write approval history or apply
  operator approvals.

### Evidence-learning dashboard/API exposure

Status: Done in PR #190

Checklist:

- [x] Add setup performance API.
- [x] Add promotion report API.
- [x] Add weak setup report API.
- [x] Add evidence drift report API.
- [x] Surface evidence-learning status through the control tower snapshot.
- [x] Preserve read-only/advisory behavior.

Implementation notes:

- Added `autonomous/evidence_learning_summary.py` to summarize realized
  autonomous outcome evidence into setup performance, promotion, weak setup,
  and drift diagnostics.
- Added read-only endpoints under `/api/autonomous/evidence`:
  `/learning-status`, `/setup-performance`, `/promotion-report`,
  `/weak-setups`, and `/drift-report`.
- Added `evidence_learning` to `/api/autonomous/control-tower` for dashboard
  consumers.
- The exposure is advisory and read-only. It does not submit, cancel, replace,
  or flatten orders; does not advance lifecycle state; does not enable live
  trading; and does not apply capital changes.

Test evidence:

- Passed: `.venv\Scripts\python.exe -m pytest tests\test_evidence_learning_summary.py tests\test_api_autonomous_evidence.py tests\test_api_autonomous_live.py::TestControlTower tests\test_evidence_calibrator.py tests\test_capital_promotion.py --basetemp=.pytest-tmp-el8-target2 -q`
  (`25 passed`).

Smoke-test evidence:

- Passed split smoke verification:
  `.venv\Scripts\python.exe -m pytest tests/test_safety_regression.py tests/test_web_api.py --basetemp=.pytest-tmp-el8-smoke1 --no-cov -q --tb=short -o faulthandler_timeout=60`
  (`203 passed`);
  `.venv\Scripts\python.exe -m pytest tests/test_portfolio_analysis.py tests/test_auth.py tests/test_config_security.py --basetemp=.pytest-tmp-el8-smoke2 --no-cov -q --tb=short -o faulthandler_timeout=60`
  (`112 passed`);
  `.venv\Scripts\python.exe -m pytest tests/test_order_executor.py tests/test_tws_bridge.py tests/test_fx_research.py --basetemp=.pytest-tmp-el8-smoke3 --no-cov -q --tb=short -o faulthandler_timeout=60`
  (`161 passed`). Total split smoke coverage: `476 passed`.

Known limitations and manual checks:

- EL8 reads from the local evidence store only; it does not configure a
  default live setup-evidence provider or write approval history.

Closeout note:

- Issue #185 is ready to close after PR #190 and this tracker closeout lands;
  EL3, EL4, EL5, EL6, and EL8 are all merged.

### IBKR real-time market-data feed for assisted-live prices

Status: In review for Issue #177

Checklist:

- [x] Add an autonomous market-data provider interface.
- [x] Adapt `TWSBridge` IBKR tick callbacks into quote snapshots.
- [x] Subscribe assisted-live candidate symbols before ranking/planning.
- [x] Replace candidate execution prices with fresh IBKR bid/ask/last quotes
  when available.
- [x] Add a live-runner readiness gate for the IBKR market-data provider.
- [x] Reject Yahoo, delayed, frozen, stale, missing bid/ask, missing
  timestamp, and unhealthy feed inputs for actual-live autonomous trading by
  default.
- [x] Preserve recommend-only research paths so Yahoo-derived candidates remain
  advisory only.
- [x] Add tests and documentation.

Implementation notes:

- Added `autonomous/market_data_provider.py` with `MarketDataQuote`,
  `MarketDataProviderStatus`, `MarketDataProvider`, and
  `IBKRRealtimeMarketDataProvider`.
- Extended `core/tws_bridge.py` with passive market-data subscription,
  snapshot, status, and permission/error handling. Market-data permission
  errors do not get misclassified as order rejections.
- `AutonomousTradingEngine` now enriches assisted-live candidates from the
  configured market-data provider before ranking and planning.
- `MarketDataHealthGuard` and `TradePlanner` now require IBKR `LIVE` market
  data for assisted-live execution by default and block Yahoo live feeds unless
  a future reviewed configuration change explicitly allows them.
- `AutonomousLiveRunner.evaluate_gates()` now includes
  `live_market_data_ready` and `live_market_data_diagnostics`, and can reject
  with `live_market_data_unavailable` before any order submission attempt.
- `web.routes.api_autonomous` wires the live runner to the current
  `ServiceManager.tws_bridge` by default, while still allowing tests or
  deployments to inject `autonomous_live_market_data_provider`.
- `.env.example` and `docs/ACTUAL_LIVE_TRADING.md` document the new live feed
  safety settings.

Test evidence:

- Passed: `.venv\Scripts\python.exe -m pytest tests\test_market_data_health.py tests\test_trade_planner_execution_quality.py tests\test_autonomous_live_runner.py tests\test_tws_bridge.py --basetemp=.pytest-tmp-177-target2 -q --no-cov`
  (`159 passed`).
- Passed: `.venv\Scripts\python.exe -m pytest tests\test_api_autonomous_live.py -x --basetemp=.pytest-tmp-177-api2 -q`
  (`79 passed`).
- Passed: `.venv\Scripts\python.exe -m pytest tests\test_config.py tests\test_api_autonomous.py tests\test_api_autonomous_live.py tests\test_technical_analysis_signal_provider.py --basetemp=.pytest-tmp-177-api -q --no-cov`
  (`156 passed`).

Smoke-test evidence:

- Passed split smoke verification:
  `.venv\Scripts\python.exe -m pytest tests/test_safety_regression.py tests/test_web_api.py --basetemp=.pytest-tmp-177-smoke1 --no-cov -q --tb=short -o faulthandler_timeout=60`
  (`203 passed`);
  `.venv\Scripts\python.exe -m pytest tests/test_portfolio_analysis.py tests/test_auth.py tests/test_config_security.py --basetemp=.pytest-tmp-177-smoke2 --no-cov -q --tb=short -o faulthandler_timeout=60`
  (`112 passed`);
  `.venv\Scripts\python.exe -m pytest tests/test_order_executor.py tests/test_tws_bridge.py tests/test_fx_research.py --basetemp=.pytest-tmp-177-smoke3b --no-cov -q --tb=short -o faulthandler_timeout=60`
  (`164 passed`). Total split smoke coverage: `479 passed`.
- The first smoke group printed a non-failing post-pytest sparkline fallback
  database message after pytest completed; the command exited 0.

Known limitations and manual checks:

- The provider uses live IBKR quotes only after TWS/Gateway grants market-data
  permissions for the subscribed symbols. A human operator must verify account
  subscriptions and TWS market-data settings before any actual-live session.
- The bridge stores latest quote snapshots; it does not yet construct
  real-time bars for strategy research.
- The live-runner readiness gate checks provider health before the cycle; the
  planner still performs the per-symbol quote freshness/source/type checks
  immediately before a plan can be live-ready.
- This change does not add a new live-order submission path and does not enable
  live trading by default.

## Issue #179 — Market event readiness context

Status: In progress.

Work completed:

- Extended the market-events store toward the durable Issue #179 model with
  source identifiers, UTC timestamps, confidence, importance, raw payload hash,
  lifecycle status, last-seen timestamps, and provider sync logs.
- Added a 28-day market-event sync path for tracked symbols and macro/calendar
  events. The first provider set covers yfinance earnings/dividends, Federal
  Reserve FOMC dates, and deterministic NYSE/Nasdaq holidays/early closes.
- Added stale marking for previously seen future events that disappear from a
  provider result instead of deleting them.
- Added dashboard/API support for event filters, sync-log status, rolling
  ticker items, and popup reminder payloads.
- Added fit-for-trading readiness event-risk context. Critical market-calendar
  blockers are fail-closed for automated paper/live readiness; medium/high
  events are surfaced as warnings/review tasks.

Safety posture:

- Live behaviour changed: no.
- Order submission path changed: no.
- Sizing changed: no.
- Risk gates changed: additive only. Event-risk checks can add warnings or
  blockers but cannot make any trading mode more permissive.
- The sync service logs provider failures and preserves existing events rather
  than deleting data after an outage.

Test evidence:

- Passed: `.venv\Scripts\python.exe -m pytest tests\test_market_events.py tests\test_web_api.py::TestMarketEventsAPI tests\test_api_trading_readiness.py --basetemp=.pytest-tmp-179 -q`
  (`31 passed`).

Smoke-test evidence:

- Initial combined web/safety smoke command timed out after 180s while still
  progressing and without a reported failure.
- Passed split smoke verification:
  `.venv\Scripts\python.exe -m pytest tests\test_web_api.py --basetemp=.pytest-tmp-179-smoke-web -q --no-cov --tb=short -o faulthandler_timeout=60`
  (`187 passed`);
  `.venv\Scripts\python.exe -m pytest tests\test_safety_regression.py --basetemp=.pytest-tmp-179-smoke-safety -q --no-cov --tb=short -o faulthandler_timeout=60`
  (`19 passed`).

Known limitations and manual checks:

- Earnings/dividend data remains best-effort because yfinance calendars vary by
  symbol and availability.
- The built-in US market calendar covers common NYSE/Nasdaq holidays and early
  closes but is not a substitute for an exchange-certified calendar feed.
- Dashboard reminder preferences are browser-local controls for ticker
  visibility, popup sensitivity, and reminder window. They do not change
  backend readiness or risk behaviour.
- Human review should confirm event-risk wording and blocker severity before
  relying on it operationally.

## Issue #195 — Market catalyst enrichment sources

Builds on Issue #179. Adds broader market catalyst sources to make TWS Robot
more context-aware without weakening any trading safety controls.

Work completed:

- Formalized `EnrichmentProvider` abstract base class with `fetch`/`fetch_safe`
  interface for isolated, independently-failing enrichment providers.
- Added `EnrichmentRecord` dataclass for normalized provider output.
- Added `signal` confidence level (joins existing `confirmed`/`estimated`/`tentative`).
- Added event type constants: `SEC_8K`, `SEC_10Q`, `SEC_10K`, `SEC_S3`,
  `SEC_FORM4`, `CPI_RELEASE`, `PPI_RELEASE`, `JOBS_REPORT`, `GDP_RELEASE`,
  `FED_MINUTES`, `CONGRESSIONAL_TRADE`, `NEWS_CATALYST`, `INVESTOR_DAY`,
  `CONFERENCE`, `PRODUCT_EVENT`, `SHAREHOLDER_MEETING`.
- Added event category classification: `SCHEDULED_EVENT`, `FILING_ALERT`,
  `CATALYST_SIGNAL`, `NEWS_CATALYST`.
- Added SEC filing provider with deterministic importance scoring for material
  8-K items, bankruptcy/M&A keywords, and filing type base scores.
- Added macro calendar provider with static 2026 CPI/PPI/Jobs/GDP/Fed Minutes
  release dates (confirmed confidence, offline-safe).
- Added congressional trading provider (catalyst signals, no confirmed future
  event date, degraded gracefully).
- Added company event and news catalyst provider stubs (degraded gracefully).
- Integrated enrichment providers into `sync_market_events` flow with 12-hour
  TTL and per-provider failure isolation.
- Updated `_normalize_event` to allow nullable `start_at_utc` for
  signal-confidence events (uses `published_at_utc` as fallback).
- Updated `_severity_for_event` to handle new macro types (`CPI_RELEASE`,
  `PPI_RELEASE`, `GDP_RELEASE`, `FED_MINUTES`) and SEC/signal types.
- Signal-confidence events capped at medium severity maximum.
- Ticker excludes low-importance signals (importance < 70).
- Reminders exclude all signal-confidence events unless mode is `all`.
- `evaluate_event_risk` ensures signal events can only produce warnings,
  never blockers — enrichment cannot make readiness more permissive.
- Extended `/api/market-events/upcoming` with `confidence` and `category`
  filter parameters and `available_categories` response field.
- Extended `_reminder_message` and `_recommended_action` for new event types.
- Updated `docs/WEB_API_REFERENCE.md` with new parameters and behavior.

Safety stance:

- No live trading enabled.
- No dry-run / paper-trading / risk / kill-switch protections weakened.
- Signal-confidence enrichment can only warn, never block or enable.
- Provider failures are isolated and logged; they cannot delete existing events.
- Deterministic scoring only; no ML-assisted scoring in this phase.
- Sizing unchanged. Risk gates unchanged (additive only).

Test evidence:

- 38 new tests in `tests/test_enrichment_providers.py` covering:
  provider interface, SEC scoring, macro calendar, congressional signals,
  nullable start_at_utc, severity scoring, ticker/reminder filtering,
  readiness behavior, provider failure isolation, dedupe, and sync logs.
- All 22 existing `tests/test_market_events.py` tests pass.
- All 6 `tests/test_web_api.py::TestMarketEventsAPI` tests pass.
- All 5 `tests/test_api_trading_readiness.py` tests pass.
- Full suite: 3062 passed, 18 skipped.

Known limitations:

- SEC provider returns empty results when EDGAR API is unreachable (graceful
  degradation). Production use requires network access and respecting SEC
  rate limits.
- Macro calendar uses static 2026 dates. Future enhancement: fetch from
  BLS/BEA/Fed APIs for dynamic calendar data.
- Congressional trading provider is a stub pending CapitolTrades or equivalent
  API integration. The `normalize_disclosure` static method is available for
  custom integrations.
- Company event and news catalyst providers are stubs pending reliable source
  APIs.
- Some enrichment sources may require API keys or configuration not yet
  implemented.

## 5. Maintenance rules

Future PRs should update this tracker when they complete a phase or checklist item.

A PR that implements a roadmap phase should update:

- the phase status;
- completed checklist items;
- PR number / notes;
- any new limitations discovered.

If implementation diverges from the spec, update both the spec and this tracker in the same PR or in a documentation follow-up PR.

## Opening Range Breakout (ORB) intraday strategy — Issue #203

| Phase | Status | Notes |
|---|---|---|
| Phase 1: Backtest-only MVP | Partial | ORB domain models, conservative `OpeningRangeConfig`, deterministic 1m→5m/15m aggregation, long-only state machine, Model A (displacement/gap) and Model B (break-retest), and a backtest runner (`backtest/opening_range_strategy.py`) are implemented and unit-tested. |
| Phase 1.5: Backtest lab / sweeps / readiness | Complete (Issue #214) | `autonomous/orb_backtest_reports.py` reports (R stats incl. net R after costs, profit factor, drawdown-R, hold time, per-model/symbol/NY-normalized time-of-day, slippage/commission sensitivity in net R, no-trade reasons from session rejections), `run_sweep`, readiness classification (READY_FOR_PAPER/NEEDS_MORE_DATA/DO_NOT_TRADE; net-R gate), evidence saving; `web/routes/api_opening_range.py` API + `/opening-range/backtest` page. Backtest-only, no TWS, evidence required before paper promotion. |
| Phase 2.1: Runtime candle provider | Complete (Issue #205) | `autonomous/candle_aggregator.py` (NY normalization, 1m quality detection, closed 5m/15m aggregation) + `autonomous/candle_data_provider.py` (`RuntimeCandleProvider`: closed 1m candles, on-demand 5m/15m, per-symbol health, backfill). Broker-free, no orders; tests `tests/test_orb_runtime_candle_{provider,aggregation}.py` (19 passing). |
| Phase 2: Paper runtime strategy | Complete (Issue #206) | `strategies/opening_range_breakout.py` (`OpeningRangeBreakoutStrategy`): BaseStrategy plugin registrable with `StrategyRegistry`, configured via `StrategyConfig.parameters`→`OpeningRangeConfig`, one `OpeningRangeSession` per symbol/session, consumes closed 1m bars, emits one long Model A/B `Signal`+`ORBTradeProposal` (stop+target always set), diagnostic-only Model C/bearish, runtime state incl. DATA_DEGRADED. No orders. Tests `tests/test_orb_runtime_strategy.py` (10 passing). |
| Phase 2.3: Dashboard config & session controls | Complete (Issue #207) | `autonomous/orb_session_manager.py` (`ORBSessionManager`): persisted strategy config (config/orb_strategies.json), modes (off/backtest_only/recommend_only/paper_autonomous; tiny-live/assisted-live locked), arm/disarm/disable-today/emergency-stop with validation, paper-readiness gate (READY_FOR_PAPER evidence) and audit logging. API `/api/orb/strategies*`, `/api/orb/status`, `/api/orb/emergency-stop` + `/opening-range/` page (`index.html`, `opening_range.js`). No orders; live locked; paper-autonomous gated. Tests `tests/test_orb_session_{manager,api}.py` (19 passing). |
| Phase 2.4: Recommend-only proposals & audit trail | Complete (Issue #208) | `autonomous/orb_proposals.py` (`ORBProposal`, `ProposalGates`, `ORBProposalStore`): transparent recommend-only trade cards built from `ORBSetup` with entry/stop/target, sizing (qty/risk dollars/position value), R/R, opening range, confirmation candle metadata, setup evidence and 11 gate results. Entry is always a `LIMIT` price (never a raw market order); proposals can't exist without stop+target or for non-long setups. Skip (optional reason) and expire (entry cutoff/invalidation/stale data/session-cap) with full audit logging (`proposal_created/skipped/expired`). API `GET /api/orb/proposals[/<id>]`, `POST .../skip`, `POST .../expire`; execute-paper reserved for the paper-execution phase. No orders placed. Tests `tests/test_orb_trade_proposals.py` (+ API tests in `tests/test_orb_session_api.py`). |
| Phase 2.5: Paper-autonomous execution & protective orders | Complete (Issue #209) | `autonomous/orb_execution.py` (`ORBPaperExecutor`, `SimulatedPaperBracketAdapter`, `ORBOrderProtectionStatus`): executes a valid recommend-only `ORBProposal` as a **paper** trade only (refuses any non-`paper_autonomous` mode; no live path). Marketable-`LIMIT` entry + `STOP`/`LIMIT` protective children — raw market orders are impossible. Bracket preferred (`BRACKET_CONFIRMED`); explicitly-configured paper `EXIT_MANAGER_FALLBACK`; otherwise `MISSING_PROTECTION_REJECTED` with no naked entry. Idempotent per proposal; emergency-stop and per-session cap block execution; every entry/stop/target order links strategy/session/setup/proposal ids; execution/rejection audit-logged (`orb_paper_execution`). `ORBProposalStore.mark_executed` adds the `proposal_executed` transition. API `POST /api/orb/proposals/<id>/execute-paper` requires the owning strategy to be in `paper_autonomous` mode **and** armed for the proposal's session date (mode alone is insufficient — arming enforces the readiness/evidence gates; un-armed, session-date mismatch, and disabled-for-session are all rejected), `GET /api/orb/trades[/<trade_id>]`; emergency-stop also trips the executor and takes precedence over the arming gates. Tests `tests/test_orb_paper_execution.py` (16) + API tests in `tests/test_orb_session_api.py`. No live execution, no shorts, no Model C. |
| Phase 2.6: Intraday exit lifecycle & in-trade monitor | Complete (Issue #210) | `autonomous/orb_trade_store.py` (`ORBTradeState`: ENTRY_PENDING/OPEN/EXIT_PENDING/CLOSED/FAILED, `ORBExitReason`, `ORBIntradayTrade`, `ORBTradeStore`) + `autonomous/orb_exit_manager.py` (`ORBExitManager`): registers each executed paper trade for in-trade monitoring, simulates entry/exit fills from a supplied price provider (never guesses — no price means no fill), and evaluates target/stop/force-flat-time/max-holding-minutes/emergency-stop triggers in priority order. Computes current R, MFE/MAE in R, entry/exit slippage, and realized R; exposes entry/target/stop/exit order status, protection status, time-in-trade, and force-flat countdown. Force-close/manual-close/force-flat/emergency-stop only ever submit a reducing (SELL, original-quantity) order — the trade store makes a second exit request against a non-OPEN trade a no-op, preventing duplicate exits and oversell/over-close. If a mandatory flatten boundary (force-flat/emergency-stop/max-holding) is hit with no live price, the trade is marked `FAILED` with an explicit note rather than silently remaining `OPEN`. Operator actions: `POST /api/orb/trades/<id>/close-now`, `POST /api/orb/trades/<id>/cancel-entry` (only while `ENTRY_PENDING`), `POST /api/orb/strategies/<name>/disable-new-entries` / `enable-new-entries` (blocks only new paper entries; never touches an already-open trade's exit management). In-trade monitor via `GET /api/orb/intraday-trades[/<trade_id>]`. Tests `tests/test_orb_intraday_exit_manager.py` (20) + API tests in `tests/test_orb_session_api.py`. Paper-only, long-only, no Model C. |
| Phase 2.7: End-of-session review & evidence ledger | Complete (Issue #211) | `autonomous/orb_evidence.py`: read-only evidence ledger reconstructed purely from the existing durable ORB audit log (`orb_proposal`/`orb_paper_execution`/`orb_intraday_exit` records) — proposal lifecycle (created/skipped/expired/executed with reasons, now including the full setup/trade-card context — entry model, entry/stop/target, opening range, confirmation candle, gates, setup evidence — reconstructed from the `proposal_created` audit record so a no-trade day still shows the setup that was skipped/expired), full trade evidence (entry/exit prices, slippage, estimated commission, realized R, MFE/MAE, exit reason including mandatory-exit-failure reasons like `FORCE_FLAT`/`EMERGENCY_STOP` when no live price was available, result WIN/LOSS/BREAKEVEN/FAILED), blocked/rejected execution attempts, and a reconstructed no-trade explanation so a no-trade day is as explainable as a trade day. Saved backtest evidence is scoped to the strategy being summarized (explicit `strategy_name` tag when present, else a symbol-overlap fallback against the strategy's watched symbols) so one strategy's `READY_FOR_PAPER` backtest evidence never leaks into another strategy's promotion classification. `autonomous/orb_session_review.py` (`ORBSessionReviewStore`): builds per-session reviews, persists operator notes (`config/orb_review_notes.json`), lists reviews for a date across configured strategies, and produces multi-session evidence summaries grouped by symbol/model/date/result with a promotion classification (READY_FOR_PAPER/NEEDS_MORE_DATA/DO_NOT_TRADE/TINY_LIVE_CANDIDATE) that distinguishes saved backtest evidence from paper evidence. `autonomous/orb_exit_manager.py` now also persists MFE/MAE on the `exit_filled` audit record so they survive a process restart. API `GET /api/orb/review`, `GET /api/orb/evidence/<strategy_name>[/export]`, `POST /api/orb/review/<session_id>/notes` + `/opening-range/review` page. Read-only reporting layer: no order is placed or affected. Tests `tests/test_orb_evidence_ledger.py` (31 passing) plus the full ORB suite (178 tests across the evidence/proposal/session/backtest/execution/exit-manager/runtime-strategy modules) and the full repository suite (3315 passed, 18 skipped). |
| Phase 3: Autonomous adapter | Complete (Issue #212) | `autonomous/opening_range_signal_provider.py` (`OpeningRangeSignalProvider`, `MappingOpeningRangeSetupSource`): optional `SignalProvider` adapter mapping a valid, still-open `ORBSetup` onto an ORB-labeled `CandidateSignal` (`ORB_LONG_MODEL_A`/`ORB_LONG_MODEL_B`, `extras.strategy="opening_range_breakout"` plus entry/stop/target/risk/reward/R:R/opening-range/confirmation-time/evidence) so ORB can flow through `AutonomousTradingEngine` orchestration (cash checks, ranking, planning, risk gates, evidence logging) without forcing the `Confirmed Rebound` / `Strong(100)` assumptions. Long-only, Model A/B only (Model C and short-side setups rejected), malformed setups (missing/invalid entry/stop/target or R:R, wrong price ordering) rejected rather than raised. `AutonomousTradingConfig.allowed_signal_labels` (optional whitelist) lets the ranker accept ORB labels without changing `required_signal_label`; when unset, prior rebound-only behavior is unchanged. `TradePlanner` gained an ORB-aware branch (`candidate.extras.strategy == "opening_range_breakout"`) that **fails closed**: it requires `candidate.signal_label in {ORB_LONG_MODEL_A, ORB_LONG_MODEL_B}`, `extras.setup_model in {MODEL_A_DISPLACEMENT_GAP, MODEL_B_BREAK_RETEST}`, and `extras.direction == "LONG"` (a missing direction is rejected, not treated as implicitly long) before trusting `extras.strategy` alone — this stops a malformed/external candidate (e.g. `signal_label="Confirmed Rebound"` + `extras.strategy="opening_range_breakout"`, or `setup_model="MODEL_C_REVERSAL"`) from receiving an ORB share-buy plan. Entry/stop/target are used exactly as provided (never overwritten by resistance/ADR/percent target logic or support-derived stops), malformed ORB extras are rejected, and ORB evidence/model/direction is preserved on the resulting `TradePlan` (`strategy`/`extras` fields, flowing into the audit log via `to_dict()`). `AutonomousTradingEngine._execute_paper`/`_execute_paper_basket` now explicitly reject any `TradePlan` with `strategy == "opening_range_breakout"` (`"ORB paper execution must use ORBProposal/ORBPaperExecutor protected path"`) so an ORB plan accepted via `allowed_signal_labels` can never reach the generic naked-entry paper adapter (`paper_adapter.buy()` with no stop/target) — the protected Phase 2.5 `ORBPaperExecutor`/bracket path remains the only paper-execution route for ORB; recommend-only planning and assisted-live plan review are unaffected. All existing VIX/emergency-stop/execution-quality/market-data/daily-cap/drawdown guards remain active for ORB candidates. Tests: `tests/test_opening_range_signal_provider.py` (20), `tests/test_orb_trade_planner.py` (16, incl. Model C / wrong signal_label / missing direction rejection), `tests/test_orb_candidate_ranker_eligibility.py` (6), `tests/test_orb_paper_execution_blocked.py` (2, engine-level regression confirming `paper_adapter.buy()` is never called for an ORB plan in `PAPER_EXECUTE`); full repository suite 3362 passed, 18 skipped. No live enablement, no shorts, no Model C, existing rebound scanner untouched. |
| Phase 4: Live-readiness review | Complete (Issue #213) | `autonomous/orb_live_readiness.py`: read-only, broker/network-free evaluation of the guarded path from paper ORB evidence to tiny-live/assisted-live review. `evaluate_orb_live_readiness()` runs a fixed checklist (config valid/persisted, evidence-gated paper thresholds via `classify_promotion` plus drawdown-R/consecutive-losses/entry-slippage bounds, no unresolved protection failures, no repeated data-quality failures, no ORB-caused emergency-stop incidents, data-provider healthy, acceptable market-data source, broker connection/account confirmation, live master switch enabled, tiny-live caps strictly stricter than paper caps (`TinyLiveRiskCaps`, default `max_deployable_cash_pct<=0.01`/`max_live_orb_trades_per_day==1`), mandatory stop/target/bracket protection, emergency-stop tested+available **and** not currently tripped, long-only, Model C disabled, and explicit operator confirmation of both account id and mode) and returns `LOCKED`/`TINY_LIVE_CANDIDATE`/`ASSISTED_LIVE_CANDIDATE` plus per-gate pass/fail reasons; assisted-live additionally requires an explicit `expected_account_id` session confirmation. Every evaluation and `log_operator_decision()` call is audit-logged (`kind="orb_live_readiness"`) regardless of outcome. `compute_r_stats()` derives max-drawdown-R/max-consecutive-losses from a chronological realized-R sequence. API `GET /api/orb/strategies/<name>/live-readiness` (`web/routes/api_opening_range.py`) wires strategy config, evidence-ledger paper summary, connection/account/emergency-stop state, and `AutonomousLiveRunnerConfig` into the evaluator. Following review feedback, the drawdown-R/consecutive-losses/entry-slippage-bps and protection/data-quality/emergency-stop counters are now reconstructed from the ORB evidence ledger itself (`compute_r_stats()` over chronological closed-trade `realized_r`, `compute_avg_entry_slippage_bps()` over `entry_slippage`/fill price, and `build_rejection_ledger()`/exit-reason/failure-note scans) rather than defaulted from query parameters; any query-string override may only ever raise an observed failure above the evidence-derived floor, never lower it. Tiny-live caps (`TinyLiveRiskCaps`) now always evaluate the actual `AutonomousLiveRunnerConfig.max_deployable_cash_pct`/`max_live_trades_per_day` for the blocking gate; if query-string cap overrides are supplied they are exposed only as `simulated_tiny_live_caps` diagnostics and never rescue an unsafe live-runner configuration. Operator account/mode confirmation is no longer accepted via GET query string: a new `POST /api/orb/strategies/<name>/live-readiness/confirm` endpoint (backed by `ORBLiveReadinessConfirmationStore`, persisted to `logs/orb_live_readiness_confirmations.json`) is the only way to satisfy the `operator_confirmation` gate, and every confirmation attempt (matched or mismatched) is persisted and audit-logged via `log_operator_decision()` with requested mode, expected/connected account id, operator, and notes; the GET endpoint only reads a prior confirmation. Query-string overrides otherwise can never unlock live trading on their own — the live master switch and a confirmed broker connection/account remain independently required. No order is placed, simulated, or routed; no live switch is flipped by this phase. Tests `tests/test_orb_live_readiness.py` (35) + `tests/test_orb_live_readiness_api.py` (14, incl. evidence-derived-failure, tiny-live-cap-sourcing, and POST-confirmation regression tests); full repository suite 3408 passed, 18 skipped. No short entries, no Model C execution, no forex/futures, no automatic live promotion. |

Work completed: `autonomous/opening_range.py`, `backtest/opening_range_strategy.py`, and tests `tests/test_opening_range_*.py` (28 tests passing). Long-only, paper/backtest-only, no broker connection, no raw market orders (marketable-limit prices), one trade per symbol per session. Review fixes: session minutes normalized to NY for timezone-aware (UTC) candles; opening range requires the exact contiguous 9:30–9:44 NY 1m bars (rejects duplicate/missing); Model B retest must occur after 5m confirmation; Model A enters only on a bar after 5m confirmation; backtest force-flat compares NY-normalized time and the per-session cap allocates by earliest `detected_at`. See `docs/OPENING_RANGE_BREAKOUT.md`.

Known limitations / risks: bearish breakouts are diagnostic-only; Model C disabled; runtime/paper/autonomous integration deferred to follow-up PRs; naive timestamps assumed NY-local.
