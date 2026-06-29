"""Opening Range Breakout (ORB) domain models, config, and state machine.

This module implements a backtest-first, long-only Opening Range Breakout
intraday strategy for US equities / ETFs. It is deliberately deterministic and
broker-free so it can be unit-tested and backtested without any TWS connection.

Safety posture (Prime Directive):
- Long-only in the MVP. Bearish breakouts are recorded as diagnostics only.
- No raw market orders. Entry prices are marketable-limit prices capped by a
  configured slippage allowance.
- One trade per symbol per session by default.
- Conservative defaults; nothing here places real orders. It only produces
  ``ORBSetup`` trade plans that downstream paper/backtest layers may consume.

All session timing is evaluated in New York market time. Timestamps passed in
should be timezone-aware; naive timestamps are assumed to already be New York
local time.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, time, timedelta
from enum import Enum
from typing import List, Optional, Tuple
from zoneinfo import ZoneInfo


class OpeningRangeState(str, Enum):
    """Lifecycle states for the ORB session state machine."""

    WAITING_FOR_SESSION = "WAITING_FOR_SESSION"
    BUILDING_RANGE = "BUILDING_RANGE"
    RANGE_READY = "RANGE_READY"
    BREAKOUT_CONFIRMED = "BREAKOUT_CONFIRMED"
    ENTRY_ARMED = "ENTRY_ARMED"
    IN_TRADE = "IN_TRADE"
    DONE_FOR_SESSION = "DONE_FOR_SESSION"
    INVALIDATED = "INVALIDATED"


class ORBDirection(str, Enum):
    LONG = "LONG"
    SHORT = "SHORT"


class ORBEntryModel(str, Enum):
    MODEL_A_DISPLACEMENT_GAP = "MODEL_A_DISPLACEMENT_GAP"
    MODEL_B_BREAK_RETEST = "MODEL_B_BREAK_RETEST"
    MODEL_C_REVERSAL = "MODEL_C_REVERSAL"


@dataclass(frozen=True)
class Candle:
    """A single OHLCV candle for an ORB timeframe."""

    symbol: str
    timeframe: str  # "1m", "5m", "15m"
    start: datetime
    end: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0
    is_closed: bool = True

    @property
    def body(self) -> float:
        return abs(self.close - self.open)

    @property
    def range(self) -> float:
        return self.high - self.low

    @property
    def is_bullish(self) -> bool:
        return self.close > self.open

    @property
    def is_bearish(self) -> bool:
        return self.close < self.open

    def is_valid(self) -> bool:
        """Basic OHLC sanity check."""
        if self.high < self.low:
            return False
        if self.high < self.open or self.high < self.close:
            return False
        if self.low > self.open or self.low > self.close:
            return False
        if self.volume < 0:
            return False
        return True


@dataclass
class OpeningRange:
    symbol: str
    session_date: str
    range_start: datetime
    range_end: datetime
    high: float
    low: float
    source_candle: Candle

    @property
    def width(self) -> float:
        return self.high - self.low

    @property
    def width_pct(self) -> float:
        if self.low <= 0:
            return 0.0
        return self.width / self.low


@dataclass
class BreakoutConfirmation:
    symbol: str
    direction: ORBDirection
    candle_5m: Candle
    range_high: float
    range_low: float
    confirmed_at: datetime


@dataclass
class ORBSetup:
    symbol: str
    direction: ORBDirection
    model: ORBEntryModel
    detected_at: datetime
    entry_price: float
    stop_price: float
    target_price: float
    risk_per_share: float
    reward_per_share: float
    rr_ratio: float
    opening_range: OpeningRange
    confirmation: BreakoutConfirmation
    evidence: dict = field(default_factory=dict)
    invalidation_reason: Optional[str] = None


@dataclass
class OpeningRangeConfig:
    """Conservative, paper/backtest-first ORB configuration."""

    enabled: bool = False

    # Scope
    symbols: List[str] = field(default_factory=lambda: ["QQQ", "SPY"])
    asset_class: str = "STK"
    exchange: str = "SMART"
    currency: str = "USD"

    # Session
    timezone: str = "America/New_York"
    session_open: str = "09:30"
    opening_range_minutes: int = 15
    trade_start_after_range_close: bool = True
    entry_cutoff_time: str = "11:30"
    force_flat_time: str = "15:55"
    skip_half_days: bool = True
    require_regular_trading_hours: bool = True

    # Data
    base_timeframe: str = "1m"
    confirmation_timeframe: str = "5m"
    range_timeframe: str = "15m"
    min_bars_after_confirmation: int = 1
    max_quote_age_seconds: float = 5.0
    tick_size: float = 0.01

    # Direction / models
    long_enabled: bool = True
    short_enabled: bool = False  # disabled in MVP
    model_a_enabled: bool = True
    model_b_enabled: bool = True
    model_c_enabled: bool = False  # enable after deterministic tests

    # Model A: displacement/gap
    displacement_body_min_atr_fraction: float = 0.25
    displacement_body_min_range_fraction: float = 0.15
    gap_min_ticks: int = 1
    gap_stop_buffer_ticks: int = 1

    # Model B: retest
    retest_tolerance_bps: float = 5.0
    retest_max_wait_minutes: int = 45
    retest_confirmation_body_min_pct: float = 0.50
    swing_lookback_bars: int = 3
    stop_buffer_ticks: int = 1

    # Model C: reversal
    reversal_enabled_after_minutes: int = 15
    reversal_requires_failed_breakout: bool = True
    order_block_lookback_bars: int = 5

    # Risk / execution
    continuation_rr: float = 2.0
    risk_per_trade_equity_pct: float = 0.002
    max_position_equity_pct: float = 0.01
    max_trades_per_symbol_per_session: int = 1
    max_total_orb_trades_per_session: int = 1
    use_marketable_limit: bool = True
    max_entry_slippage_bps: float = 10.0
    require_bracket_order: bool = True

    # Quality gates
    min_opening_range_width_pct: float = 0.001
    max_opening_range_width_pct: float = 0.03
    min_volume_in_opening_range: float = 0.0
    avoid_earnings_within_days: int = 1
    vix_guard_enabled: bool = True

    def tzinfo(self) -> ZoneInfo:
        return ZoneInfo(self.timezone)

    def parse_time(self, value: str) -> time:
        hour, minute = value.split(":")
        return time(int(hour), int(minute))


def _session_minutes(dt: datetime, tzinfo: Optional[ZoneInfo] = None) -> int:
    """Minutes-since-midnight in market time.

    Timezone-aware timestamps are normalized to ``tzinfo`` (New York by default)
    so UTC candles (e.g. 13:30 UTC == 09:30 NY) compare correctly. Naive
    timestamps are assumed to already be in market local time.
    """
    if tzinfo is not None and dt.tzinfo is not None:
        dt = dt.astimezone(tzinfo)
    return dt.hour * 60 + dt.minute


class OpeningRangeSession:
    """Deterministic per-symbol ORB state machine for a single session.

    Consumers feed closed 1-minute candles via :meth:`on_closed_1m`. The session
    aggregates them into 5-minute confirmation candles internally, evaluates the
    opening range, breakout confirmation, and long-only entry models (A/B), and
    transitions through :class:`OpeningRangeState`.
    """

    def __init__(self, symbol: str, session_date: str, config: OpeningRangeConfig):
        self.symbol = symbol
        self.session_date = session_date
        self.config = config

        self.state = OpeningRangeState.WAITING_FOR_SESSION
        self.opening_range: Optional[OpeningRange] = None
        self.confirmation: Optional[BreakoutConfirmation] = None
        self.setup: Optional[ORBSetup] = None
        self.trades_taken = 0
        self.rejections: List[str] = []
        self.diagnostics: List[dict] = []

        self._range_1m: List[Candle] = []
        self._post_range_1m: List[Candle] = []
        self._seen_bearish_diag_ends: set = set()  # tracks c5.end datetimes already logged
        self._tz = config.tzinfo()
        self._open = config.parse_time(config.session_open)
        self._cutoff = config.parse_time(config.entry_cutoff_time)
        self._range_end_min = (
            self._open.hour * 60 + self._open.minute + config.opening_range_minutes
        )

    # ------------------------------------------------------------------
    def on_closed_1m(self, candle: Candle) -> Optional[ORBSetup]:
        """Process one closed 1-minute candle. Returns an ORBSetup if armed."""
        if not candle.is_closed:
            return None
        minute = _session_minutes(candle.start, self._tz)
        open_min = self._open.hour * 60 + self._open.minute

        if minute < open_min:
            return None  # remain WAITING_FOR_SESSION

        if minute < self._range_end_min:
            self.state = OpeningRangeState.BUILDING_RANGE
            if candle.is_valid():
                self._range_1m.append(candle)
            return None

        # At/after range end: finalize the range once.
        if self.opening_range is None and self.state in (
            OpeningRangeState.BUILDING_RANGE,
            OpeningRangeState.WAITING_FOR_SESSION,
        ):
            self._finalize_range()
            if self.state == OpeningRangeState.INVALIDATED:
                return None

        if self.state in (OpeningRangeState.DONE_FOR_SESSION, OpeningRangeState.INVALIDATED):
            return None

        # Entry cutoff: no new setups after cutoff.
        if minute >= (self._cutoff.hour * 60 + self._cutoff.minute):
            if self.state in (OpeningRangeState.RANGE_READY, OpeningRangeState.BREAKOUT_CONFIRMED):
                self.state = OpeningRangeState.DONE_FOR_SESSION
                self.rejections.append("entry_cutoff_reached")
            return None

        self._post_range_1m.append(candle)

        if self.state == OpeningRangeState.RANGE_READY:
            self._check_confirmation()
        if self.state == OpeningRangeState.BREAKOUT_CONFIRMED:
            return self._scan_entry_models()
        return None

    # ------------------------------------------------------------------
    def _finalize_range(self) -> None:
        cfg = self.config
        bars = self._range_1m
        if len(bars) < cfg.opening_range_minutes:
            self.state = OpeningRangeState.INVALIDATED
            self.rejections.append(
                f"insufficient_range_bars:{len(bars)}/{cfg.opening_range_minutes}"
            )
            return
        open_min = self._open.hour * 60 + self._open.minute
        expected = [open_min + i for i in range(cfg.opening_range_minutes)]
        actual = [_session_minutes(b.start, self._tz) for b in bars]
        if actual != expected:
            self.state = OpeningRangeState.INVALIDATED
            self.rejections.append(
                f"non_contiguous_range_bars:{actual}!={expected}"
            )
            return
        high = max(b.high for b in bars)
        low = min(b.low for b in bars)
        if high - low <= 0:
            self.state = OpeningRangeState.INVALIDATED
            self.rejections.append("range_width_zero")
            return
        width_pct = (high - low) / low if low > 0 else 0.0
        if width_pct < cfg.min_opening_range_width_pct:
            self.state = OpeningRangeState.INVALIDATED
            self.rejections.append(f"range_too_narrow:{width_pct:.5f}")
            return
        if width_pct > cfg.max_opening_range_width_pct:
            self.state = OpeningRangeState.INVALIDATED
            self.rejections.append(f"range_too_wide:{width_pct:.5f}")
            return
        source = Candle(
            symbol=self.symbol,
            timeframe="15m",
            start=bars[0].start,
            end=bars[-1].end,
            open=bars[0].open,
            high=high,
            low=low,
            close=bars[-1].close,
            volume=sum(b.volume for b in bars),
        )
        self.opening_range = OpeningRange(
            symbol=self.symbol,
            session_date=self.session_date,
            range_start=bars[0].start,
            range_end=bars[-1].end,
            high=high,
            low=low,
            source_candle=source,
        )
        self.state = OpeningRangeState.RANGE_READY

    def _aggregate_5m(self) -> List[Candle]:
        return aggregate_candles(self._post_range_1m, 5, self._tz)

    def _check_confirmation(self) -> None:
        if self.opening_range is None:
            return
        for c5 in self._aggregate_5m():
            if c5.close > self.opening_range.high:
                if self.config.long_enabled:
                    self.confirmation = BreakoutConfirmation(
                        symbol=self.symbol,
                        direction=ORBDirection.LONG,
                        candle_5m=c5,
                        range_high=self.opening_range.high,
                        range_low=self.opening_range.low,
                        confirmed_at=c5.end,
                    )
                    self.state = OpeningRangeState.BREAKOUT_CONFIRMED
                    return
            elif c5.close < self.opening_range.low:
                if c5.end not in self._seen_bearish_diag_ends:
                    self._seen_bearish_diag_ends.add(c5.end)
                    self.diagnostics.append(
                        {"type": "bearish_breakout", "rejected": not self.config.short_enabled,
                         "time": c5.end.isoformat()}
                    )

    def _scan_entry_models(self) -> Optional[ORBSetup]:
        if self.trades_taken >= self.config.max_trades_per_symbol_per_session:
            return None
        bars = self._post_range_1m
        if not bars:
            return None
        setup = None
        if self.config.model_a_enabled:
            setup = detect_model_a(bars, self.opening_range, self.confirmation, self.config)
        if setup is None and self.config.model_b_enabled:
            setup = detect_model_b(bars, self.opening_range, self.confirmation, self.config)
        if setup is not None:
            self.setup = setup
            self.state = OpeningRangeState.ENTRY_ARMED
            self.trades_taken += 1
            self.state = OpeningRangeState.IN_TRADE
            return setup
        return None

    def status(self) -> dict:
        rng = self.opening_range
        return {
            "symbol": self.symbol,
            "session_date": self.session_date,
            "state": self.state.value,
            "range_high": rng.high if rng else None,
            "range_low": rng.low if rng else None,
            "range_width_pct": rng.width_pct if rng else None,
            "breakout": self.confirmation.direction.value if self.confirmation else None,
            "entry_model": self.setup.model.value if self.setup else None,
            "trades_taken": self.trades_taken,
            "rejections": list(self.rejections),
        }


def aggregate_candles(one_min: List[Candle], factor: int,
                      tzinfo: Optional[ZoneInfo] = None) -> List[Candle]:
    """Aggregate consecutive 1m candles into closed factor-minute candles.

    Candles are grouped by their wall-clock minute aligned to the *factor*
    boundary (e.g. 5m boundaries at :00, :05). Only complete groups are emitted
    as closed candles; a partial trailing group is omitted (never treated closed).
    """
    if factor <= 1:
        return list(one_min)
    groups: List[List[Candle]] = []
    bucket: List[Candle] = []
    current_key: Optional[int] = None
    for c in one_min:
        key = (_session_minutes(c.start, tzinfo)) // factor
        if current_key is None or key != current_key:
            if bucket:
                groups.append(bucket)
            bucket = [c]
            current_key = key
        else:
            bucket.append(c)
    if bucket:
        groups.append(bucket)
    out: List[Candle] = []
    for g in groups:
        if len(g) != factor:
            continue  # too many or too few bars; not a clean closed group
        mins = [_session_minutes(c.start, tzinfo) for c in g]
        base = (mins[0] // factor) * factor
        if sorted(mins) != list(range(base, base + factor)):
            continue  # non-contiguous or duplicate minute timestamps within the bucket
        out.append(
            Candle(
                symbol=g[0].symbol,
                timeframe=f"{factor}m",
                start=g[0].start,
                end=g[-1].end,
                open=g[0].open,
                high=max(b.high for b in g),
                low=min(b.low for b in g),
                close=g[-1].close,
                volume=sum(b.volume for b in g),
                is_closed=True,
            )
        )
    return out


def _build_long_setup(
    entry: float,
    stop: float,
    model: ORBEntryModel,
    bars: List[Candle],
    rng: OpeningRange,
    conf: BreakoutConfirmation,
    cfg: OpeningRangeConfig,
    evidence: dict,
) -> Optional[ORBSetup]:
    if stop >= entry:
        return None
    risk = entry - stop
    if risk <= 0:
        return None
    target = entry + cfg.continuation_rr * risk
    if target <= entry:
        return None
    return ORBSetup(
        symbol=rng.symbol,
        direction=ORBDirection.LONG,
        model=model,
        detected_at=bars[-1].end,
        entry_price=round(entry, 4),
        stop_price=round(stop, 4),
        target_price=round(target, 4),
        risk_per_share=round(risk, 4),
        reward_per_share=round(target - entry, 4),
        rr_ratio=cfg.continuation_rr,
        opening_range=rng,
        confirmation=conf,
        evidence=evidence,
    )


def detect_model_a(bars, rng, conf, cfg) -> Optional[ORBSetup]:
    """Model A: long displacement / gap breakout above opening range high."""
    if rng is None or conf is None or len(bars) < 2:
        return None
    cur = bars[-1]
    prev = bars[-2]
    if not cur.is_closed:
        return None
    # Enter only on bars after the 5-minute confirmation (Phase 2 -> 1m entry).
    min_after = max(cfg.min_bars_after_confirmation, 1)
    if cur.start < conf.confirmed_at + timedelta(minutes=min_after - 1):
        return None
    if cur.close <= rng.high:
        return None
    if cur.body < cfg.displacement_body_min_range_fraction * rng.width:
        return None
    gap_threshold = prev.high + cfg.tick_size * cfg.gap_min_ticks
    if cur.low <= gap_threshold:
        return None
    entry = cur.close * (1 + cfg.max_entry_slippage_bps / 10_000)
    stop = min(prev.low, cur.low) - cfg.tick_size * cfg.gap_stop_buffer_ticks
    evidence = {"prev_high": prev.high, "prev_low": prev.low, "gap_low": cur.low}
    return _build_long_setup(entry, stop, ORBEntryModel.MODEL_A_DISPLACEMENT_GAP,
                             bars, rng, conf, cfg, evidence)


def detect_model_b(bars, rng, conf, cfg) -> Optional[ORBSetup]:
    """Model B: long break-and-retest of the opening range high."""
    if rng is None or conf is None or len(bars) < 2:
        return None
    tol = cfg.retest_tolerance_bps / 10_000
    zone_low = rng.high * (1 - tol)
    zone_high = rng.high * (1 + tol)
    retest_idx = None
    for i in range(len(bars) - 1):
        c = bars[i]
        if c.start < conf.confirmed_at:
            continue
        if c.low <= zone_high and c.high >= zone_low:
            retest_idx = i
            break
    if retest_idx is None:
        return None
    minutes_since = (bars[-1].end - conf.confirmed_at).total_seconds() / 60.0
    if minutes_since > cfg.retest_max_wait_minutes:
        return None
    cur = bars[-1]
    if not cur.is_closed or cur.close <= rng.high or cur.close <= cur.open:
        return None
    if cur.range <= 0:
        return None
    body_pct = cur.body / cur.range
    if body_pct < cfg.retest_confirmation_body_min_pct:
        return None
    window = bars[max(0, len(bars) - cfg.swing_lookback_bars):]
    swing_low = min(b.low for b in window)
    entry = cur.close * (1 + cfg.max_entry_slippage_bps / 10_000)
    stop = swing_low - cfg.tick_size * cfg.stop_buffer_ticks
    evidence = {"retest_index": retest_idx, "swing_low": swing_low, "body_pct": body_pct}
    return _build_long_setup(entry, stop, ORBEntryModel.MODEL_B_BREAK_RETEST,
                             bars, rng, conf, cfg, evidence)
