from datetime import datetime, timedelta, timezone

from autonomous.autonomous_config import AutonomousTradingConfig
from autonomous import AutonomousMode
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
    assert plan.market_data_health["allowed"] is True
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


def test_planner_blocks_stale_quote_for_assisted_live():
    now = datetime.now(timezone.utc)
    planner = TradePlanner(
        AutonomousTradingConfig(
            mode=AutonomousMode.ASSISTED_LIVE,
            market_data_max_quote_age_seconds=30,
            risk_per_trade_sizing_enabled=False,
            volatility_sizing_enabled=False,
            drawdown_governor_enabled=False,
        )
    )
    reasons = []

    plan = planner.plan(
        _candidate(
            extras={
                "bid": 99.95,
                "ask": 100.05,
                "execution_last": 100.0,
                "quote_timestamp": (now - timedelta(seconds=90)).isoformat(),
            }
        ),
        deployable_cash=100_000.0,
        equity=100_000.0,
        reasons=reasons,
    )

    assert plan is None
    assert any("market data health rejected" in reason for reason in reasons)
    assert any("quote age" in reason for reason in reasons)


def test_planner_can_block_missing_bid_ask_for_assisted_live_when_configured():
    planner = TradePlanner(
        AutonomousTradingConfig(
            mode=AutonomousMode.ASSISTED_LIVE,
            market_data_block_missing_bid_ask_live=True,
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
    assert any("bid/ask unavailable" in reason for reason in reasons)


def test_planner_records_market_data_health_diagnostics_on_plan():
    now = datetime.now(timezone.utc)
    planner = TradePlanner(
        AutonomousTradingConfig(
            risk_per_trade_sizing_enabled=False,
            volatility_sizing_enabled=False,
            drawdown_governor_enabled=False,
        )
    )

    plan = planner.plan(
        _candidate(
            extras={
                "bid": 99.95,
                "ask": 100.05,
                "execution_last": 100.0,
                "quote_timestamp": (now - timedelta(seconds=5)).isoformat(),
                "market_data_status": "healthy",
                "market_is_open": True,
            }
        ),
        deployable_cash=100_000.0,
        equity=100_000.0,
    )

    assert plan is not None
    assert plan.market_data_health["allowed"] is True
    assert plan.market_data_health["quote_age_seconds"] is not None
    assert plan.to_dict()["market_data_health"]["reason"] == "market-data health acceptable"
