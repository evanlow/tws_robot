# Strategy Equity Curve and Loss-Limit Controls

This is PR 2 of the final implementation tranche.

The goal is to consume realized `autonomous_outcome` evidence records and turn
them into a strategy-level risk lifecycle decision before new entries are
planned.

## What it adds

`autonomous/risk_lifecycle.py` adds:

- `StrategyEquityCurveBuilder`
- `StrategyEquityPoint`
- `LossLimitGuard`
- `LossLimitDecision`

## Equity curve

The equity curve is built from realized outcome records only:

```text
evidence_type = autonomous_outcome
outcome.realized = true
outcome.realized_r_multiple = <number>
```

For each realized outcome, it calculates cumulative P&L and cumulative R.

## Loss-limit guard

The guard evaluates:

- daily realized R;
- weekly realized R;
- monthly realized R;
- consecutive losing outcomes;
- max strategy drawdown in R units.

If a configured limit is breached, `AutonomousTradingEngine` now returns
`RISK_REJECTED` before scanning/planning new entries.

## Config

New `AutonomousTradingConfig` fields:

```python
risk_lifecycle_guard_enabled = True
risk_lifecycle_recent_record_limit = 1000
max_daily_loss_r = 2.0
max_weekly_loss_r = 4.0
max_monthly_loss_r = 6.0
max_consecutive_losses = 3
max_strategy_drawdown_r = 6.0
```

## Safety posture

This is defensive only:

- it can block new entries;
- it cannot create orders;
- it cannot increase size;
- it does not alter live execution mode;
- it is based only on realized outcome evidence.

## Current limitations

This first version uses recent append-only evidence records.  A later dashboard
or reporting endpoint can expose the equity curve directly for operator review.
