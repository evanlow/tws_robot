"""Tests for ORB-aware planning in autonomous.trade_planner.TradePlanner.

Covers preservation of ORB entry/stop/target levels, rejection of malformed
ORB extras, and non-interference with the existing rebound (Confirmed
Rebound) planning path.
"""

from autonomous.autonomous_config import AutonomousMode, AutonomousTradingConfig
from autonomous.candidate_scanner import CandidateSignal
from autonomous.trade_planner import TradePlanner, TradeType


def _orb_candidate(**extras_overrides):
    extras = {
        "strategy": "opening_range_breakout",
        "setup_model": "MODEL_A_DISPLACEMENT_GAP",
        "direction": "LONG",
        "opening_range_high": 101.0,
        "opening_range_low": 100.0,
        "confirmation_time": "2026-06-01T09:50:00",
        "entry_price": 101.5,
        "stop_price": 100.5,
        "target_price": 105.5,
        "risk_per_share": 1.0,
        "reward_per_share": 4.0,
        "rr_ratio": 4.0,
        "orb_evidence": {"note": "test evidence"},
    }
    extras.update(extras_overrides)
    return CandidateSignal(
        symbol="QQQ",
        strength_score=100,
        signal_label="ORB_LONG_MODEL_A",
        last_price=101.5,
        support_price=100.5,
        resistance_price=105.5,
        extras=extras,
    )


def _legacy_cfg(**kwargs):
    return AutonomousTradingConfig(
        risk_per_trade_sizing_enabled=False,
        volatility_sizing_enabled=False,
        **kwargs,
    )


def test_orb_candidate_preserves_entry_stop_target_exactly():
    cfg = _legacy_cfg()
    plan = TradePlanner(cfg).plan(
        _orb_candidate(),
        deployable_cash=1_000_000.0,
        equity=1_000_000.0,
    )
    assert plan is not None
    assert plan.trade_type == TradeType.BUY_SHARES
    assert plan.limit_price == 101.5
    assert plan.stop_price == 100.5
    assert plan.target_price == 105.5
    assert plan.target_mode == "opening_range_breakout"
    assert plan.strategy == "opening_range_breakout"
    assert plan.extras["setup_model"] == "MODEL_A_DISPLACEMENT_GAP"
    assert plan.extras["orb_evidence"] == {"note": "test evidence"}


def test_orb_target_not_overwritten_by_resistance_or_adr_config():
    # exit_target_mode / adr config would normally recompute target — ORB
    # must ignore this and keep the ORB target as-is.
    cfg = _legacy_cfg(exit_target_mode="adr_intraday", adr_lookback_days=14)
    plan = TradePlanner(cfg).plan(
        _orb_candidate(),
        deployable_cash=1_000_000.0,
        equity=1_000_000.0,
    )
    assert plan is not None
    assert plan.target_price == 105.5
    assert plan.target_mode == "opening_range_breakout"


def test_orb_stop_not_derived_from_generic_support():
    # candidate.support_price differs from the ORB stop_price; the ORB stop
    # must win, not candidate.support_price * 0.97 (the rebound heuristic).
    cfg = _legacy_cfg()
    candidate = _orb_candidate()
    candidate.support_price = 90.0  # would produce stop=87.3 if misused
    plan = TradePlanner(cfg).plan(
        candidate,
        deployable_cash=1_000_000.0,
        equity=1_000_000.0,
    )
    assert plan is not None
    assert plan.stop_price == 100.5


def test_orb_rejects_missing_stop_price():
    cfg = _legacy_cfg()
    reasons = []
    plan = TradePlanner(cfg).plan(
        _orb_candidate(stop_price=None),
        deployable_cash=1_000_000.0,
        equity=1_000_000.0,
        reasons=reasons,
    )
    assert plan is None
    assert any("malformed ORB extras" in r for r in reasons)


def test_orb_rejects_missing_target_price():
    cfg = _legacy_cfg()
    reasons = []
    plan = TradePlanner(cfg).plan(
        _orb_candidate(target_price=None),
        deployable_cash=1_000_000.0,
        equity=1_000_000.0,
        reasons=reasons,
    )
    assert plan is None
    assert any("malformed ORB extras" in r for r in reasons)


def test_orb_rejects_missing_entry_price():
    cfg = _legacy_cfg()
    reasons = []
    plan = TradePlanner(cfg).plan(
        _orb_candidate(entry_price=None),
        deployable_cash=1_000_000.0,
        equity=1_000_000.0,
        reasons=reasons,
    )
    assert plan is None
    assert any("malformed ORB extras" in r for r in reasons)


def test_orb_rejects_invalid_rr_ratio():
    cfg = _legacy_cfg()
    reasons = []
    plan = TradePlanner(cfg).plan(
        _orb_candidate(rr_ratio=0.0),
        deployable_cash=1_000_000.0,
        equity=1_000_000.0,
        reasons=reasons,
    )
    assert plan is None
    assert any("malformed ORB extras" in r for r in reasons)


def test_orb_rejects_stop_above_entry():
    cfg = _legacy_cfg()
    reasons = []
    plan = TradePlanner(cfg).plan(
        _orb_candidate(stop_price=110.0),
        deployable_cash=1_000_000.0,
        equity=1_000_000.0,
        reasons=reasons,
    )
    assert plan is None
    assert any("malformed ORB extras" in r for r in reasons)


def test_orb_rejects_target_below_entry():
    cfg = _legacy_cfg()
    reasons = []
    plan = TradePlanner(cfg).plan(
        _orb_candidate(target_price=100.0),
        deployable_cash=1_000_000.0,
        equity=1_000_000.0,
        reasons=reasons,
    )
    assert plan is None
    assert any("malformed ORB extras" in r for r in reasons)


def test_orb_rejects_short_direction():
    cfg = _legacy_cfg()
    reasons = []
    plan = TradePlanner(cfg).plan(
        _orb_candidate(direction="SHORT"),
        deployable_cash=1_000_000.0,
        equity=1_000_000.0,
        reasons=reasons,
    )
    assert plan is None
    assert any("long-only" in r for r in reasons)


def test_orb_assisted_live_requires_stop_and_target():
    cfg = _legacy_cfg(
        mode=AutonomousMode.ASSISTED_LIVE,
        require_stop_price_for_assisted_live=True,
        market_data_health_guard_enabled=False,
    )
    plan = TradePlanner(cfg).plan(
        _orb_candidate(),
        deployable_cash=1_000_000.0,
        equity=1_000_000.0,
    )
    assert plan is not None
    assert plan.stop_price == 100.5
    assert plan.target_price == 105.5


def test_orb_respects_position_sizing_caps():
    cfg = _legacy_cfg(max_new_position_pct=0.10)
    # 10% of 500 equity = $50 cap, ORB entry price is 101.5 → cannot afford.
    plan = TradePlanner(cfg).plan(
        _orb_candidate(),
        deployable_cash=10_000.0,
        equity=500.0,
    )
    assert plan is None


def test_non_orb_candidate_unaffected_by_orb_branch():
    """The existing Confirmed Rebound planning path must be untouched."""
    cfg = _legacy_cfg()
    candidate = CandidateSignal(
        symbol="AAA",
        strength_score=100,
        signal_label="Confirmed Rebound",
        last_price=100.0,
        support_price=95.0,
        resistance_price=110.0,
    )
    plan = TradePlanner(cfg).plan(candidate, deployable_cash=10_000.0, equity=100_000.0)
    assert plan is not None
    assert plan.strategy == ""
    assert plan.target_mode == "resistance"
    assert plan.stop_price == round(95.0 * 0.97, 2)
