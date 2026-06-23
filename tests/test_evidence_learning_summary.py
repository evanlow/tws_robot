from datetime import datetime, timedelta, timezone

from autonomous.evidence_learning_summary import summarize_evidence_learning


BASE = datetime(2026, 6, 23, 12, 0, tzinfo=timezone.utc)


def _outcome(r_value, *, index=0, symbol="AAA"):
    return {
        "schema_version": 3,
        "evidence_type": "autonomous_outcome",
        "timestamp": (BASE + timedelta(minutes=index)).isoformat(),
        "mode": "paper",
        "symbol": symbol,
        "strategy_bucket": {
            "signal_label": "Confirmed Rebound",
            "quality_label": "Strong",
            "momentum_label": "Confirmed Rebound",
            "market_classification": "Bullish / Volatility Acceptable",
            "vix_level_regime": "normal",
            "vix_direction_regime": "falling",
            "sector": "Technology",
        },
        "selected": {
            "features": {
                "sector_regime": "sector_supportive",
                "time_of_day_regime": "regular_session",
                "support_distance_pct": 0.02,
                "resistance_room_pct": 0.12,
                "adr_pct": 0.035,
            },
        },
        "trade_plan": {"symbol": symbol, "trade_type": "BUY_SHARES"},
        "outcome": {
            "realized": True,
            "realized_r_multiple": r_value,
            "realized_pnl": r_value * 100,
        },
    }


def test_evidence_learning_summary_exposes_el8_sections():
    records = [_outcome(0.7, index=i) for i in range(8)]

    summary = summarize_evidence_learning(records, now=BASE)

    assert summary["safety_notes"]["read_only"] is True
    assert summary["safety_notes"]["does_not_apply_capital_changes"] is True
    assert summary["counts"]["outcomes"] == 8
    assert summary["setup_performance"]["count"] == 1
    assert summary["setup_performance"]["setups"][0]["setup_id"].startswith("setup_v1__")
    assert "promotion_report" in summary
    assert "weak_setups" in summary
    assert "drift_report" in summary


def test_evidence_learning_summary_reports_weak_setups_and_drift():
    records = (
        [_outcome(1.0, index=i) for i in range(6)]
        + [_outcome(-1.0, index=6 + i) for i in range(4)]
    )

    summary = summarize_evidence_learning(
        records,
        drift_recent_trades=4,
        drift_min_trades=3,
        drift_expected_r_delta=0.5,
        now=BASE,
    )

    assert summary["weak_setups"]["count"] == 1
    assert summary["weak_setups"]["setups"][0]["recommended_size_state"] == "PAPER_ONLY"
    assert summary["drift_report"]["count"] == 1
    assert summary["drift_report"]["setups"][0]["direction"] == "weakening"
    assert summary["drift_report"]["setups"][0]["expected_r_delta"] < 0
