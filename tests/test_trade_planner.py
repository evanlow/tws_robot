"""Tests for autonomous.trade_planner."""

from datetime import date

from autonomous.autonomous_config import AutonomousTradingConfig
from autonomous.candidate_scanner import CandidateSignal
from autonomous.trade_planner import OptionChainHint, TradePlanner, TradeType


def _candidate(**kw):
    return CandidateSignal(
        symbol=kw.pop("symbol", "AAA"),
        strength_score=kw.pop("strength_score", 100),
        signal_label=kw.pop("signal_label", "Confirmed Rebound"),
        last_price=kw.pop("last_price", 100.0),
        support_price=kw.pop("support_price", 95.0),
        resistance_price=kw.pop("resistance_price", 110.0),
        **kw,
    )


def test_buy_shares_respects_max_position_pct():
    # 10% cap on $100k equity = $10k → at $100/share that is 100 shares max,
    # even though deployable cash could fund many more.
    cfg = AutonomousTradingConfig(max_new_position_pct=0.10)
    plan = TradePlanner(cfg).plan(
        _candidate(last_price=100.0),
        deployable_cash=1_000_000.0,
        equity=100_000.0,
    )
    assert plan is not None
    assert plan.trade_type == TradeType.BUY_SHARES
    assert plan.quantity == 100
    assert plan.required_cash == 100 * 100.0
    assert plan.limit_price == 100.0


def test_buy_shares_uses_limit_order_only():
    cfg = AutonomousTradingConfig()
    plan = TradePlanner(cfg).plan(
        _candidate(last_price=50.0),
        deployable_cash=10_000.0,
        equity=100_000.0,
    )
    # Limit price set; risk_notes mentions limit-only.
    assert plan.limit_price == 50.0
    assert any("Limit order" in n for n in plan.risk_notes)


def test_buy_shares_none_when_cap_below_one_share():
    cfg = AutonomousTradingConfig(max_new_position_pct=0.10)
    # 10% of $500 equity = $50 cap, but stock costs $100 → no plan.
    plan = TradePlanner(cfg).plan(
        _candidate(last_price=100.0),
        deployable_cash=10_000.0,
        equity=500.0,
    )
    assert plan is None


def test_short_put_reserves_strike_times_100_times_contracts():
    cfg = AutonomousTradingConfig(prefer_cash_secured_put=True, allow_short_put=True)
    hint = OptionChainHint(
        strike=90.0,
        expiry=date(2026, 12, 18),
        bid=1.10,
        ask=1.30,
        contracts_available=5,
    )
    # Support at 95 ⇒ strike 90 is at-or-below support ⇒ allowed.
    plan = TradePlanner(cfg).plan(
        _candidate(last_price=100.0, support_price=95.0),
        deployable_cash=500_000.0,
        equity=1_000_000.0,
        option_hint=hint,
    )
    assert plan is not None
    assert plan.trade_type == TradeType.SELL_CASH_SECURED_PUT
    # Lower of 10% deployable cash and 10% equity leaves room for 5 contracts.
    assert plan.contracts == 5
    assert plan.required_cash == 90.0 * 100 * 5
    assert plan.strike == 90.0
    assert plan.limit_price == round((1.10 + 1.30) / 2, 2)
    assert plan.action == "SELL"


def test_short_put_falls_back_to_shares_when_strike_above_support():
    cfg = AutonomousTradingConfig()
    hint = OptionChainHint(
        strike=100.0,
        expiry=date(2026, 12, 18),
        bid=1.0, ask=1.2,
        contracts_available=2,
    )
    plan = TradePlanner(cfg).plan(
        _candidate(last_price=100.0, support_price=95.0),
        deployable_cash=10_000.0,
        equity=100_000.0,
        option_hint=hint,
    )
    assert plan.trade_type == TradeType.BUY_SHARES


def test_short_put_skipped_when_no_contracts_available():
    cfg = AutonomousTradingConfig()
    hint = OptionChainHint(
        strike=90.0, expiry=date(2026, 12, 18),
        bid=1, ask=1.2, contracts_available=0,
    )
    plan = TradePlanner(cfg).plan(
        _candidate(),
        deployable_cash=50_000.0,
        equity=100_000.0,
        option_hint=hint,
    )
    assert plan.trade_type == TradeType.BUY_SHARES


def test_planner_returns_none_when_share_buy_disabled_and_no_option():
    cfg = AutonomousTradingConfig(
        allow_share_buy=False,
        allow_short_put=True,
        prefer_cash_secured_put=True,
    )
    assert TradePlanner(cfg).plan(_candidate(), 100_000.0, 100_000.0) is None
