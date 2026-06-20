from autonomous.autonomous_config import AutonomousTradingConfig
from autonomous.candidate_ranker import CandidateRanker
from autonomous.candidate_scanner import CandidateSignal


def _candidate(symbol, support, resistance, quality=90):
    return CandidateSignal(
        symbol=symbol,
        strength_score=100,
        signal_label="Confirmed Rebound",
        sector="Tech",
        last_price=100.0,
        support_price=support,
        resistance_price=resistance,
        volume_ok=True,
        trend_ok=True,
        extras={
            "quality_label": "Strong",
            "quality_score": quality,
            "momentum_label": "Confirmed Rebound",
            "momentum_confirmation": "confirmed_rebound",
            "rsi_14": 45,
            "adr_pct": 0.02,
        },
    )


def _market_gate():
    return {
        "classification": "Bullish / Volatility Acceptable",
        "bullish": True,
        "size_multiplier": 1.0,
        "vix": {
            "available": True,
            "level_regime": "normal",
            "direction_regime": "falling",
        },
    }


def test_ranker_prefers_higher_expected_r_candidate():
    cfg = AutonomousTradingConfig(edge_ranking_enabled=True, edge_score_weight=10.0)
    ranker = CandidateRanker(cfg)
    high_rr = _candidate("AAA", support=95.0, resistance=120.0)
    low_rr = _candidate("BBB", support=80.0, resistance=104.0)

    ranked, rejected = ranker.rank_with_rejections(
        [low_rr, high_rr],
        positions={},
        equity=100_000.0,
        market_gate=_market_gate(),
    )

    assert not rejected
    assert [rc.candidate.symbol for rc in ranked] == ["AAA", "BBB"]
    assert ranked[0].edge_estimate is not None
    assert ranked[0].edge_estimate.expected_r > ranked[1].edge_estimate.expected_r
    assert "expected_r" in " ".join(ranked[0].reasons)


def test_ranker_can_reject_low_expected_r_when_threshold_set():
    cfg = AutonomousTradingConfig(
        edge_ranking_enabled=True,
        min_expected_r=0.5,
    )
    ranker = CandidateRanker(cfg)
    poor = _candidate("BBB", support=70.0, resistance=102.0, quality=40)
    poor.extras["quality_label"] = "Strong"  # hard filter passes; edge threshold rejects

    ranked, rejected = ranker.rank_with_rejections(
        [poor],
        positions={},
        equity=100_000.0,
        market_gate=_market_gate(),
    )

    assert ranked == []
    assert rejected[0]["symbol"] == "BBB"
    assert "expected_r" in rejected[0]["reason"]


def test_ranker_can_disable_edge_ranking():
    cfg = AutonomousTradingConfig(edge_ranking_enabled=False)
    ranker = CandidateRanker(cfg)
    a = _candidate("AAA", support=95.0, resistance=120.0)

    ranked, _ = ranker.rank_with_rejections([a], positions={}, equity=100_000.0)

    assert ranked[0].edge_estimate is None
    assert ranked[0].features == {}
