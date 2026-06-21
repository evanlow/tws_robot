from autonomous.autonomous_config import AutonomousTradingConfig
from autonomous.basket_planner import BasketPlanner
from autonomous.candidate_ranker import RankedCandidate
from autonomous.candidate_scanner import CandidateSignal


def _ranked(symbol, sector, score=100.0, price=100.0, support=95.0):
    return RankedCandidate(
        candidate=CandidateSignal(
            symbol=symbol,
            strength_score=100,
            signal_label="Confirmed Rebound",
            company_name=f"{symbol} Corp",
            sector=sector,
            last_price=price,
            support_price=support,
            resistance_price=110.0,
        ),
        score=score,
        reasons=["test"],
    )


def test_basket_planner_selects_top_candidates_with_caps():
    cfg = AutonomousTradingConfig(
        basket_enabled=True,
        basket_max_size=3,
        basket_total_deployable_cash_pct=0.006,
        basket_single_position_deployable_cash_pct=0.002,
        basket_max_same_sector_positions=1,
    )
    planner = BasketPlanner(cfg)

    basket = planner.plan(
        [
            _ranked("AAA", "Tech", 100),
            _ranked("BBB", "Health", 99),
            _ranked("CCC", "Finance", 98),
        ],
        deployable_cash=100_000.0,
        equity=100_000.0,
    )

    assert basket is not None
    assert [p.symbol for p in basket.trade_plans] == ["AAA", "BBB", "CCC"]
    assert basket.total_required_cash <= basket.max_basket_value
    assert basket.max_basket_value == 600.0
    assert basket.risk_allocation is not None
    diagnostics = basket.to_dict()["risk_allocation"]
    assert diagnostics["enabled"] is True
    assert diagnostics["allocation_mode"] == "equal_risk"
    assert diagnostics["max_basket_risk_dollars"] == 200.0
    assert diagnostics["total_planned_risk_dollars"] <= 200.0
    assert [leg["allocated_risk_dollars"] for leg in diagnostics["legs"]] == [66.67, 66.67, 66.67]


def test_basket_planner_applies_sector_cap():
    cfg = AutonomousTradingConfig(
        basket_enabled=True,
        basket_max_size=3,
        basket_total_deployable_cash_pct=0.01,
        basket_single_position_deployable_cash_pct=0.002,
        basket_max_same_sector_positions=1,
    )
    planner = BasketPlanner(cfg)

    basket = planner.plan(
        [
            _ranked("AAA", "Tech", 100),
            _ranked("BBB", "Tech", 99),
            _ranked("CCC", "Health", 98),
        ],
        deployable_cash=100_000.0,
        equity=100_000.0,
    )

    assert basket is not None
    assert [p.symbol for p in basket.trade_plans] == ["AAA", "CCC"]
    assert any("sector cap" in r["reason"] for r in basket.rejected)


def test_basket_planner_disabled_returns_none():
    cfg = AutonomousTradingConfig(basket_enabled=False)
    planner = BasketPlanner(cfg)

    assert planner.plan([_ranked("AAA", "Tech")], deployable_cash=100_000, equity=100_000) is None


def test_basket_risk_allocator_reduces_leg_quantity_to_equal_risk_budget():
    cfg = AutonomousTradingConfig(
        basket_enabled=True,
        basket_max_size=3,
        basket_total_deployable_cash_pct=0.30,
        basket_single_position_deployable_cash_pct=0.10,
        max_risk_per_trade_equity_pct=0.10,
        max_basket_risk_equity_pct=0.002,
        basket_max_same_sector_positions=1,
    )
    planner = BasketPlanner(cfg)

    basket = planner.plan(
        [
            _ranked("AAA", "Tech", 100, price=100, support=90),
            _ranked("BBB", "Health", 99, price=100, support=90),
            _ranked("CCC", "Finance", 98, price=100, support=90),
        ],
        deployable_cash=100_000.0,
        equity=100_000.0,
    )

    assert basket is not None
    assert [p.quantity for p in basket.trade_plans] == [5, 5, 5]
    assert all(p.sizing["binding_cap"] == "basket_risk_cap" for p in basket.trade_plans)
    diagnostics = basket.to_dict()["risk_allocation"]
    assert diagnostics["max_basket_risk_dollars"] == 200.0
    assert diagnostics["total_planned_risk_dollars"] == 190.5
    assert all(leg["resized"] for leg in diagnostics["legs"])


def test_basket_risk_allocator_rejects_leg_when_one_share_exceeds_allocated_risk():
    cfg = AutonomousTradingConfig(
        basket_enabled=True,
        basket_max_size=2,
        basket_total_deployable_cash_pct=0.30,
        basket_single_position_deployable_cash_pct=0.10,
        max_risk_per_trade_equity_pct=0.10,
        max_basket_risk_equity_pct=0.001,
        basket_max_same_sector_positions=1,
        basket_min_leg_risk_dollars=0.0,
    )
    planner = BasketPlanner(cfg)

    basket = planner.plan(
        [
            _ranked("AAA", "Tech", 100, price=100, support=30),
            _ranked("BBB", "Health", 99, price=100, support=95),
        ],
        deployable_cash=100_000.0,
        equity=100_000.0,
    )

    assert basket is not None
    assert [p.symbol for p in basket.trade_plans] == ["BBB"]
    assert any("one-share risk" in item["reason"] for item in basket.rejected)
    diagnostics = basket.to_dict()["risk_allocation"]
    assert diagnostics["total_planned_risk_dollars"] <= diagnostics["max_basket_risk_dollars"]
    rejected_leg = next(leg for leg in diagnostics["legs"] if leg["symbol"] == "AAA")
    assert rejected_leg["allowed"] is False


def test_basket_risk_allocator_can_be_disabled_for_compatibility():
    cfg = AutonomousTradingConfig(
        basket_enabled=True,
        basket_risk_allocator_enabled=False,
        basket_max_size=2,
        basket_total_deployable_cash_pct=0.30,
        basket_single_position_deployable_cash_pct=0.10,
        max_risk_per_trade_equity_pct=0.10,
        max_basket_risk_equity_pct=0.001,
        basket_max_same_sector_positions=1,
    )
    planner = BasketPlanner(cfg)

    basket = planner.plan(
        [
            _ranked("AAA", "Tech", 100, price=100, support=30),
            _ranked("BBB", "Health", 99, price=100, support=95),
        ],
        deployable_cash=100_000.0,
        equity=100_000.0,
    )

    assert basket is not None
    assert [p.symbol for p in basket.trade_plans] == ["AAA", "BBB"]
    diagnostics = basket.to_dict()["risk_allocation"]
    assert diagnostics["enabled"] is False
