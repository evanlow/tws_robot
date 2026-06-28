"""System maintenance runner for market metadata refresh and hygiene.

This module is deliberately metadata-only.  It reads/writes constituent CSVs,
backup files, maintenance reports, and delegates market event refresh to the
existing market-events service.  It must not import order placement or execution
adapters.
"""

from __future__ import annotations

import csv
import logging
import os
import re
import shutil
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Mapping, Optional, Sequence

from web.maintenance import reports
from web.maintenance.tasks import (
    STATUS_FAILED,
    STATUS_PARTIAL_FAILURE,
    STATUS_SKIPPED,
    STATUS_SUCCESS,
    MaintenanceRunReport,
    MaintenanceTaskResult,
    ValidationResult,
)
from web.maintenance.validators import validate_constituent_rows

logger = logging.getLogger(__name__)

ConstituentLoader = Callable[[], List[Dict[str, str]]]

_DEFAULT_TASKS = ("sp500_constituents", "sti_constituents", "hsi_constituents", "market_events")

_CONSTITUENT_TASKS = {
    "sp500_constituents": {
        "market": "sp500",
        "filename": "sp500_constituents.csv",
        "source_module": "web.maintenance.sources.sp500",
        "source_url_attr": "SOURCE_URL",
    },
    "sti_constituents": {
        "market": "sti",
        "filename": "sti_constituents.csv",
        "source_module": "web.maintenance.sources.sti",
        "source_url_attr": "SOURCE_URL",
    },
    "hsi_constituents": {
        "market": "hsi",
        "filename": "hsi_constituents.csv",
        "source_module": "web.maintenance.sources.hsi",
        "source_url_attr": "SOURCE_URL",
    },
}


class MaintenanceRunner:
    """Run dry-run/apply maintenance tasks and write audit reports."""

    def __init__(
        self,
        *,
        repo_root: Optional[Path] = None,
        source_loaders: Optional[Dict[str, ConstituentLoader]] = None,
        report_dir: Optional[Path] = None,
    ) -> None:
        self.repo_root = repo_root or Path(__file__).resolve().parents[2]
        self.data_dir = self.repo_root / "data"
        self.backup_root = self.data_dir / "backups" / "constituents"
        self.report_dir = report_dir or (self.repo_root / reports.DEFAULT_REPORT_DIR)
        self._source_loaders = source_loaders or {}

    def run(
        self,
        *,
        tasks: Optional[Sequence[str]] = None,
        dry_run: bool = True,
        event_symbols: Optional[Sequence[str]] = None,
        days_ahead: int = 28,
        allow_large_change: bool = False,
    ) -> MaintenanceRunReport:
        """Run selected maintenance tasks and write reports.

        Dry-run is the safe default.  Apply mode is required to write refreshed
        constituent files or update market-event DB rows.
        """
        started = time.monotonic()
        task_names = list(tasks or _DEFAULT_TASKS)
        report = MaintenanceRunReport(
            report_id=_new_report_id(),
            dry_run=dry_run,
        )

        for task_name in task_names:
            if task_name in _CONSTITUENT_TASKS:
                result = self._run_constituent_task(
                    task_name,
                    dry_run=dry_run,
                    allow_large_change=allow_large_change,
                )
            elif task_name == "market_events":
                result = self._run_market_events_task(
                    dry_run=dry_run,
                    event_symbols=event_symbols,
                    days_ahead=days_ahead,
                )
            elif task_name == "metadata_validation":
                result = self._run_metadata_validation_task(dry_run=dry_run)
            else:
                task_started = time.monotonic()
                result = MaintenanceTaskResult(task=task_name, status=STATUS_FAILED, dry_run=dry_run)
                result.errors.append(f"Unknown maintenance task: {task_name}")
                result.finish(started_monotonic=task_started, now_monotonic=time.monotonic())
            report.results.append(result)

        report.finalize(started_monotonic=started, now_monotonic=time.monotonic())
        reports.write_report(report, self.report_dir)
        return report

    def get_status(self) -> Dict[str, object]:
        """Return current maintenance status for the dashboard."""
        constituent_status = []
        for task_name, cfg in _CONSTITUENT_TASKS.items():
            path = self.data_dir / str(cfg["filename"])
            rows = _read_csv_rows(path) if path.exists() else []
            row_count = len(rows)
            mtime = datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat() if path.exists() else None
            validation = validate_constituent_rows(
                rows,
                market=str(cfg["market"]),
                before_count=row_count,
            ) if path.exists() else ValidationResult(status=STATUS_FAILED, errors=["File not found"])
            constituent_status.append({
                "task": task_name,
                "file": str(path),
                "row_count": row_count,
                "last_modified_at": mtime,
                "validation": validation.to_dict(),
            })
        return {
            "constituents": constituent_status,
            "reports": reports.list_reports(self.report_dir, limit=5),
        }

    def list_reports(self, *, limit: int = 20) -> List[Dict[str, object]]:
        return reports.list_reports(self.report_dir, limit=limit)

    def read_report(self, report_id: str) -> Optional[Dict[str, object]]:
        return reports.read_report(self.report_dir, report_id)

    # ------------------------------------------------------------------
    # Task implementations
    # ------------------------------------------------------------------

    def _run_constituent_task(
        self,
        task_name: str,
        *,
        dry_run: bool,
        allow_large_change: bool,
    ) -> MaintenanceTaskResult:
        started = time.monotonic()
        cfg = _CONSTITUENT_TASKS[task_name]
        result = MaintenanceTaskResult(task=task_name, dry_run=dry_run, source=self._source_url(task_name))
        output_path = self.data_dir / str(cfg["filename"])
        current_rows = _read_csv_rows(output_path)
        result.before_count = len(current_rows)

        try:
            proposed_rows = self._fetch_constituent_rows(task_name)
            proposed_rows, backfilled = _backfill_enrichment(proposed_rows, current_rows)
            if backfilled:
                result.detail["enrichment_backfilled"] = backfilled
            result.after_count = len(proposed_rows)
            result.added, result.removed = _symbol_diff(current_rows, proposed_rows)
            result.validation = validate_constituent_rows(
                proposed_rows,
                market=str(cfg["market"]),
                before_count=result.before_count,
                allow_large_change=allow_large_change,
            )
            if not result.validation.passed:
                result.status = STATUS_FAILED
                result.errors.append("Validation failed; existing file preserved")
                return result
            if dry_run:
                result.detail["would_write"] = str(output_path)
                return result

            backup_path = self._backup_existing_file(output_path)
            self._write_csv_atomically(output_path, proposed_rows)
            result.detail["backup_path"] = str(backup_path) if backup_path else None
            result.detail["written_path"] = str(output_path)
            self._invalidate_screener_cache(task_name, result)
            return result
        except Exception as exc:
            logger.error("Constituent task %s failed: %s", task_name, exc, exc_info=True)
            result.status = STATUS_FAILED
            result.errors.append(str(exc))
            return result
        finally:
            result.finish(started_monotonic=started, now_monotonic=time.monotonic())

    def _run_metadata_validation_task(self, *, dry_run: bool) -> MaintenanceTaskResult:
        started = time.monotonic()
        result = MaintenanceTaskResult(task="metadata_validation", dry_run=dry_run, source="local-files")
        try:
            for task_name, cfg in _CONSTITUENT_TASKS.items():
                path = self.data_dir / str(cfg["filename"])
                rows = _read_csv_rows(path)
                validation = validate_constituent_rows(rows, market=str(cfg["market"]), before_count=len(rows))
                detail_key = str(cfg["market"])
                result.detail[detail_key] = validation.to_dict()
                if validation.errors:
                    result.errors.extend(f"{task_name}: {err}" for err in validation.errors)
                if validation.warnings:
                    result.warnings.extend(f"{task_name}: {warn}" for warn in validation.warnings)
            result.status = STATUS_FAILED if result.errors else STATUS_SUCCESS
            return result
        finally:
            result.finish(started_monotonic=started, now_monotonic=time.monotonic())

    def _run_market_events_task(
        self,
        *,
        dry_run: bool,
        event_symbols: Optional[Sequence[str]],
        days_ahead: int,
    ) -> MaintenanceTaskResult:
        started = time.monotonic()
        result = MaintenanceTaskResult(task="market_events", dry_run=dry_run, source="data.market_events")
        symbols = sorted({str(s).upper() for s in (event_symbols or []) if s})
        result.detail["symbols"] = symbols
        result.detail["days_ahead"] = days_ahead
        try:
            if dry_run:
                result.status = STATUS_SKIPPED
                result.warnings.append("Dry-run does not update market-event DB rows; run apply mode to refresh events")
                return result

            from data.market_events import get_market_events_service

            svc = get_market_events_service()
            summary = svc.refresh(portfolio_symbols=symbols, force=True, days_ahead=days_ahead)
            result.detail["summary"] = summary
            result.after_count = int(summary.get("total_upserted") or 0)
            total_errors = int(summary.get("total_errors") or 0)
            if summary.get("status") == "failed":
                result.status = STATUS_FAILED
                result.errors.append(str(summary.get("error") or "Market events refresh failed"))
            elif summary.get("status") == "partial_failure" or total_errors:
                result.status = STATUS_PARTIAL_FAILURE
                result.warnings.append("One or more market-event providers failed; see provider_results")
            return result
        except Exception as exc:
            logger.error("Market events task failed: %s", exc, exc_info=True)
            result.status = STATUS_FAILED
            result.errors.append(str(exc))
            return result
        finally:
            result.finish(started_monotonic=started, now_monotonic=time.monotonic())

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _fetch_constituent_rows(self, task_name: str) -> List[Dict[str, str]]:
        if task_name in self._source_loaders:
            return _normalise_rows(self._source_loaders[task_name]())
        module = _import_module(str(_CONSTITUENT_TASKS[task_name]["source_module"]))
        return _normalise_rows(module.fetch_constituents())

    def _source_url(self, task_name: str) -> Optional[str]:
        try:
            module = _import_module(str(_CONSTITUENT_TASKS[task_name]["source_module"]))
            return str(getattr(module, str(_CONSTITUENT_TASKS[task_name]["source_url_attr"])))
        except Exception:
            return None

    def _backup_existing_file(self, output_path: Path) -> Optional[Path]:
        if not output_path.exists():
            return None
        timestamped_backup_dir = self.backup_root / datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")
        timestamped_backup_dir.mkdir(parents=True, exist_ok=True)
        backup_path = timestamped_backup_dir / output_path.name
        shutil.copy2(output_path, backup_path)
        return backup_path

    def _write_csv_atomically(self, output_path: Path, rows: Sequence[Mapping[str, object]]) -> None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        fieldnames = _fieldnames(rows)
        fd, tmp_name = tempfile.mkstemp(prefix=output_path.name + ".", suffix=".tmp", dir=str(output_path.parent))
        tmp_path = Path(tmp_name)
        try:
            with os.fdopen(fd, "w", newline="", encoding="utf-8") as fh:
                writer = csv.DictWriter(fh, fieldnames=fieldnames)
                writer.writeheader()
                for row in rows:
                    writer.writerow({field: row.get(field, "") for field in fieldnames})
            os.replace(tmp_path, output_path)
        finally:
            if tmp_path.exists():
                tmp_path.unlink()

    def _invalidate_screener_cache(self, task_name: str, result: MaintenanceTaskResult) -> None:
        try:
            if task_name == "sp500_constituents":
                from web.sp500_screener_service import sp500_screener_service
                sp500_screener_service.invalidate_cache()
            elif task_name == "sti_constituents":
                from web.sti_screener_service import sti_screener_service
                sti_screener_service.invalidate_cache()
            elif task_name == "hsi_constituents":
                from web.hsi_screener_service import hsi_screener_service
                hsi_screener_service.invalidate_cache()
            result.detail.setdefault("cache_invalidated", True)
        except Exception as exc:
            result.warnings.append(f"Cache invalidation failed: {exc}")


# ----------------------------------------------------------------------
# Module helpers
# ----------------------------------------------------------------------


def _new_report_id() -> str:
    return "maintenance_" + datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _read_csv_rows(path: Path) -> List[Dict[str, str]]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as fh:
        return [dict(row) for row in csv.DictReader(fh)]


def _normalise_rows(rows: Iterable[Mapping[str, object]]) -> List[Dict[str, str]]:
    normalized: List[Dict[str, str]] = []
    for row in rows:
        item = {str(k): "" if v is None else str(v).strip() for k, v in row.items()}
        if item.get("symbol"):
            item["symbol"] = item["symbol"].upper()
        for col in ("security", "sector", "sub_industry"):
            item.setdefault(col, "")
        normalized.append(item)
    return normalized


def _fieldnames(rows: Sequence[Mapping[str, object]]) -> List[str]:
    base = ["symbol"]
    if any("display_symbol" in row for row in rows):
        base.append("display_symbol")
    base.extend(["security", "sector", "sub_industry"])
    extras = sorted({str(k) for row in rows for k in row.keys()} - set(base))
    return base + extras


def _symbol_diff(before: Sequence[Mapping[str, object]], after: Sequence[Mapping[str, object]]) -> tuple[List[str], List[str]]:
    before_symbols = {str(row.get("symbol") or "").strip().upper() for row in before if row.get("symbol")}
    after_symbols = {str(row.get("symbol") or "").strip().upper() for row in after if row.get("symbol")}
    return sorted(after_symbols - before_symbols), sorted(before_symbols - after_symbols)


_ENRICHMENT_FIELDS = ("sector", "sub_industry")

# Corporate suffixes stripped when matching companies by name so a symbol change
# (e.g. STI "T39" -> "5E2" for Seatrium) still recovers prior sector enrichment.
_NAME_SUFFIXES = (
    "limited", "ltd", "plc", "holdings", "holding", "corporation", "corp",
    "incorporated", "inc", "company", "co", "group", "the",
)


def _normalise_security_name(value: object) -> str:
    text = str(value or "").lower()
    text = re.sub(r"\[[^\]]*\]", " ", text)  # drop footnote markers like "[zh]"
    text = re.sub(r"[^a-z0-9]+", " ", text).strip()
    if not text:
        return ""
    tokens = [tok for tok in text.split() if tok not in _NAME_SUFFIXES]
    return " ".join(tokens) if tokens else text


def _backfill_enrichment(
    proposed: Sequence[Mapping[str, str]],
    current: Sequence[Mapping[str, str]],
) -> tuple[List[Dict[str, str]], int]:
    """Fill empty enrichment fields on proposed rows from existing rows.

    Matches on symbol first, then on a normalized company name so a source that
    no longer exposes sector/sub_industry cannot silently wipe curated metadata.
    Only blank fields are filled; non-empty source values are never overridden.
    """
    by_symbol: Dict[str, Mapping[str, str]] = {}
    by_name: Dict[str, Mapping[str, str]] = {}
    for row in current:
        symbol = str(row.get("symbol") or "").strip().upper()
        if symbol:
            by_symbol.setdefault(symbol, row)
        name = _normalise_security_name(row.get("security"))
        if name:
            by_name.setdefault(name, row)

    enriched: List[Dict[str, str]] = []
    backfilled = 0
    for row in proposed:
        new_row = dict(row)
        symbol = str(new_row.get("symbol") or "").strip().upper()
        source = by_symbol.get(symbol) or by_name.get(_normalise_security_name(new_row.get("security")))
        if source:
            row_changed = False
            for field in _ENRICHMENT_FIELDS:
                current_value = str(new_row.get(field) or "").strip()
                fallback_value = str(source.get(field) or "").strip()
                if not current_value and fallback_value:
                    new_row[field] = fallback_value
                    row_changed = True
            if row_changed:
                backfilled += 1
        enriched.append(new_row)
    return enriched, backfilled


def _import_module(module_name: str):
    import importlib
    return importlib.import_module(module_name)
