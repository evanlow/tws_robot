# Opening Range Breakout (ORB) — Backtest-first MVP

Long-only intraday Opening Range Breakout strategy for US equities/ETFs.
Phase 1 is backtest/paper-only and requires **no broker or TWS connection**.

## What changed

- `autonomous/opening_range.py`: ORB domain models, `OpeningRangeConfig`,
  deterministic 1m→5m/15m candle aggregation, and the `OpeningRangeSession`
  state machine with Model A (displacement/gap) and Model B (break-and-retest)
  long-only entry rules.
- `backtest/opening_range_strategy.py`: `OpeningRangeBacktest` runner over
  1-minute OHLCV with bracket exits (target/stop/force-flat) and per-symbol /
  per-model reporting.

## Safety controls

- Long-only; bearish breakouts are diagnostic-only (`short_enabled=False`).
- No raw market orders: entries use marketable-limit prices capped by
  `max_entry_slippage_bps`.
- One trade per symbol per session; conservative defaults; `enabled=False`.
- Setups rejected when stop ≥ entry, risk ≤ 0, target ≤ entry, or range width
  outside `[min_opening_range_width_pct, max_opening_range_width_pct]`.

## Usage

```python
from autonomous.opening_range import OpeningRangeConfig
from backtest.opening_range_strategy import OpeningRangeBacktest

result = OpeningRangeBacktest(OpeningRangeConfig()).run(candles_1m)
print(result.summary())
```

`candles_1m` is a list of `autonomous.opening_range.Candle` (timeframe "1m").
Session windows are evaluated in New York time; persist UTC internally.

## Tests

```bash
python -m pytest tests/test_opening_range_models.py \
  tests/test_opening_range_aggregation.py \
  tests/test_opening_range_state_machine.py \
  tests/test_opening_range_backtest.py
```

## Limitations

Model C disabled. Runtime strategy, candle provider, autonomous adapter, and
live-readiness gates are follow-up PRs (Phases 2–4).
