# Execution Quality Guard

This is Group 4 of the intraday trading-intelligence roadmap.

The goal is to avoid giving away edge through poor execution quality before an
autonomous order is submitted.

## What it checks

The guard evaluates a BUY limit plan against available quote data:

- bid / ask spread;
- ask price relative to the intended limit;
- latest price movement above the plan reference price.

If quote data is unavailable, the default behaviour is to warn but not block.
This can be changed to fail closed via the `execution_block_on_missing_quote`
field in `AutonomousTradingConfig`.

## Config

New `AutonomousTradingConfig` fields:

```python
execution_quality_guard_enabled = True
execution_max_spread_pct = 0.003
execution_max_slippage_pct = 0.005
execution_max_price_move_pct = 0.01
execution_block_on_missing_quote = False
```

Default interpretation:

- maximum spread: 0.3%;
- maximum ask-above-limit distance: 0.5%;
- maximum latest-price move above reference: 1.0%;
- missing quote: warn but do not block.

## Data source

The first implementation is data-feed agnostic.  It looks for quote fields in
`CandidateSignal.extras`:

```python
bid / quote_bid / execution_bid
ask / quote_ask / execution_ask
last / quote_last / execution_last / current_price
```

A later production improvement should wire these fields from live TWS market data
or a broker quote snapshot immediately before order submission.

## Integration

`TradePlanner` now evaluates execution quality before returning a `BUY_SHARES`
plan.  When the guard rejects, the planner returns `None` with a clear rejection
reason.

Every accepted `TradePlan` includes:

```json
"execution_quality": {
  "allowed": true,
  "reason": "execution quality acceptable",
  "spread_pct": 0.001,
  "slippage_pct": 0.0,
  "price_move_pct": 0.0,
  "warnings": []
}
```

## Applicability

Because the guard is inside `TradePlanner`, it applies to:

- single-trade recommendations;
- paper execution;
- assisted-live execution;
- each basket leg.

## Current limitations

This phase does not yet implement cancel/replace for resting orders or partial
fill analytics.  Those require deeper integration with the broker order lifecycle
and should be implemented as a later execution-management phase.
