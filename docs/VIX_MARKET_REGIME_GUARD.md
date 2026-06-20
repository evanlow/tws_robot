# VIX Market-Regime Guard

TWS Robot's autonomous strategy is long-biased by default.  A positive SPY
intraday move is useful context, but it is not enough: SPY can be green while
market fear/volatility is rising.  The VIX guard adds a second market-regime
layer before any autonomous entry is planned or executed.

## Applies to single-trade and continuous modes

The guard is implemented inside `AutonomousTradingEngine.run_once()`.  That path
is shared by:

- recommend-only scans/proposals
- paper autonomous execution
- live dry-run
- actual-live single trade
- actual-live continuous cycles

Because continuous mode calls `run_once()` for each subsequent cycle, every
cycle re-evaluates the same SPY/VIX market regime before planning a new entry.

## What the guard checks

The provider returns SPY and VIX day-open/current values:

```json
{
  "open": 500.0,
  "current": 503.0,
  "vix_open": 17.2,
  "vix_current": 18.1
}
```

The evaluator then returns a payload like:

```json
{
  "bullish": true,
  "trade_allowed": true,
  "classification": "Bullish / Volatility Caution",
  "size_multiplier": 0.5,
  "vix": {
    "level_regime": "normal",
    "direction_regime": "rising_caution"
  }
}
```

## Default behaviour

| Condition | Action |
|---|---|
| SPY not bullish intraday | Block new entries |
| VIX >= 30 | Block new entries |
| VIX rises >= 5% intraday | Block new entries |
| VIX >= 20 | Allow but reduce size |
| VIX rises >= 2.5% intraday | Allow but reduce size |
| VIX unavailable | Warn, but do not block by default |

When the regime is cautionary but not blocked, the engine applies
`size_multiplier` to deployable cash before the trade planner sizes the position.
For example, a 0.5x multiplier reduces a USD 10,000 deployable-cash budget to
USD 5,000 for that run.

## Configuration

The following fields are available on `AutonomousTradingConfig`:

```python
vix_guard_enabled = True
vix_missing_blocks_trade = False
vix_caution_level = 20.0
vix_block_level = 30.0
vix_caution_intraday_rise_pct = 2.5
vix_block_intraday_rise_pct = 5.0
vix_caution_size_multiplier = 0.50
vix_high_size_multiplier = 0.25
apply_market_regime_size_multiplier = True
```

For stricter retirement-style trading, consider setting:

```python
vix_missing_blocks_trade = True
vix_caution_level = 18.0
vix_block_level = 25.0
```

## Market data source

The Flask app installs a default yfinance-backed provider that fetches both SPY
and `^VIX`.  Existing operator overrides through
`current_app.config['autonomous_spy_price_provider']` still take precedence.

A future production improvement is to replace yfinance with a TWS market-data
snapshot for SPY and VIX/volatility proxy so the regime gate uses the same broker
market-data path as execution.
