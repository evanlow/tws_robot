from autonomous.candidate_scanner import CandidateSignal
from autonomous.edge_estimator import RuleBasedEdgeEstimator
from autonomous.feature_builder import FeatureBuilder


def _candidate(**kwargs):
    data = {
        "symbol": "AAA",
        "strength_score": 100,
        "signal_label": "Confirmed Rebound",
        "sector": "Tech",
        "last_price": 100.0,
        "support_price": 95.0,
        "resistance_price": 112.0,
        "extras": {
            "quality_label": "Strong",
            "quality_score": 90,
            "momentum_label": "Confirmed Rebound",
            "momentum_confirmation": "confirmed_rebound",
            "bollinger_status": "near_lower_band",
            "rsi_14": 45,
            "rsi_status": "rsi_neutral",
            "adr_pct": 0.025,
            "levels_valid": True,
        },
    }
    data.update(kwargs)
    return CandidateSignal(**data)


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


def test_feature_builder_extracts_risk_reward_and_market_context():
    features = FeatureBuilder().build(_candidate(), market_gate=_market_gate())

    assert features["symbol"] == "AAA"
    assert features["quality_label"] == "Strong"
    assert features["momentum_label"] == "Confirmed Rebound"
    assert features["support_distance_pct"] == 0.05
    assert features["resistance_room_pct"] == 0.12
    assert features["risk_reward"] > 1.0
    assert features["spy_bullish"] is True
    assert features["vix_level_regime"] == "normal"


def test_rule_based_edge_estimator_returns_positive_edge_for_good_features():
    features = FeatureBuilder().build(_candidate(), market_gate=_market_gate())

    estimate = RuleBasedEdgeEstimator().estimate(features)

    assert estimate.p_win > 0.5
    assert estimate.expected_r > 0
    assert estimate.confidence > 0
    assert estimate.source == "rule_based_bootstrap"
    assert any("quality_label=Strong" in reason for reason in estimate.reasons)


def test_rule_based_edge_estimator_penalises_stress_features():
    weak = _candidate(
        support_price=70.0,
        resistance_price=104.0,
        extras={
            "quality_label": "Weak",
            "quality_score": 30,
            "momentum_label": "Confirmed Rebound",
            "rsi_14": 75,
            "adr_pct": 0.08,
        },
    )
    stressed_market = {
        "classification": "Bullish / Volatility Caution",
        "bullish": True,
        "vix": {"level_regime": "caution", "direction_regime": "rising_caution"},
    }
    features = FeatureBuilder().build(weak, market_gate=stressed_market)

    estimate = RuleBasedEdgeEstimator().estimate(features)

    assert estimate.p_win < 0.55
    assert any("VIX rising" in reason for reason in estimate.reasons)
