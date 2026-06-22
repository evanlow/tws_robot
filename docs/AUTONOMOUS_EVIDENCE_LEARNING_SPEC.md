# Autonomous Evidence-Based Learning Specification

This document extends `docs/AUTONOMOUS_TRADING_SYSTEM_SPEC.md`.

It makes evidence-based learning a primary design objective for TWS Robot.

## 1. Primary learning objective

TWS Robot should learn from realized evidence so that it can:

1. know which setups work best;
2. size more intelligently;
3. reject weak conditions;
4. recommend capital increases only when evidence supports them.

This does not mean the robot should auto-promote itself or aggressively optimize parameters.  It means the robot should become increasingly evidence-calibrated while preserving operator control and hard risk limits.

## 2. Design principle

The robot should move from:

```text
rule-based prior
```

toward:

```text
rule-based prior
+ realized setup performance
+ risk-adjusted performance metrics
+ evidence-calibrated edge estimate
+ operator-approved capital promotion
```

The rule-based estimator remains useful as a prior when evidence is sparse.  As realized evidence grows, the robot should increasingly rely on measured setup performance.

## 3. What counts as evidence

Edge and performance calibration must use realized outcomes, not merely signals or paper assumptions. Non-trade decision records (e.g. rejected or no-trade decisions) are still logged as evidence for opportunity and operational analysis.

Valid evidence records include:

- `autonomous_outcome` records;
- realized P&L;
- realized R-multiple;
- entry and exit fill summaries;
- slippage;
- commission;
- exit reason;
- partial-fill status;
- strategy bucket;
- market regime;
- sector regime;
- time-of-day regime;
- basket vs single-leg context;
- planned risk versus realized outcome.

Signals that did not become trades may be useful for opportunity analysis, but they should not be treated as realized edge evidence.

## 4. Setup identity

Every realized trade should be mapped into a repeatable setup identity.

Example setup dimensions:

```text
signal_label
quality_label
momentum_label
market_classification
vix_level_regime
vix_direction_regime
sector_regime
time_of_day_regime
support_distance_bucket
resistance_room_bucket
adr_volatility_bucket
basket_context
trade_type
```

Example setup ID:

```text
StrongConfirmedRebound
+ SPYBullish
+ VIXNormal
+ SectorSupportive
+ NearSupport
+ RegularSession
+ BasketLeg
```

The setup ID should be deterministic so that future outcomes aggregate cleanly.

### Current implementation

Reusable EL2 setup identity and registry metadata are implemented in:

```text
autonomous/setup_registry.py
```

The registry maps evidence records and candidate feature payloads into stable,
readable setup IDs using canonical dimensions for signal, quality, momentum,
market classification, VIX level/direction, sector regime, time-of-day regime,
support-distance bucket, resistance-room bucket, ADR volatility bucket, basket
context, and trade type.

Sparse records are handled defensively with explicit `unknown_*` dimensions so
future aggregation remains deterministic instead of silently dropping records.
The module is analytics-only. It does not alter sizing, eligibility, capital
promotion, risk gates, or order execution.

## 5. Performance metrics

TWS Robot should calculate performance metrics from realized outcome evidence.

### Core trade metrics

- trade count;
- win count;
- loss count;
- win rate;
- average R;
- median R;
- total R;
- average win R;
- average loss R;
- expected R;
- profit factor;
- max drawdown in R;
- consecutive losses;
- average slippage;
- average commission;
- partial-fill rate.

### Risk-adjusted metrics

- per-trade Sharpe ratio using R-multiples;
- rolling Sharpe over recent trades;
- Sortino ratio;
- Calmar ratio where a time-based return series exists;
- downside deviation;
- volatility of R outcomes.

### Operational metrics

- rejected order rate;
- stale quote rejection rate;
- broker disconnect frequency;
- unconfirmed protection events;
- recovery-required events;
- live vs paper slippage difference.

### Current implementation

Reusable EL1 trade and risk-adjusted metrics are implemented in:

```text
autonomous/performance_metrics.py
```

It calculates realized outcome metrics from `autonomous_outcome` evidence,
including trade count, win/loss/breakeven count, win rate, average R, median R,
total R, average win/loss R, expected R, profit factor, per-trade Sharpe,
rolling Sharpe, Sortino, max drawdown in R, consecutive losses, downside
deviation, R volatility, average slippage, average commission, total
commission, and partial-fill rate.

The module is analytics-only. It does not alter sizing, eligibility, capital
promotion, risk gates, or order execution.

## 6. Evidence calibration

The robot should include an evidence calibrator that computes setup-level statistics.

Current module:

```text
autonomous/evidence_calibrator.py
```

Responsibilities:

- group realized outcomes by setup ID;
- calculate setup-level performance metrics;
- apply minimum sample-size thresholds;
- apply Bayesian/shrinkage adjustments so small samples do not overstate edge;
- produce confidence scores;
- mark setups as insufficient-evidence, weak, acceptable, strong, or retired.

Proposed setup states:

```text
INSUFFICIENT_EVIDENCE
WEAK
ACCEPTABLE
STRONG
RETIRED
PAPER_ONLY
LIVE_ELIGIBLE
```

### Current implementation

Reusable EL3 evidence calibration is implemented in:

```text
autonomous/evidence_calibrator.py
```

The calibrator groups realized outcome records by deterministic setup ID from
`autonomous/setup_registry.py`, calculates setup-level performance metrics with
`autonomous/performance_metrics.py`, and emits serializable setup summaries.
Each summary includes sample size, setup metadata, raw performance metrics,
Bayesian/shrinkage-adjusted win rate, average win R, average loss R, expected R,
prior/evidence weights, confidence, setup state, and classification reasons.

Calibration is intentionally conservative: sparse samples remain
`INSUFFICIENT_EVIDENCE`, observed setup metrics are shrunk toward neutral
priors, drawdown can keep a setup `PAPER_ONLY`, and sufficiently negative
evidence can mark a setup `RETIRED`.

This module is analytics-only. It does not alter sizing, eligibility, capital
promotion, risk gates, dry-run/paper/live mode, broker connectivity, or order
execution.

## 7. Adaptive edge estimation

The current rule-based estimator should become one input into an adaptive estimator.

Proposed module:

```text
autonomous/adaptive_edge_estimator.py
```

Target behaviour:

```text
if evidence_count < minimum:
    use mostly rule-based prior
elif evidence_count is moderate:
    blend prior with realized setup performance
else:
    realized setup performance dominates
```

The adaptive estimator should output:

```text
p_win
avg_win_r
avg_loss_r
expected_r
confidence
source
sample_size
setup_id
prior_weight
evidence_weight
reasons
```

The existing `EdgeEstimate` structure can be extended rather than replaced.

## 8. Intelligent rejection of weak conditions

TWS Robot should reject or downgrade setups when evidence is weak.

Examples:

```text
expected_r <= 0 -> reject
sample_size sufficient and avg_r < 0 -> reject
profit_factor below threshold -> reject
rolling Sharpe below threshold -> reduce size or reject
setup state = RETIRED -> reject
setup state = PAPER_ONLY -> do not live trade
setup state = INSUFFICIENT_EVIDENCE -> recommend/paper only or tiny live only
```

This should be implemented as a new gating layer before final planning/execution.

Proposed module:

```text
autonomous/setup_eligibility.py
```

## 9. Smarter sizing from evidence

Sizing should remain constrained by existing hard caps:

- deployable-cash cap;
- equity cap;
- risk-per-trade cap;
- volatility cap;
- basket risk budget;
- drawdown cap;
- lifecycle loss limits;
- operator caps.

Evidence should never bypass hard risk caps.

Evidence can influence sizing by reducing or modestly allowing more allocation within caps when all criteria are met.

Sizing inputs should include:

```text
setup expected R
setup confidence
sample size
rolling Sharpe
drawdown
live-vs-paper consistency
execution quality
slippage history
```

Suggested sizing states:

```text
NO_TRADE
PAPER_ONLY
TINY_LIVE
NORMAL_CAPPED
REDUCED_SIZE
RETIRED
```

## 10. Capital promotion recommendations

TWS Robot should recommend capital increases only when evidence supports them.

It should not auto-promote itself.

Proposed module:

```text
autonomous/capital_promotion.py
```

Promotion report should include:

- completed trade count;
- recent trade count;
- avg R;
- expected R;
- win rate;
- profit factor;
- rolling Sharpe;
- Sortino;
- max drawdown;
- slippage statistics;
- partial-fill rate;
- operational incidents;
- paper vs live consistency;
- recommended max risk level;
- reasons for approval or rejection.

Example promotion levels:

| Level | Description | Typical criteria |
|---:|---|---|
| 0 | Recommend only | System healthy |
| 1 | Paper single | Clean paper recommendations |
| 2 | Paper basket | Clean paper basket evidence |
| 3 | Tiny live | Broker path proven with tiny trades |
| 4 | Assisted-live basket | Basket risk and live fills proven |
| 5 | Limited continuous | Supervisor/recovery proven |
| 6 | Mature continuous | Long evidence history and operator approval |

## 11. Versatility without reckless expansion

TWS Robot should become more versatile by testing and tracking multiple setup families, but new setup families should start in recommend-only or paper mode.

Potential future setup families:

- Strong + Confirmed Rebound;
- pullback to support;
- VWAP reclaim;
- sector-supported rebound;
- opening-range continuation;
- low-volatility high-quality rebound;
- basket of independent sector leaders.

Each setup family must have:

- setup ID;
- eligibility state;
- evidence summary;
- capital level;
- promotion/demotion history.

No setup family should trade meaningful live capital without evidence.

## 12. Dashboard and API requirements

The control tower should expose evidence-learning status.

Suggested views:

### Setup performance table

Columns:

- setup ID;
- status;
- trade count;
- avg R;
- expected R;
- win rate;
- profit factor;
- Sharpe;
- max drawdown;
- current allowed mode;
- recommended capital level.

### Promotion report

Shows whether the robot recommends moving to the next capital level.

### Weak setup report

Shows setups that should be retired, paper-only, or reduced-size.

### Evidence drift report

Shows when recent performance diverges from historical performance.

## 13. Acceptance criteria

The evidence-learning objective is satisfied when TWS Robot can answer:

1. Which setups have worked best historically?
2. Which setups are currently weakening?
3. Which setups are paper-only?
4. Which setups are live-eligible?
5. What is the expected R for this setup?
6. What evidence supports that estimate?
7. What is the confidence level?
8. How should size be adjusted based on evidence?
9. Should this setup be rejected today?
10. Should capital be increased, reduced, or held constant?

## 14. Recommended implementation phases

### Phase EL1 — Performance metrics

Add:

```text
autonomous/performance_metrics.py
```

Implement:

- expectancy;
- profit factor;
- per-trade Sharpe;
- rolling Sharpe;
- Sortino;
- max drawdown;
- trade-count helpers.

### Phase EL2 — Setup identity and registry

Add:

```text
autonomous/setup_registry.py
```

Implement deterministic setup IDs and setup metadata.

### Phase EL3 — Evidence calibrator

Add:

```text
autonomous/evidence_calibrator.py
```

Implement setup-level evidence summaries and confidence scoring.

### Phase EL4 — Adaptive edge estimator

Add:

```text
autonomous/adaptive_edge_estimator.py
```

Blend rule-based prior with evidence-calibrated setup statistics.

### Phase EL5 — Setup eligibility gate

Add:

```text
autonomous/setup_eligibility.py
```

Reject or downgrade weak setups before execution.

### Phase EL6 — Evidence-aware sizing overlay

Extend sizing so evidence can reduce size, hold size, or modestly allow more size within hard caps.

### Phase EL7 — Capital promotion report

Add:

```text
autonomous/capital_promotion.py
```

Generate evidence-based capital promotion/demotion recommendations.

### Phase EL8 — Dashboard/API exposure

Expose setup performance, promotion reports, and weak-setup diagnostics.

## 15. Relationship to existing roadmap

This evidence-learning specification does not replace the continuous-live readiness roadmap.

It complements it.

Recommended sequencing:

1. Basket-level risk allocation.
2. Performance metrics and setup registry.
3. Evidence calibrator.
4. Adaptive edge estimator.
5. Broker order lifecycle and protection verification.
6. Setup eligibility and evidence-aware sizing.
7. Continuous supervisor / recovery / dashboard.
8. Capital promotion gates.

This sequencing lets TWS Robot become smarter while also becoming safer operationally.
