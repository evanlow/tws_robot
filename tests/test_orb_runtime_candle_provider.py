"""Tests for the runtime ORB candle provider (Phase 2.1)."""

from datetime import datetime, timedelta, timezone

from autonomous.candle_aggregator import CandleDataStatus
from autonomous.candle_data_provider import RuntimeCandleProvider
from autonomous.opening_range import Candle


def _bar(symbol, t, base=100.0, closed=True):
    return Candle(symbol, "1m", t, t + timedelta(minutes=1), base, base + 1, base - 1, base + 0.5, 1000.0,
                  is_closed=closed)


def _feed(provider, symbol, start, n, closed=True):
    for i in range(n):
        provider.ingest(_bar(symbol, start + timedelta(minutes=i), 100 + i, closed=closed))


def test_returns_closed_1m_for_subscribed_symbols():
    p = RuntimeCandleProvider()
    p.subscribe_candles(["QQQ", "SPY"])
    start = datetime(2026, 6, 1, 13, 30, tzinfo=timezone.utc)
    _feed(p, "QQQ", start, 3)
    assert len(p.recent_closed_candles("QQQ", "1m", 10)) == 3
    assert p.latest_closed_candle("QQQ", "1m").close == 102.5


def test_aggregates_5m_and_15m():
    p = RuntimeCandleProvider()
    p.subscribe_candles(["QQQ"])
    _feed(p, "QQQ", datetime(2026, 6, 1, 13, 30, tzinfo=timezone.utc), 15)
    assert len(p.recent_closed_candles("QQQ", "5m", 10)) == 3
    assert p.latest_closed_candle("QQQ", "15m") is not None


def test_forming_candle_not_returned_as_closed():
    p = RuntimeCandleProvider()
    p.subscribe_candles(["QQQ"])
    p.ingest(_bar("QQQ", datetime(2026, 6, 1, 13, 30, tzinfo=timezone.utc), closed=False))
    assert p.latest_closed_candle("QQQ", "1m") is None
    assert p.status()["QQQ"]["status"] == CandleDataStatus.FORMING_ONLY.value


def test_healthy_status():
    p = RuntimeCandleProvider(now_fn=lambda: datetime(2026, 6, 1, 13, 35, tzinfo=timezone.utc))
    p.subscribe_candles(["QQQ"])
    _feed(p, "QQQ", datetime(2026, 6, 1, 13, 30, tzinfo=timezone.utc), 5)
    st = p.status()["QQQ"]
    assert st["status"] == CandleDataStatus.HEALTHY.value
    assert st["last_closed_ny"].endswith("09:34:00-04:00")


def test_stale_detected():
    now = datetime(2026, 6, 1, 18, 0, tzinfo=timezone.utc)
    p = RuntimeCandleProvider(stale_seconds=120, now_fn=lambda: now)
    p.subscribe_candles(["QQQ"])
    _feed(p, "QQQ", datetime(2026, 6, 1, 13, 30, tzinfo=timezone.utc), 5)
    assert p.status()["QQQ"]["status"] == CandleDataStatus.STALE.value


def test_missing_bars_status():
    p = RuntimeCandleProvider(now_fn=lambda: datetime(2026, 6, 1, 13, 36, tzinfo=timezone.utc))
    p.subscribe_candles(["QQQ"])
    start = datetime(2026, 6, 1, 13, 30, tzinfo=timezone.utc)
    p.ingest(_bar("QQQ", start))
    p.ingest(_bar("QQQ", start + timedelta(minutes=2)))  # skip minute 1
    assert p.status()["QQQ"]["status"] == CandleDataStatus.MISSING_BARS.value


def test_waiting_for_data():
    p = RuntimeCandleProvider()
    p.subscribe_candles(["QQQ"])
    assert p.status()["QQQ"]["status"] == CandleDataStatus.WAITING_FOR_DATA.value


def test_backfill_recovers_session():
    p = RuntimeCandleProvider()
    p.subscribe_candles(["QQQ"])
    start = datetime(2026, 6, 1, 13, 30, tzinfo=timezone.utc)
    p.backfill([_bar("QQQ", start + timedelta(minutes=i), 100 + i) for i in range(15)])
    assert len(p.recent_closed_candles("QQQ", "1m", 100)) == 15
    assert len(p.recent_closed_candles("QQQ", "15m", 10)) == 1


def test_base_timeframe_must_be_1m():
    p = RuntimeCandleProvider()
    try:
        p.subscribe_candles(["QQQ"], base_timeframe="5m")
        assert False
    except ValueError:
        pass
