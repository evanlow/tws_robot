"""Unit tests for ORB candle aggregation utilities."""

from datetime import datetime, timedelta

from autonomous.opening_range import Candle, aggregate_candles


def make_1m(n, start_h=9, start_m=30, base=100.0):
    out = []
    t = datetime(2026, 6, 1, start_h, start_m)
    for i in range(n):
        o = base + i
        out.append(Candle("QQQ", "1m", t, t + timedelta(minutes=1),
                          o, o + 0.5, o - 0.5, o + 0.2, 10.0))
        t += timedelta(minutes=1)
    return out


def test_15_one_minute_aggregate_to_one_15m():
    bars = make_1m(15)
    agg = aggregate_candles(bars, 15)
    assert len(agg) == 1
    assert agg[0].timeframe == "15m"
    assert agg[0].open == bars[0].open
    assert agg[0].close == bars[-1].close
    assert agg[0].high == max(b.high for b in bars)
    assert agg[0].low == min(b.low for b in bars)
    assert agg[0].volume == sum(b.volume for b in bars)


def test_5_one_minute_aggregate_to_one_5m():
    bars = make_1m(5)
    agg = aggregate_candles(bars, 5)
    assert len(agg) == 1
    assert agg[0].timeframe == "5m"


def test_partial_group_not_emitted():
    bars = make_1m(7)
    agg = aggregate_candles(bars, 5)
    assert len(agg) == 1  # only the first complete 5m, trailing 2 dropped


def test_aligned_to_boundaries():
    # Start at 9:32 so first bucket has fewer than 5 -> dropped
    bars = make_1m(8, start_m=32)
    agg = aggregate_candles(bars, 5)
    # boundary at :35 -> 32,33,34 partial (3) dropped, 35-39 complete
    assert len(agg) == 1
    assert agg[0].start.minute == 35


def test_factor_one_returns_same():
    bars = make_1m(3)
    assert aggregate_candles(bars, 1) == bars
