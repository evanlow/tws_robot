# Support/Resistance and Live Stop Policy

This is Sprint 2 of the intraday trading-intelligence roadmap.

The goal is to make autonomous live trading depend on explicit technical
invalidation levels instead of generic fallback stops.

## What changed

### 1. Support/resistance helper

`autonomous/technical_levels.py` adds `compute_support_resistance_levels()`.

Given recent OHLC bars and the current price, it returns:

- nearest recent low below current price as `support_price`
- nearest recent high above current price as `resistance_price`
- source metadata
- lookback/bars-used metadata

This is intentionally simple and transparent.  It is a foundation for more
advanced support/resistance later, such as VWAP bands, volume profile, swing
structure, or intraday levels.

### 2. Signal provider enrichment

`TechnicalAnalysisSignalProvider` now forwards screener-published
`support_price` and `resistance_price` when available.

When a qualifying `Strong / Confirmed Rebound` signal has no screener-provided
levels, the production provider can fetch recent daily bars and enrich the signal
with derived support/resistance.

Direct/test construction keeps level enrichment disabled by default to avoid
accidental network I/O.

### 3. Assisted-live stop requirement

`AutonomousTradingConfig` adds:

```python
require_stop_price_for_assisted_live = True
```

When the engine is in `ASSISTED_LIVE` mode, `TradePlanner` now refuses to return
a `BUY_SHARES` plan unless the plan has a valid `stop_price` derived from
support/invalidation level.

This means the live runner should no longer need to rely on generic fallback stop
synthesis for normal live operation.  Recommend-only and paper mode may still
show no-stop plans for review/testing.

## Why this matters

Risk-per-trade sizing, expected-R ranking, and fractional Kelly require a real
risk denominator:

```text
risk_per_share = entry_price - stop_price
```

Without a valid stop/invalidation level, Kelly or risk-based sizing becomes
misleading.  Blocking live plans without valid stops prevents the system from
placing real-money entries where downside risk is undefined.

## Current limitations

The first implementation uses daily-bar nearest low/high levels.  It does not
yet include:

- intraday swing highs/lows
- VWAP bands
- volume-profile levels
- prior session high/low/open/close aggregation
- liquidity-aware stop buffers
- event/news-aware level invalidation

These should be added in later roadmap phases.

## Suggested next step

Sprint 3 should build on this by implementing a paper-only `BasketPlanner` that
uses these levels to ensure every basket leg has a valid target/stop before live
basket readiness is ever allowed.
