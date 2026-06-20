import json
from datetime import datetime, timezone

from autonomous.evidence_store import SCHEMA_VERSION, TradeEvidenceStore


def _audit_record():
    return {
        "engine": "AutonomousTradingEngine",
        "config": {"mode": "recommend_only", "max_trades_per_day": 1},
        "decision": {
            "status": "recommended",
            "mode": "recommend_only",
            "deployable_cash": 10_000.0,
            "cash_snapshot": {"deployable_cash": 10_000.0},
            "market_gate": {
                "classification": "Bullish / Volatility Acceptable",
                "bullish": True,
                "vix": {
                    "level_regime": "normal",
                    "direction_regime": "falling",
                },
            },
            "selected": {
                "candidate": {
                    "symbol": "AAA",
                    "sector": "Technology",
                    "strength_score": 100,
                    "signal_label": "Confirmed Rebound",
                    "extras": {
                        "quality_label": "Strong",
                        "momentum_label": "Confirmed Rebound",
                    },
                },
                "score": 100.0,
            },
            "trade_plan": {
                "symbol": "AAA",
                "trade_type": "BUY_SHARES",
                "quantity": 10,
                "limit_price": 100.0,
                "target_price": 108.0,
                "stop_price": 96.0,
                "required_cash": 1_000.0,
                "target_mode": "percent",
            },
            "shortlist": [{"candidate": {"symbol": "AAA"}, "score": 100.0}],
            "rejected_candidates": [{"symbol": "BBB", "reason": "weak"}],
            "notes": ["recommend_only mode — no order placed"],
        },
    }


def test_evidence_store_builds_schema_versioned_learning_record(tmp_path):
    store = TradeEvidenceStore(str(tmp_path))
    when = datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)

    record = store.build_decision_record(_audit_record(), when=when)

    assert record["schema_version"] == SCHEMA_VERSION
    assert record["evidence_type"] == "autonomous_decision"
    assert record["status"] == "recommended"
    assert record["symbol"] == "AAA"
    assert record["strategy_bucket"]["quality_label"] == "Strong"
    assert record["strategy_bucket"]["vix_level_regime"] == "normal"
    assert record["planned_risk"]["risk_per_share"] == 4.0
    assert record["planned_risk"]["planned_dollar_risk"] == 40.0
    assert record["planned_risk"]["planned_r_multiple"] == 2.0
    assert record["candidate_counts"] == {"shortlist": 1, "rejected": 1, "basket_legs": 0}
    assert record["outcome"]["realized"] is False


def test_evidence_store_writes_and_reads_recent_records(tmp_path):
    store = TradeEvidenceStore(str(tmp_path))
    when = datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)

    path = store.log_decision(_audit_record(), when=when)

    assert path is not None
    assert path.exists()
    line = path.read_text(encoding="utf-8").strip()
    assert json.loads(line)["symbol"] == "AAA"

    recent = store.recent(limit=1)
    assert len(recent) == 1
    assert recent[0]["symbol"] == "AAA"


def _outcome_record(symbol: str, r: float, when: datetime) -> dict:
    return {
        "schema_version": 3,
        "evidence_type": "autonomous_outcome",
        "timestamp": when.isoformat(),
        "symbol": symbol,
        "outcome": {
            "realized": True,
            "realized_r_multiple": r,
            "realized_pnl": r * 100,
        },
    }


def _decision_record(symbol: str, when: datetime) -> dict:
    return {
        "schema_version": 3,
        "evidence_type": "autonomous_decision",
        "timestamp": when.isoformat(),
        "symbol": symbol,
        "status": "risk_rejected",
    }


def test_recent_outcomes_excludes_non_outcome_records(tmp_path):
    store = TradeEvidenceStore(str(tmp_path))
    when = datetime(2026, 3, 1, 12, 0, 0, tzinfo=timezone.utc)

    path = store._path_for(when)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        fh.write(json.dumps(_outcome_record("AAA", -1.0, when)) + "\n")
        fh.write(json.dumps(_decision_record("BBB", when)) + "\n")
        fh.write(json.dumps(_outcome_record("CCC", 2.0, when)) + "\n")

    results = store.recent_outcomes(limit=10)

    assert len(results) == 2
    symbols = [r["symbol"] for r in results]
    assert "BBB" not in symbols
    assert "AAA" in symbols
    assert "CCC" in symbols


def test_recent_outcomes_limit_is_respected(tmp_path):
    store = TradeEvidenceStore(str(tmp_path))
    when = datetime(2026, 3, 2, 12, 0, 0, tzinfo=timezone.utc)

    path = store._path_for(when)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for i in range(5):
            fh.write(json.dumps(_outcome_record(f"S{i}", float(i), when)) + "\n")
        for i in range(10):
            fh.write(json.dumps(_decision_record(f"D{i}", when)) + "\n")

    results = store.recent_outcomes(limit=3)

    assert len(results) == 3


def test_recent_outcomes_returns_newest_first(tmp_path):
    store = TradeEvidenceStore(str(tmp_path))
    t1 = datetime(2026, 3, 3, 10, 0, 0, tzinfo=timezone.utc)
    t2 = datetime(2026, 3, 3, 11, 0, 0, tzinfo=timezone.utc)
    t3 = datetime(2026, 3, 3, 12, 0, 0, tzinfo=timezone.utc)

    path = store._path_for(t1)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        fh.write(json.dumps(_outcome_record("FIRST", 1.0, t1)) + "\n")
        fh.write(json.dumps(_outcome_record("SECOND", -0.5, t2)) + "\n")
        fh.write(json.dumps(_outcome_record("THIRD", 2.0, t3)) + "\n")

    results = store.recent_outcomes(limit=10)

    assert results[0]["symbol"] == "THIRD"
    assert results[-1]["symbol"] == "FIRST"
