# Risk-per-trade and volatility sizing

This is Sprint 4 of the intraday trading-intelligence roadmap.

The goal is to move position sizing beyond simple cash/equity caps.  The new
sizing layer still respects those hard caps, but can further reduce size based
on:

1. risk per share, using the planned stop price; and
2. volatility, using ADR/ATR-style percentage range when available.

## Design principle

The sizing layer can only **reduce** exposure.  It never increases position size
beyond existing cash/equity, basket, live, or operator caps.

```text
final_quantity = min(
    cash/equity cap quantity,
    risk-per-trade quantity,
    volatility-adjusted quantity
)
```

## Config

New `AutonomousTradingConfig` fields:

```python
risk_per_trade_sizing_enabled = True
max_risk_per_trade_equity_pct = 0.002
volatility_sizing_enabled = True
volatility_reference_pct = 0.02
volatility_min_size_multiplier = 0.25
```

Defaults are conservative:

- max risk per trade/leg = 0.2% of equity;
- volatility reference = 2% daily range;
- volatility multiplier will not shrink below 0.25x.

## Risk-per-trade sizing

When a valid stop exists:

```text
risk_per_share = entry_price - stop_price
max_risk_dollars = equity * max_risk_per_trade_equity_pct
risk_quantity = floor(max_risk_dollars / risk_per_share)
```

If no valid stop exists, risk-per-trade sizing is skipped.  Assisted-live mode
already requires a valid planner stop, so live entries should normally receive
this cap.

## Volatility sizing

When a candidate has `adr_pct` in `candidate.extras`:

```text
volatility_multiplier = min(1.0, volatility_reference_pct / adr_pct)
volatility_multiplier = max(volatility_min_size_multiplier, volatility_multiplier)
```

The base cash/equity cap is multiplied by this value.  A high-volatility stock
therefore receives a smaller position than a low-volatility stock.

## Binding-cap audit

Every `BUY_SHARES` `TradePlan` now includes a `sizing` block:

```json
{
  "quantity": 12,
  "required_cash": 1200.0,
  "binding_cap": "risk_per_trade_cap",
  "caps": {
    "base_cap_value": 10000.0,
    "risk_per_share": 7.85,
    "max_risk_dollars": 200.0,
    "cap_values": {
      "cash_equity_cap": 10000.0,
      "risk_per_trade_cap": 2500.0,
      "volatility_cap": 5000.0
    },
    "final_cap_value": 2500.0
  }
}
```

Evidence records also preserve this sizing block in `planned_risk` and
`basket_planned_risk`, so future edge estimation and fractional Kelly can see
which cap was binding.

## Applicability

This applies to:

- single-stock recommendations;
- paper execution;
- assisted-live plans;
- each basket leg.

## What this does not implement yet

This sprint does not add Kelly, edge estimation, correlation weighting, or
liquidity-aware sizing.  It creates the sizing foundation those later phases
need.
