# Realized Outcome and Execution Accounting

This is the first PR in the final implementation tranche.

The goal is to convert closed autonomous trade records into realized outcome
evidence.  This makes the strategy-arm learner, validation framework,
fractional sizing, and drawdown controls useful with real completed trades.

## Scope

This implementation adds:

- fill aggregation;
- realized outcome calculation;
- R-multiple calculation from planned risk per share;
- entry slippage;
- exit slippage versus planned target when available;
- commission accounting;
- partial-fill detection;
- outcome evidence record generation;
- a small append-only outcome evidence writer.

## Safety posture

This is accounting-only.  It does not submit orders, cancel orders, alter live
mode, or change any sizing config.

## Evidence lifecycle

```text
trade plan
-> order/fill lifecycle
-> closed autonomous trade
-> outcome reconciliation
-> autonomous_outcome evidence record
-> strategy-arm learning / validation
```

## Output

The reconciler emits evidence-shaped records with:

- `evidence_type = autonomous_outcome`
- `symbol`
- `strategy_bucket`
- `planned_risk`
- `trade_plan`
- `order`
- realized `outcome`

The outcome section contains realized price, result, R-multiple, fill summaries,
slippage, commission, partial-fill flag, and exit reason.

## Current limitations

This first version accepts fill rows supplied by callers or falls back to the
prices already stored on `AutonomousTrade`.  A later integration can wire this to
broker execution reports automatically.
