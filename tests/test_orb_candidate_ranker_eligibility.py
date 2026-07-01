"""Tests for ORB label eligibility in autonomous.candidate_ranker.CandidateRanker.

ORB candidates (``ORB_LONG_MODEL_A`` / ``ORB_LONG_MODEL_B``) must be
acceptable via ``AutonomousTradingConfig.allowed_signal_labels`` without
requiring ``required_signal_label == "Confirmed Rebound"``. Existing
rebound-only behaviour (default config) must be unaffected.
"""

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


def test_default_config_still_rejects_orb_labels():
    cfg = AutonomousTradingConfig()
    r = CandidateRanker(cfg)
    out = r.rank([_sig("QQQ", label="ORB_LONG_MODEL_A")])
    assert out == []


def test_allowed_signal_labels_accepts_orb_labels():
    cfg = AutonomousTradingConfig(allowed_signal_labels=["ORB_LONG_MODEL_A", "ORB_LONG_MODEL_B"])
    r = CandidateRanker(cfg)
    ranked = r.rank([_sig("QQQ", label="ORB_LONG_MODEL_A")])
    assert [rc.candidate.symbol for rc in ranked] == ["QQQ"]


def test_allowed_signal_labels_still_rejects_labels_outside_the_list():
    cfg = AutonomousTradingConfig(allowed_signal_labels=["ORB_LONG_MODEL_A"])
    r = CandidateRanker(cfg)
    out = r.rank([_sig("QQQ", label="Confirmed Rebound")])
    assert out == []


def test_allowed_signal_labels_overrides_required_signal_label():
    # required_signal_label remains "Confirmed Rebound" but is ignored once
    # allowed_signal_labels is a non-empty list.
    cfg = AutonomousTradingConfig(
        required_signal_label="Confirmed Rebound",
        allowed_signal_labels=["ORB_LONG_MODEL_B"],
    )
    r = CandidateRanker(cfg)
    out = r.rank([_sig("AAA", label="Confirmed Rebound")])
    assert out == []
    ranked = r.rank([_sig("BBB", label="ORB_LONG_MODEL_B")])
    assert [rc.candidate.symbol for rc in ranked] == ["BBB"]


def test_empty_allowed_signal_labels_falls_back_to_required_signal_label():
    cfg = AutonomousTradingConfig(allowed_signal_labels=[])
    r = CandidateRanker(cfg)
    ranked = r.rank([_sig("AAA", label="Confirmed Rebound")])
    assert [rc.candidate.symbol for rc in ranked] == ["AAA"]
    out = r.rank([_sig("BBB", label="ORB_LONG_MODEL_A")])
    assert out == []


def test_existing_safety_guards_still_apply_to_orb_candidates():
    # Strength-score gate must still apply even with allowed_signal_labels set.
    cfg = AutonomousTradingConfig(
        allowed_signal_labels=["ORB_LONG_MODEL_A"],
        min_signal_strength=100,
    )
    r = CandidateRanker(cfg)
    out = r.rank([_sig("QQQ", label="ORB_LONG_MODEL_A", strength=50)])
    assert out == []
