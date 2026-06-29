"""Backtest tests for the ORB strategy on synthetic 1-minute OHLCV days."""

from datetime import datetime, timedelta

from autonomous.opening_range import Candle, OpeningRangeConfig
from backtest.opening_range_strategy import OpeningRangeBacktest


def candle(t, o, h, l, c, vol=1000.0):
    return Candle("QQQ", "1m", t, t + timedelta(minutes=1), o, h, l, c, vol)


def build_day(day=datetime(2026, 6, 1)):
    bars = []
    t = day.replace(hour=9, minute=30)
    # 15 opening-range bars in [100, 102]
    for _ in range(15):
        bars.append(candle(t, 101, 102, 100, 101)); t += timedelta(minutes=1)
    # confirmation 5m bucket above range high
    for _ in range(5):
        bars.append(candle(t, 103, 103.3, 102.8, 103)); t += timedelta(minutes=1)
    # model A gap-up entry bars
    bars.append(candle(t, 103.1, 103.3, 103.0, 103.2)); t += timedelta(minutes=1)
    bars.append(candle(t, 103.6, 105.0, 103.5, 104.9)); t += timedelta(minutes=1)
    # run-up to target
    for _ in range(20):
        bars.append(candle(t, 105, 110, 105, 110)); t += timedelta(minutes=1)
    return bars


def test_backtest_takes_one_trade_and_hits_target():
    res = OpeningRangeBacktest(OpeningRangeConfig()).run(build_day())
    assert res.total_trades == 1
    trade = res.trades[0]
    assert trade.exit_reason == "target"
    assert trade.pnl > 0
    assert trade.quantity > 0
    assert "MODEL_A" in trade.model


def test_backtest_force_flat_closes():
    bars = []
    t = datetime(2026, 6, 1, 9, 30)
    for _ in range(15):
        bars.append(candle(t, 101, 102, 100, 101)); t += timedelta(minutes=1)
    for _ in range(5):
        bars.append(candle(t, 103, 103.3, 102.8, 103)); t += timedelta(minutes=1)
    bars.append(candle(t, 103.1, 103.3, 103.0, 103.2)); t += timedelta(minutes=1)
    bars.append(candle(t, 103.6, 104.0, 103.5, 104.0)); t += timedelta(minutes=1)
    # flat (below target) into force-flat time at 15:55
    t = datetime(2026, 6, 1, 15, 55)
    bars.append(candle(t, 104.1, 104.2, 104.0, 104.1))
    res = OpeningRangeBacktest(OpeningRangeConfig()).run(bars)
    assert res.total_trades == 1
    assert res.trades[0].exit_reason == "force_flat"


def test_backtest_summary_keys():
    res = OpeningRangeBacktest(OpeningRangeConfig()).run(build_day())
    summary = res.summary()
    assert summary["total_trades"] == 1
    assert "by_model" in summary and "by_symbol" in summary
    assert res.win_rate == 1.0


def build_day_for(symbol, day=datetime(2026, 6, 1)):
    bars = []
    t = day.replace(hour=9, minute=30)
    for _ in range(15):
        bars.append(Candle(symbol, "1m", t, t + timedelta(minutes=1), 101, 102, 100, 101, 1000.0)); t += timedelta(minutes=1)
    for _ in range(5):
        bars.append(Candle(symbol, "1m", t, t + timedelta(minutes=1), 103, 103.3, 102.8, 103, 1000.0)); t += timedelta(minutes=1)
    bars.append(Candle(symbol, "1m", t, t + timedelta(minutes=1), 103.1, 103.3, 103.0, 103.2, 1000.0)); t += timedelta(minutes=1)
    bars.append(Candle(symbol, "1m", t, t + timedelta(minutes=1), 103.6, 105.0, 103.5, 104.9, 1000.0)); t += timedelta(minutes=1)
    for _ in range(20):
        bars.append(Candle(symbol, "1m", t, t + timedelta(minutes=1), 105, 110, 105, 110, 1000.0)); t += timedelta(minutes=1)
    return bars


def test_backtest_enforces_total_trades_per_session_cap():
    multi = build_day_for("QQQ") + build_day_for("SPY")
    res = OpeningRangeBacktest(OpeningRangeConfig()).run(multi)
    assert res.total_trades == 1  # default cap is one ORB trade per session


def test_backtest_allows_two_when_cap_raised():
    multi = build_day_for("QQQ") + build_day_for("SPY")
    cfg = OpeningRangeConfig(max_total_orb_trades_per_session=2)
    res = OpeningRangeBacktest(cfg).run(multi)
    assert res.total_trades == 2


def test_backtest_force_flat_normalizes_utc():
    from datetime import timezone
    bars = []
    t = datetime(2026, 6, 1, 13, 30, tzinfo=timezone.utc)  # 09:30 NY
    for _ in range(15):
        bars.append(Candle("QQQ", "1m", t, t + timedelta(minutes=1), 101, 102, 100, 101, 1000.0)); t += timedelta(minutes=1)
    for _ in range(5):
        bars.append(Candle("QQQ", "1m", t, t + timedelta(minutes=1), 103, 103.3, 102.8, 103, 1000.0)); t += timedelta(minutes=1)
    bars.append(Candle("QQQ", "1m", t, t + timedelta(minutes=1), 103.1, 103.3, 103.0, 103.2, 1000.0)); t += timedelta(minutes=1)
    bars.append(Candle("QQQ", "1m", t, t + timedelta(minutes=1), 103.6, 104.0, 103.5, 104.0, 1000.0)); t += timedelta(minutes=1)
    # 18:00 UTC (14:00 NY): not yet force-flat
    mid = datetime(2026, 6, 1, 18, 0, tzinfo=timezone.utc)
    bars.append(Candle("QQQ", "1m", mid, mid + timedelta(minutes=1), 104.1, 104.2, 104.0, 104.1, 1000.0))
    # 19:55 UTC == 15:55 NY: force-flat
    ff = datetime(2026, 6, 1, 19, 55, tzinfo=timezone.utc)
    bars.append(Candle("QQQ", "1m", ff, ff + timedelta(minutes=1), 104.1, 104.2, 104.0, 104.1, 1000.0))
    res = OpeningRangeBacktest(OpeningRangeConfig()).run(bars)
    assert res.total_trades == 1
    assert res.trades[0].exit_reason == "force_flat"


def test_backtest_cap_picks_earliest_setup_not_alphabetical():
    # ZZZ triggers earlier (no extra delay); AAA delayed past cutoff allocation.
    early = build_day_for("ZZZ")
    late = build_day_for("AAA", day=datetime(2026, 6, 1))
    # delay AAA setup by shifting its post-range bars later
    late = late[:20] + [Candle("AAA", c.timeframe, c.start + timedelta(minutes=30),
                               c.end + timedelta(minutes=30), c.open, c.high, c.low, c.close, c.volume)
                        for c in late[20:]]
    res = OpeningRangeBacktest(OpeningRangeConfig()).run(early + late)
    assert res.total_trades == 1
    assert res.trades[0].symbol == "ZZZ"
