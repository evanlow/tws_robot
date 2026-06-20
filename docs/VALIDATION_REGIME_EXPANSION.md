# Validation and Regime Expansion

This is the last planned feature PR in the current tranche.

The goal is to improve validation discipline and enrich candidate features with
sector and time-of-day context.  This remains analytics/context only; it does not
automatically change live mode, sizing, or order submission.

## Sector regime context

`autonomous/regime_context.py` maps S&P sector names to common sector ETFs:

```text
Information Technology -> XLK
Financials -> XLF
Health Care -> XLV
Consumer Discretionary -> XLY
Industrials -> XLI
Energy -> XLE
Consumer Staples -> XLP
Utilities -> XLU
Materials -> XLB
Real Estate -> XLRE
Communication Services -> XLC
```

It also creates a sector regime label using optional candidate extras:

```python
sector_etf_bullish
sector_relative_strength_pct
```

Possible labels include:

- `sector_supportive`
- `sector_hostile`
- `sector_relative_strength`
- `sector_relative_weakness`
- `sector_unknown`

## Time-of-day regime

The helper adds coarse intraday labels:

- `opening_volatility`
- `regular_session`
- `midday_liquidity_lull`
- `closing_volatility`
- `outside_regular_session`

The first version uses UTC clock labels and existing timestamps from candidate
extras or market-gate payloads when available.

## FeatureBuilder integration

`FeatureBuilder` now includes:

```python
sector_etf
sector_bullish
sector_relative_strength_pct
sector_regime
time_of_day_regime
```

These fields become visible in ranked candidate feature output and can support
future edge calibration and strategy-arm grouping.

## Chronological validation

`autonomous/walk_forward_report.py` adds:

- `ChronoValidator`
- `ChronoValidationReport`
- `ChronoValidationWindow`

It evaluates realized evidence records in sequential earlier/later windows using
`ValidationFramework`.  This provides a simple out-of-sample style report before
any operator considers scaling capital.

## Safety posture

- No automatic strategy promotion.
- No automatic config change.
- No live-mode change.
- No order submission change.
- No sizing increase.

This PR only adds context labels and validation reports.
