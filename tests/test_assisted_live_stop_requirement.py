from autonomous.autonomous_config import AutonomousMode, AutonomousTradingConfig
from autonomous.candidate_scanner import CandidateSignal
from autonomous.trade_planner import TradePlanner


def _candidate(**kwargs):
    data = {
        "symbol": "AAA",
        "strength_score": 100,
        "signal_label": "Confirmed Rebound",
        "last_price": 100.0,
        "support_price": None,
        "resistance_price": 108.0,
    }
    data.update(kwargs)
    return CandidateSignal(**data)


def test_assisted_live_share_plan_requires_stop_price():
    planner = TradePlanner(
        AutonomousTradingConfig(
            mode=AutonomousMode.ASSISTED_LIVE,
            require_stop_price_for_assisted_live=True,
        )
    )
    reasons = []

    plan = planner.plan(
        _candidate(support_price=None),
        deployable_cash=50_000.0,
        equity=100_000.0,
        reasons=reasons,
    )

    assert plan is None
    assert any("requires valid stop_price" in reason for reason in reasons)


def test_assisted_live_share_plan_allows_valid_support_stop():
    planner = TradePlanner(
        AutonomousTradingConfig(
            mode=AutonomousMode.ASSISTED_LIVE,
            require_stop_price_for_assisted_live=True,
        )
    )

    plan = planner.plan(
        _candidate(support_price=96.0),
        deployable_cash=50_000.0,
        equity=100_000.0,
    )

    assert plan is not None
    assert plan.stop_price == 93.12


def test_recommend_only_still_allows_no_stop_for_review():
    planner = TradePlanner(
        AutonomousTradingConfig(
            mode=AutonomousMode.RECOMMEND_ONLY,
            require_stop_price_for_assisted_live=True,
        )
    )

    plan = planner.plan(
        _candidate(support_price=None),
        deployable_cash=50_000.0,
        equity=100_000.0,
    )

    assert plan is not None
    assert plan.stop_price is None
