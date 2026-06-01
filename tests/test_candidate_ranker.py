"""Tests for autonomous.candidate_ranker."""

from datetime import date, timedelta

import pytest

from autonomous.autonomous_config import AutonomousTradingConfig
from autonomous.candidate_ranker import CandidateRanker
from autonomous.candidate_scanner import CandidateSignal


def _sig(symbol, strength=100, label="Confirmed Rebound", **kw):
    return CandidateSignal(
        symbol=symbol,
        strength_score=strength,
        signal_label=label,
        last_price=kw.pop("last_price", 100.0),
        support_price=kw.pop("support_price", 95.0),
        resistance_price=kw.pop("resistance_price", 110.0),
        **kw,
    )


def test_ranker_filters_weak_strength():
    cfg = AutonomousTradingConfig()
    r = CandidateRanker(cfg)
    out = r.rank([_sig("AAA", strength=99)])
    assert out == []


def test_ranker_filters_wrong_label():
    cfg = AutonomousTradingConfig()
    r = CandidateRanker(cfg)
    out = r.rank([_sig("AAA", label="Early Rebound")])
    assert out == []


def test_ranker_picks_best_among_multiple():
    cfg = AutonomousTradingConfig()
    r = CandidateRanker(cfg)
    # Both pass hard filters; B has the higher strength_score → wins.
    a = _sig("AAA", strength=100)
    b = _sig("BBB", strength=120)
    ranked = r.rank([a, b])
    assert [rc.candidate.symbol for rc in ranked] == ["BBB", "AAA"]


def test_ranker_rejects_close_to_earnings():
    cfg = AutonomousTradingConfig(avoid_earnings_within_days=7)
    r = CandidateRanker(cfg)
    today = date(2026, 6, 1)
    near = _sig("AAA", earnings_date=today + timedelta(days=3))
    far = _sig("BBB", earnings_date=today + timedelta(days=30))
    ranked = r.rank([near, far], today=today)
    assert [rc.candidate.symbol for rc in ranked] == ["BBB"]


def test_ranker_filters_over_concentrated_position():
    cfg = AutonomousTradingConfig(max_new_position_pct=0.10)
    r = CandidateRanker(cfg)
    # Existing position is 15% of 100k equity, exceeds the 10% cap.
    positions = {"AAA": {"market_value": 15000.0}}
    out = r.rank([_sig("AAA")], positions=positions, equity=100000.0)
    assert out == []


def test_ranker_rejection_reasons_recorded():
    cfg = AutonomousTradingConfig()
    r = CandidateRanker(cfg)
    _ranked, rejected = r.rank_with_rejections(
        [_sig("AAA", strength=10), _sig("BBB", label="Early Rebound")]
    )
    reasons = {row["symbol"]: row["reason"] for row in rejected}
    assert "strength_score 10" in reasons["AAA"]
    assert "signal_label" in reasons["BBB"]


def test_pick_best_returns_none_when_empty():
    cfg = AutonomousTradingConfig()
    r = CandidateRanker(cfg)
    assert r.pick_best([]) is None
