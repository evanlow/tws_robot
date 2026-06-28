"""Unit tests for the ORB state machine and Model A/B detection."""

from datetime import datetime, timedelta

from autonomous.opening_range import (
    Candle,
    ORBDirection,
    ORBEntryModel,
    OpeningRangeConfig,
    OpeningRangeSession,
    OpeningRangeState,
)


def candle(t, o, h, l, c, vol=100.0):
    return Candle("QQQ", "1m", t, t + timedelta(minutes=1), o, h, l, c, vol)


def range_bars(low=100.0, high=102.0):
    """15 valid 1m bars from 9:30 with range [100,102]."""
    bars = []
    t = datetime(2026, 6, 1, 9, 30)
    for i in range(15):
        bars.append(candle(t, 101, high, low, 101))
        t += timedelta(minutes=1)
    return bars


def test_waiting_before_open():
    s = OpeningRangeSession("QQQ", "2026-06-01", OpeningRangeConfig())
    t = datetime(2026, 6, 1, 9, 0)
    s.on_closed_1m(candle(t, 100, 100.5, 99.5, 100))
    assert s.state == OpeningRangeState.WAITING_FOR_SESSION


def test_building_then_ready():
    s = OpeningRangeSession("QQQ", "2026-06-01", OpeningRangeConfig())
    for b in range_bars():
        s.on_closed_1m(b)
    assert s.state == OpeningRangeState.BUILDING_RANGE
    # bar at 9:45 finalizes the range
    s.on_closed_1m(candle(datetime(2026, 6, 1, 9, 45), 102, 102.5, 101.5, 102))
    assert s.state == OpeningRangeState.RANGE_READY
    assert s.opening_range.high == 102.0
    assert s.opening_range.low == 100.0


def test_invalidated_missing_bars():
    s = OpeningRangeSession("QQQ", "2026-06-01", OpeningRangeConfig())
    for b in range_bars()[:10]:
        s.on_closed_1m(b)
    s.on_closed_1m(candle(datetime(2026, 6, 1, 9, 45), 102, 102.5, 101.5, 102))
    assert s.state == OpeningRangeState.INVALIDATED


def _drive_5m_confirm(s):
    t = datetime(2026, 6, 1, 9, 45)
    for _ in range(5):
        s.on_closed_1m(candle(t, 103, 103.3, 102.8, 103))
        t += timedelta(minutes=1)
    return t


def test_bearish_confirmation_rejected_when_short_disabled():
    s = OpeningRangeSession("QQQ", "2026-06-01", OpeningRangeConfig())
    for b in range_bars():
        s.on_closed_1m(b)
    s.on_closed_1m(candle(datetime(2026, 6, 1, 9, 45), 100, 100, 99, 99.5))
    t = datetime(2026, 6, 1, 9, 46)
    for _ in range(5):
        s.on_closed_1m(candle(t, 99, 99.2, 98, 98.5))
        t += timedelta(minutes=1)
    assert s.state == OpeningRangeState.RANGE_READY
    assert any(d["type"] == "bearish_breakout" and d["rejected"] for d in s.diagnostics)


def test_model_a_displacement_gap():
    s = OpeningRangeSession("QQQ", "2026-06-01", OpeningRangeConfig())
    for b in range_bars():
        s.on_closed_1m(b)
    t = _drive_5m_confirm(s)
    assert s.state == OpeningRangeState.BREAKOUT_CONFIRMED
    s.on_closed_1m(candle(t, 103.1, 103.3, 103.0, 103.2))  # prev high 103.3
    t += timedelta(minutes=1)
    setup = s.on_closed_1m(candle(t, 103.6, 105.0, 103.5, 104.9))  # gap up, strong body
    assert setup is not None
    assert setup.model == ORBEntryModel.MODEL_A_DISPLACEMENT_GAP
    assert setup.direction == ORBDirection.LONG
    assert setup.stop_price < setup.entry_price < setup.target_price
    assert abs(setup.rr_ratio - 2.0) < 1e-9


def test_model_b_break_retest():
    cfg = OpeningRangeConfig(model_a_enabled=False, retest_tolerance_bps=50)
    s = OpeningRangeSession("QQQ", "2026-06-01", cfg)
    for b in range_bars():
        s.on_closed_1m(b)
    t = _drive_5m_confirm(s)
    # retest near range high (102), then a strong confirming bar above 102
    s.on_closed_1m(candle(t, 102.3, 102.4, 101.95, 102.2)); t += timedelta(minutes=1)
    setup = s.on_closed_1m(candle(t, 102.1, 103.0, 102.0, 102.95))
    assert setup is not None
    assert setup.model == ORBEntryModel.MODEL_B_BREAK_RETEST
    assert setup.stop_price < setup.entry_price


def test_one_trade_per_session():
    s = OpeningRangeSession("QQQ", "2026-06-01", OpeningRangeConfig())
    for b in range_bars():
        s.on_closed_1m(b)
    t = _drive_5m_confirm(s)
    s.on_closed_1m(candle(t, 103.1, 103.3, 103.0, 103.2)); t += timedelta(minutes=1)
    s.on_closed_1m(candle(t, 103.6, 105.0, 103.5, 104.9)); t += timedelta(minutes=1)
    assert s.state == OpeningRangeState.IN_TRADE
    nxt = s.on_closed_1m(candle(t, 105.6, 107.0, 105.5, 106.9))
    assert nxt is None  # no further entries
    assert s.trades_taken == 1


def test_entry_cutoff_blocks_setup():
    s = OpeningRangeSession("QQQ", "2026-06-01", OpeningRangeConfig())
    for b in range_bars():
        s.on_closed_1m(b)
    s.on_closed_1m(candle(datetime(2026, 6, 1, 9, 45), 102, 102.5, 101.5, 102))
    s.on_closed_1m(candle(datetime(2026, 6, 1, 12, 0), 103, 103.5, 102.5, 103))
    assert s.state == OpeningRangeState.DONE_FOR_SESSION
