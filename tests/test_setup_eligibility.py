from autonomous.autonomous_config import AutonomousMode, AutonomousTradingConfig
from autonomous.candidate_ranker import CandidateRanker
from autonomous.candidate_scanner import CandidateSignal
from autonomous.evidence_calibrator import (
    SETUP_STATE_ACCEPTABLE,
    SETUP_STATE_INSUFFICIENT_EVIDENCE,
    SETUP_STATE_LIVE_ELIGIBLE,
    SETUP_STATE_PAPER_ONLY,
    SETUP_STATE_RETIRED,
    SetupEvidenceSummary,
)
from autonomous.performance_metrics import calculate_performance_metrics
from autonomous.setup_eligibility import (
    SETUP_ELIGIBILITY_ALLOW,
    SETUP_ELIGIBILITY_PAPER_ONLY,
    SETUP_ELIGIBILITY_REJECT,
    SetupEligibilityGate,
)
from autonomous.setup_registry import SetupMetadata, SetupRegistry


def _candidate(symbol="AAA"):
    return CandidateSignal(
        symbol=symbol,
        strength_score=100,
        signal_label="Confirmed Rebound",
        sector="Tech",
        last_price=100.0,
        support_price=95.0,
        resistance_price=125.0,
        volume_ok=True,
        trend_ok=True,
        extras={
            "quality_label": "Strong",
            "quality_score": 92,
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


def _summary(
    *,
    state,
    sample_size=40,
    expected_r=0.20,
    confidence=0.65,
):
    metadata = SetupRegistry().metadata_for_record(
        {
            "symbol": "AAA",
            "strategy_bucket": {
                "signal_label": "Confirmed Rebound",
                "quality_label": "Strong",
                "momentum_label": "Confirmed Rebound",
                "market_classification": "Bullish / Volatility Acceptable",
                "vix_level_regime": "normal",
                "vix_direction_regime": "falling",
                "sector": "Tech",
            },
            "selected": {
                "features": {
                    "sector_regime": "sector_supportive",
                    "time_of_day_regime": "regular_session",
                    "support_distance_pct": 0.02,
                    "resistance_room_pct": 0.25,
                    "adr_pct": 0.02,
                }
            },
            "trade_plan": {"symbol": "AAA", "trade_type": "BUY_SHARES"},
        }
    )
    assert isinstance(metadata, SetupMetadata)
    return SetupEvidenceSummary(
        setup_id=metadata.setup_id,
        state=state,
        sample_size=sample_size,
        confidence=confidence,
        evidence_weight=0.70,
        prior_weight=0.30,
        posterior_win_rate=0.58,
        posterior_avg_win_r=1.10,
        posterior_avg_loss_r=-1.00,
        posterior_expected_r=expected_r,
        metrics=calculate_performance_metrics([]),
        setup_metadata=metadata,
        reasons=[f"state={state}"],
    )


def test_setup_eligibility_rejects_retired_setups():
    decision = SetupEligibilityGate().evaluate(
        mode=AutonomousMode.RECOMMEND_ONLY,
        setup_evidence=_summary(state=SETUP_STATE_RETIRED, expected_r=0.30),
    )

    assert decision.eligible is False
    assert decision.action == SETUP_ELIGIBILITY_REJECT
    assert "RETIRED" in decision.reason


def test_setup_eligibility_rejects_sufficient_non_positive_expected_r():
    decision = SetupEligibilityGate().evaluate(
        mode=AutonomousMode.PAPER_EXECUTE,
        setup_evidence=_summary(
            state=SETUP_STATE_ACCEPTABLE,
            sample_size=40,
            expected_r=0.0,
        ),
    )

    assert decision.eligible is False
    assert decision.action == SETUP_ELIGIBILITY_REJECT
    assert "expected_r" in decision.reason


def test_setup_eligibility_allows_paper_only_in_paper_mode_but_blocks_live():
    gate = SetupEligibilityGate()
    summary = _summary(state=SETUP_STATE_PAPER_ONLY, expected_r=0.04)

    paper_decision = gate.evaluate(
        mode=AutonomousMode.PAPER_EXECUTE,
        setup_evidence=summary,
    )
    live_decision = gate.evaluate(
        mode=AutonomousMode.ASSISTED_LIVE,
        setup_evidence=summary,
    )

    assert paper_decision.eligible is True
    assert paper_decision.action == SETUP_ELIGIBILITY_PAPER_ONLY
    assert AutonomousMode.ASSISTED_LIVE.value not in paper_decision.allowed_modes
    assert live_decision.eligible is False
    assert live_decision.action == SETUP_ELIGIBILITY_REJECT


def test_setup_eligibility_blocks_insufficient_evidence_in_assisted_live():
    decision = SetupEligibilityGate().evaluate(
        mode=AutonomousMode.ASSISTED_LIVE,
        setup_evidence=_summary(
            state=SETUP_STATE_INSUFFICIENT_EVIDENCE,
            sample_size=5,
            expected_r=0.15,
        ),
    )

    assert decision.eligible is False
    assert decision.action == SETUP_ELIGIBILITY_REJECT
    assert "insufficient setup evidence" in decision.reason
    assert decision.allowed_modes == [
        AutonomousMode.RECOMMEND_ONLY.value,
        AutonomousMode.PAPER_EXECUTE.value,
    ]


def test_setup_eligibility_allows_live_eligible_evidence():
    decision = SetupEligibilityGate().evaluate(
        mode=AutonomousMode.ASSISTED_LIVE,
        setup_evidence=_summary(
            state=SETUP_STATE_LIVE_ELIGIBLE,
            sample_size=120,
            expected_r=0.35,
        ),
    )

    assert decision.eligible is True
    assert decision.action == SETUP_ELIGIBILITY_ALLOW
    assert AutonomousMode.ASSISTED_LIVE.value in decision.allowed_modes


def test_ranker_rejects_candidate_when_setup_evidence_is_retired():
    candidate = _candidate()
    summary = _summary(state=SETUP_STATE_RETIRED, sample_size=45, expected_r=-0.20)
    ranker = CandidateRanker(
        AutonomousTradingConfig(edge_ranking_enabled=True),
        setup_evidence_provider=lambda _candidate, _features, _edge: summary,
    )

    ranked, rejected = ranker.rank_with_rejections(
        [candidate],
        positions={},
        equity=100_000.0,
        market_gate=_market_gate(),
    )

    assert ranked == []
    assert rejected[0]["symbol"] == candidate.symbol
    assert "setup_eligibility REJECT" in rejected[0]["reason"]
    assert candidate.extras["setup_eligibility"]["setup_state"] == SETUP_STATE_RETIRED
    assert candidate.extras["edge_observed_trades"] == 45


def test_ranker_records_paper_only_diagnostics_without_rejecting_recommend_mode():
    candidate = _candidate()
    summary = _summary(
        state=SETUP_STATE_INSUFFICIENT_EVIDENCE,
        sample_size=8,
        expected_r=0.10,
    )
    ranker = CandidateRanker(
        AutonomousTradingConfig(
            mode=AutonomousMode.RECOMMEND_ONLY,
            edge_ranking_enabled=True,
        ),
        setup_evidence_provider=lambda _candidate, _features, _edge: summary,
    )

    ranked, rejected = ranker.rank_with_rejections(
        [candidate],
        positions={},
        equity=100_000.0,
        market_gate=_market_gate(),
    )

    assert rejected == []
    assert len(ranked) == 1
    assert candidate.extras["setup_eligibility"]["action"] == SETUP_ELIGIBILITY_PAPER_ONLY
    assert candidate.extras["setup_eligibility"]["eligible"] is True
    assert "setup_eligibility=PAPER_ONLY" in " ".join(ranked[0].reasons)


def test_ranker_fails_closed_when_explicit_evidence_provider_errors():
    candidate = _candidate()

    def _broken_provider(_candidate, _features, _edge):
        raise RuntimeError("provider unavailable")

    ranker = CandidateRanker(
        AutonomousTradingConfig(edge_ranking_enabled=True),
        setup_evidence_provider=_broken_provider,
    )

    ranked, rejected = ranker.rank_with_rejections(
        [candidate],
        positions={},
        equity=100_000.0,
        market_gate=_market_gate(),
    )

    assert ranked == []
    assert rejected[0]["symbol"] == candidate.symbol
    assert rejected[0]["reason"] == "setup eligibility evidence provider failed"
