# Fractional Edge Sizing and Drawdown Governor

This is Group 3 of the intraday trading-intelligence roadmap.

The goal is to add two capital-preservation overlays on top of the existing
cash/equity, risk-per-trade, volatility, basket, and live-runner caps:

1. fractional edge sizing; and
2. drawdown-based sizing reduction / halt.

## Safety posture

The overlays are conservative by design:

- fractional edge sizing is disabled by default;
- positive fractional sizing requires a minimum evidence count;
- by default it cannot increase size above the current cap;
- non-positive edge can reduce size to zero;
- drawdown governor is enabled by default;
- severe drawdown can halt new entries by forcing a zero cap.

## Fractional edge sizing

The helper reads the candidate's `edge_estimate` and converts it into an optional
position cap.

It uses the same core expression discussed in the roadmap:

```text
raw_fraction = p_win - ((1 - p_win) / (avg_win_R / avg_loss_R))
adjusted_fraction = max(0, raw_fraction) * configured_fraction * confidence
```

Then it applies hard caps:

```text
final_fraction = min(
    adjusted_fraction,
    fractional_edge_max_position_pct,
    fractional_edge_retirement_mode_max_pct
)
```

This produces `fractional_edge_cap` only when:

- the feature is enabled;
- the estimate is complete;
- observed trades meet the configured minimum; and
- the resulting cap reduces size, unless size increases are explicitly allowed.

## Config

```python
fractional_edge_sizing_enabled = False
fractional_edge_fraction = 0.10
fractional_edge_min_trades = 100
fractional_edge_max_position_pct = 0.01
fractional_edge_retirement_mode_max_pct = 0.005
fractional_edge_allow_size_increase = False
fractional_edge_can_reduce_size = True
```

## Drawdown governor

The drawdown governor maps strategy drawdown to a multiplier:

| Drawdown | Multiplier |
|---:|---:|
| < 2% | 1.00x |
| 2% - 4% | 0.75x |
| 4% - 6% | 0.50x |
| 6% - 8% | 0.25x |
| > 8% | 0.00x / halt |

Config:

```python
drawdown_governor_enabled = True
strategy_drawdown_pct = 0.0
```

The first version uses `strategy_drawdown_pct` from config or from candidate
extras.  A later phase should compute this automatically from realized evidence
and the strategy equity curve.

## Integration

`PositionSizer` now evaluates caps in this order:

```text
cash/equity cap
risk-per-trade cap
volatility cap
fractional edge cap
drawdown cap
```

The final quantity is based on the smallest cap.  Each `TradePlan.sizing` block
records:

- binding cap;
- cap values;
- fractional edge decision;
- drawdown governor decision;
- notes explaining skipped or applied overlays.

## What this does not implement yet

This phase does not yet compute realized strategy drawdown automatically and does
not calibrate edge estimates from actual closed trades.  Those belong to future
phases: realized-outcome reconciliation, strategy equity curve, and validation
framework.
