from autonomous.position_sizing import PositionSizer


def _edge(p_win=0.70, avg_win_r=2.0, avg_loss_r=1.0, confidence=0.8):
    return {
        "p_win": p_win,
        "avg_win_r": avg_win_r,
        "avg_loss_r": avg_loss_r,
        "confidence": confidence,
    }


def test_position_sizer_applies_drawdown_cap():
    sizer = PositionSizer(
        risk_per_trade_sizing_enabled=False,
        volatility_sizing_enabled=False,
        drawdown_governor_enabled=True,
        strategy_drawdown_pct=0.05,
    )

    decision = sizer.size_buy_shares(
        symbol="AAA",
        entry_price=100.0,
        stop_price=95.0,
        base_cap_value=10_000.0,
        equity=100_000.0,
    )

    assert decision.quantity == 50
    assert decision.binding_cap == "drawdown_cap"
    assert decision.caps["drawdown_governor"]["multiplier"] == 0.5


def test_position_sizer_halts_on_severe_drawdown():
    sizer = PositionSizer(
        risk_per_trade_sizing_enabled=False,
        volatility_sizing_enabled=False,
        drawdown_governor_enabled=True,
        strategy_drawdown_pct=0.09,
    )

    decision = sizer.size_buy_shares(
        symbol="AAA",
        entry_price=100.0,
        stop_price=95.0,
        base_cap_value=10_000.0,
        equity=100_000.0,
    )

    assert decision.quantity == 0
    assert decision.binding_cap == "drawdown_cap"
    assert decision.caps["drawdown_governor"]["halted"] is True


def test_position_sizer_applies_fractional_edge_cap_when_enabled_and_evidence_sufficient():
    sizer = PositionSizer(
        risk_per_trade_sizing_enabled=False,
        volatility_sizing_enabled=False,
        fractional_edge_sizing_enabled=True,
        fractional_edge_min_trades=10,
        fractional_edge_fraction=0.10,
        fractional_edge_allow_size_increase=False,
        drawdown_governor_enabled=False,
    )

    decision = sizer.size_buy_shares(
        symbol="AAA",
        entry_price=100.0,
        stop_price=95.0,
        base_cap_value=2_000.0,
        equity=100_000.0,
        edge_estimate=_edge(),
        observed_edge_trades=50,
    )

    assert decision.binding_cap == "fractional_edge_cap"
    assert decision.caps["fractional_edge"]["applied"] is True
    assert decision.quantity < 20


def test_position_sizer_fractional_edge_noop_when_insufficient_evidence():
    sizer = PositionSizer(
        risk_per_trade_sizing_enabled=False,
        volatility_sizing_enabled=False,
        fractional_edge_sizing_enabled=True,
        fractional_edge_min_trades=100,
        drawdown_governor_enabled=False,
    )

    decision = sizer.size_buy_shares(
        symbol="AAA",
        entry_price=100.0,
        stop_price=95.0,
        base_cap_value=2_000.0,
        equity=100_000.0,
        edge_estimate=_edge(),
        observed_edge_trades=10,
    )

    assert decision.binding_cap == "cash_equity_cap"
    assert decision.quantity == 20
    assert decision.caps["fractional_edge"]["applied"] is False
