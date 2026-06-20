"""Chronological validation reports for realized evidence."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional

from autonomous.validation_framework import ValidationFramework, ValidationThresholds


@dataclass
class ChronoValidationWindow:
    index: int
    earlier_count: int
    later_count: int
    earlier_report: Dict[str, Any]
    later_report: Dict[str, Any]
    passed: bool
    reasons: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "index": self.index,
            "earlier_count": self.earlier_count,
            "later_count": self.later_count,
            "earlier_report": dict(self.earlier_report),
            "later_report": dict(self.later_report),
            "passed": self.passed,
            "reasons": list(self.reasons),
        }


@dataclass
class ChronoValidationReport:
    windows: List[ChronoValidationWindow]
    passed: bool
    reasons: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "windows": [w.to_dict() for w in self.windows],
            "passed": self.passed,
            "reasons": list(self.reasons),
        }


class ChronoValidator:
    """Evaluate realized evidence across sequential earlier/later windows."""

    def __init__(self, *, earlier_size: int = 30, later_size: int = 10, step_size: int = 10, thresholds: Optional[ValidationThresholds] = None) -> None:
        self.earlier_size = earlier_size
        self.later_size = later_size
        self.step_size = step_size
        self.thresholds = thresholds or ValidationThresholds()

    def evaluate(self, records: Iterable[Dict[str, Any]]) -> ChronoValidationReport:
        rows = [_row(record) for record in records]
        rows = [row for row in rows if row is not None]
        rows.sort(key=lambda row: row["timestamp"])
        minimum = self.earlier_size + self.later_size
        if len(rows) < minimum:
            return ChronoValidationReport([], False, [f"insufficient records: {len(rows)} < {minimum}"])

        framework = ValidationFramework(self.thresholds)
        windows: List[ChronoValidationWindow] = []
        start = 0
        index = 0
        while start + minimum <= len(rows):
            earlier = [row["record"] for row in rows[start:start + self.earlier_size]]
            later_start = start + self.earlier_size
            later = [row["record"] for row in rows[later_start:later_start + self.later_size]]
            earlier_report = framework.evaluate(earlier).to_dict()
            later_report = framework.evaluate(later).to_dict()
            passed = bool(earlier_report.get("passed")) and bool(later_report.get("passed"))
            reasons = []
            if not earlier_report.get("passed"):
                reasons.append("earlier window failed")
            if not later_report.get("passed"):
                reasons.append("later window failed")
            windows.append(ChronoValidationWindow(index, len(earlier), len(later), earlier_report, later_report, passed, reasons or ["window passed"]))
            start += self.step_size
            index += 1

        passed_all = all(window.passed for window in windows)
        return ChronoValidationReport(windows, passed_all, ["all windows passed"] if passed_all else ["one or more windows failed"])


def _row(record: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    outcome = record.get("outcome") or {}
    if not outcome.get("realized") or outcome.get("realized_r_multiple") is None:
        return None
    return {"timestamp": _parse_ts(record.get("timestamp")), "record": record}


def _parse_ts(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value)
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
        except ValueError:
            return datetime.now(timezone.utc)
    return datetime.now(timezone.utc)
