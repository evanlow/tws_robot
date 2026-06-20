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
        "extras": {},
    }
    data.update(kwargs)
    return CandidateSignal(**data)


def test_trade_planner_records_binding_risk_cap():
    cfg = AutonomousTradingConfig(
        max_new_position_pct=0.10,
        risk_per_trade_sizing_enabled=True,
        max_risk_per_trade_equity_pct=0.001,
        volatility_sizing_enabled=False,
    )
    planner = TradePlanner(cfg)

    plan = planner.plan(
        _candidate(),
        deployable_cash=100_000.0,
        equity=100_000.0,
    )

    assert plan is not None
    # support 95 * 0.97 = 92.15, risk/share 7.85, $100 risk budget => 12 shares
    assert plan.quantity == 12
    assert plan.sizing["binding_cap"] == "risk_per_trade_cap"
    assert plan.sizing["caps"]["risk_per_share"] == 7.85
    assert any("Binding sizing cap" in note for note in plan.risk_notes)


def test_trade_planner_records_binding_volatility_cap():
    cfg = AutonomousTradingConfig(
        max_new_position_pct=0.10,
        risk_per_trade_sizing_enabled=False,
        volatility_sizing_enabled=True,
        volatility_reference_pct=0.02,
        volatility_min_size_multiplier=0.25,
    )
    planner = TradePlanner(cfg)

    plan = planner.plan(
        _candidate(extras={"adr_pct": 0.04}),
        deployable_cash=100_000.0,
        equity=100_000.0,
    )

    assert plan is not None
    assert plan.quantity == 50
    assert plan.sizing["binding_cap"] == "volatility_cap"
    assert plan.sizing["caps"]["volatility_multiplier"] == 0.5


def test_trade_planner_can_disable_new_sizers():
    cfg = AutonomousTradingConfig(
        max_new_position_pct=0.01,
        risk_per_trade_sizing_enabled=False,
        volatility_sizing_enabled=False,
    )
    planner = TradePlanner(cfg)

    plan = planner.plan(
        _candidate(extras={"adr_pct": 0.10}),
        deployable_cash=100_000.0,
        equity=100_000.0,
    )

    assert plan is not None
    assert plan.quantity == 10
    assert plan.sizing["binding_cap"] == "cash_equity_cap"
