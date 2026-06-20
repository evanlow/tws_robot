from autonomous.autonomous_config import AutonomousTradingConfig
from autonomous.basket_planner import BasketPlanner
from autonomous.candidate_ranker import RankedCandidate
from autonomous.candidate_scanner import CandidateSignal


def _ranked(symbol, sector, score=100.0, price=100.0):
    return RankedCandidate(
        candidate=CandidateSignal(
            symbol=symbol,
            strength_score=100,
            signal_label="Confirmed Rebound",
            company_name=f"{symbol} Corp",
            sector=sector,
            last_price=price,
            support_price=95.0,
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
