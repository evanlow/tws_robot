"""Structured result models for the system maintenance module.

The maintenance subsystem is intentionally metadata-only.  These lightweight
models make task output easy to serialize into API responses, JSON reports, and
Markdown summaries without coupling the runner to Flask or trading services.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


STATUS_SUCCESS = "success"
STATUS_FAILED = "failed"
STATUS_SKIPPED = "skipped"
STATUS_WARNING = "warning"
STATUS_PARTIAL_FAILURE = "partial_failure"


def utc_now_iso() -> str:
    """Return a timezone-aware UTC timestamp suitable for reports."""
    return datetime.now(timezone.utc).isoformat()


@dataclass
class ValidationResult:
    """Validation outcome for one maintenance artifact."""

    status: str = STATUS_SUCCESS
    warnings: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    detail: Dict[str, Any] = field(default_factory=dict)

    @property
    def passed(self) -> bool:
        return not self.errors

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class MaintenanceTaskResult:
    """Result returned by each maintenance task.

    Keep this object deliberately explicit so future UI/API code can display
    counts, diffs, sources, warnings, and errors without parsing logs.
    """

    task: str
    status: str = STATUS_SUCCESS
    dry_run: bool = True
    source: Optional[str] = None
    started_at: str = field(default_factory=utc_now_iso)
    finished_at: Optional[str] = None
    duration_seconds: float = 0.0
    before_count: Optional[int] = None
    after_count: Optional[int] = None
    added: List[str] = field(default_factory=list)
    removed: List[str] = field(default_factory=list)
    validation: ValidationResult = field(default_factory=ValidationResult)
    warnings: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    detail: Dict[str, Any] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return self.status == STATUS_SUCCESS and not self.errors and self.validation.passed

    def finish(self, *, started_monotonic: float, now_monotonic: float) -> None:
        self.finished_at = utc_now_iso()
        self.duration_seconds = round(max(0.0, now_monotonic - started_monotonic), 3)
        if self.validation.errors and self.status == STATUS_SUCCESS:
            self.status = STATUS_FAILED
        if self.errors and self.status == STATUS_SUCCESS:
            self.status = STATUS_FAILED
        if self.validation.warnings:
            self.warnings.extend(w for w in self.validation.warnings if w not in self.warnings)

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["validation"] = self.validation.to_dict()
        data["ok"] = self.ok
        return data


@dataclass
class MaintenanceRunReport:
    """Top-level report produced by a maintenance run."""

    report_id: str
    dry_run: bool
    status: str = STATUS_SUCCESS
    started_at: str = field(default_factory=utc_now_iso)
    finished_at: Optional[str] = None
    duration_seconds: float = 0.0
    results: List[MaintenanceTaskResult] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    report_json_path: Optional[str] = None
    report_markdown_path: Optional[str] = None

    def finalize(self, *, started_monotonic: float, now_monotonic: float) -> None:
        self.finished_at = utc_now_iso()
        self.duration_seconds = round(max(0.0, now_monotonic - started_monotonic), 3)
        self.warnings = [w for r in self.results for w in r.warnings]
        self.errors = [e for r in self.results for e in list(r.errors) + list(r.validation.errors)]
        if any(r.status == STATUS_FAILED for r in self.results):
            self.status = STATUS_FAILED
        elif any(r.status == STATUS_PARTIAL_FAILURE for r in self.results):
            self.status = STATUS_PARTIAL_FAILURE
        elif any(r.warnings for r in self.results):
            self.status = STATUS_WARNING
        else:
            self.status = STATUS_SUCCESS

    def to_dict(self) -> Dict[str, Any]:
        return {
            "report_id": self.report_id,
            "dry_run": self.dry_run,
            "status": self.status,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "duration_seconds": self.duration_seconds,
            "results": [r.to_dict() for r in self.results],
            "warnings": list(self.warnings),
            "errors": list(self.errors),
            "report_json_path": self.report_json_path,
            "report_markdown_path": self.report_markdown_path,
        }
