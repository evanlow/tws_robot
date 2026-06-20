from datetime import datetime, timezone

from autonomous.outcome_evidence_writer import OutcomeEvidenceWriter
from autonomous.outcome_reconciliation import OutcomeReconciler
from autonomous.trade_store import AutonomousTrade, CLOSED


def test_outcome_writer_appends_record(tmp_path):
    writer = OutcomeEvidenceWriter(str(tmp_path))
    when = datetime(2026, 1, 2, tzinfo=timezone.utc)

    path = writer.append_outcome({"symbol": "AAA", "outcome": {"realized": True}}, when=when)

    assert path is not None
    assert path.exists()
    text = path.read_text(encoding="utf-8")
    assert "autonomous_outcome" in text
    assert "AAA" in text


def test_outcome_reconciler_builds_record():
    item = AutonomousTrade(
        autonomous_trade_id="t1",
        symbol="AAA",
        trade_type="BUY_SHARES",
        status=CLOSED,
        entry_order_id=101,
        entry_time=datetime(2026, 1, 1, tzinfo=timezone.utc),
        entry_limit_price=100.0,
        entry_filled_price=100.5,
        quantity=10,
        target_price=110.0,
        stop_price=95.0,
        exit_order_id=102,
        exit_time=datetime(2026, 1, 2, tzinfo=timezone.utc),
        exit_price=108.0,
        exit_reason="target_exit",
    )
    base = {
        "symbol": "AAA",
        "strategy_bucket": {"quality_label": "Strong"},
        "trade_plan": {"target_price": 110.0},
        "planned_risk": {"risk_per_share": 5.0},
    }

    result = OutcomeReconciler().reconcile_trade(item, base_evidence_record=base)
    record = result.to_evidence_record(base_record=base)

    assert result is not None
    assert result.realized_r_multiple == 1.5
    assert result.entry_slippage == 0.5
    assert record["evidence_type"] == "autonomous_outcome"
    assert record["strategy_bucket"]["quality_label"] == "Strong"
