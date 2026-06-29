"""Tests for closed-candle aggregation and data-quality detection (ORB Phase 2.1)."""

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from autonomous.candle_aggregator import (
    CandleDataStatus,
    assess_one_minute_quality,
    closed_aggregates,
    is_contiguous,
    normalize_to_ny,
)
from autonomous.opening_range import Candle

NY = ZoneInfo("America/New_York")


def _utc_1m(symbol, t, base=100.0):
    return Candle(symbol, "1m", t, t + timedelta(minutes=1), base, base + 1, base - 1, base + 0.5, 1000.0)


def _series(symbol, start, n):
    return [_utc_1m(symbol, start + timedelta(minutes=i), 100 + i) for i in range(n)]


def test_normal_aggregation_5m_15m():
    # 09:30 NY == 13:30 UTC
    start = datetime(2026, 6, 1, 13, 30, tzinfo=timezone.utc)
    bars = _series("QQQ", start, 15)
    five = closed_aggregates(bars, 5)
    fifteen = closed_aggregates(bars, 15)
    assert len(five) == 3
    assert len(fifteen) == 1
    assert five[0].open == bars[0].open
    assert five[0].close == bars[4].close
    assert fifteen[0].high == max(b.high for b in bars)
    assert fifteen[0].low == min(b.low for b in bars)


def test_utc_normalizes_to_ny_session():
    start = datetime(2026, 6, 1, 13, 30, tzinfo=timezone.utc)
    c = _utc_1m("QQQ", start)
    ny = normalize_to_ny(c)
    assert ny.start.hour == 9 and ny.start.minute == 30


def test_incomplete_group_not_aggregated():
    start = datetime(2026, 6, 1, 13, 30, tzinfo=timezone.utc)
    bars = _series("QQQ", start, 4)  # < 5
    assert closed_aggregates(bars, 5) == []


def test_forming_candle_never_aggregated():
    start = datetime(2026, 6, 1, 13, 30, tzinfo=timezone.utc)
    bars = _series("QQQ", start, 5)
    bars[-1] = Candle("QQQ", "1m", bars[-1].start, bars[-1].end, 1, 2, 0, 1, 1, is_closed=False)
    assert closed_aggregates(bars, 5) == []


def test_healthy_sequence():
    bars = _series("QQQ", datetime(2026, 6, 1, 13, 30, tzinfo=timezone.utc), 5)
    assert assess_one_minute_quality(bars) == CandleDataStatus.HEALTHY
    assert is_contiguous(bars)


def test_missing_bar_detected():
    bars = _series("QQQ", datetime(2026, 6, 1, 13, 30, tzinfo=timezone.utc), 5)
    del bars[2]
    assert assess_one_minute_quality(bars) == CandleDataStatus.MISSING_BARS


def test_duplicate_bar_detected():
    bars = _series("QQQ", datetime(2026, 6, 1, 13, 30, tzinfo=timezone.utc), 5)
    bars.append(bars[2])
    assert assess_one_minute_quality(bars) == CandleDataStatus.DUPLICATE_BARS


def test_out_of_order_detected():
    bars = _series("QQQ", datetime(2026, 6, 1, 13, 30, tzinfo=timezone.utc), 5)
    bars[1], bars[3] = bars[3], bars[1]
    assert assess_one_minute_quality(bars) == CandleDataStatus.OUT_OF_ORDER


def test_empty_waiting():
    assert assess_one_minute_quality([]) == CandleDataStatus.WAITING_FOR_DATA


def test_forming_only():
    c = Candle("QQQ", "1m", datetime(2026, 6, 1, 13, 30, tzinfo=timezone.utc),
               datetime(2026, 6, 1, 13, 31, tzinfo=timezone.utc), 1, 2, 0, 1, 1, is_closed=False)
    assert assess_one_minute_quality([c]) == CandleDataStatus.FORMING_ONLY
