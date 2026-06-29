"""Tests for ORB backtest reporting, sweeps, readiness, and evidence saving."""

from datetime import datetime, timedelta

import pytest

from autonomous.opening_range import Candle, OpeningRangeConfig
from autonomous.orb_backtest_reports import (
    DO_NOT_TRADE,
    NEEDS_MORE_DATA,
    READY_FOR_PAPER,
    ReadinessCriteria,
    _model_label,
    build_report,
    classify_readiness,
    run_backtest,
    run_sweep,
    save_evidence,
)
from backtest.opening_range_strategy import ORBBacktestResult, ORBTradeResult


def _winning_day(symbol="QQQ", day=datetime(2026, 6, 1)):
    bars = []
    t = day.replace(hour=9, minute=30)
    for _ in range(15):
        bars.append(Candle(symbol, "1m", t, t + timedelta(minutes=1), 101, 102, 100, 101, 1000.0)); t += timedelta(minutes=1)
    for _ in range(5):
        bars.append(Candle(symbol, "1m", t, t + timedelta(minutes=1), 103, 103.3, 102.8, 103, 1000.0)); t += timedelta(minutes=1)
    bars.append(Candle(symbol, "1m", t, t + timedelta(minutes=1), 103.1, 103.3, 103.0, 103.2, 1000.0)); t += timedelta(minutes=1)
    bars.append(Candle(symbol, "1m", t, t + timedelta(minutes=1), 103.6, 105.0, 103.5, 104.9, 1000.0)); t += timedelta(minutes=1)
    for _ in range(20):
        bars.append(Candle(symbol, "1m", t, t + timedelta(minutes=1), 105, 110, 105, 110, 1000.0)); t += timedelta(minutes=1)
    return bars


def _fake_result(rs):
    res = ORBBacktestResult()
    for r in rs:
        pnl = abs(r) * 100 if r >= 0 else -abs(r) * 100
        res.trades.append(ORBTradeResult("QQQ", "2026-06-01", "MODEL_A_x", "LONG",
                                          100, 99, 102, 101, "target", 10, r, pnl))
    return res


def test_run_backtest_report_fields():
    report = run_backtest(_winning_day(), OpeningRangeConfig())
    for key in ("total_trades", "win_rate", "avg_r", "median_r", "total_pnl",
                "profit_factor", "max_drawdown_r", "avg_hold_minutes",
                "by_model", "by_symbol", "by_hour",
                "slippage_sensitivity_r", "commission_sensitivity_r", "no_trade_reasons"):
        assert key in report
    assert report["total_trades"] == 1
    assert "MODEL_A" in report["by_model"]
    assert "QQQ" in report["by_symbol"]


def test_model_label_buckets():
    assert _model_label("MODEL_A_DISPLACEMENT_GAP") == "MODEL_A"
    assert _model_label("MODEL_B_BREAK_RETEST") == "MODEL_B"
    assert _model_label("MODEL_C_REVERSAL") == "MODEL_C_REVERSAL"


def test_profit_factor_and_drawdown():
    report = build_report(_fake_result([1, 1, -1, 1]))
    assert report["profit_factor"] == 3.0
    assert report["max_drawdown_r"] == 1.0


def test_readiness_ready():
    report = build_report(_fake_result([1] * 30))
    out = classify_readiness(report, ReadinessCriteria(min_trade_count=30))
    assert out["status"] == READY_FOR_PAPER


def test_readiness_needs_more_data():
    report = build_report(_fake_result([1, 1, 1]))
    out = classify_readiness(report, ReadinessCriteria(min_trade_count=30))
    assert out["status"] == NEEDS_MORE_DATA


def test_readiness_do_not_trade_negative_r():
    report = build_report(_fake_result([-1] * 30))
    out = classify_readiness(report)
    assert out["status"] == DO_NOT_TRADE


def test_sweep_returns_comparable_sets():
    results = run_sweep(_winning_day(), entry_cutoff_times=["10:30", "11:30"],
                        continuation_rrs=[1.5, 2.0])
    assert len(results) == 4
    for r in results:
        assert "params" in r and "report" in r


def test_save_evidence(tmp_path):
    report = build_report(_fake_result([1] * 30))
    readiness = classify_readiness(report)
    path = save_evidence(report, readiness, log_dir=str(tmp_path), symbols=["QQQ"])
    assert path.endswith(".jsonl")
    assert tmp_path.joinpath(path.split("/")[-1]).read_text().strip()
