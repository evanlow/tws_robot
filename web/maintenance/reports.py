"""JSON and Markdown report helpers for maintenance runs."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from web.maintenance.tasks import MaintenanceRunReport


DEFAULT_REPORT_DIR = Path("reports") / "maintenance"


def write_report(report: MaintenanceRunReport, report_dir: Path) -> tuple[Path, Path]:
    """Write JSON and Markdown reports and return their paths."""
    report_dir.mkdir(parents=True, exist_ok=True)
    json_path = report_dir / f"{report.report_id}.json"
    md_path = report_dir / f"{report.report_id}.md"

    report.report_json_path = str(json_path)
    report.report_markdown_path = str(md_path)

    json_path.write_text(
        json.dumps(report.to_dict(), indent=2, sort_keys=True, default=str),
        encoding="utf-8",
    )
    md_path.write_text(render_markdown_report(report), encoding="utf-8")
    return json_path, md_path


def render_markdown_report(report: MaintenanceRunReport) -> str:
    """Render a concise human-readable Markdown summary."""
    lines = [
        f"# Maintenance Report: {report.report_id}",
        "",
        f"- Status: `{report.status}`",
        f"- Dry run: `{report.dry_run}`",
        f"- Started: `{report.started_at}`",
        f"- Finished: `{report.finished_at}`",
        f"- Duration: `{report.duration_seconds}s`",
        "",
        "## Task Summary",
        "",
        "| Task | Status | Before | After | Added | Removed | Warnings | Errors |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for result in report.results:
        lines.append(
            "| {task} | `{status}` | {before} | {after} | {added} | {removed} | {warnings} | {errors} |".format(
                task=result.task,
                status=result.status,
                before=_fmt_count(result.before_count),
                after=_fmt_count(result.after_count),
                added=len(result.added),
                removed=len(result.removed),
                warnings=len(result.warnings),
                errors=len(result.errors) + len(result.validation.errors),
            )
        )

    for result in report.results:
        lines.extend(["", f"## {result.task}", ""])
        lines.append(f"- Source: `{result.source or 'n/a'}`")
        lines.append(f"- Status: `{result.status}`")
        if result.added:
            lines.append("- Added: " + ", ".join(result.added[:50]))
        if result.removed:
            lines.append("- Removed: " + ", ".join(result.removed[:50]))
        for warning in result.warnings:
            lines.append(f"- Warning: {warning}")
        for error in result.validation.errors + result.errors:
            lines.append(f"- Error: {error}")
    lines.append("")
    return "\n".join(lines)


def list_reports(report_dir: Path, *, limit: int = 20) -> List[Dict[str, Any]]:
    """Return recent report summaries from newest to oldest."""
    if not report_dir.exists():
        return []
    reports = []
    for path in sorted(report_dir.glob("maintenance_*.json"), reverse=True)[:limit]:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        reports.append({
            "report_id": payload.get("report_id") or path.stem,
            "status": payload.get("status"),
            "dry_run": payload.get("dry_run"),
            "started_at": payload.get("started_at"),
            "finished_at": payload.get("finished_at"),
            "duration_seconds": payload.get("duration_seconds"),
            "warnings_count": len(payload.get("warnings") or []),
            "errors_count": len(payload.get("errors") or []),
            "path": str(path),
        })
    return reports


def read_report(report_dir: Path, report_id: str) -> Optional[Dict[str, Any]]:
    """Read one JSON report by report id."""
    safe_id = "".join(ch for ch in report_id if ch.isalnum() or ch in {"_", "-"})
    if not safe_id:
        return None
    path = report_dir / f"{safe_id}.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _fmt_count(value: Any) -> str:
    return "-" if value is None else str(value)
