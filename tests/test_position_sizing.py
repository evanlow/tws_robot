from autonomous.position_sizing import PositionSizer


def test_risk_per_trade_cap_reduces_quantity():
    sizer = PositionSizer(
        risk_per_trade_sizing_enabled=True,
        max_risk_per_trade_equity_pct=0.001,  # $100 on $100k equity
        volatility_sizing_enabled=False,
    )

    decision = sizer.size_buy_shares(
        symbol="AAA",
        entry_price=100.0,
        stop_price=95.0,
        base_cap_value=10_000.0,
        equity=100_000.0,
    )

    assert decision.quantity == 20
    assert decision.required_cash == 2_000.0
    assert decision.binding_cap == "risk_per_trade_cap"
    assert decision.caps["risk_per_share"] == 5.0
    assert decision.caps["max_risk_dollars"] == 100.0


def test_volatility_cap_reduces_quantity_when_adr_high():
    sizer = PositionSizer(
        risk_per_trade_sizing_enabled=False,
        volatility_sizing_enabled=True,
        volatility_reference_pct=0.02,
        volatility_min_size_multiplier=0.25,
    )

    decision = sizer.size_buy_shares(
        symbol="AAA",
        entry_price=100.0,
        stop_price=None,
        base_cap_value=10_000.0,
        equity=100_000.0,
        adr_pct=0.04,
    )

    assert decision.quantity == 50
    assert decision.required_cash == 5_000.0
    assert decision.binding_cap == "volatility_cap"
    assert decision.caps["volatility_multiplier"] == 0.5


def test_sizer_skips_risk_when_stop_missing():
    sizer = PositionSizer(
        risk_per_trade_sizing_enabled=True,
        volatility_sizing_enabled=False,
    )

    decision = sizer.size_buy_shares(
        symbol="AAA",
        entry_price=100.0,
        stop_price=None,
        base_cap_value=1_000.0,
        equity=100_000.0,
    )

    assert decision.quantity == 10
    assert decision.binding_cap == "cash_equity_cap"
    assert decision.caps["risk_per_trade_skipped"] is True


def test_sizer_skips_risk_when_equity_unavailable():
    sizer = PositionSizer(
        risk_per_trade_sizing_enabled=True,
        volatility_sizing_enabled=False,
    )

    decision = sizer.size_buy_shares(
        symbol="AAA",
        entry_price=100.0,
        stop_price=95.0,
        base_cap_value=1_000.0,
        equity=0.0,
    )

    assert decision.quantity == 10
    assert decision.binding_cap == "cash_equity_cap"
    assert decision.caps["risk_per_trade_skipped"] is True
    assert "equity unavailable" in decision.notes[0]
