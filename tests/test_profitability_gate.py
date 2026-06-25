"""Unit tests for the commission-aware profitability gate."""

import pytest

from autonomous.profitability_gate import ProfitabilityGate


def _gate(**kw):
    params = {
        "enabled": True,
        "estimated_commission_per_order": 1.09,
        "min_net_profit_usd": 0.0,
        "min_net_profit_pct_of_trade": 0.0,
    }
    params.update(kw)
    return ProfitabilityGate(**params)


def test_disabled_gate_allows_everything():
    gate = ProfitabilityGate(enabled=False, estimated_commission_per_order=1000.0)
    decision = gate.evaluate_buy_shares(
        symbol="KR", quantity=1, entry_price=58.08, target_price=58.73
    )
    assert decision.allowed is True
    assert "disabled" in decision.reason


def test_kr_two_shares_is_uneconomic_after_commission():
    """The KR-style example from the issue: 2 shares, +0.65/share gross, but
    ~2.18 USD round-trip commission leaves a net loss."""

    gate = _gate()
    decision = gate.evaluate_buy_shares(
        symbol="KR", quantity=2, entry_price=58.08, target_price=58.73
    )

    assert decision.allowed is False
    assert decision.gross_profit == pytest.approx(0.65 * 2)
    assert decision.round_trip_commission == pytest.approx(2 * 1.09)
    # Gross 1.30 - commission 2.18 = -0.88 net.
    assert decision.net_profit == pytest.approx(1.30 - 2.18)
    # 4 shares is the smallest size that clears commissions at this target.
    assert decision.min_quantity_for_profit == 4
    assert "below minimum" in decision.reason


def test_larger_quantity_same_move_is_economical():
    """Same +0.65/share move becomes economical at a larger size."""

    gate = _gate()
    decision = gate.evaluate_buy_shares(
        symbol="KR", quantity=100, entry_price=58.08, target_price=58.73
    )

    assert decision.allowed is True
    assert decision.net_profit == pytest.approx(0.65 * 100 - 2.18)
    assert "clears minimum" in decision.reason


def test_min_quantity_boundary_clears_commission():
    gate = _gate()
    # 4 shares: gross 2.60 - 2.18 = 0.42 net > 0.
    decision = gate.evaluate_buy_shares(
        symbol="KR", quantity=4, entry_price=58.08, target_price=58.73
    )
    assert decision.allowed is True
    assert decision.net_profit > 0


def test_missing_target_is_rejected_fail_closed():
    gate = _gate()
    decision = gate.evaluate_buy_shares(
        symbol="KR", quantity=100, entry_price=58.08, target_price=None
    )
    assert decision.allowed is False
    assert "no positive expected gross profit" in decision.reason


def test_target_below_entry_is_rejected():
    gate = _gate()
    decision = gate.evaluate_buy_shares(
        symbol="KR", quantity=100, entry_price=58.08, target_price=57.0
    )
    assert decision.allowed is False


def test_min_net_profit_usd_threshold_enforced():
    gate = _gate(min_net_profit_usd=50.0)
    # 100 shares nets ~62.82 which clears a 50 USD floor.
    ok = gate.evaluate_buy_shares(
        symbol="KR", quantity=100, entry_price=58.08, target_price=58.73
    )
    assert ok.allowed is True
    # 50 shares nets ~30.32 which does not clear the 50 USD floor.
    rejected = gate.evaluate_buy_shares(
        symbol="KR", quantity=50, entry_price=58.08, target_price=58.73
    )
    assert rejected.allowed is False
    assert rejected.required_net_profit == 50.0


def test_min_net_profit_pct_of_trade_threshold_enforced():
    # Require net profit >= 1% of traded notional.
    gate = _gate(min_net_profit_pct_of_trade=0.01)
    # 100 shares: trade value 5808, 1% = 58.08; net 62.82 clears it.
    ok = gate.evaluate_buy_shares(
        symbol="KR", quantity=100, entry_price=58.08, target_price=58.73
    )
    assert ok.allowed is True
    # 80 shares: trade value 4646.4, 1% = 46.46; net = 0.65*80 - 2.18 = 49.82
    # still clears; 70 shares: net = 45.5 - 2.18 = 43.32 < 1% (40.66?) check.
    rejected = gate.evaluate_buy_shares(
        symbol="KR", quantity=10, entry_price=58.08, target_price=58.73
    )
    assert rejected.allowed is False


def test_zero_quantity_is_skipped():
    gate = _gate()
    decision = gate.evaluate_buy_shares(
        symbol="KR", quantity=0, entry_price=58.08, target_price=58.73
    )
    assert decision.allowed is True
    assert "skipped" in decision.reason


def test_to_dict_is_json_friendly():
    gate = _gate()
    decision = gate.evaluate_buy_shares(
        symbol="KR", quantity=2, entry_price=58.08, target_price=58.73
    )
    payload = decision.to_dict()
    assert payload["allowed"] is False
    assert payload["net_profit"] == round(-0.88, 4)
    assert payload["min_quantity_for_profit"] == 4
    # Net profit is consistently derived from gross profit and commissions.
    assert payload["net_profit"] == pytest.approx(
        payload["gross_profit"] - payload["round_trip_commission"]
    )
    assert payload["round_trip_commission"] == pytest.approx(
        payload["entry_commission"] + payload["exit_commission"]
    )
    assert set(payload).issuperset(
        {
            "gross_profit",
            "entry_commission",
            "exit_commission",
            "round_trip_commission",
            "required_net_profit",
        }
    )
