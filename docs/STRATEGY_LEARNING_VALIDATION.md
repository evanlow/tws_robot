# Strategy Learning and Validation

This is Group 5 of the intraday trading-intelligence roadmap.

The goal is to analyze realized evidence records and produce reviewable reports.
This phase is advisory only and does not change order submission, live mode, or
position size automatically.

## Strategy arms

`autonomous/strategy_arm.py` groups realized evidence records using these stable
bucket fields:

```text
signal_label | quality_label | momentum_label | market_classification | vix_level_regime
```

For each arm, it calculates:

- realized trade count;
- wins and losses;
- win rate;
- average R;
- total R;
- standard deviation of R;
- UCB-style exploration score.

## Validation framework

`autonomous/validation_framework.py` evaluates realized evidence against simple
thresholds:

```python
ValidationThresholds(
    min_trades=30,
    min_avg_r=0.05,
    min_win_rate=0.45,
    max_drawdown_r=6.0,
)
```

The report includes trade count, win rate, average R, total R, max drawdown in R
units, pass/fail status, and clear reasons.

## Evidence source

Both modules accept evidence-style dictionaries, including records returned by
`TradeEvidenceStore.recent()`.

Only records with realized outcomes are used. Unrealized records are ignored.

## Safety posture

This phase is analytics-only:

- no automatic strategy promotion;
- no automatic configuration update;
- no automatic live-mode change;
- no change to existing execution gates.

The operator should review the outputs before any later rollout decision.

## Future work

A later phase should connect close-trade reconciliation into the evidence store
so realized outcomes are updated automatically. After that, these statistics can
support calibrated edge estimates and controlled promotion rules.
