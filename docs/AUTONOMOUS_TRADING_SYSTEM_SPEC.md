# Autonomous Trading System Specification

This document is the design and implementation reference for the TWS Robot autonomous trading feature.

It consolidates the completed trading-intelligence tranche and the next roadmap for continuous autonomous live readiness.

Implementation progress is tracked separately in:

```text
docs/AUTONOMOUS_IMPLEMENTATION_TRACKER.md
```

## 1. Objective

TWS Robot should evolve from a guarded trading automation tool into a robust autonomous trading system that can identify, size, execute, monitor, and reconcile trades while preserving a safety-first operating model.

The objective is not maximum trade frequency, maximum leverage, or maximum short-term return.

The objective is:

> Maximize expected long-term risk-adjusted wealth growth while minimizing probability of ruin, operational mistakes, and regime-driven drawdowns.

## 2. Core philosophy

The robot should behave like a disciplined operator, not a gambler.

Key principles:

- Prefer missing a trade over entering a bad trade.
- Prefer small repeated positive-expectancy bets over one concentrated bet.
- Express edge through controlled baskets when enough candidates exist.
- Never allow one module to bypass hard risk controls.
- Do not scale capital automatically without evidence and operator approval.
- Make every decision reconstructable from signal to outcome.
- Treat live broker state as the source of truth for actual positions and orders.

## 3. Current architecture

The autonomous pipeline is intentionally layered:

```text
SignalProvider / CandidateScanner
-> CandidateRanker
-> TradePlanner / BasketPlanner
-> AutonomousTradingEngine gates
-> AutonomousPaperRunner or AutonomousLiveRunner
-> OrderExecutor
-> TradeStore / EvidenceStore
-> Outcome reconciliation / risk lifecycle
```

Responsibilities:

| Layer | Responsibility |
|---|---|
| Signal provider | Convert market data/screener rows into candidate signals |
| Scanner | Scan configured universe and produce candidates |
| Ranker | Apply hard filters and edge-aware ranking |
| Feature builder | Build candidate/regime features for edge estimation |
| Trade planner | Build individual trade plans with targets, stops, and sizing |
| Basket planner | Convert ranked candidates into capped multi-leg plans |
| Engine | Apply gates and produce a structured autonomous decision |
| Paper runner | Execute eligible plans in paper mode |
| Live runner | Submit live-ready plans through OrderExecutor when live gates pass |
| OrderExecutor | Submit broker orders with existing risk/reconciliation checks |
| Evidence store | Persist decision and outcome evidence |
| Outcome reconciler | Convert closed trades/fills into realized outcome records |
| Risk lifecycle | Stop new entries after loss/drawdown events |

## 4. Operating modes

| Mode | Description | Order placement |
|---|---|---|
| Recommend only | Generate decision and trade plan only | No order |
| Paper execute | Submit through paper adapter | Paper order only |
| Assisted live | Engine prepares `LIVE_PLAN_READY`; live runner submits through `OrderExecutor` | Real order if all live gates pass |
| Continuous live | Repeated live cycles under supervisor | Future target; not yet fully ready |

Important clarification:

- `AutonomousTradingEngine.run_once()` does not itself directly submit live orders; it returns `LIVE_PLAN_READY`.
- `AutonomousLiveRunner.run_once()` can submit a real live order through `OrderExecutor` when live gates pass and dry-run is disabled.

## 5. Implemented capabilities snapshot

The first major trading-intelligence tranche has been substantially implemented through PRs #162-#172.

| Capability | Status |
|---|---|
| Evidence foundation | Implemented |
| Recent evidence API | Implemented |
| Support/resistance enrichment | Implemented |
| Assisted-live stop requirement | Implemented |
| VIX / market-regime guard | Implemented |
| Opt-in basket planner | Implemented |
| Risk-per-trade sizing | Implemented |
| Volatility sizing | Implemented |
| Feature builder | Implemented |
| Rule-based edge estimator | Implemented |
| Expected-R ranking | Implemented |
| Fractional edge / fractional-Kelly-style sizing | Implemented as `FractionalEdgeSizer` |
| Drawdown governor | Implemented |
| Execution quality guard | Implemented |
| Strategy-arm learning | Implemented |
| Validation framework | Implemented |
| Outcome reconciliation | Implemented |
| Strategy equity curve and risk lifecycle | Implemented |
| Sector/time-of-day context | Implemented |
| Chronological validation reports | Implemented |

## 6. Current readiness assessment

TWS Robot is currently suitable for:

- recommend-only autonomous analysis;
- paper execution;
- evidence collection;
- controlled assisted-live trading with conservative caps;
- live order submission through `AutonomousLiveRunner` when all live gates pass.

TWS Robot is not yet suitable for:

- unattended continuous live operation;
- automatic capital scaling;
- unsupervised recovery from broker/local state mismatch;
- assuming every live position is protected unless broker-side protection is verified;
- treating baskets as the default live mode without basket-level risk budgeting.

## 7. Non-negotiable safety invariants

These rules should hold across all future development.

1. No market orders from autonomous mode.
2. No live trade without a valid stop or explicit fallback protection policy.
3. No continuous live mode without broker-state reconciliation.
4. No duplicate order for the same signal/basket leg.
5. No automatic capital promotion.
6. No basket mode that multiplies total risk without a basket-level risk budget.
7. No new entries when emergency stop is active.
8. No new entries when risk lifecycle blocks trading.
9. No live trading on stale or degraded quote data.
10. Every live position must have confirmed broker-side protection before the system is considered healthy.
11. Every order state transition must be auditable.
12. Every trade must be reconstructable from signal to decision to order to exit to outcome.

## 8. Basket trading design

### 8.1 Rationale

A single trade is a high-variance expression of an edge.

If the strategy has positive expectancy, it is generally better to express that edge across multiple smaller independent or semi-independent bets than through one concentrated bet.

Basket mode should therefore become the preferred long-term autonomous model, but only if total basket risk is controlled.

### 8.2 Current basket behaviour

The current basket planner:

- takes ranked candidates in order;
- stops at `basket_max_size`;
- applies per-position exposure caps;
- applies total basket notional/exposure cap;
- applies same-sector concentration cap;
- applies a shared basket-level stop-risk budget;
- reduces or rejects legs that cannot fit the allocated stop-risk;
- returns multiple `TradePlan` objects when possible;
- falls back to a single candidate if no valid basket plan is produced.

### 8.3 Basket-level risk allocation

Basket mode controls both notional/exposure and a centrally allocated shared
stop-risk budget across all basket legs.

Desired behaviour:

```text
max_basket_risk_equity_pct = 0.002
account equity = 50,000
max basket planned risk = 100

3-leg basket:
leg A planned risk <= 33
leg B planned risk <= 33
leg C planned risk <= 33
sum(all planned stop-risk) <= 100
```

The robot should prefer:

```text
more trades, smaller per-leg risk, same controlled total risk
```

not:

```text
more trades, same per-leg risk, multiplied total risk
```

Current behaviour:

- `BasketRiskAllocator` is enabled by default when basket mode is enabled.
- The default allocation mode is `equal_risk`.
- The allocator only supports `BUY_SHARES` legs with a valid stop below entry.
- The allocator can reduce a leg quantity or reject a leg, but cannot increase size.
- Basket diagnostics include budget, planned risk, budget usage, and per-leg decisions.

## 9. Evidence and audit requirements

Every autonomous decision should be evidence-backed.

Decision evidence should include:

- timestamp;
- config snapshot;
- market regime;
- risk lifecycle status;
- deployable cash snapshot;
- candidate shortlist;
- rejected candidates and reasons;
- selected candidate or basket;
- trade plans;
- sizing diagnostics;
- execution quality diagnostics;
- planned risk;
- target and stop;
- order references when submitted.

Outcome evidence should include:

- autonomous trade ID;
- symbol;
- strategy bucket;
- entry order ID;
- exit order ID;
- fill summaries;
- entry price;
- exit price;
- commissions;
- slippage;
- partial-fill flag;
- realized P&L;
- realized R-multiple;
- exit reason.

## 10. Current implementation naming note: KellySizer vs FractionalEdgeSizer

The original roadmap used the term `KellySizer`.

The implemented module is named `FractionalEdgeSizer`.

This is intentional and acceptable because the implementation is a conservative fractional-Kelly-style sizing cap, not full Kelly sizing.

Current behaviour:

- disabled by default;
- requires minimum evidence count;
- uses `p_win`, `avg_win_r`, `avg_loss_r`, and confidence;
- computes a raw Kelly-style fraction;
- applies a conservative fraction multiplier;
- cannot increase size by default;
- can reduce size when the edge estimate is poor.

Roadmap interpretation:

| Roadmap term | Implemented term |
|---|---|
| KellySizer | FractionalEdgeSizer |
| KellySizingDecision | FractionalSizingDecision |
| KELLY_* config | fractional_edge_* config |

A rename is not required unless traceability becomes confusing.

## 11. Next implementation roadmap: continuous autonomous live readiness

The next roadmap shifts from trading-intelligence features to operational robustness.

### Phase 1 — Basket-level risk allocation

#### Problem

Basket mode should not multiply risk simply because more candidates are selected.

#### Target behaviour

A shared basket risk budget is allocated across selected legs.

#### Module

```text
autonomous/basket_risk_allocator.py
```

#### Config

```python
basket_risk_allocator_enabled: bool = True
max_basket_risk_equity_pct: float = 0.002
basket_risk_allocation_mode: str = "equal_risk"
basket_min_leg_risk_dollars: float = 20.0
```

#### Acceptance criteria

- Total basket planned stop-risk cannot exceed configured basket risk budget.
- Each leg shows planned risk dollars.
- Basket output shows total planned risk dollars and budget usage.
- Legs that cannot fit the risk budget are rejected with reasons.
- Existing sector and notional caps continue to apply.

#### Current implementation status

Implemented in the basket-level risk allocation PR continuing issue #161.

The implementation is conservative: it only reduces or rejects basket legs and
does not change order submission, live-gate, or broker execution paths.

#### Test plan

- 3-leg basket splits total risk budget equally.
- Leg is rejected if one share exceeds allocated risk budget.
- Total risk remains within budget after rejection.
- Basket diagnostics are included in `BasketPlan.to_dict()` and evidence.

### Phase 2 — Broker order lifecycle state machine

#### Problem

Continuous trading requires explicit state tracking for every autonomous broker order.

#### Proposed module

```text
autonomous/order_lifecycle.py
```

#### Config

```python
order_lifecycle_store_path: str = "logs/autonomous_order_lifecycle.jsonl"
```

#### Proposed states

```text
PLANNED
SUBMITTED
ACKNOWLEDGED
PARTIALLY_FILLED
FILLED
PROTECTIVE_STOP_PENDING
PROTECTIVE_STOP_CONFIRMED
TARGET_PENDING
EXIT_PENDING
CLOSED
RECONCILED
```

Failure / recovery states:

```text
REJECTED
CANCELLED
EXPIRED
STALE_QUOTE_BLOCKED
BROKER_DISCONNECTED
ORPHANED_ORDER
DUPLICATE_ORDER_BLOCKED
RECOVERY_REQUIRED
```

#### Acceptance criteria

- Every live autonomous order has a lifecycle record.
- Every transition is evidence-backed.
- Rejected orders do not silently consume live-trade slots forever.
- Partial fills are visible and tied to order IDs.
- Orphaned orders can be detected and flagged.

#### Current implementation status

Implemented in the current PR continuing issue #161.

The implementation adds an append-only `OrderLifecycleStore` and records live
runner lifecycle events for:

- planned entry orders before the `OrderExecutor` call;
- submitted parent entry orders;
- bracket target and protective-stop child orders as pending;
- `OrderExecutor` rejections;
- broker-rejected entry reconciliation;
- bracket target/stop fills;
- stale local open trades whose broker position is no longer present.

This is an audit/state-tracking layer. It does not add a new order submission
path or enable live trading. Broker-side protective stop verification is
implemented in Phase 3 below.

### Phase 3 — Broker-side protective stop / bracket verification

#### Problem

A planned stop is not the same as broker-confirmed protection.

#### Target behaviour

```text
entry filled
-> stop/bracket submitted
-> broker acknowledges protective order
-> stop quantity matches filled quantity
-> trade marked protected
```

#### Proposed module

```text
autonomous/protection_verifier.py
```

#### Acceptance criteria

- Every live autonomous position has a confirmed broker-side stop/bracket or equivalent exit protection.
- Missing protection marks the trade/system as `RECOVERY_REQUIRED`.
- New entries are blocked while protection is missing.
- Partial-fill protection quantity is adjusted to actual filled quantity.

#### Config

```python
require_broker_protection_confirmation: bool = True
```

Environment variable:

```text
AUTONOMOUS_REQUIRE_BROKER_PROTECTION_CONFIRMATION=true
```

#### Current implementation status

Implemented in the current PR continuing issue #161.

The implementation adds `autonomous/protection_verifier.py` and verifies open
autonomous live trades against broker-visible open-order snapshots from
`TWSBridge.get_open_order_snapshots()`.  A trade is marked protected only when
the broker snapshot contains an active protective SELL stop/bracket order for
the trade symbol with quantity at least as large as the broker-held position.

When protection is missing or cannot be verified:

- `AutonomousLiveRunner.evaluate_gates()` fails closed;
- readiness output includes `protection_diagnostics`;
- the order lifecycle store records `RECOVERY_REQUIRED`;
- the open trade continues to consume its live slot so new entries remain
  blocked until protection is restored or the trade is reconciled closed.

When protection is verified, the stop lifecycle records
`PROTECTIVE_STOP_CONFIRMED`.

This does not submit replacement stop orders, cancel orders, or alter live
order routing. Recovery remains an operator/manual follow-up until the later
supervisor/recovery phases.

### Phase 4 — Idempotency and duplicate-order prevention

#### Problem

Repeated cycles, browser refreshes, or crashes can otherwise produce duplicate orders.

#### Proposed module

```text
autonomous/idempotency.py
```

#### Proposed identifiers

```text
run_id
decision_id
basket_id
leg_id
signal_timestamp
symbol
intended_action
```

#### Acceptance criteria

- The same signal/basket leg cannot submit duplicate orders.
- Restart after submission but before evidence write cannot create duplicate exposure.
- Existing open autonomous trade for a symbol blocks duplicate entry unless explicitly allowed.
- Operator can inspect and clear stale idempotency locks.

#### Config

```python
allow_duplicate_symbol_live_entries: bool = False
idempotency_store_path: str = "logs/autonomous_idempotency.jsonl"
idempotency_stale_minutes: int = 120
```

Environment variables:

```text
AUTONOMOUS_ALLOW_DUPLICATE_SYMBOL_LIVE_ENTRIES=false
AUTONOMOUS_IDEMPOTENCY_STORE_PATH=logs/autonomous_idempotency.jsonl
AUTONOMOUS_IDEMPOTENCY_STALE_MINUTES=120
```

#### Current implementation status

Implemented in the current PR continuing issue #161.

The implementation adds `autonomous/idempotency.py`, an append-only JSONL
lock store for live autonomous entry attempts.  Non-dry-run live execution now
acquires a symbol/action idempotency lock before recording `PLANNED` and
before calling `OrderExecutor`.  If an active lock already exists, or if a
local open autonomous trade already exists for the same symbol, the runner
fails closed with `duplicate_order_blocked` and records
`DUPLICATE_ORDER_BLOCKED` in the order lifecycle store.

The basket live-runner path preflights the full basket before submitting any
leg.  A repeated symbol, existing open trade, or existing idempotency lock
blocks the basket before the first broker submission, avoiding partial basket
execution caused by duplicate-leg detection.

Accepted broker submissions mark the lock `SUBMITTED` with the broker order ID
and autonomous trade ID.  Rejections, lifecycle write failures, and executor
exceptions clear the in-flight lock.  Locks for locally terminal trades are
cleared during readiness reconciliation, and operators can inspect stale locks
or explicitly clear a lock with the runner recovery helpers.

This phase does not add any new live-order route, does not auto-clear stale
locks, and does not weaken the existing live/dry-run/risk gates.

### Phase 5 — Quote freshness and market-data health guard

#### Problem

Execution quality checks are not enough if the quote itself is stale or the feed is degraded.

#### Proposed module

```text
autonomous/market_data_health.py
```

#### Checks

- bid timestamp;
- ask timestamp;
- last timestamp;
- quote age;
- spread;
- last-vs-mid deviation;
- market open/closed state;
- market data feed health.

#### Acceptance criteria

- Live mode blocks stale quotes.
- Decision/evidence records include market-data health diagnostics.
- Missing bid/ask can be configured to block in live mode.
- Stale-data reason is visible in rejection output.

#### Current implementation status

Implemented in the Issue #161 continuation PR:

- `autonomous/market_data_health.py` evaluates quote freshness, bid/ask
  presence, crossed/wide spreads, last-vs-mid deviation, market-open state,
  and feed health.
- `AutonomousTradingConfig` exposes market-data guard settings:
  `market_data_health_guard_enabled`,
  `market_data_max_quote_age_seconds`, `market_data_max_spread_pct`,
  `market_data_max_last_mid_deviation_pct`,
  `market_data_block_stale_quotes_live`,
  `market_data_block_missing_bid_ask_live`,
  `market_data_block_missing_timestamp_live`,
  `market_data_block_feed_unhealthy_live`, and
  `market_data_block_market_closed_live`.
- `TradePlanner` evaluates market-data health before execution-quality
  checks, blocks assisted-live stale/degraded/closed-market plans, records
  rejection reasons, and attaches `market_data_health` diagnostics to
  successful trade plans.
- `TechnicalAnalysisSignalProvider` maps available quote metadata into
  candidate `extras` so planner diagnostics can be evidence-ready.
- Missing bid/ask blocking remains configurable; the default preserves
  current recommend-only and assisted-live fixtures while allowing operators
  to fail closed by setting `market_data_block_missing_bid_ask_live=True`.

This phase does not add any new live-order submission path and does not
enable live trading.

### Phase 6 — Automatic broker-fill ingestion

#### Problem

Outcome reconciliation should not depend on manual fill handoff in continuous mode.

#### Proposed module

```text
autonomous/broker_fill_ingestor.py
```

#### Inputs

- execution ID;
- order ID;
- symbol;
- side;
- quantity;
- fill price;
- commission;
- timestamp;
- exchange/liquidity when available.

#### Acceptance criteria

- IBKR fill events update trade store.
- Partial fills are aggregated.
- Commission is captured.
- Closed trades automatically emit `autonomous_outcome` records.
- Risk lifecycle and equity curve can consume outcomes without manual intervention.

#### Current implementation status

Implemented in the Issue #161 continuation PR:

- `autonomous/broker_fill_ingestor.py` consumes execution-level broker fill
  snapshots, merges repeated/enriched executions by execution ID, aggregates
  partial entry and exit fills, and updates `TradeStore`.
- `AutonomousTrade` persists `entry_fills`, `exit_fills`, and
  `outcome_emitted` so fill evidence survives process restarts.
- `TWSBridge` captures IBKR `execDetails` and `commissionReport` callbacks and
  exposes `pop_broker_fill_events()` for idempotent ingestion.
- `AutonomousLiveRunner` optionally drains broker fill events before readiness
  checks so continuous-mode slot counts and outcome evidence reflect broker
  fills before the next cycle.
- `OrderLifecycleStore` receives `PARTIALLY_FILLED`, `FILLED`, and `CLOSED`
  transitions from ingested fills.
- Closed trades emit `autonomous_outcome` records through
  `OutcomeReconciler` and `OutcomeEvidenceWriter` when an outcome writer is
  configured.

This phase is accounting-only. It does not add any order submission,
cancel/replace, child-order resize, or live-mode enablement path.

### Phase 7 — Continuous-run supervisor

#### Problem

The engine should not also be the scheduler, watchdog, and recovery controller.

#### Proposed module

```text
autonomous/continuous_supervisor.py
```

#### Responsibilities

- prevent overlapping runs;
- maintain heartbeat;
- enforce run cadence;
- pause after errors;
- pause after broker disconnect;
- pause after unreconciled lifecycle state;
- pause after risk-lifecycle breach;
- expose supervisor status.

#### Acceptance criteria

- Only one autonomous cycle can run at a time.
- Supervisor can pause/resume without changing strategy code.
- Serious operational faults stop new entries.
- Heartbeat is visible to API/dashboard.

#### Current implementation status

Implemented in the Issue #161 continuation PR:

- `autonomous/continuous_supervisor.py` adds a dependency-injected
  `ContinuousSupervisor` with non-overlap locking, cadence enforcement,
  heartbeat/status snapshots, pause/resume controls, and structured
  `SupervisorFault` / `SupervisorCycleResult` records.
- The live lifecycle worker and `/api/autonomous/live/status` auto-advance path
  route continuous cycles through the supervisor so status polling cannot
  bypass overlap or cadence controls.
- The supervisor pauses fail-closed on broker disconnect, emergency stop,
  unreconciled protection/lifecycle recovery state, failed live trades, risk
  lifecycle breach results, and tick exceptions.
- `/api/autonomous/live/status` exposes `continuous_supervisor` state including
  heartbeat, pause reason, last result, counters, and next eligible run time.

This phase is a coordination layer only. It does not add order submission,
automatic recovery, cancel/replace, live-mode enablement, or capital scaling.

### Phase 8 — Restart recovery and broker reconciliation

#### Problem

After restart, the robot must reconstruct actual broker reality before trading.

#### Proposed module

```text
autonomous/recovery_manager.py
```

#### Reconcile

- local trade store;
- evidence logs;
- IBKR open orders;
- IBKR current positions;
- recent executions;
- cash/deployable cash;
- risk lifecycle status.

#### Startup classifications

```text
SAFE_TO_TRADE
SAFE_TO_MONITOR_ONLY
RECOVERY_REQUIRED
MANUAL_INTERVENTION_REQUIRED
```

#### Acceptance criteria

- Robot cannot blindly resume trading after restart.
- Broker/local mismatches block new entries until resolved.
- Recovery decisions are logged.
- Operator can see what needs manual action.

#### Current implementation status

Implemented in the current PR continuing issue #161.

The implementation adds `autonomous/recovery_manager.py` and a read-only
startup/recovery classifier used by `AutonomousLiveRunner.evaluate_gates()`.
The recovery report reconciles:

- local autonomous trade-store state;
- append-only order lifecycle current states;
- active/stale idempotency locks;
- broker positions;
- broker-visible open orders;
- broker-side protection diagnostics;
- deployable-cash snapshot.

Startup/readiness is classified as:

```text
SAFE_TO_TRADE
SAFE_TO_MONITOR_ONLY
RECOVERY_REQUIRED
MANUAL_INTERVENTION_REQUIRED
```

`/api/autonomous/live/status` exposes the recovery classification through the
existing live-runner readiness payload.  Continuous supervision pauses
fail-closed when recovery is required.

The recovery manager is deliberately conservative.  Local/broker position
mismatches, unmatched active broker BUY orders, stale or trade-less
idempotency locks, broker protection failures, and recovery lifecycle states
block new entries until an operator reviews or clears the condition.

This phase does not submit replacement stop orders, cancel open orders, flatten
positions, auto-clear stale locks, or enable live trading.  It only classifies
and blocks unsafe restart/resume states.

### Phase 9 — Enhanced emergency stop operations

#### Current state

TWS Robot already has an emergency stop that blocks new autonomous trading.

#### Target enhancement

Upgrade it into a continuous-mode operational stop system.

#### Desired behaviour

- block new entries;
- pause supervisor;
- optionally cancel pending entry orders;
- preserve protective exit orders unless explicitly flattening;
- alert/log the stop event;
- require manual reset.

#### Separate controls

```text
Emergency Stop = pause and block new entries
Panic Flatten = close autonomous positions explicitly
```

#### Acceptance criteria

- Emergency stop state is visible via API/dashboard.
- Pending entry order cleanup is available.
- Protective exits are not accidentally cancelled.
- Reset is auditable.

#### Implementation notes

Phase 9 adds enhanced autonomous emergency-stop operations:

- `POST /api/autonomous/emergency-stop` writes the emergency-stop marker,
  turns paper and live autonomous modes off, stops lifecycle workers, pauses
  the live continuous supervisor, and writes an autonomous audit event.
- The same endpoint accepts `cancel_pending_entries=true` to forward broker
  cancel requests for pending live autonomous entry order IDs only.  Paper
  entry order IDs are reported but not sent to the broker, and target/stop
  child order IDs are reported as preserved protective exits.
- `POST /api/autonomous/emergency-reset` requires `confirm=true`, removes only
  an emergency-stop marker created by `/api/autonomous/emergency-stop`, keeps
  autonomous modes off, resumes the supervisor only when it was paused by
  emergency stop, and writes an audit event.  Global/manual emergency markers
  must be cleared through `/api/emergency/resume`.
- `GET /api/autonomous/status` and `GET /api/autonomous/live/status` expose a
  structured `emergency_stop` payload including file state, reset requirement,
  and the fact that Panic Flatten is a separate explicit control.

This phase does not flatten positions, cancel protective exits, submit
replacement stops, auto-reactivate autonomous mode, or enable live trading.

### Phase 10 — Control tower dashboard/API

#### Problem

The operator needs fast visibility into system status.

#### Expose

- current mode;
- autonomous enabled/disabled;
- last heartbeat;
- IBKR connection state;
- market-data health;
- cash/deployable cash;
- open autonomous trades;
- open broker orders;
- basket risk usage;
- confirmed protective stops;
- daily/weekly/monthly R;
- recent decisions;
- recent rejections;
- recent fills;
- emergency stop status.

#### Acceptance criteria

- Operator can understand robot status in under 30 seconds.
- Open trade drilldown links signal -> decision -> order -> outcome.
- Serious warnings are visible.
- Emergency stop status is prominent.

#### Implementation notes

Phase 10 adds a consolidated passive operator snapshot endpoint:

- `GET /api/autonomous/control-tower` exposes current paper/live mode state,
  autonomous enabled state, live supervisor heartbeat, IBKR connection/account
  context, cash/deployable-cash diagnostics, paper/live autonomous trade
  counts, broker-visible open-order snapshots, append-only order lifecycle
  current states, latest basket risk diagnostics from evidence, passive
  broker-protection verification, risk/recovery readiness, recent decisions,
  recent rejections, recent fills/outcomes, and emergency-stop status.
- The control-tower endpoint computes live readiness passively from service
  state, config, trade store, broker open-order snapshots, and the protection
  verifier. It deliberately does not call the live runner's
  `evaluate_gates()` because that method ingests broker fills/rejections,
  reconciles stale positions, releases idempotency locks, and can append
  lifecycle diagnostics.
- The payload includes `safety_notes` and live-readiness `side_effects`
  markers so operators and tests can verify that this endpoint does not submit
  orders, cancel orders, flatten positions, or advance autonomous lifecycle.

This phase improves visibility only. It does not add order submission,
cancel/replace, panic flattening, automatic recovery, capital promotion, or
live-mode activation.

### Phase 11 — Replay / chaos testing harness

#### Problem

Failure handling must be proven before unattended live operation.

#### Proposed modules

```text
autonomous/replay_engine.py
tests/simulated_broker/
```

#### Simulate

- normal fill;
- partial fill;
- order rejection;
- broker disconnect;
- stale quote;
- restart after submission;
- restart after fill before evidence write;
- basket with one failed leg;
- stop hit;
- target hit;
- unconfirmed protective stop.

#### Acceptance criteria

- Each scenario is reproducible.
- No scenario creates duplicate exposure.
- Supervisor pauses or recovers as designed.
- Evidence remains reconstructable.

### Phase 12 — Capital ramp and promotion gates

#### Problem

The robot should earn the right to trade larger capital.

#### Proposed module

```text
autonomous/capital_promotion.py
```

#### Example levels

| Level | Mode | Requirement | Typical cap |
|---:|---|---|---|
| 0 | Recommend-only | System healthy | 0 |
| 1 | Paper single | Clean recommendations | 0 |
| 2 | Paper basket | Clean paper basket evidence | 0 |
| 3 | Tiny assisted-live | Clean tiny live trades | 0.05%-0.10% equity |
| 4 | Assisted-live basket | Slippage/reconciliation clean | 0.10%-0.20% equity |
| 5 | Limited continuous | Supervisor/recovery proven | tightly capped |
| 6 | Mature continuous | Long evidence history and operator approval | operator-approved |

#### Acceptance criteria

- No auto-promotion.
- Promotion report is evidence-based.
- Operator approval is required.
- Drawdown, faults, or stale evidence can demote the system.

## 12. Continuous-live readiness definition

TWS Robot should not be considered continuous-live-ready until it can answer and evidence all of the following:

1. What candidates were considered?
2. Why were these basket legs chosen?
3. What is the total basket planned stop-risk?
4. What orders were submitted?
5. What did IBKR acknowledge?
6. What filled, partially filled, rejected, or cancelled?
7. Are all live positions protected by confirmed broker-side stops/brackets?
8. Is the quote feed fresh?
9. Is broker state consistent with local state?
10. Is the robot still allowed to trade under risk-lifecycle rules?
11. Can the robot restart without confusion?
12. Can the operator stop it immediately?
13. Can every trade be reconstructed from signal to decision to order to exit to outcome?

## 13. Implementation discipline

Each future implementation PR should include:

- link to this specification;
- exact phase implemented;
- config changes;
- evidence/logging impact;
- tests;
- safety posture;
- explicit limitations;
- whether it changes live trading behaviour.

If a PR changes live trading behaviour, the PR description must explicitly state:

```text
Live behaviour changed: yes/no
Order submission path changed: yes/no
Sizing changed: yes/no
Risk gates changed: yes/no
```

Future PRs that complete roadmap work should also update:

```text
docs/AUTONOMOUS_IMPLEMENTATION_TRACKER.md
```

## 14. Immediate next PR

The next implementation PR should be:

```text
Add replay / chaos testing harness
```

This should implement Phase 11 of the continuous autonomous live readiness roadmap.
