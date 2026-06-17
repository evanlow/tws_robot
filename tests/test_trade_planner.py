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


# ---------------------------------------------------------------------------
# Quantitative rejection diagnostics (reasons accumulator)
# ---------------------------------------------------------------------------


def test_reasons_accumulator_explains_cap_below_share_price():
    """When sizing cap < share price the planner records the exact numbers."""
    cfg = AutonomousTradingConfig(max_new_position_pct=0.10)
    reasons: list[str] = []
    plan = TradePlanner(cfg).plan(
        _candidate(symbol="NVDA", last_price=500.0),
        deployable_cash=2_674.25,
        equity=10_000.0,
        reasons=reasons,
    )
    assert plan is None
    assert any("NVDA" in r and "cap" in r and "share price" in r for r in reasons), reasons
    # The numeric figures themselves should be present.
    joined = " ".join(reasons)
    assert "267.43" in joined or "267.42" in joined  # 2674.25 * 0.10
    assert "500.00" in joined


def test_reasons_accumulator_empty_when_plan_succeeds():
    cfg = AutonomousTradingConfig(max_new_position_pct=0.10)
    reasons: list[str] = []
    plan = TradePlanner(cfg).plan(
        _candidate(last_price=50.0),
        deployable_cash=10_000.0,
        equity=100_000.0,
        reasons=reasons,
    )
    assert plan is not None
    assert reasons == []


def test_reasons_accumulator_records_share_buy_disabled():
    cfg = AutonomousTradingConfig(
        allow_share_buy=False,
        allow_short_put=True,
        prefer_cash_secured_put=True,
    )
    reasons: list[str] = []
    assert TradePlanner(cfg).plan(
        _candidate(), 100_000.0, 100_000.0, reasons=reasons
    ) is None
    assert any("allow_share_buy=False" in r for r in reasons), reasons


def test_reasons_accumulator_records_short_put_strike_above_support():
    cfg = AutonomousTradingConfig(prefer_cash_secured_put=True, allow_short_put=True)
    hint = OptionChainHint(
        strike=100.0, expiry=date(2026, 12, 18),
        bid=1.0, ask=1.2, contracts_available=2,
    )
    reasons: list[str] = []
    # share_buy still allowed → should fall back to BUY_SHARES, but the
    # short-put rejection reason must be recorded along the way.
    plan = TradePlanner(cfg).plan(
        _candidate(last_price=100.0, support_price=95.0),
        deployable_cash=100_000.0,
        equity=100_000.0,
        option_hint=hint,
        reasons=reasons,
    )
    assert plan.trade_type == TradeType.BUY_SHARES
    assert any("support" in r and "strike" in r for r in reasons), reasons


# ---------------------------------------------------------------------------
# Split caps: independent deployable-cash and equity fractions
# ---------------------------------------------------------------------------


def test_split_caps_loose_deployable_lets_high_priced_share_through():
    """With a tight equity cap (10%) but loose deployable-cash cap (50%),
    a high-priced share that the old single-pct rule would have blocked
    should now be fundable from a small deployable-cash balance."""
    cfg = AutonomousTradingConfig(
        max_position_deployable_cash_pct=0.50,
        max_position_equity_pct=0.10,
    )
    # Old behavior (both at 10%): cap = min(0.1*2674, 0.1*8531) = 267 < 454 → None.
    # New behavior: cap = min(0.5*2674, 0.1*8531) = min(1337, 853) = 853 ≥ 454 → 1 share.
    plan = TradePlanner(cfg).plan(
        _candidate(symbol="CIEN", last_price=454.11),
        deployable_cash=2_674.0,
        equity=8_531.0,
    )
    assert plan is not None
    assert plan.trade_type == TradeType.BUY_SHARES
    assert plan.quantity == 1


def test_split_caps_equity_side_still_binds():
    """A loose deployable cap must not bypass the equity guard."""
    cfg = AutonomousTradingConfig(
        max_position_deployable_cash_pct=0.99,
        max_position_equity_pct=0.05,
    )
    # 5% of $10k equity = $500 cap → at $100/share = 5 shares regardless of
    # the $9,900 deployable-side allowance.
    plan = TradePlanner(cfg).plan(
        _candidate(last_price=100.0),
        deployable_cash=10_000.0,
        equity=10_000.0,
    )
    assert plan is not None
    assert plan.quantity == 5


def test_split_caps_fall_back_to_max_new_position_pct():
    """Unset split caps preserve the legacy single-percentage behavior."""
    cfg = AutonomousTradingConfig(max_new_position_pct=0.20)
    assert cfg.deployable_cash_cap_pct() == 0.20
    assert cfg.equity_cap_pct() == 0.20


def test_split_caps_reject_reason_shows_both_pcts():
    """When the cap blocks the trade the reason string must show the
    actual percentages used on each side (not a single value)."""
    cfg = AutonomousTradingConfig(
        max_position_deployable_cash_pct=0.10,
        max_position_equity_pct=0.05,
    )
    reasons: list[str] = []
    plan = TradePlanner(cfg).plan(
        _candidate(symbol="ZZZ", last_price=1_000.0),
        deployable_cash=2_000.0,
        equity=10_000.0,
        reasons=reasons,
    )
    assert plan is None
    joined = " ".join(reasons)
    assert "10%" in joined  # deployable side
    assert "5%" in joined   # equity side


def test_split_caps_invalid_value_rejected():
    import pytest
    with pytest.raises(ValueError):
        AutonomousTradingConfig(max_position_deployable_cash_pct=0.0)
    with pytest.raises(ValueError):
        AutonomousTradingConfig(max_position_equity_pct=1.5)
