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
