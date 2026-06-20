from datetime import datetime, timezone

from autonomous.outcome_evidence_writer import OutcomeEvidenceWriter


def test_outcome_writer_appends_record(tmp_path):
    writer = OutcomeEvidenceWriter(str(tmp_path))
    when = datetime(2026, 1, 2, tzinfo=timezone.utc)

    path = writer.append_outcome({"symbol": "AAA", "outcome": {"realized": True}}, when=when)

    assert path is not None
    assert path.exists()
    text = path.read_text(encoding="utf-8")
    assert "autonomous_outcome" in text
    assert "AAA" in text
