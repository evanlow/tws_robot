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
