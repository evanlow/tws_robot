# Feature Builder and Expected-R Ranking

This is Group 2 of the intraday trading-intelligence roadmap.

The goal is to move ranking beyond raw signal strength and toward expected edge.
Existing hard filters still run first.  Expected-R ranking cannot bypass signal,
trend, volume, earnings, concentration, market-regime, sizing, stop, or live
execution gates.

## Components

### `FeatureBuilder`

`autonomous/feature_builder.py` converts each `CandidateSignal` plus market
context into stable features:

- signal label and strength
- quality label / score
- momentum label
- RSI
- Bollinger status
- support distance
- resistance room
- risk/reward estimate
- ADR percentage, when available
- SPY/VIX regime context

### `RuleBasedEdgeEstimator`

`autonomous/edge_estimator.py` creates a transparent bootstrap estimate:

```python
class EdgeEstimate:
    p_win: float
    avg_win_r: float
    avg_loss_r: float
    expected_r: float
    confidence: float
    source: str
    reasons: list[str]
```

This is not a trained ML model yet.  It is a conservative, explainable first
step until enough realized trade evidence exists.

### Candidate ranking

`CandidateRanker` now attaches:

- `features`
- `edge_estimate`

and, when `edge_ranking_enabled=True`, adds expected-R contribution to the score:

```text
score = base_score + expected_r * edge_score_weight
```

## Config

```python
edge_ranking_enabled = True
min_expected_r = -1.0
min_edge_confidence = 0.0
edge_score_weight = 10.0
```

The default threshold values avoid aggressive rejection while still surfacing and
using expected-R in ranking. Operators can later tighten thresholds after there
is enough evidence.

## Why this matters

Before this phase, candidates with the same strength score were ranked mostly by
support/resistance proximity and room to target.  This phase exposes the system's
reasoning in terms of expected R:

```text
expected_r = p_win * avg_win_r - (1 - p_win) * avg_loss_r
```

That is the necessary bridge toward:

- learned/calibrated edge estimates;
- fractional Kelly sizing;
- strategy-arm comparison;
- promotion rules for live capital scaling.

## Current limitations

This estimator is rule-based and bootstrap-only.  It does not yet learn from
realized outcomes.  The next related work should connect closed trade outcomes
from the evidence store and calibrate `p_win`, `avg_win_r`, and `avg_loss_r` by
strategy bucket.
