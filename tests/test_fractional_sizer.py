from autonomous.fractional_sizer import FractionalEdgeSizer


def _edge(p_win=0.60, avg_win_r=1.5, avg_loss_r=1.0, confidence=0.5):
    return {
        "p_win": p_win,
        "avg_win_r": avg_win_r,
        "avg_loss_r": avg_loss_r,
        "confidence": confidence,
    }


def test_fractional_sizer_disabled_is_noop():
    decision = FractionalEdgeSizer(enabled=False).evaluate(
        equity=100_000,
        current_cap_value=10_000,
        edge_estimate=_edge(),
        observed_trades=200,
    )

    assert decision.enabled is False
    assert decision.applied is False


def test_fractional_sizer_requires_evidence_for_positive_cap():
    decision = FractionalEdgeSizer(enabled=True, min_trades=100).evaluate(
        equity=100_000,
        current_cap_value=10_000,
        edge_estimate=_edge(),
        observed_trades=20,
    )

    assert decision.enabled is True
    assert decision.applied is False
    assert any("insufficient evidence" in r for r in decision.reasons)


def test_fractional_sizer_applies_reducing_cap_when_evidence_sufficient():
    decision = FractionalEdgeSizer(
        enabled=True,
        min_trades=10,
        fraction=0.10,
        max_position_pct=0.01,
        retirement_mode_max_pct=0.005,
        allow_size_increase=False,
    ).evaluate(
        equity=100_000,
        current_cap_value=2_000,
        edge_estimate=_edge(p_win=0.70, avg_win_r=2.0, confidence=0.8),
        observed_trades=50,
    )

    assert decision.applied is True
    assert decision.cap_value is not None
    assert decision.cap_value < 2_000


def test_fractional_sizer_zeroes_non_positive_fraction_when_reduce_enabled():
    decision = FractionalEdgeSizer(enabled=True, can_reduce_size=True).evaluate(
        equity=100_000,
        current_cap_value=10_000,
        edge_estimate=_edge(p_win=0.30, avg_win_r=0.5),
        observed_trades=200,
    )

    assert decision.applied is True
    assert decision.cap_value == 0.0
