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
| Basket risk diagnostics | Done | PR #175; basket plans now emit shared risk budget, per-leg allocation, planned risk, and rejection/resize reasons for future evidence-aware sizing |
| Order lifecycle diagnostics | Done | PR #175; live-runner order lifecycle events now record planned, submitted, rejected, filled, closed, pending-protection, confirmed-protection, recovery-required, and orphaned states for future operational metrics |
| Broker protection diagnostics | Done | PR #175; open live trades now emit confirmed-protection or recovery-required diagnostics for future unconfirmed-protection metrics |
| Duplicate-order diagnostics | Done | PR #175; active idempotency locks and same-symbol open trades now emit duplicate-order-blocked lifecycle diagnostics for future operational incident metrics |
| Market-data health diagnostics | Done | PR #175; trade plans now emit quote freshness, spread, last-vs-mid, feed-health, and market-open diagnostics for future stale-quote and degraded-feed metrics |
| Broker fill ingestion diagnostics | Done | PR #175; broker execution and commission callbacks now update trade fills, lifecycle states, and realized outcome evidence for future fill-quality and partial-fill metrics |
| Continuous supervisor diagnostics | Done | PR #175; continuous cycles now expose heartbeat, pause reason, cadence/overlap counters, and operational fault diagnostics for future incident metrics |
| Restart recovery diagnostics | Done | PR #176; live readiness now exposes broker/local recovery classifications, mismatch reasons, stale idempotency locks, unmatched broker orders, and recovery-required states for future operational metrics |
| Emergency stop operations diagnostics | Done | PR #178; autonomous emergency stop/reset now exposes marker state, supervisor pause state, pending-entry cleanup reports, preserved protective exits, and reset audit events for future operational metrics |
| Control tower operational snapshot | Done | PR #180; consolidated API exposure for mode, heartbeat, broker/account, cash, open trades/orders, basket risk, protection, recovery/risk state, recent decisions/rejections/fills, and emergency-stop status |
| Replay evidence reconstructability checks | Done | PR #181; Phase 11 replay harness verifies fill/outcome reconstructability under normal fill, partial fill, restart, stop/target, failed-leg, stale-quote, disconnect, and missing-protection scenarios |
| Evidence-based adaptive edge estimator | Pending | Not yet implemented |
| Setup registry | Pending | Not yet implemented |
| Setup eligibility gate | Pending | Not yet implemented |
| Evidence-aware sizing overlay | Pending | Not yet implemented |
| Capital promotion report | Done | PR #182; advisory EL7 report recommends approve/hold/demote from realized outcome evidence and operational incidents without applying capital changes |
| Sharpe / Sortino / profit-factor metrics | Done | Current PR; implemented in reusable `autonomous/performance_metrics.py` for realized outcome evidence |

## 2. Evidence-learning phases

| Phase | Work item | Status | Target PR |
|---:|---|---|---|
| EL1 | Performance metrics | Done | Current PR |
| EL2 | Setup identity and registry | Pending | TBD |
| EL3 | Evidence calibrator | Pending | TBD |
| EL4 | Adaptive edge estimator | Pending | TBD |
| EL5 | Setup eligibility gate | Pending | TBD |
| EL6 | Evidence-aware sizing overlay | Pending | TBD |
| EL7 | Capital promotion report | Done | PR #182 |
| EL8 | Dashboard/API exposure | Pending | TBD |

## 3. Phase detail tracker

### EL1 — Performance metrics

Status: Done in current PR

Goal:

- Calculate risk-adjusted and trade-quality metrics from realized `autonomous_outcome` evidence.

Checklist:

- [x] Add `autonomous/performance_metrics.py`.
- [x] Calculate trade count, win rate, avg R, median R, total R.
- [x] Calculate avg win R and avg loss R.
- [x] Calculate expected R.
- [x] Calculate profit factor.
- [x] Calculate per-trade Sharpe using R-multiples.
- [x] Calculate rolling Sharpe.
- [x] Calculate Sortino ratio.
- [x] Calculate max drawdown in R.
- [x] Add tests using realized outcome records.
- [x] Add docs.

Implementation notes:

- Added `PerformanceMetricsCalculator`, `PerformanceMetrics`,
  `PerformanceOutcome`, and `calculate_performance_metrics`.
- Metrics include trade count, win/loss/breakeven count, win rate, avg R,
  median R, total R, avg win/loss R, expected R, profit factor, Sharpe,
  rolling Sharpe, Sortino, max drawdown in R, consecutive losses, downside
  deviation, R volatility, slippage, commission, and partial-fill rate.
- Non-realized and non-finite R records are ignored.
- Unbounded profit factor is serialized as `profit_factor=None` plus
  `profit_factor_unbounded=true` so future API use remains JSON-friendly.
- This module is analytics-only and does not change live execution, sizing,
  eligibility, risk gates, or capital promotion behavior.

Test evidence:

- Passed: `.venv\Scripts\python.exe -m pytest tests\test_performance_metrics.py --basetemp=.pytest-tmp -q`
  (`7 passed`).
- Passed: `.venv\Scripts\python.exe -m pytest tests\test_performance_metrics.py tests\test_capital_promotion.py tests\test_validation_framework.py tests\test_trade_evidence_store.py tests\test_risk_lifecycle.py tests\test_strategy_arm.py --basetemp=.pytest-tmp -q`
  (`35 passed`).

Smoke-test evidence:

- Passed split smoke verification:
  `.venv\Scripts\python.exe -m pytest tests/test_safety_regression.py tests/test_web_api.py --basetemp=.pytest-tmp --no-cov -q --tb=short -o faulthandler_timeout=60`
  (`203 passed`);
  `.venv\Scripts\python.exe -m pytest tests/test_portfolio_analysis.py tests/test_auth.py tests/test_config_security.py --basetemp=.pytest-tmp --no-cov -q --tb=short -o faulthandler_timeout=60`
  (`112 passed`);
  `.venv\Scripts\python.exe -m pytest tests/test_order_executor.py tests/test_tws_bridge.py tests/test_fx_research.py --basetemp=.pytest-tmp --no-cov -q --tb=short -o faulthandler_timeout=60`
  (`161 passed`). Total split smoke coverage: `476 passed`.
- Smoke groups 1 and 2 printed non-failing post-pytest database/cache fetch
  messages after pytest completed; both commands exited 0.

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

Status: Done in PR #182

Goal:

- Recommend capital increases only when evidence supports them.

Checklist:

- [x] Add `autonomous/capital_promotion.py`.
- [x] Define promotion levels.
- [x] Calculate report from realized evidence and operational metrics.
- [x] Include trade count, avg R, expected R, win rate, profit factor, rolling Sharpe, Sortino, max drawdown, slippage, partial-fill rate, and operational incidents.
- [x] Recommend approve/hold/demote.
- [x] Require operator approval; no auto-promotion.
- [x] Add tests.

Implementation notes:

- `CapitalPromotionEvaluator` consumes realized `autonomous_outcome` evidence
  and optional operational event records, then returns an advisory
  `CapitalPromotionReport`.
- Reports include fixed levels 0-6, the current and recommended level, the
  target level, approval/rejection/demotion reasons, stale-evidence age,
  paper/live counts, and paper-vs-live consistency diagnostics.
- Demotion can be recommended after excessive drawdown, unresolved operational
  incidents, stale evidence, or live/paper inconsistency at higher levels.
- The module does not implement EL8 API/dashboard exposure and does not apply
  approvals or capital changes.

Test evidence:

- Passed: `.venv\Scripts\python.exe -m pytest tests\test_capital_promotion.py --basetemp=.pytest-tmp -q`
  (`6 passed`).
- Passed: `.venv\Scripts\python.exe -m pytest tests\test_capital_promotion.py tests\test_validation_framework.py tests\test_trade_evidence_store.py tests\test_risk_lifecycle.py --basetemp=.pytest-tmp -q`
  (`23 passed`).

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

The current Issue #161 continuation work completes EL1 performance metrics:

- `autonomous/performance_metrics.py` calculates reusable risk-adjusted and
  trade-quality metrics from realized `autonomous_outcome` evidence.
- Metrics include trade count, win/loss/breakeven count, win rate, avg R,
  median R, total R, avg win/loss R, expected R, profit factor, per-trade
  Sharpe, rolling Sharpe, Sortino, max drawdown in R, consecutive losses,
  downside deviation, R volatility, average slippage, average commission, total
  commission, and partial-fill rate.
- The calculator ignores non-realized and non-finite R records and sorts
  outcomes chronologically before calculating drawdown and recent loss streaks.
- The implementation is passive: it does not change live trading, order
  placement, sizing, risk gates, eligibility gates, or capital promotion.

Test evidence:

- Passed: `.venv\Scripts\python.exe -m pytest tests\test_performance_metrics.py --basetemp=.pytest-tmp -q`
  (`7 passed`).
- Passed: `.venv\Scripts\python.exe -m pytest tests\test_performance_metrics.py tests\test_capital_promotion.py tests\test_validation_framework.py tests\test_trade_evidence_store.py tests\test_risk_lifecycle.py tests\test_strategy_arm.py --basetemp=.pytest-tmp -q`
  (`35 passed`).

Smoke-test evidence:

- Passed split smoke verification:
  `.venv\Scripts\python.exe -m pytest tests/test_safety_regression.py tests/test_web_api.py --basetemp=.pytest-tmp --no-cov -q --tb=short -o faulthandler_timeout=60`
  (`203 passed`);
  `.venv\Scripts\python.exe -m pytest tests/test_portfolio_analysis.py tests/test_auth.py tests/test_config_security.py --basetemp=.pytest-tmp --no-cov -q --tb=short -o faulthandler_timeout=60`
  (`112 passed`);
  `.venv\Scripts\python.exe -m pytest tests/test_order_executor.py tests/test_tws_bridge.py tests/test_fx_research.py --basetemp=.pytest-tmp --no-cov -q --tb=short -o faulthandler_timeout=60`
  (`161 passed`). Total split smoke coverage: `476 passed`.
- Smoke groups 1 and 2 printed non-failing post-pytest database/cache fetch
  messages after pytest completed; both commands exited 0.

Known limitations:

- This PR does not yet group metrics by setup ID; that remains EL2/EL3.
- This PR does not expose the metrics through an API or dashboard; that remains
  EL8.
- Operational incident rates such as rejected-order rate, stale-quote rejection
  rate, broker disconnect frequency, unconfirmed-protection events, and
  recovery-required events remain for later operational metrics work once event
  streams are normalized.

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
