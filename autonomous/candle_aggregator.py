"""Closed-candle aggregation and data-quality detection for runtime ORB.

This module turns a stream of closed 1-minute OHLCV candles into closed 5-minute
and 15-minute candles, normalizing session boundaries to New York market time
while preserving the original (UTC-aware) timestamps. It also classifies the
quality of a 1-minute candle sequence so the runtime provider can mark data as
degraded when bars are missing, duplicated, out of order, stale, or still
forming.

Safety posture (Prime Directive):
- No broker, order, or TWS imports. This is a pure data layer.
- A forming candle is never aggregated as a closed candle.
- Aggregated candles are emitted only from complete, contiguous 1-minute groups.
"""

from __future__ import annotations

from enum import Enum
from typing import List, Optional
from zoneinfo import ZoneInfo

from autonomous.opening_range import Candle, aggregate_candles

NY_TZ = ZoneInfo("America/New_York")
UTC_MINUTES_PER_DAY = 24 * 60


class CandleDataStatus(str, Enum):
    """Per-symbol/per-timeframe runtime candle health states."""

    HEALTHY = "HEALTHY"
    WAITING_FOR_DATA = "WAITING_FOR_DATA"
    STALE = "STALE"
    MISSING_BARS = "MISSING_BARS"
    DUPLICATE_BARS = "DUPLICATE_BARS"
    OUT_OF_ORDER = "OUT_OF_ORDER"
    FORMING_ONLY = "FORMING_ONLY"
    PROVIDER_ERROR = "PROVIDER_ERROR"


def normalize_to_ny(candle: Candle) -> Candle:
    """Return a copy with timestamps normalized to New York market time.

    Timezone-aware timestamps are converted to ``America/New_York``. Naive
    timestamps are assumed to already be NY local time and left unchanged.
    """
    start = candle.start.astimezone(NY_TZ) if candle.start.tzinfo is not None else candle.start
    end = candle.end.astimezone(NY_TZ) if candle.end.tzinfo is not None else candle.end
    return Candle(
        symbol=candle.symbol,
        timeframe=candle.timeframe,
        start=start,
        end=end,
        open=candle.open,
        high=candle.high,
        low=candle.low,
        close=candle.close,
        volume=candle.volume,
        is_closed=candle.is_closed,
    )


def assess_one_minute_quality(candles: List[Candle]) -> CandleDataStatus:
    """Classify the quality of a 1-minute closed-candle sequence.

    The list is assumed to represent a single contiguous session. Detection is
    ordered by severity so the most actionable degraded state is surfaced first.
    Forming bars must be filtered out before calling this for closed analysis.
    """
    if not candles:
        return CandleDataStatus.WAITING_FOR_DATA

    closed = [c for c in candles if c.is_closed]
    if not closed:
        return CandleDataStatus.FORMING_ONLY

    minutes = [_session_minutes(c) for c in closed]
    if len(set(minutes)) != len(minutes):
        return CandleDataStatus.DUPLICATE_BARS
    if minutes != sorted(minutes):
        return CandleDataStatus.OUT_OF_ORDER
    if (minutes[-1] - minutes[0] + 1) != len(minutes):
        return CandleDataStatus.MISSING_BARS
    return CandleDataStatus.HEALTHY


def is_contiguous(candles: List[Candle]) -> bool:
    """True if 1m closed candles are unique, ordered, and gap-free."""
    return assess_one_minute_quality(candles) == CandleDataStatus.HEALTHY


def closed_aggregates(one_min: List[Candle], factor: int) -> List[Candle]:
    """Aggregate closed 1m candles into closed factor-minute candles.

    Forming candles are excluded; only complete, contiguous groups become closed
    aggregates. NY session boundaries are used for grouping.
    """
    closed = [c for c in one_min if c.is_closed]
    return aggregate_candles(closed, factor, tzinfo=NY_TZ)


def _session_minutes(candle: Candle) -> int:
    dt = candle.start
    if dt.tzinfo is not None:
        dt = dt.astimezone(NY_TZ)
    return dt.toordinal() * UTC_MINUTES_PER_DAY + dt.hour * 60 + dt.minute
