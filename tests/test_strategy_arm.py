from autonomous.strategy_arm import StrategyArmLearner


def _record(r, quality="Strong", momentum="Confirmed Rebound", market="Bullish", vix="normal"):
    return {
        "strategy_bucket": {
            "signal_label": "Confirmed Rebound",
            "quality_label": quality,
            "momentum_label": momentum,
            "market_classification": market,
            "vix_level_regime": vix,
        },
        "outcome": {
            "realized": True,
            "realized_r_multiple": r,
        },
    }


def test_strategy_arm_learner_groups_realized_records():
    learner = StrategyArmLearner()
    records = [_record(1.0), _record(-0.5), _record(2.0, quality="Weak")]

    stats = learner.build_stats(records)

    assert len(stats) == 2
    strong_arm = [arm for arm in stats.values() if "Strong" in arm.arm_id][0]
    assert strong_arm.trades == 2
    assert strong_arm.wins == 1
    assert strong_arm.avg_r == 0.25


def test_strategy_arm_learner_ignores_unrealized_records():
    learner = StrategyArmLearner()
    records = [
        _record(1.0),
        {"strategy_bucket": {}, "outcome": {"realized": False, "realized_r_multiple": 5.0}},
    ]

    stats = learner.build_stats(records)

    assert sum(arm.trades for arm in stats.values()) == 1


def test_strategy_arm_learner_ranks_by_ucb_score():
    learner = StrategyArmLearner(exploration=0.5)
    records = [
        _record(1.0, quality="Strong"),
        _record(1.0, quality="Strong"),
        _record(0.2, quality="Weak"),
    ]

    ranked = learner.rank_arms(records)

    assert ranked[0]["avg_r"] >= ranked[1]["avg_r"]
    assert "ucb_score" in ranked[0]
