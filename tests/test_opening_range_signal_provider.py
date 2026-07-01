"""Tests for autonomous.opening_range_signal_provider.OpeningRangeSignalProvider."""

from datetime import datetime, timedelta

import pytest

from autonomous.candidate_scanner import CandidateSignal
from autonomous.opening_range import (
    BreakoutConfirmation,
    Candle,
    ORBDirection,
    ORBEntryModel,
    ORBSetup,
    OpeningRange,
)
from autonomous.opening_range_signal_provider import (
    SIGNAL_LABEL_MODEL_A,
    SIGNAL_LABEL_MODEL_B,
    MappingOpeningRangeSetupSource,
    OpeningRangeSignalProvider,
)


def _candle(symbol="QQQ", o=101.0, h=101.5, l=100.5, c=101.2):
    t = datetime(2026, 6, 1, 9, 45)
    return Candle(symbol, "5m", t, t + timedelta(minutes=5), o, h, l, c, 1000.0)


def _opening_range(symbol="QQQ", high=101.0, low=100.0):
    t = datetime(2026, 6, 1, 9, 30)
    return OpeningRange(
        symbol=symbol,
        session_date="2026-06-01",
        range_start=t,
        range_end=t + timedelta(minutes=15),
        high=high,
        low=low,
        source_candle=_candle(symbol, o=100.5, h=high, l=low, c=100.8),
    )


def _confirmation(symbol="QQQ", confirmed_at=None):
    return BreakoutConfirmation(
        symbol=symbol,
        direction=ORBDirection.LONG,
        candle_5m=_candle(symbol),
        range_high=101.0,
        range_low=100.0,
        confirmed_at=confirmed_at or datetime(2026, 6, 1, 9, 50),
    )


def _setup(
    symbol="QQQ",
    direction=ORBDirection.LONG,
    model=ORBEntryModel.MODEL_A_DISPLACEMENT_GAP,
    entry_price=101.5,
    stop_price=100.5,
    target_price=103.5,
    risk_per_share=1.0,
    reward_per_share=2.0,
    rr_ratio=2.0,
    invalidation_reason=None,
    evidence=None,
):
    return ORBSetup(
        symbol=symbol,
        direction=direction,
        model=model,
        detected_at=datetime(2026, 6, 1, 9, 50),
        entry_price=entry_price,
        stop_price=stop_price,
        target_price=target_price,
        risk_per_share=risk_per_share,
        reward_per_share=reward_per_share,
        rr_ratio=rr_ratio,
        opening_range=_opening_range(symbol),
        confirmation=_confirmation(symbol),
        evidence=evidence or {"note": "test evidence"},
        invalidation_reason=invalidation_reason,
    )


def test_valid_model_a_setup_maps_to_candidate_signal():
    source = MappingOpeningRangeSetupSource({"QQQ": _setup()})
    provider = OpeningRangeSignalProvider(setup_source=source)

    signal = provider.analyze("qqq")

    assert isinstance(signal, CandidateSignal)
    assert signal.symbol == "QQQ"
    assert signal.signal_label == SIGNAL_LABEL_MODEL_A
    assert signal.last_price == 101.5
    assert signal.support_price == 100.5
    assert signal.resistance_price == 103.5
    assert signal.strength_score == 100

    extras = signal.extras
    assert extras["strategy"] == "opening_range_breakout"
    assert extras["setup_model"] == ORBEntryModel.MODEL_A_DISPLACEMENT_GAP.value
    assert extras["direction"] == "LONG"
    assert extras["opening_range_high"] == 101.0
    assert extras["opening_range_low"] == 100.0
    assert extras["confirmation_time"] == "2026-06-01T09:50:00"
    assert extras["entry_price"] == 101.5
    assert extras["stop_price"] == 100.5
    assert extras["target_price"] == 103.5
    assert extras["risk_per_share"] == 1.0
    assert extras["reward_per_share"] == 2.0
    assert extras["rr_ratio"] == 2.0
    assert extras["orb_evidence"] == {"note": "test evidence"}


def test_valid_model_b_setup_uses_model_b_label():
    source = MappingOpeningRangeSetupSource({"SPY": _setup(symbol="SPY", model=ORBEntryModel.MODEL_B_BREAK_RETEST)})
    provider = OpeningRangeSignalProvider(setup_source=source)

    signal = provider.analyze("SPY")

    assert signal is not None
    assert signal.signal_label == SIGNAL_LABEL_MODEL_B


def test_no_setup_returns_none():
    provider = OpeningRangeSignalProvider(setup_source=lambda symbol: None)
    assert provider.analyze("AAPL") is None


def test_setup_source_exception_returns_none():
    def _raise(symbol):
        raise RuntimeError("boom")

    provider = OpeningRangeSignalProvider(setup_source=_raise)
    assert provider.analyze("AAPL") is None


def test_short_direction_rejected():
    source = MappingOpeningRangeSetupSource({"QQQ": _setup(direction=ORBDirection.SHORT)})
    provider = OpeningRangeSignalProvider(setup_source=source)
    assert provider.analyze("QQQ") is None


def test_model_c_rejected():
    source = MappingOpeningRangeSetupSource({"QQQ": _setup(model=ORBEntryModel.MODEL_C_REVERSAL)})
    provider = OpeningRangeSignalProvider(setup_source=source)
    assert provider.analyze("QQQ") is None


def test_invalidated_setup_rejected():
    source = MappingOpeningRangeSetupSource({"QQQ": _setup(invalidation_reason="stale data")})
    provider = OpeningRangeSignalProvider(setup_source=source)
    assert provider.analyze("QQQ") is None


@pytest.mark.parametrize(
    "kwargs",
    [
        {"entry_price": 0.0},
        {"entry_price": -5.0},
        {"stop_price": 0.0},
        {"target_price": 0.0},
        {"stop_price": 102.0},  # stop above entry
        {"target_price": 100.0},  # target below entry
        {"risk_per_share": 0.0},
        {"reward_per_share": 0.0},
        {"rr_ratio": 0.0},
        {"rr_ratio": -1.0},
    ],
)
def test_malformed_setup_rejected(kwargs):
    source = MappingOpeningRangeSetupSource({"QQQ": _setup(**kwargs)})
    provider = OpeningRangeSignalProvider(setup_source=source)
    assert provider.analyze("QQQ") is None


def test_strength_score_provider_overrides_default():
    source = MappingOpeningRangeSetupSource({"QQQ": _setup()})
    provider = OpeningRangeSignalProvider(
        setup_source=source,
        strength_score_provider=lambda setup: 87.0,
    )
    signal = provider.analyze("QQQ")
    assert signal.strength_score == 87


def test_strength_score_provider_none_falls_back_to_default():
    source = MappingOpeningRangeSetupSource({"QQQ": _setup()})
    provider = OpeningRangeSignalProvider(
        setup_source=source,
        strength_score=42,
        strength_score_provider=lambda setup: None,
    )
    signal = provider.analyze("QQQ")
    assert signal.strength_score == 42


def test_mapping_setup_source_set_and_clear():
    source = MappingOpeningRangeSetupSource()
    assert source("QQQ") is None
    source.set("qqq", _setup())
    assert source("QQQ") is not None
    source.clear("qqq")
    assert source("QQQ") is None
