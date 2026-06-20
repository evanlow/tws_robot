from autonomous.autonomous_config import AutonomousTradingConfig
from autonomous.candidate_scanner import CandidateSignal
from autonomous.trade_planner import TradePlanner


def _candidate(**kwargs):
    data = {
        "symbol": "AAA",
        "strength_score": 100,
        "signal_label": "Confirmed Rebound",
        "last_price": 100.0,
        "support_price": 95.0,
        "resistance_price": 110.0,
        "extras": {
            "bid": 99.95,
            "ask": 100.05,
            "execution_last": 100.0,
        },
    }
    data.update(kwargs)
    return CandidateSignal(**data)


def test_planner_includes_execution_quality_on_plan():
    planner = TradePlanner(
        AutonomousTradingConfig(
            execution_quality_guard_enabled=True,
            risk_per_trade_sizing_enabled=False,
            volatility_sizing_enabled=False,
            drawdown_governor_enabled=False,
        )
    )

    plan = planner.plan(_candidate(), deployable_cash=100_000.0, equity=100_000.0)

    assert plan is not None
    assert plan.execution_quality["allowed"] is True
    assert "execution quality" in " ".join(plan.risk_notes).lower()


def test_planner_rejects_wide_spread():
    planner = TradePlanner(
        AutonomousTradingConfig(
            execution_quality_guard_enabled=True,
            execution_max_spread_pct=0.003,
            risk_per_trade_sizing_enabled=False,
            volatility_sizing_enabled=False,
            drawdown_governor_enabled=False,
        )
    )
    reasons = []

    plan = planner.plan(
        _candidate(extras={"bid": 99.0, "ask": 101.0}),
        deployable_cash=100_000.0,
        equity=100_000.0,
        reasons=reasons,
    )

    assert plan is None
    assert any("execution quality rejected" in r for r in reasons)


def test_planner_can_block_missing_quote_when_configured():
    planner = TradePlanner(
        AutonomousTradingConfig(
            execution_quality_guard_enabled=True,
            execution_block_on_missing_quote=True,
            risk_per_trade_sizing_enabled=False,
            volatility_sizing_enabled=False,
            drawdown_governor_enabled=False,
        )
    )
    reasons = []

    plan = planner.plan(
        _candidate(extras={}),
        deployable_cash=100_000.0,
        equity=100_000.0,
        reasons=reasons,
    )

    assert plan is None
    assert any("bid/ask unavailable" in r for r in reasons)


def test_planner_allows_missing_quote_by_default():
    planner = TradePlanner(
        AutonomousTradingConfig(
            execution_quality_guard_enabled=True,
            execution_block_on_missing_quote=False,
            risk_per_trade_sizing_enabled=False,
            volatility_sizing_enabled=False,
            drawdown_governor_enabled=False,
        )
    )

    plan = planner.plan(
        _candidate(extras={}),
        deployable_cash=100_000.0,
        equity=100_000.0,
    )

    assert plan is not None
    assert plan.execution_quality["allowed"] is True
    assert plan.execution_quality["warnings"]
