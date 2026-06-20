import datetime

import pytest

from autonomous.autonomous_config import AutonomousTradingConfig
from autonomous.candidate_scanner import CandidateSignal
from autonomous.trade_planner import OptionChainHint, TradePlanner


def _candidate(**kwargs):
    data = {
        "symbol": "AAA",
        "strength_score": 100,
        "signal_label": "Confirmed Rebound",
        "last_price": 100.0,
        "support_price": 95.0,
        "resistance_price": 115.0,
        "extras": {
            "edge_estimate": {
                "p_win": 0.70,
                "avg_win_r": 2.0,
                "avg_loss_r": 1.0,
                "confidence": 0.8,
            },
            "edge_observed_trades": 50,
        },
    }
    data.update(kwargs)
    return CandidateSignal(**data)


def test_trade_planner_applies_drawdown_governor():
    cfg = AutonomousTradingConfig(
        risk_per_trade_sizing_enabled=False,
        volatility_sizing_enabled=False,
        drawdown_governor_enabled=True,
        strategy_drawdown_pct=0.05,
        max_new_position_pct=0.10,
    )
    planner = TradePlanner(cfg)

    plan = planner.plan(_candidate(), deployable_cash=100_000.0, equity=100_000.0)

    assert plan is not None
    assert plan.quantity == 50
    assert plan.sizing["binding_cap"] == "drawdown_cap"


def test_trade_planner_applies_fractional_edge_when_enabled():
    cfg = AutonomousTradingConfig(
        risk_per_trade_sizing_enabled=False,
        volatility_sizing_enabled=False,
        drawdown_governor_enabled=False,
        fractional_edge_sizing_enabled=True,
        fractional_edge_min_trades=10,
        fractional_edge_allow_size_increase=False,
        max_new_position_pct=0.02,
    )
    planner = TradePlanner(cfg)

    plan = planner.plan(_candidate(), deployable_cash=100_000.0, equity=100_000.0)

    assert plan is not None
    assert plan.sizing["binding_cap"] == "fractional_edge_cap"
    assert plan.sizing["caps"]["fractional_edge"]["applied"] is True
    assert plan.quantity < 20


def _option_hint(strike=90.0, contracts_available=5, bid=1.0, ask=1.5):
    return OptionChainHint(
        strike=strike,
        expiry=datetime.date(2025, 1, 17),
        bid=bid,
        ask=ask,
        contracts_available=contracts_available,
    )


def test_short_put_plan_applies_drawdown_governor_reduces_contracts():
    """Drawdown governor reduces the cap used to compute max contracts."""
    cfg = AutonomousTradingConfig(
        risk_per_trade_sizing_enabled=False,
        volatility_sizing_enabled=False,
        drawdown_governor_enabled=True,
        strategy_drawdown_pct=0.05,  # 50% multiplier
        prefer_cash_secured_put=True,
        allow_short_put=True,
        allow_share_buy=False,
        max_new_position_pct=0.10,
    )
    planner = TradePlanner(cfg)
    # strike=90 => per_contract_cash=9000; cap before governor = 10000 (10% of 100k)
    # cap after governor = 10000 * 0.5 = 5000 => max_contracts = floor(5000/9000) = 0
    # Use a larger deployable_cash so contracts > 0 after governor
    # cap = 0.10 * 200_000 = 20_000; after 50% -> 10_000 => floor(10_000/9_000) = 1
    plan = planner.plan(
        _candidate(support_price=95.0),
        deployable_cash=200_000.0,
        equity=200_000.0,
        option_hint=_option_hint(strike=90.0, contracts_available=5),
    )

    assert plan is not None
    assert plan.contracts == 1


def test_short_put_plan_halts_on_severe_drawdown():
    """Drawdown governor halts new short-put entries above 8% drawdown."""
    cfg = AutonomousTradingConfig(
        risk_per_trade_sizing_enabled=False,
        volatility_sizing_enabled=False,
        drawdown_governor_enabled=True,
        strategy_drawdown_pct=0.09,  # above 8% halt threshold
        prefer_cash_secured_put=True,
        allow_short_put=True,
        allow_share_buy=False,
        max_new_position_pct=0.10,
    )
    planner = TradePlanner(cfg)

    plan = planner.plan(
        _candidate(support_price=95.0),
        deployable_cash=100_000.0,
        equity=100_000.0,
        option_hint=_option_hint(strike=90.0, contracts_available=5),
    )

    assert plan is None


def test_config_rejects_strategy_drawdown_pct_above_one():
    with pytest.raises(ValueError, match="strategy_drawdown_pct must be in \\[0, 1\\]"):
        AutonomousTradingConfig(strategy_drawdown_pct=5.0)
