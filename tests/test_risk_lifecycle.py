from datetime import datetime, timedelta, timezone

from autonomous.risk_lifecycle import LossLimitGuard, StrategyEquityCurveBuilder


def _outcome(r_value, days_ago=0, symbol="AAA"):
    ts = datetime(2026, 1, 10, tzinfo=timezone.utc) - timedelta(days=days_ago)
    return {
        "evidence_type": "autonomous_outcome",
        "timestamp": ts.isoformat(),
        "symbol": symbol,
        "outcome": {
            "realized": True,
            "realized_r_multiple": r_value,
            "realized_pnl": r_value * 100,
        },
    }


def test_strategy_equity_curve_accumulates_r_and_pnl():
    curve = StrategyEquityCurveBuilder().build([
        _outcome(1.0, days_ago=2, symbol="A"),
        _outcome(-0.5, days_ago=1, symbol="B"),
    ])

    assert len(curve) == 2
    assert curve[-1].cumulative_r == 0.5
    assert curve[-1].cumulative_pnl == 50.0


def test_loss_limit_guard_blocks_daily_breach():
    guard = LossLimitGuard(max_daily_loss_r=2.0)
    decision = guard.evaluate(
        [_outcome(-1.2), _outcome(-1.0)],
        now=datetime(2026, 1, 10, tzinfo=timezone.utc),
    )

    assert decision.allowed is False
    assert "daily" in decision.reason


def test_loss_limit_guard_blocks_consecutive_losses():
    guard = LossLimitGuard(max_consecutive_losses=2)
    decision = guard.evaluate(
        [_outcome(1.0, days_ago=3), _outcome(-0.5, days_ago=1), _outcome(-0.5)],
        now=datetime(2026, 1, 10, tzinfo=timezone.utc),
    )

    assert decision.allowed is False
    assert "consecutive" in decision.reason


def test_loss_limit_guard_allows_when_limits_clear():
    guard = LossLimitGuard(max_daily_loss_r=2.0, max_consecutive_losses=3)
    decision = guard.evaluate(
        [_outcome(1.0, days_ago=1), _outcome(-0.2)],
        now=datetime(2026, 1, 10, tzinfo=timezone.utc),
    )

    assert decision.allowed is True
    assert decision.reason == "risk lifecycle limits clear"


def test_loss_limit_guard_accepts_generator_without_double_consume():
    """evaluate() must materialise records before iterating so a generator works."""
    guard = LossLimitGuard(max_daily_loss_r=2.0)
    records = (_outcome(r) for r in [-1.0, -1.5])  # generator, can only be consumed once
    decision = guard.evaluate(records, now=datetime(2026, 1, 10, tzinfo=timezone.utc))

    # The equity curve must have been built from the same data; if records were
    # consumed twice the curve would be empty and the drawdown would be 0.
    assert decision.allowed is False
    assert len(decision.equity_curve) == 2


def test_loss_limit_guard_zero_daily_limit_does_not_block():
    """max_daily_loss_r=0 should disable the daily check, not block everything."""
    guard = LossLimitGuard(max_daily_loss_r=0, max_weekly_loss_r=0, max_monthly_loss_r=0)
    decision = guard.evaluate(
        [_outcome(-5.0)],
        now=datetime(2026, 1, 10, tzinfo=timezone.utc),
    )

    assert decision.allowed is True


def test_loss_limit_guard_zero_weekly_limit_does_not_block():
    guard = LossLimitGuard(max_daily_loss_r=0, max_weekly_loss_r=0, max_monthly_loss_r=0)
    decision = guard.evaluate(
        [_outcome(-3.0, days_ago=3)],
        now=datetime(2026, 1, 10, tzinfo=timezone.utc),
    )

    assert decision.allowed is True
