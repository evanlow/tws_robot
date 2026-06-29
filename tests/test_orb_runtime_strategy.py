"""Tests for the runtime OpeningRangeBreakoutStrategy plugin (ORB Phase 2.2)."""

from datetime import datetime, timedelta

from strategies.base_strategy import StrategyConfig
from strategies.signal import SignalType
from strategies.strategy_registry import StrategyRegistry
from strategies.opening_range_breakout import (
    OpeningRangeBreakoutStrategy,
    ORBRuntimeState,
    ORBTradeProposal,
)


def bar(t, o, h, l, c, vol=100.0, closed=True):
    return {
        "timestamp": t,
        "open": o,
        "high": h,
        "low": l,
        "close": c,
        "volume": vol,
        "is_closed": closed,
    }


def range_bars(low=100.0, high=102.0):
    out = []
    t = datetime(2026, 6, 1, 9, 30)
    for _ in range(15):
        out.append(bar(t, 101, high, low, 101))
        t += timedelta(minutes=1)
    return out


def _make() -> OpeningRangeBreakoutStrategy:
    cfg = StrategyConfig(name="ORB_QQQ", symbols=["QQQ"], parameters={})
    s = OpeningRangeBreakoutStrategy(cfg)
    s.start()
    return s


def _confirm(s, t):
    for _ in range(5):
        s.on_bar("QQQ", bar(t, 103, 103.3, 102.8, 103))
        t += timedelta(minutes=1)
    return t


def test_registry_registration_and_instantiation():
    reg = StrategyRegistry()
    reg.register_strategy_class("OpeningRangeBreakout", OpeningRangeBreakoutStrategy)
    assert "OpeningRangeBreakout" in reg.get_registered_classes()
    cfg = StrategyConfig(name="ORB_QQQ", symbols=["QQQ"], parameters={"opening_range_minutes": 15})
    strat = reg.create_strategy("OpeningRangeBreakout", cfg)
    assert isinstance(strat, OpeningRangeBreakoutStrategy)
    assert strat.orb_config.opening_range_minutes == 15


def test_normal_model_a_setup_emits_one_signal():
    s = _make()
    for b in range_bars():
        s.on_bar("QQQ", b)
    t = _confirm(s, datetime(2026, 6, 1, 9, 45))
    s.on_bar("QQQ", bar(t, 103.1, 103.3, 103.0, 103.2)); t += timedelta(minutes=1)
    sig = s.on_bar("QQQ", bar(t, 103.6, 105.0, 103.5, 104.9))
    assert sig is not None
    assert sig.signal_type == SignalType.BUY
    assert sig.stop_loss is not None and sig.take_profit is not None
    assert sig.stop_loss < sig.target_price < sig.take_profit
    assert len(s.proposals) == 1
    assert s.runtime_state("QQQ") == ORBRuntimeState.IN_TRADE


def test_no_signal_before_range_close():
    s = _make()
    for b in range_bars():
        assert s.on_bar("QQQ", b) is None
    assert s.runtime_state("QQQ") == ORBRuntimeState.BUILDING_RANGE
    assert s.proposals == []


def test_no_signal_before_5m_confirmation():
    s = _make()
    for b in range_bars():
        s.on_bar("QQQ", b)
    t = datetime(2026, 6, 1, 9, 45)
    for _ in range(4):  # only 4 bars: no 5m bucket closes
        assert s.on_bar("QQQ", bar(t, 103, 103.3, 102.8, 103)) is None
        t += timedelta(minutes=1)
    assert s.runtime_state("QQQ") == ORBRuntimeState.RANGE_READY


def test_invalid_range_marks_invalidated():
    s = _make()
    for b in range_bars()[:10]:
        s.on_bar("QQQ", b)
    s.on_bar("QQQ", bar(datetime(2026, 6, 1, 9, 45), 102, 102.5, 101.5, 102))
    assert s.runtime_state("QQQ") == ORBRuntimeState.INVALIDATED


def test_data_degraded_on_invalid_candle():
    s = _make()
    # high < low -> invalid OHLC
    s.on_bar("QQQ", bar(datetime(2026, 6, 1, 9, 30), 100, 99, 101, 100))
    assert s.runtime_state("QQQ") == ORBRuntimeState.DATA_DEGRADED


def test_entry_cutoff_done_for_session():
    s = _make()
    for b in range_bars():
        s.on_bar("QQQ", b)
    s.on_bar("QQQ", bar(datetime(2026, 6, 1, 9, 45), 102, 102.5, 101.5, 102))
    s.on_bar("QQQ", bar(datetime(2026, 6, 1, 12, 0), 103, 103.5, 102.5, 103))
    assert s.runtime_state("QQQ") == ORBRuntimeState.DONE_FOR_SESSION


def test_duplicate_proposal_prevention():
    s = _make()
    for b in range_bars():
        s.on_bar("QQQ", b)
    t = _confirm(s, datetime(2026, 6, 1, 9, 45))
    s.on_bar("QQQ", bar(t, 103.1, 103.3, 103.0, 103.2)); t += timedelta(minutes=1)
    s.on_bar("QQQ", bar(t, 103.6, 105.0, 103.5, 104.9)); t += timedelta(minutes=1)
    nxt = s.on_bar("QQQ", bar(t, 105.6, 107.0, 105.5, 106.9))
    assert nxt is None
    assert len(s.proposals) == 1


def test_bearish_and_model_c_diagnostic_only():
    s = _make()
    assert s.orb_config.short_enabled is False
    assert s.orb_config.model_c_enabled is False
    for b in range_bars():
        s.on_bar("QQQ", b)
    t = datetime(2026, 6, 1, 9, 45)
    for _ in range(5):
        s.on_bar("QQQ", bar(t, 99, 99.5, 98, 98.5))
        t += timedelta(minutes=1)
    assert s.proposals == []
    assert s.runtime_state("QQQ") == ORBRuntimeState.RANGE_READY


def test_proposal_to_dict_includes_stop_and_target():
    s = _make()
    for b in range_bars():
        s.on_bar("QQQ", b)
    t = _confirm(s, datetime(2026, 6, 1, 9, 45))
    s.on_bar("QQQ", bar(t, 103.1, 103.3, 103.0, 103.2)); t += timedelta(minutes=1)
    s.on_bar("QQQ", bar(t, 103.6, 105.0, 103.5, 104.9))
    p = s.proposals[0]
    assert isinstance(p, ORBTradeProposal)
    d = p.to_dict()
    assert d["stop_price"] < d["entry_price"] < d["target_price"]
