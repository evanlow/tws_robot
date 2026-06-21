# Autonomous Evidence-Learning Implementation Tracker

This tracker complements:

- `docs/AUTONOMOUS_TRADING_SYSTEM_SPEC.md`
- `docs/AUTONOMOUS_IMPLEMENTATION_TRACKER.md`
- `docs/AUTONOMOUS_EVIDENCE_LEARNING_SPEC.md`

It tracks the implementation of TWS Robot's evidence-based learning objective:

> learn from realized evidence, know which setups work best, size more intelligently, reject weak conditions, and recommend capital increases only when evidence supports them.

Legend:

| Status | Meaning |
|---|---|
| Done | Implemented and merged |
| Partial | Implemented in part, or implemented but not fully evidence-calibrated |
| Pending | Accepted roadmap item, not yet implemented |
| Planned | Future accepted roadmap item |

## 1. Existing foundations

| Capability | Status | Notes |
|---|---|---|
| Realized outcome evidence | Done | Implemented in PR #170 |
| Realized R-multiple | Done | Implemented in PR #170 |
| Slippage / commission / partial-fill fields | Done | Implemented in PR #170 |
| Strategy-arm analytics | Done | Implemented in PR #169 |
| Rule-based edge estimator | Done | Implemented in PR #166 |
| Feature builder | Done | Implemented in PR #166 and expanded in PR #172 |
| Sector / time-of-day regime context | Done | Implemented in PR #172 |
| Risk lifecycle using outcome records | Done | Implemented in PR #171 |
| Chronological validation report | Done | Implemented in PR #172 |
| Basket risk diagnostics | Done | Current PR continuing #161; basket plans now emit shared risk budget, per-leg allocation, planned risk, and rejection/resize reasons for future evidence-aware sizing |
| Order lifecycle diagnostics | Done | Current PR continuing #161; live-runner order lifecycle events now record planned, submitted, rejected, filled, closed, pending-protection, confirmed-protection, recovery-required, and orphaned states for future operational metrics |
| Broker protection diagnostics | Done | Current PR continuing #161; open live trades now emit confirmed-protection or recovery-required diagnostics for future unconfirmed-protection metrics |
| Duplicate-order diagnostics | Done | Current PR continuing #161; active idempotency locks and same-symbol open trades now emit duplicate-order-blocked lifecycle diagnostics for future operational incident metrics |
| Market-data health diagnostics | Done | Current PR continuing #161; trade plans now emit quote freshness, spread, last-vs-mid, feed-health, and market-open diagnostics for future stale-quote and degraded-feed metrics |
| Evidence-based adaptive edge estimator | Pending | Not yet implemented |
| Setup registry | Pending | Not yet implemented |
| Setup eligibility gate | Pending | Not yet implemented |
| Evidence-aware sizing overlay | Pending | Not yet implemented |
| Capital promotion report | Pending | Not yet implemented |
| Sharpe / Sortino / profit-factor metrics | Pending | Not yet implemented as dedicated metrics module |

## 2. Evidence-learning phases

| Phase | Work item | Status | Target PR |
|---:|---|---|---|
| EL1 | Performance metrics | Pending | TBD |
| EL2 | Setup identity and registry | Pending | TBD |
| EL3 | Evidence calibrator | Pending | TBD |
| EL4 | Adaptive edge estimator | Pending | TBD |
| EL5 | Setup eligibility gate | Pending | TBD |
| EL6 | Evidence-aware sizing overlay | Pending | TBD |
| EL7 | Capital promotion report | Pending | TBD |
| EL8 | Dashboard/API exposure | Pending | TBD |

## 3. Phase detail tracker

### EL1 — Performance metrics

Status: Pending

Goal:

- Calculate risk-adjusted and trade-quality metrics from realized `autonomous_outcome` evidence.

Checklist:

- [ ] Add `autonomous/performance_metrics.py`.
- [ ] Calculate trade count, win rate, avg R, median R, total R.
- [ ] Calculate avg win R and avg loss R.
- [ ] Calculate expected R.
- [ ] Calculate profit factor.
- [ ] Calculate per-trade Sharpe using R-multiples.
- [ ] Calculate rolling Sharpe.
- [ ] Calculate Sortino ratio.
- [ ] Calculate max drawdown in R.
- [ ] Add tests using realized outcome records.
- [ ] Add docs.

### EL2 — Setup identity and registry

Status: Pending

Goal:

- Give every realized trade a deterministic setup ID and metadata record.

Checklist:

- [ ] Add `autonomous/setup_registry.py`.
- [ ] Define setup dimensions.
- [ ] Generate deterministic setup IDs.
- [ ] Include market, VIX, sector, time-of-day, support/resistance, volatility, and basket context.
- [ ] Add setup metadata model.
- [ ] Add tests.

### EL3 — Evidence calibrator

Status: Pending

Goal:

- Aggregate realized evidence by setup and determine setup quality.

Checklist:

- [ ] Add `autonomous/evidence_calibrator.py`.
- [ ] Group outcomes by setup ID.
- [ ] Calculate setup-level performance metrics.
- [ ] Apply minimum sample-size threshold.
- [ ] Add Bayesian/shrinkage confidence scoring.
- [ ] Classify setups as `INSUFFICIENT_EVIDENCE`, `WEAK`, `ACCEPTABLE`, `STRONG`, `RETIRED`, `PAPER_ONLY`, or `LIVE_ELIGIBLE`.
- [ ] Add tests.

### EL4 — Adaptive edge estimator

Status: Pending

Goal:

- Blend the current rule-based prior with realized setup performance.

Checklist:

- [ ] Add `autonomous/adaptive_edge_estimator.py`.
- [ ] Accept current `EdgeEstimate` prior.
- [ ] Accept setup evidence summary.
- [ ] Compute prior weight and evidence weight.
- [ ] Output calibrated `p_win`, `avg_win_r`, `avg_loss_r`, `expected_r`, and confidence.
- [ ] Include setup ID and sample size.
- [ ] Preserve transparent reasons.
- [ ] Add tests.

### EL5 — Setup eligibility gate

Status: Pending

Goal:

- Reject or downgrade weak setups before execution.

Checklist:

- [ ] Add `autonomous/setup_eligibility.py`.
- [ ] Reject `expected_r <= 0` when evidence is sufficient.
- [ ] Reject retired setups.
- [ ] Restrict `PAPER_ONLY` setups from live execution.
- [ ] Downgrade insufficient-evidence setups to recommend/paper/tiny-live only.
- [ ] Add evidence diagnostics to decisions.
- [ ] Add tests.

### EL6 — Evidence-aware sizing overlay

Status: Pending

Goal:

- Let evidence reduce, hold, or modestly increase size within hard caps.

Checklist:

- [ ] Extend sizing diagnostics with evidence score.
- [ ] Use setup confidence, expected R, rolling Sharpe, drawdown, and slippage history.
- [ ] Never bypass deployable cash, basket risk, risk-per-trade, drawdown, or operator caps.
- [ ] Add size-state output: `NO_TRADE`, `PAPER_ONLY`, `TINY_LIVE`, `NORMAL_CAPPED`, `REDUCED_SIZE`, `RETIRED`.
- [ ] Add tests.

### EL7 — Capital promotion report

Status: Pending

Goal:

- Recommend capital increases only when evidence supports them.

Checklist:

- [ ] Add `autonomous/capital_promotion.py`.
- [ ] Define promotion levels.
- [ ] Calculate report from realized evidence and operational metrics.
- [ ] Include trade count, avg R, expected R, win rate, profit factor, rolling Sharpe, Sortino, max drawdown, slippage, partial-fill rate, and operational incidents.
- [ ] Recommend approve/hold/demote.
- [ ] Require operator approval; no auto-promotion.
- [ ] Add tests.

### EL8 — Dashboard/API exposure

Status: Pending

Goal:

- Make learning status visible to the operator.

Checklist:

- [ ] Add setup performance API.
- [ ] Add promotion report API.
- [ ] Add weak setup report API.
- [ ] Add evidence drift report API.
- [ ] Update dashboard/control tower when available.

## 4. Current PR note

The current Issue #161 continuation PR does not complete an evidence-learning
EL phase. It improves the evidence substrate used by future EL6
evidence-aware sizing and by future operational metrics:

- `basket_plan.risk_allocation` records basket risk budget, total planned
  stop-risk, budget usage, and per-leg risk decisions.
- Adjusted leg `sizing` diagnostics include a `basket_risk` block.
- The allocator can only reduce or reject basket legs; it cannot bypass hard
  sizing, risk, drawdown, or operator caps.
- `order_lifecycle` records live order state transitions for future rejected
  order rate, protection-event, fill-state, duplicate-order-blocked, and
  recovery-required metrics.
- Broker protection verification records `PROTECTIVE_STOP_CONFIRMED` or
  `RECOVERY_REQUIRED` lifecycle events for open live trades.
- Idempotency locks record live submission attempts and duplicate-block
  diagnostics without adding any new order submission path.
- `trade_plan.market_data_health` records quote age, bid/ask/last age,
  spread, last-vs-mid deviation, feed-health, market-open status, warnings,
  and rejection reasons for stale/degraded quote analysis.

Test evidence:

- Passed: `.venv\Scripts\python.exe -m pytest tests/test_basket_planner.py tests/test_autonomous_engine_basket.py tests/test_config.py --basetemp=.pytest-tmp`
- Passed: `.venv\Scripts\python.exe -m pytest tests/test_order_lifecycle.py --basetemp=.pytest-tmp -q`
  (`4 passed`).
- Passed: `.venv\Scripts\python.exe -m pytest tests/test_order_lifecycle.py tests/test_basket_planner.py tests/test_autonomous_engine_basket.py tests/test_config.py --basetemp=.pytest-tmp -q`
  (`49 passed`).
- Passed: `.venv\Scripts\python.exe -m pytest tests/test_order_lifecycle.py tests/test_tws_bridge.py::TestBridgeOpenOrderSnapshots --basetemp=.pytest-tmp -q`
  (`8 passed`).
- Passed: `.venv\Scripts\python.exe -m pytest tests/test_idempotency.py tests/test_order_lifecycle.py tests/test_autonomous_live_runner_basket.py --basetemp=.pytest-tmp -q`
  (`15 passed`).
- Passed: `.venv\Scripts\python.exe -m pytest tests\test_market_data_health.py tests\test_trade_planner_execution_quality.py tests\test_trade_planner.py tests\test_technical_analysis_signal_provider.py tests\test_autonomous_engine_basket.py tests\test_order_lifecycle.py --basetemp=.pytest-tmp -q`
  (`57 passed`).
- Full suite: `.venv\Scripts\python.exe -m pytest --basetemp=.pytest-tmp`
  completed with `2799 passed`, `18 skipped`, and `6 failed`; the failures
  were existing autonomous/live-runner expectation issues outside this PR's
  evidence-learning or basket-risk diagnostics path.

Smoke-test evidence:

- Passed: `.venv\Scripts\python.exe -m pytest tests/test_safety_regression.py tests/test_web_api.py tests/test_portfolio_analysis.py tests/test_auth.py tests/test_config_security.py tests/test_order_executor.py tests/test_tws_bridge.py tests/test_fx_research.py --basetemp=.pytest-tmp --no-cov -vv --tb=short -o faulthandler_timeout=60`
  (`473 passed`).

Known limitations:

- No adaptive edge estimator, setup eligibility gate, or evidence-aware sizing
  overlay is implemented in this PR.
- Basket risk diagnostics should be consumed by future evidence-learning
  modules, but no automatic capital promotion or live-mode expansion is added.
- Order lifecycle events are not yet surfaced through a dedicated setup
  calibrator, adaptive edge estimator, or promotion report.
- Idempotency and duplicate-block events are operational diagnostics only in
  this PR; they are not yet consumed by an adaptive evidence calibrator.
- Market-data health events are pre-submission operational diagnostics only;
  they are not yet consumed by an adaptive evidence calibrator or dashboard.

## 5. Maintenance rules

Future evidence-learning PRs should update this tracker when they complete work.

A PR that implements an EL phase should update:

- phase status;
- completed checklist items;
- PR number / notes;
- new limitations discovered;
- any spec deviations.

If an implementation changes live trading behaviour, follow the PR-description template defined in `docs/AUTONOMOUS_TRADING_SYSTEM_SPEC.md`. Evidence-learning PRs should also include the following additional line:

```text
Evidence-learning behaviour changed: yes/no
```
