from autonomous.candidate_scanner import CandidateSignal
from autonomous.feature_builder import FeatureBuilder
from autonomous.regime_context import build_regime_context, classify_time_of_day, sector_etf_for


def test_sector_etf_mapping():
    assert sector_etf_for("Information Technology") == "XLK"
    assert sector_etf_for("Financials") == "XLF"


def test_time_of_day_regime_from_timestamp():
    assert classify_time_of_day("2026-01-02T13:45:00+00:00") == "opening_volatility"
    assert classify_time_of_day("2026-01-02T20:45:00+00:00") == "closing_volatility"


def test_build_regime_context_with_sector_strength():
    context = build_regime_context(
        sector="Information Technology",
        extras={"sector_etf_bullish": True, "sector_relative_strength_pct": 0.01},
    )

    assert context["sector_etf"] == "XLK"
    assert context["sector_regime"] == "sector_supportive"


def test_feature_builder_includes_regime_context():
    candidate = CandidateSignal(
        symbol="AAA",
        sector="Information Technology",
        signal_label="Confirmed Rebound",
        strength_score=100,
        last_price=100.0,
        support_price=95.0,
        resistance_price=110.0,
        extras={"sector_etf_bullish": True, "sector_relative_strength_pct": 0.01},
    )

    features = FeatureBuilder().build(candidate)

    assert features["sector_etf"] == "XLK"
    assert features["sector_regime"] == "sector_supportive"
    assert features["time_of_day_regime"] is not None
