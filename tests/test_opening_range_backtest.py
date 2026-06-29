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


def test_backtest_groups_candles_by_ny_date_not_utc_date():
    """UTC candles whose date() differs from their NY date must be bucketed to the NY date."""
    from datetime import timezone
    # Build a session on 2026-06-01 in UTC (13:30-14:10 UTC = 09:30-10:10 NY).
    bars = []
    t = datetime(2026, 6, 1, 13, 30, tzinfo=timezone.utc)  # 09:30 NY June 1
    for _ in range(15):
        bars.append(Candle("QQQ", "1m", t, t + timedelta(minutes=1), 101, 102, 100, 101, 1000.0))
        t += timedelta(minutes=1)
    for _ in range(5):
        bars.append(Candle("QQQ", "1m", t, t + timedelta(minutes=1), 103, 103.3, 102.8, 103, 1000.0))
        t += timedelta(minutes=1)
    bars.append(Candle("QQQ", "1m", t, t + timedelta(minutes=1), 103.1, 103.3, 103.0, 103.2, 1000.0)); t += timedelta(minutes=1)
    bars.append(Candle("QQQ", "1m", t, t + timedelta(minutes=1), 103.6, 105.0, 103.5, 104.9, 1000.0)); t += timedelta(minutes=1)
    for _ in range(20):
        bars.append(Candle("QQQ", "1m", t, t + timedelta(minutes=1), 105, 110, 105, 110, 1000.0)); t += timedelta(minutes=1)
    # Inject a stray after-hours UTC candle whose UTC date() is June 2 but NY date is June 1
    # (00:30 UTC on June 2 = 20:30 NY on June 1 — same NY session)
    stray_t = datetime(2026, 6, 2, 0, 30, tzinfo=timezone.utc)
    bars.append(Candle("QQQ", "1m", stray_t, stray_t + timedelta(minutes=1), 109, 110, 108, 109, 100.0))
    # With NY-normalised bucketing, the stray goes to the June 1 NY bucket (not a new June 2 session)
    # so the backtest still produces exactly 1 trade (one day, one session-cap slot).
    res = OpeningRangeBacktest(OpeningRangeConfig()).run(bars)
    assert res.total_trades == 1
