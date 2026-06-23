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
| Evidence-based adaptive edge estimator | Done | PR #187; passive rule-prior plus setup-evidence blending implemented in `autonomous/adaptive_edge_estimator.py` |
| Setup registry | Done | PR #184; deterministic setup IDs and metadata registry implemented in `autonomous/setup_registry.py` |
| Evidence calibrator | Done | PR #186; setup-level evidence summaries and conservative Bayesian/shrinkage classification implemented in `autonomous/evidence_calibrator.py` |
| Setup eligibility gate | Done | PR #188; conservative setup-state and expected-R gate implemented in `autonomous/setup_eligibility.py` with optional ranker integration |
| Evidence-aware sizing overlay | Done | PR #189; setup evidence can hold, reduce, tiny-cap, or block share sizing without bypassing hard caps |
| Capital promotion report | Done | PR #182; advisory EL7 report recommends approve/hold/demote from realized outcome evidence and operational incidents without applying capital changes |
| Sharpe / Sortino / profit-factor metrics | Done | PR #183; implemented in reusable `autonomous/performance_metrics.py` for realized outcome evidence |
| Evidence-learning dashboard/API exposure | Current PR | Read-only EL8 setup performance, promotion, weak setup, and drift diagnostics exposed through evidence APIs and control tower |

## 2. Evidence-learning phases

| Phase | Work item | Status | Target PR |
|---:|---|---|---|
| EL1 | Performance metrics | Done | PR #183 |
| EL2 | Setup identity and registry | Done | PR #184 |
| EL3 | Evidence calibrator | Done | PR #186 |
| EL4 | Adaptive edge estimator | Done | PR #187 |
| EL5 | Setup eligibility gate | Done | PR #188 |
| EL6 | Evidence-aware sizing overlay | Done | PR #189 |
| EL7 | Capital promotion report | Done | PR #182 |
| EL8 | Dashboard/API exposure | Current PR | Issue #185 |

## 3. Phase detail tracker

### EL1 — Performance metrics

Status: Done in PR #183

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

Status: Done in PR #184

Goal:

- Give every realized trade a deterministic setup ID and metadata record.

Checklist:

- [x] Add `autonomous/setup_registry.py`.
- [x] Define setup dimensions.
- [x] Generate deterministic setup IDs.
- [x] Include market, VIX, sector, time-of-day, support/resistance, volatility, and basket context.
- [x] Add setup metadata model.
- [x] Add tests.

Implementation notes:

- Added `SetupRegistry`, `SetupDimensions`, `SetupMetadata`, and
  `setup_id_for_record`.
- Setup IDs are stable, readable `setup_v1__...` identifiers built from
  signal, quality, momentum, market, VIX, sector, time-of-day, support,
  resistance, volatility, basket context, and trade type dimensions.
- Sparse evidence records are assigned explicit `unknown_*` dimensions instead
  of being dropped, preserving deterministic grouping for future calibration.
- The registry tracks setup metadata and observation symbols only; it does not
  calculate performance, classify setup quality, or alter trading behaviour.
- This module is analytics-only and does not change live execution, sizing,
  eligibility gates, risk gates, or capital promotion.

Test evidence:

- Passed: `.venv\Scripts\python.exe -m pytest tests\test_setup_registry.py --basetemp=.pytest-tmp -q`
  (`4 passed`).
- Passed: `.venv\Scripts\python.exe -m pytest tests\test_setup_registry.py tests\test_feature_builder_edge_estimator.py tests\test_strategy_arm.py tests\test_trade_evidence_store.py tests\test_performance_metrics.py tests\test_validation_framework.py --basetemp=.pytest-tmp -q`
  (`28 passed`).

Smoke-test evidence:

- Passed split smoke verification:
  `.venv\Scripts\python.exe -m pytest tests/test_safety_regression.py tests/test_web_api.py --basetemp=.pytest-tmp --no-cov -q --tb=short -o faulthandler_timeout=60`
  (`203 passed` after rerunning with a longer command timeout);
  `.venv\Scripts\python.exe -m pytest tests/test_portfolio_analysis.py tests/test_auth.py tests/test_config_security.py --basetemp=.pytest-tmp --no-cov -q --tb=short -o faulthandler_timeout=60`
  (`112 passed`);
  `.venv\Scripts\python.exe -m pytest tests/test_order_executor.py tests/test_tws_bridge.py tests/test_fx_research.py --basetemp=.pytest-tmp --no-cov -q --tb=short -o faulthandler_timeout=60`
  (`161 passed`). Total split smoke coverage: `476 passed`.
- The first smoke group initially timed out at 300 seconds with no reported
  failures and then passed when rerun with a longer command timeout. Smoke
  groups 1 and 2 printed non-failing post-pytest database/cache messages after
  pytest completed; both rerun/passing commands exited 0. After a self-review
  support-distance denominator fix, targeted tests and all three split smoke
  groups were rerun and passed with the same counts.

### EL3 — Evidence calibrator

Status: Done in PR #186

Goal:

- Aggregate realized evidence by setup and determine setup quality.

Checklist:

- [x] Add `autonomous/evidence_calibrator.py`.
- [x] Group outcomes by setup ID.
- [x] Calculate setup-level performance metrics.
- [x] Apply minimum sample-size threshold.
- [x] Add Bayesian/shrinkage confidence scoring.
- [x] Classify setups as `INSUFFICIENT_EVIDENCE`, `WEAK`, `ACCEPTABLE`, `STRONG`, `RETIRED`, `PAPER_ONLY`, or `LIVE_ELIGIBLE`.
- [x] Add tests.

Implementation notes:

- Added `EvidenceCalibrator`, `EvidenceCalibrationThresholds`,
  `SetupEvidenceSummary`, setup-state constants, and
  `calibrate_setup_evidence`.
- The calibrator filters to realized outcome records, groups those records by
  deterministic setup ID from `SetupRegistry`, and calculates setup-level
  `PerformanceMetrics`.
- Summary output includes sample size, setup metadata, raw metrics,
  prior/evidence weights, posterior win rate, posterior average win/loss R,
  posterior expected R, confidence, setup state, and classification reasons.
- Sparse samples are classified as `INSUFFICIENT_EVIDENCE`. Sufficiently poor
  evidence can become `WEAK` or `RETIRED`. Positive but not yet acceptable
  calibrated edge remains `PAPER_ONLY`. High-quality evidence can become
  `STRONG` or `LIVE_ELIGIBLE`.
- This module is analytics-only and does not change live execution, order
  placement, sizing, eligibility gates, risk gates, dry-run/paper/live mode, or
  capital promotion.

Test evidence:

- Passed: `.venv\Scripts\python.exe -m pytest tests\test_evidence_calibrator.py --basetemp=.pytest-tmp -q`
  (`7 passed`).
- Passed: `.venv\Scripts\python.exe -m pytest tests\test_evidence_calibrator.py tests\test_setup_registry.py tests\test_performance_metrics.py tests\test_strategy_arm.py tests\test_validation_framework.py tests\test_trade_evidence_store.py --basetemp=.pytest-tmp -q`
  (`32 passed`).

Smoke-test evidence:

- Passed split smoke verification:
  `.venv\Scripts\python.exe -m pytest tests/test_safety_regression.py tests/test_web_api.py --basetemp=.pytest-tmp-smoke1 --no-cov -q --tb=short -o faulthandler_timeout=60`
  (`203 passed`);
  `.venv\Scripts\python.exe -m pytest tests/test_portfolio_analysis.py tests/test_auth.py tests/test_config_security.py --basetemp=.pytest-tmp-smoke2 --no-cov -q --tb=short -o faulthandler_timeout=60`
  (`112 passed`);
  `.venv\Scripts\python.exe -m pytest tests/test_order_executor.py tests/test_tws_bridge.py tests/test_fx_research.py --basetemp=.pytest-tmp-smoke3 --no-cov -q --tb=short -o faulthandler_timeout=60`
  (`161 passed`). Total split smoke coverage: `476 passed`.
- Smoke groups 1 and 2 printed non-failing post-pytest database/cache messages
  after pytest completed; both commands exited 0.

### EL4 — Adaptive edge estimator

Status: Done in PR #187

Goal:

- Blend the current rule-based prior with realized setup performance.

Checklist:

- [x] Add `autonomous/adaptive_edge_estimator.py`.
- [x] Accept current `EdgeEstimate` prior.
- [x] Accept setup evidence summary.
- [x] Compute prior weight and evidence weight.
- [x] Output calibrated `p_win`, `avg_win_r`, `avg_loss_r`, `expected_r`, and confidence.
- [x] Include setup ID and sample size.
- [x] Preserve transparent reasons.
- [x] Add tests.

Implementation notes:

- Added `AdaptiveEdgeEstimator` and `AdaptiveEdgeBlendConfig`.
- Extended `EdgeEstimate` with optional `setup_id`, `sample_size`,
  `prior_weight`, `evidence_weight`, and `setup_state` fields so adaptive
  outputs can flow through existing serialization without replacing the
  estimator contract.
- The estimator returns a prior-only estimate when setup evidence is
  unavailable.
- Sparse or insufficient setup evidence receives low weight, mature/high
  confidence evidence can dominate up to a conservative cap, and weak/retired
  evidence is allowed to pull calibrated expected R down.
- Loss magnitude convention is preserved for `EdgeEstimate.avg_loss_r` even
  though EL3 stores posterior average loss R as a negative R value.
- This module is passive in this PR; it is not wired into active ranking,
  trade planning, sizing, eligibility, live execution, or capital promotion.

Test evidence:

- Passed: `.venv\Scripts\python.exe -m pytest tests\test_adaptive_edge_estimator.py --basetemp=.pytest-tmp -q`
  (`5 passed`).
- Passed: `.venv\Scripts\python.exe -m pytest tests\test_adaptive_edge_estimator.py tests\test_feature_builder_edge_estimator.py tests\test_candidate_ranker_edge.py tests\test_evidence_calibrator.py tests\test_setup_registry.py tests\test_performance_metrics.py tests\test_validation_framework.py --basetemp=.pytest-tmp -q`
  (`34 passed`).

Smoke-test evidence:

- Passed split smoke verification:
  `.venv\Scripts\python.exe -m pytest tests/test_safety_regression.py tests/test_web_api.py --basetemp=.pytest-tmp-el4-smoke1b --no-cov -q --tb=short -o faulthandler_timeout=60`
  (`203 passed`);
  `.venv\Scripts\python.exe -m pytest tests/test_portfolio_analysis.py tests/test_auth.py tests/test_config_security.py --basetemp=.pytest-tmp-el4-smoke2b --no-cov -q --tb=short -o faulthandler_timeout=60`
  (`112 passed`);
  `.venv\Scripts\python.exe -m pytest tests/test_order_executor.py tests/test_tws_bridge.py tests/test_fx_research.py --basetemp=.pytest-tmp-el4-smoke3b --no-cov -q --tb=short -o faulthandler_timeout=60`
  (`161 passed`). Total split smoke coverage: `476 passed`.
- Final split smoke rerun completed without smoke-test product failures.

### EL5 — Setup eligibility gate

Status: Done in PR #188

Goal:

- Reject or downgrade weak setups before execution.

Checklist:

- [x] Add `autonomous/setup_eligibility.py`.
- [x] Reject `expected_r <= 0` when evidence is sufficient.
- [x] Reject retired setups.
- [x] Restrict `PAPER_ONLY` setups from live execution.
- [x] Downgrade insufficient-evidence setups to recommend/paper/tiny-live only.
- [x] Add evidence diagnostics to decisions.
- [x] Add tests.

Implementation notes:

- Added `SetupEligibilityGate`, `SetupEligibilityConfig`, and serializable
  `SetupEligibilityDecision` diagnostics.
- The gate rejects `RETIRED` and `WEAK` setups, rejects sufficiently sampled
  non-positive expected R, blocks `PAPER_ONLY` and insufficient-evidence setups
  from `ASSISTED_LIVE`, and records recommend/paper-only downgrades when those
  states appear outside live mode.
- `CandidateRanker` now accepts an optional setup-evidence provider. When
  supplied, it blends adaptive edge, evaluates setup eligibility before
  planning/execution, records `setup_eligibility` diagnostics on candidate
  extras, and fails closed if the provider raises.
- `AutonomousTradingEngine` exposes the optional setup-evidence provider hook
  and passes it into the ranker. Without a provider, default runtime ranking
  behavior is unchanged.
- The gate does not enable live trading, place orders, change sizing, or bypass
  risk controls.

Test evidence:

- Passed: `.venv\Scripts\python.exe -m pytest tests\test_setup_eligibility.py tests\test_candidate_ranker.py tests\test_candidate_ranker_edge.py tests\test_autonomous_engine.py tests\test_autonomous_engine_evidence.py tests\test_adaptive_edge_estimator.py tests\test_evidence_calibrator.py tests\test_setup_registry.py --basetemp=.pytest-tmp-el5-target2 -q`
  (`52 passed`).

Smoke-test evidence:

- Passed split smoke verification:
  `.venv\Scripts\python.exe -m pytest tests/test_safety_regression.py tests/test_web_api.py --basetemp=.pytest-tmp-el5-smoke1 --no-cov -q --tb=short -o faulthandler_timeout=60`
  (`203 passed`);
  `.venv\Scripts\python.exe -m pytest tests/test_portfolio_analysis.py tests/test_auth.py tests/test_config_security.py --basetemp=.pytest-tmp-el5-smoke2 --no-cov -q --tb=short -o faulthandler_timeout=60`
  (`112 passed`);
  `.venv\Scripts\python.exe -m pytest tests/test_order_executor.py tests/test_tws_bridge.py tests/test_fx_research.py --basetemp=.pytest-tmp-el5-smoke3 --no-cov -q --tb=short -o faulthandler_timeout=60`
  (`161 passed`). Total split smoke coverage: `476 passed`.
- Smoke groups 1 and 2 printed non-failing post-pytest database/cache fetch
  messages after pytest completed; both commands exited 0. The messages come
  from market overview/event fallback logging and did not indicate smoke-test
  assertion failures.

Tracking note:

- EL5 is complete in PR #188. Remaining Issue #185 work is EL6 and EL8.

### EL6 — Evidence-aware sizing overlay

Status: Current PR

Goal:

- Let evidence reduce, hold, or modestly increase size within hard caps.

Checklist:

- [x] Extend sizing diagnostics with evidence score.
- [x] Use setup confidence, expected R, rolling Sharpe, drawdown, and slippage history.
- [x] Never bypass deployable cash, basket risk, risk-per-trade, drawdown, or operator caps.
- [x] Add size-state output: `NO_TRADE`, `PAPER_ONLY`, `TINY_LIVE`, `NORMAL_CAPPED`, `REDUCED_SIZE`, `RETIRED`.
- [x] Add tests.

Implementation notes:

- Added `autonomous/evidence_aware_sizer.py` with `EvidenceAwareSizer`,
  `EvidenceAwareSizingConfig`, serializable decision diagnostics, evidence
  score output, and explicit EL6 sizing states.
- `PositionSizer` now evaluates the evidence-aware overlay after fractional
  edge sizing and before the drawdown governor. The overlay adds an
  `evidence_aware_cap` only when it reduces or blocks sizing; otherwise
  existing cash/equity, risk-per-trade, volatility, fractional, drawdown, and
  operator caps remain binding.
- `TradePlanner` passes candidate evidence diagnostics into sizing through
  `edge_estimate`, `edge_observed_trades`, `setup_eligibility`,
  `strategy_drawdown_pct`, and `edge_avg_slippage_bps`/`avg_slippage_bps`.
- The feature is disabled by default. It does not enable live trading, place
  orders, weaken dry-run/paper/live mode gates, bypass risk controls, or apply
  capital changes.

Tracking note:

- Targeted verification passed:
  `.venv\Scripts\python.exe -m pytest tests\test_evidence_aware_sizer.py tests\test_trade_planner_evidence_sizing.py tests\test_trade_planner_sizing.py tests\test_trade_planner_fractional_drawdown.py tests\test_setup_eligibility.py tests\test_candidate_ranker_edge.py tests\test_autonomous_engine.py --basetemp=.pytest-tmp-el6-target2 -q`
  (`46 passed`).
- Smoke-test evidence will be recorded after final split verification for this
  PR.

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

Status: Current PR

Goal:

- Make learning status visible to the operator.

Checklist:

- [x] Add setup performance API.
- [x] Add promotion report API.
- [x] Add weak setup report API.
- [x] Add evidence drift report API.
- [x] Update dashboard/control tower when available.

Implementation notes:

- Added `autonomous/evidence_learning_summary.py` as an analytics-only EL8
  summarizer over realized autonomous evidence.
- Added read-only endpoints under `/api/autonomous/evidence`:
  `/learning-status`, `/setup-performance`, `/promotion-report`,
  `/weak-setups`, and `/drift-report`.
- Added `evidence_learning` to `/api/autonomous/control-tower` so dashboard
  consumers can read setup performance, promotion, weak setup, and drift
  diagnostics from the consolidated operator snapshot.
- Promotion reports remain advisory. The EL8 exposure does not submit, cancel,
  replace, or flatten orders; does not advance lifecycle state; does not enable
  live trading; and does not apply capital changes.

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

## 4. Current PR note

The current Issue #185 continuation work implements EL8 dashboard/API exposure:

- `autonomous/evidence_learning_summary.py` builds read-only setup
  performance, promotion, weak setup, and drift diagnostics.
- `/api/autonomous/evidence/learning-status` returns the full EL8 payload.
- `/api/autonomous/evidence/setup-performance`,
  `/api/autonomous/evidence/promotion-report`,
  `/api/autonomous/evidence/weak-setups`, and
  `/api/autonomous/evidence/drift-report` expose focused views.
- `/api/autonomous/control-tower` includes an `evidence_learning` block for
  dashboard/control-tower consumers.
- All EL8 outputs are advisory/read-only and do not apply capital changes or
  mutate broker/order/lifecycle state.

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

Known limitations:

- The setup-evidence provider hook is explicit; no default live evidence source
  is configured in this PR. EL8 summarizes evidence already available through
  the evidence store.
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
