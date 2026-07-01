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
  `save_evidence`. Profit factor is JSON-safe: `null` + `profit_factor_unbounded`
  true when there are gains but no losses.
- `web/routes/api_opening_range.py`: `POST /api/opening-range/backtest/{run,
  sweep,save-evidence}` plus the `/opening-range/backtest` page. Backtest-only —
  no TWS connection, no live/paper orders. Inline candles allow deterministic
  runs; yfinance fetch is optional. Promotion to paper requires saved evidence.

## Phase 2.1: Runtime candle provider and closed-candle aggregation (Issue #205)

The runtime data layer needed before ORB can run in recommend-only or
paper-autonomous mode. It is broker-free and places no orders:

- `autonomous/candle_aggregator.py`: `CandleDataStatus` health enum, NY
  normalization (`normalize_to_ny`, preserving UTC for storage/audit), 1m
  sequence quality classification (`assess_one_minute_quality` /
  `is_contiguous` — detects duplicate, out-of-order, and missing bars), and
  `closed_aggregates` which builds closed 5m/15m candles only from complete,
  contiguous 1m groups. Forming candles are excluded.
- `autonomous/candle_data_provider.py`: `CandleDataProvider` protocol and an
  in-memory `RuntimeCandleProvider` (`subscribe_candles`, `latest_closed_candle`,
  `recent_closed_candles`, `status`). It produces closed 1m candles for a symbol
  whitelist, aggregates 5m/15m on demand, marks data degraded when missing,
  duplicate, out-of-order, stale, or forming-only, supports session `backfill`
  for restart recovery, and exposes per-symbol health (UTC + NY timestamps) for
  the future dashboard/API. A forming candle is never returned as closed.

```bash
python -m pytest tests/test_orb_runtime_candle_aggregation.py \
  tests/test_orb_runtime_candle_provider.py
```

## Phase 2.2: Runtime ORB strategy plugin (Issue #206)

`strategies/opening_range_breakout.py`: `OpeningRangeBreakoutStrategy` subclasses
`BaseStrategy` and wraps the Phase 1 `OpeningRangeSession` state machine so ORB
can run inside `StrategyRegistry`. It builds an `OpeningRangeConfig` from the
persisted `StrategyConfig.parameters`, maintains one session per symbol/session
date, consumes only closed 1m candles via `on_bar`, and advances ORB state
deterministically. On a valid long-only Model A/B setup it emits exactly one
`Signal` (BUY, with stop/target/metadata) and a structured `ORBTradeProposal`;
it never submits orders. Model C and bearish breakouts stay diagnostic-only.
Closed 1m bars that arrive duplicated, out of order, or with a single dropped
bar inside a forming 5m bucket are skipped and the symbol is marked
DATA_DEGRADED, protecting the session's internal 5m aggregation. Per-symbol
`runtime_state` exposes WAITING_FOR_SESSION, BUILDING_RANGE, RANGE_READY,
BREAKOUT_CONFIRMED, PROPOSAL_READY, DONE_FOR_SESSION, INVALIDATED, and
DATA_DEGRADED for the dashboard/API. In this proposal-only phase the session's
IN_TRADE collapses to PROPOSAL_READY; a true IN_TRADE belongs to the later paper
execution / trade lifecycle work (#209/#210).

```bash
python -m pytest tests/test_orb_runtime_strategy.py
```

## Limitations

Model C disabled. Runtime strategy, autonomous adapter, and live-readiness gates
are follow-up PRs (Phases 2–4). No order execution, dashboard UI, live-readiness
gate, or forex/futures support in the Phase 2.1 candle layer. No automatic
parameter optimization.

## Dashboard configuration & session controls (Phase 2.3, #207)

`/opening-range/` is a trader-facing page to create/edit an ORB strategy, pick a
mode, and arm/disarm a session. Config persists to `config/orb_strategies.json`
(survives restart). Modes: off, backtest_only, recommend_only, paper_autonomous;
tiny_live_candidate and assisted_live are **locked** and can never arm. Paper
autonomous cannot arm unless paper-readiness gates pass (a saved
`READY_FOR_PAPER` backtest evidence record exists for a symbol); recommend-only
may arm with missing execution gates, which the dashboard shows. Arm, disarm,
disable-today, and emergency-stop are audit logged. No orders are placed.

```bash
python -m pytest tests/test_orb_session_manager.py tests/test_orb_session_api.py
```

## Recommend-only proposals & setup audit trail (Phase 2.4, #208)

`autonomous/orb_proposals.py` turns a deterministic `ORBSetup` into a
transparent *recommend-only* trade card (`ORBProposal`) — what ORB would do
**before** any order is placed. Each proposal carries entry/stop/target, sizing
(quantity, risk dollars, position value), R/R, the opening range, confirmation
candle metadata, setup evidence, and transparent `ProposalGates` (opening range
valid, 5m breakout confirmed, 1m model detected, market data healthy, spread
acceptable when quote data exists, risk manager approved, stop/target present,
session cap available, no existing open ORB trade, emergency stop inactive). The
entry is always a marketable `LIMIT` price — a proposal can never be a raw
market order — and `build_proposal` rejects any setup missing a stop/target,
non-long direction, or a stop that is not below the entry.

`ORBProposalStore` keeps proposals in memory and audit-logs every lifecycle
event (`proposal_created`, `proposal_skipped`, `proposal_expired`) to the
autonomous audit log. A trader can skip a proposal with an optional reason;
proposals expire on entry cutoff (`expire_due`), invalidation, stale data, or
session-cap consumption. API (read + skip/expire only; no execution):

```text
GET  /api/orb/proposals
GET  /api/orb/proposals/<proposal_id>
POST /api/orb/proposals/<proposal_id>/skip
POST /api/orb/proposals/<proposal_id>/expire
```

The `execute-paper` endpoint is wired in Phase 2.5 (see below). In this Phase
2.4 layer no paper or live order is placed.

```bash
python -m pytest tests/test_orb_trade_proposals.py tests/test_orb_session_api.py
```

## Paper-autonomous execution & protective orders (Phase 2.5, #209)

`autonomous/orb_execution.py` (`ORBPaperExecutor`, `SimulatedPaperBracketAdapter`)
turns a *valid, recommend-only* `ORBProposal` into a **paper** trade — and only
ever a paper trade — when the trader has explicitly enabled paper-autonomous
mode. It preserves the ORB safety posture (Prime Directive):

- **Paper only.** The executor refuses any mode other than `paper_autonomous`;
  there is no live/real-money execution path. Assisted/live modes are rejected
  outright rather than tolerating missing broker-visible protection.
- **No raw market orders.** The entry is always a marketable `LIMIT` order and
  the protective children are `STOP`/`LIMIT` orders. The adapter refuses to
  construct anything else, so a market order is impossible.
- **Stop and target mandatory.** A proposal that is not a recommend-only,
  long-only `stop < entry < target` card (or has zero quantity) is rejected
  before any order is submitted.
- **Protection status.** Bracket submission is preferred when the adapter
  supports it (`BRACKET_CONFIRMED`). A paper-only `EXIT_MANAGER_FALLBACK` is
  allowed only when explicitly configured (`orb_allow_exit_manager_fallback`)
  and is surfaced in the execution result. Otherwise the proposal is rejected as
  `MISSING_PROTECTION_REJECTED` and no entry is placed.
- **Idempotent.** Re-executing the same proposal returns the original trade and
  never places duplicate orders.
- **Emergency stop & session cap.** `POST /api/orb/emergency-stop` trips the
  executor and blocks execution; the per-session cap
  (`max_total_orb_trades_per_session`) blocks execution once consumed.
- **Evidence linkage.** Every entry/stop/target order carries the ORB strategy,
  session, setup, and proposal ids, and every execution/rejection is written to
  the autonomous audit log (`orb_paper_execution`).

Recommend-only mode never submits orders: the owning strategy must be in
`paper_autonomous` mode **and** actively armed for the proposal's session date
for `execute-paper` to place a trade. Mode alone is not sufficient — arming is
where the readiness/evidence gates are enforced (see the arm/disarm workflow
above). `execute-paper` rejects an un-armed strategy, a strategy armed for a
different session date, and a session disabled for the day.

```text
POST /api/orb/proposals/<proposal_id>/execute-paper
GET  /api/orb/trades
GET  /api/orb/trades/<trade_id>
```

```bash
python -m pytest tests/test_orb_paper_execution.py tests/test_orb_session_api.py
```

## Intraday exit lifecycle & in-trade monitor (Phase 2.6, #210)

Once `execute-paper` has submitted a trade's entry/protective orders,
`autonomous/orb_trade_store.py` (`ORBTradeStore`, `ORBIntradayTrade`,
`ORBTradeState`, `ORBExitReason`) and `autonomous/orb_exit_manager.py`
(`ORBExitManager`) own its intraday lifecycle and monitoring:

- **Lifecycle states.** `ENTRY_PENDING` → `OPEN` → `EXIT_PENDING` →
  `CLOSED`/`FAILED`, matching the states used by the existing multi-day
  autonomous trade store (`autonomous/trade_store.py`).
- **Exit triggers**, evaluated in priority order: emergency stop, manual close
  (operator `close-now`), take-profit (last price ≥ target), stop-loss (last
  price ≤ stop), force-flat time (per-strategy `force_flat_time`), and an
  optional per-trade max-holding-minutes cap.
- **In-trade monitor fields**: trade/strategy/symbol/entry model, entry/target/
  stop/exit order status, protection status, current price, current R, MFE/MAE
  in R, planned-vs-actual entry slippage, exit slippage, time in trade, and a
  force-flat countdown.
- **No fake fills.** Fills are only ever simulated against a live price
  supplied by the configured `price_provider`; if no price is available when a
  mandatory flatten boundary (force-flat/emergency-stop/max-holding) is hit,
  the trade is marked `FAILED` with an explicit note rather than silently
  remaining `OPEN`.
- **Exposure can only be reduced.** Every exit — target, stop, force-flat,
  emergency-stop, or manual close — submits a single SELL sized to the trade's
  original (never increased) quantity. The trade store makes a second exit
  request against a trade that is not `OPEN` a no-op, so duplicate exits and
  oversell/over-close attempts never place a second reducing order.
- **Operator actions**: `close-now` (requires `OPEN`), `cancel-entry` (only
  while `ENTRY_PENDING`; never opens/increases exposure), and
  `disable-new-entries`/`enable-new-entries` per strategy (blocks only *new*
  paper entries — an already-open trade keeps being evaluated for exit
  normally).

```text
GET  /api/orb/intraday-trades
GET  /api/orb/intraday-trades/<trade_id>
POST /api/orb/trades/<trade_id>/close-now
POST /api/orb/trades/<trade_id>/cancel-entry
POST /api/orb/strategies/<name>/disable-new-entries
POST /api/orb/strategies/<name>/enable-new-entries
```

`POST /api/orb/emergency-stop` now also trips the exit manager and evaluates
every open ORB trade so nothing is left open behind an emergency stop.

```bash
python -m pytest tests/test_orb_intraday_exit_manager.py tests/test_orb_session_api.py
```

