"""Unit tests for ORB domain models and config defaults."""

from datetime import datetime

from autonomous.opening_range import (
    Candle,
    OpeningRange,
    OpeningRangeConfig,
)


def _c(o, h, l, c, vol=100.0):
    return Candle("QQQ", "1m", datetime(2026, 6, 1, 9, 30), datetime(2026, 6, 1, 9, 31), o, h, l, c, vol)


def test_candle_properties():
    candle = _c(100, 105, 99, 104)
    assert candle.body == 4
    assert candle.range == 6
    assert candle.is_bullish and not candle.is_bearish
    assert candle.is_valid()


def test_candle_invalid_ohlc():
    bad = Candle("QQQ", "1m", datetime(2026, 6, 1), datetime(2026, 6, 1), 100, 99, 101, 100)
    assert not bad.is_valid()


def test_config_defaults_are_conservative():
    cfg = OpeningRangeConfig()
    assert cfg.enabled is False
    assert cfg.long_enabled is True
    assert cfg.short_enabled is False
    assert cfg.model_c_enabled is False
    assert cfg.use_marketable_limit is True
    assert cfg.max_trades_per_symbol_per_session == 1
    assert cfg.require_bracket_order is True


def test_opening_range_width():
    rng = OpeningRange("QQQ", "2026-06-01", datetime(2026, 6, 1, 9, 30),
                       datetime(2026, 6, 1, 9, 44), 105.0, 100.0, _c(100, 105, 100, 104))
    assert rng.width == 5.0
    assert abs(rng.width_pct - 0.05) < 1e-9
