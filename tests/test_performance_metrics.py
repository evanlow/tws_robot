from datetime import datetime, timedelta, timezone

import pytest

from autonomous.performance_metrics import (
    PerformanceMetricsCalculator,
    calculate_performance_metrics,
)


BASE = datetime(2026, 6, 22, 12, 0, tzinfo=timezone.utc)


def _record(
    r_value,
    *,
    index=0,
    symbol="AAA",
    realized=True,
    slippage_pct=None,
    commission=0.0,
    partial=False,
):
    return {
        "schema_version": 3,
        "evidence_type": "autonomous_outcome",
        "timestamp": (BASE + timedelta(minutes=index)).isoformat(),
        "symbol": symbol,
        "outcome": {
            "realized": realized,
            "realized_r_multiple": r_value,
            "realized_pnl": r_value * 100 if isinstance(r_value, (int, float)) else None,
            "entry_slippage_pct": slippage_pct,
            "commission": commission,
            "partial_fill": partial,
        },
    }


def test_performance_metrics_calculates_core_trade_statistics():
    records = [
        _record(1.0, index=0),
        _record(0.5, index=1),
        _record(-0.5, index=2),
        _record(0.0, index=3),
        _record(2.0, index=4),
    ]

    metrics = calculate_performance_metrics(records)

    assert metrics.trade_count == 5
    assert metrics.win_count == 3
    assert metrics.loss_count == 1
    assert metrics.breakeven_count == 1
    assert metrics.win_rate == pytest.approx(0.6)
    assert metrics.total_r == pytest.approx(3.0)
    assert metrics.avg_r == pytest.approx(0.6)
    assert metrics.expected_r == pytest.approx(0.6)
    assert metrics.median_r == pytest.approx(0.5)
    assert metrics.avg_win_r == pytest.approx((1.0 + 0.5 + 2.0) / 3)
    assert metrics.avg_loss_r == pytest.approx(-0.5)
    assert metrics.profit_factor == pytest.approx(7.0)


def test_performance_metrics_calculates_risk_adjusted_metrics():
    records = [
        _record(2.0, index=0),
        _record(-1.0, index=1),
        _record(-1.0, index=2),
        _record(1.0, index=3),
        _record(-0.5, index=4),
    ]

    metrics = PerformanceMetricsCalculator(rolling_window=3).calculate(records)

    assert metrics.max_drawdown_r == pytest.approx(2.0)
    assert metrics.consecutive_losses == 1
    assert metrics.volatility_r is not None
    assert metrics.downside_deviation is not None
    assert metrics.sharpe is not None
    assert metrics.rolling_sharpe is not None
    assert metrics.sortino is not None


def test_performance_metrics_tracks_execution_quality_fields():
    records = [
        _record(1.0, index=0, slippage_pct=0.0005, commission=1.25),
        _record(-0.5, index=1, slippage_pct=-0.0010, commission=0.75, partial=True),
        _record(0.5, index=2, slippage_pct=None, commission=1.00),
    ]

    metrics = calculate_performance_metrics(records)

    assert metrics.avg_slippage_bps == pytest.approx(7.5)
    assert metrics.max_slippage_bps == pytest.approx(10.0)
    assert metrics.total_commission == pytest.approx(3.0)
    assert metrics.avg_commission == pytest.approx(1.0)
    assert metrics.partial_fill_rate == pytest.approx(1 / 3)


def test_performance_metrics_ignores_unrealized_and_nonfinite_records():
    records = [
        _record(1.0, index=0),
        _record(5.0, index=1, realized=False),
        _record(float("nan"), index=2),
        _record(float("inf"), index=3),
        _record("not-a-number", index=4),
    ]

    metrics = calculate_performance_metrics(records)

    assert metrics.trade_count == 1
    assert metrics.total_r == pytest.approx(1.0)


def test_performance_metrics_serializes_unbounded_profit_factor_safely():
    metrics = calculate_performance_metrics([
        _record(1.0, index=0),
        _record(0.5, index=1),
    ])

    data = metrics.to_dict()

    assert metrics.profit_factor == float("inf")
    assert data["profit_factor"] is None
    assert data["profit_factor_unbounded"] is True


def test_performance_metrics_sorts_outcomes_by_timestamp_for_loss_streaks():
    records = [
        _record(-1.0, index=2),
        _record(1.0, index=0),
        _record(-0.5, index=1),
    ]

    metrics = calculate_performance_metrics(records)

    assert [row.r_multiple for row in metrics.outcomes] == [1.0, -0.5, -1.0]
    assert metrics.consecutive_losses == 2


def test_performance_metrics_empty_input_is_safe():
    metrics = calculate_performance_metrics([])

    assert metrics.trade_count == 0
    assert metrics.to_dict()["profit_factor"] == 0.0
    assert metrics.to_dict()["profit_factor_unbounded"] is False
    assert metrics.sharpe is None
