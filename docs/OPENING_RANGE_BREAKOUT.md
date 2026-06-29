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
- One ORB trade per session overall: backtests enforce
  `max_total_orb_trades_per_session` across symbols per date.
- Setups rejected when stop ≥ entry, risk ≤ 0, target ≤ entry, or range width
  outside `[min_opening_range_width_pct, max_opening_range_width_pct]`.
- Opening range requires the exact contiguous 9:30–9:44 NY one-minute bars;
  duplicate/missing/out-of-order timestamps invalidate the session.
- Model B accepts only retests that occur after the 5-minute breakout confirmation.
- Model A enters only on a bar after the 5-minute confirmation (no same-close entry); honors `min_bars_after_confirmation`.
- Backtest exits are evaluated in NY time: `force_flat_time` compares timezone-aware (UTC) candles after normalizing to NY; the per-session cap allocates by earliest `detected_at`, not symbol order.

## Usage

```python
from autonomous.opening_range import OpeningRangeConfig
from backtest.opening_range_strategy import OpeningRangeBacktest

result = OpeningRangeBacktest(OpeningRangeConfig()).run(candles_1m)
print(result.summary())
```

`candles_1m` is a list of `autonomous.opening_range.Candle` (timeframe "1m").
Session windows are evaluated in New York time: timezone-aware timestamps
(e.g. UTC) are normalized to NY before comparing session minutes; naive
timestamps are assumed to already be NY local time.

## Tests

```bash
python -m pytest tests/test_opening_range_models.py \
  tests/test_opening_range_aggregation.py \
  tests/test_opening_range_state_machine.py \
  tests/test_opening_range_backtest.py \
  tests/test_orb_backtest_reports.py \
  tests/test_opening_range_api.py
```

## Phase 1.5: Backtest lab, sweeps, and readiness (Issue #214)

A trader can run ORB backtests, parameter sweeps, classify readiness, and save
evidence without writing Python:

- `autonomous/orb_backtest_reports.py`: full report fields (total trades, win
  rate, avg/median R and net R after costs, total P&L, profit factor, max
  drawdown in R, avg hold time, per-model/symbol/time-of-day buckets — NY-session
  normalized, slippage/commission sensitivity in net R, no-trade reasons surfaced
  from session rejections), `run_sweep`, conservative `classify_readiness`
  (`READY_FOR_PAPER` / `NEEDS_MORE_DATA` / `DO_NOT_TRADE`; gates on net R), and
  `save_evidence`.
- `web/routes/api_opening_range.py`: `POST /api/opening-range/backtest/{run,
  sweep,save-evidence}` plus the `/opening-range/backtest` page. Backtest-only —
  no TWS connection, no live/paper orders. Inline candles allow deterministic
  runs; yfinance fetch is optional. Promotion to paper requires saved evidence.

## Limitations

Model C disabled. Runtime strategy, candle provider, autonomous adapter, and
live-readiness gates are follow-up PRs (Phases 2–4). No automatic parameter
optimization.
