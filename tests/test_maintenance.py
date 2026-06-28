"""Tests for the System Maintenance metadata refresh module."""

from __future__ import annotations

import csv
from pathlib import Path

import pytest

from web import create_app
from web.maintenance.runner import MaintenanceRunner
from web.maintenance.validators import validate_constituent_rows


@pytest.fixture
def app(monkeypatch):
    monkeypatch.setattr(
        "web.services.ServiceManager._start_market_events_refresh",
        lambda self: None,
    )
    monkeypatch.setattr("web.routes.api_connection.is_accepted", lambda: True)
    return create_app({"TESTING": True, "LOGIN_DISABLED": True, "WTF_CSRF_ENABLED": False})


@pytest.fixture
def client(app):
    return app.test_client()


def test_validate_constituents_rejects_duplicates():
    rows = _sp500_rows(451)
    rows.append(dict(rows[0]))

    result = validate_constituent_rows(rows, market="sp500", before_count=451)

    assert not result.passed
    assert any("Duplicate symbols" in err for err in result.errors)


def test_validate_constituents_warns_on_large_but_allowed_change():
    result = validate_constituent_rows(_sp500_rows(510), market="sp500", before_count=450)

    assert result.passed
    assert any("Large count change" in warn for warn in result.warnings)


def test_dry_run_preserves_existing_file_and_writes_report(tmp_path):
    current = _sp500_rows(450)
    proposed = _sp500_rows(451)
    _write_constituents(tmp_path / "data" / "sp500_constituents.csv", current)
    runner = _runner(tmp_path, {"sp500_constituents": lambda: proposed})

    report = runner.run(tasks=["sp500_constituents"], dry_run=True)

    assert report.status in {"success", "warning"}
    assert _read_symbols(tmp_path / "data" / "sp500_constituents.csv") == [r["symbol"] for r in current]
    assert report.report_json_path is not None
    assert Path(report.report_json_path).exists()
    assert report.results[0].detail["would_write"].endswith("sp500_constituents.csv")


def test_apply_creates_backup_and_replaces_file(tmp_path, monkeypatch):
    current = _sp500_rows(450)
    proposed = _sp500_rows(451)
    output_path = tmp_path / "data" / "sp500_constituents.csv"
    _write_constituents(output_path, current)
    _disable_cache_invalidation(monkeypatch)
    runner = _runner(tmp_path, {"sp500_constituents": lambda: proposed})

    report = runner.run(tasks=["sp500_constituents"], dry_run=False)

    assert report.status in {"success", "warning"}
    assert _read_symbols(output_path) == [r["symbol"] for r in proposed]
    backups = list((tmp_path / "data" / "backups" / "constituents").glob("*/sp500_constituents.csv"))
    assert backups, "Expected timestamped backup before apply replacement"
    assert report.results[0].detail["cache_invalidated"] is True


def test_source_failure_preserves_existing_file_and_reports_error(tmp_path, monkeypatch):
    current = _sp500_rows(450)
    output_path = tmp_path / "data" / "sp500_constituents.csv"
    _write_constituents(output_path, current)
    _disable_cache_invalidation(monkeypatch)

    def failing_source():
        raise RuntimeError("source unavailable")

    runner = _runner(tmp_path, {"sp500_constituents": failing_source})

    report = runner.run(tasks=["sp500_constituents"], dry_run=False)

    assert report.status == "failed"
    assert "source unavailable" in report.errors
    assert _read_symbols(output_path) == [r["symbol"] for r in current]
    assert not (tmp_path / "data" / "backups" / "constituents").exists()


def test_validation_failure_preserves_existing_file(tmp_path, monkeypatch):
    current = _sp500_rows(450)
    invalid = _sp500_rows(1)
    output_path = tmp_path / "data" / "sp500_constituents.csv"
    _write_constituents(output_path, current)
    _disable_cache_invalidation(monkeypatch)
    runner = _runner(tmp_path, {"sp500_constituents": lambda: invalid})

    report = runner.run(tasks=["sp500_constituents"], dry_run=False)

    assert report.status == "failed"
    assert _read_symbols(output_path) == [r["symbol"] for r in current]
    assert not (tmp_path / "data" / "backups" / "constituents").exists()


def test_market_events_dry_run_is_metadata_only(tmp_path):
    runner = _runner(tmp_path, {})

    report = runner.run(tasks=["market_events"], dry_run=True)

    assert report.results[0].status == "skipped"
    assert "Dry-run does not update market-event DB rows" in report.results[0].warnings[0]


def test_dry_run_all_is_failed_when_any_task_fails(tmp_path):
    current_hsi = _sp500_rows(85)
    _write_constituents(tmp_path / "data" / "hsi_constituents.csv", current_hsi)

    def failing_source():
        raise RuntimeError("HTTP Error 403: Forbidden")

    runner = _runner(
        tmp_path,
        {
            "sp500_constituents": failing_source,
            "sti_constituents": failing_source,
            "hsi_constituents": lambda: current_hsi,
        },
    )

    report = runner.run(dry_run=True)

    assert report.status == "failed"
    assert any(result.task == "sp500_constituents" and result.status == "failed" for result in report.results)
    assert any(result.task == "sti_constituents" and result.status == "failed" for result in report.results)


def test_apply_backfills_missing_enrichment_from_existing_file(tmp_path, monkeypatch):
    """A source that drops sector/sub_industry must not wipe curated enrichment."""
    existing = [
        {
            "symbol": f"X{i:02d}.SI",
            "display_symbol": f"X{i:02d}",
            "security": f"Company {i}",
            "sector": "Financials",
            "sub_industry": "Banks",
        }
        for i in range(30)
    ]
    output_path = tmp_path / "data" / "sti_constituents.csv"
    _write_sti_constituents(output_path, existing)
    _disable_cache_invalidation(monkeypatch)

    # Source returns the same names/symbols but with empty sector/sub_industry.
    stripped = [
        {**row, "sector": "", "sub_industry": ""}
        for row in existing
    ]
    runner = _runner(tmp_path, {"sti_constituents": lambda: stripped})

    report = runner.run(tasks=["sti_constituents"], dry_run=False)

    assert report.status in {"success", "warning"}
    written = {row["symbol"]: row for row in _read_rows(output_path)}
    assert all(written[sym]["sector"] == "Financials" for sym in written)
    assert all(written[sym]["sub_industry"] == "Banks" for sym in written)
    assert report.results[0].detail.get("enrichment_backfilled") == 30


def test_apply_backfills_enrichment_across_symbol_change_by_name(tmp_path, monkeypatch):
    """Enrichment should follow a company when only its ticker changes."""
    existing = [
        {
            "symbol": f"OLD{i:02d}.SI",
            "display_symbol": f"OLD{i:02d}",
            "security": f"Company {i}",
            "sector": "Industrials",
            "sub_industry": "Airlines",
        }
        for i in range(30)
    ]
    output_path = tmp_path / "data" / "sti_constituents.csv"
    _write_sti_constituents(output_path, existing)
    _disable_cache_invalidation(monkeypatch)

    # Same companies, new tickers, with corporate suffix variations and no sectors.
    renamed = [
        {
            "symbol": f"NEW{i:02d}.SI",
            "display_symbol": f"NEW{i:02d}",
            "security": f"Company {i} Limited",
            "sector": "",
            "sub_industry": "",
        }
        for i in range(30)
    ]
    runner = _runner(tmp_path, {"sti_constituents": lambda: renamed})

    report = runner.run(tasks=["sti_constituents"], dry_run=False)

    assert report.status in {"success", "warning"}
    written = _read_rows(output_path)
    assert all(row["sector"] == "Industrials" for row in written)
    assert all(row["sub_industry"] == "Airlines" for row in written)


def test_apply_does_not_override_present_source_enrichment(tmp_path, monkeypatch):
    """Backfill must never overwrite non-empty sector values from the source."""
    existing = [
        {
            "symbol": f"X{i:02d}.SI",
            "display_symbol": f"X{i:02d}",
            "security": f"Company {i}",
            "sector": "StaleSector",
            "sub_industry": "StaleSub",
        }
        for i in range(30)
    ]
    output_path = tmp_path / "data" / "sti_constituents.csv"
    _write_sti_constituents(output_path, existing)
    _disable_cache_invalidation(monkeypatch)

    fresh = [
        {
            "symbol": f"X{i:02d}.SI",
            "display_symbol": f"X{i:02d}",
            "security": f"Company {i}",
            "sector": "FreshSector",
            "sub_industry": "FreshSub",
        }
        for i in range(30)
    ]
    runner = _runner(tmp_path, {"sti_constituents": lambda: fresh})

    report = runner.run(tasks=["sti_constituents"], dry_run=False)

    assert report.status in {"success", "warning"}
    written = _read_rows(output_path)
    assert all(row["sector"] == "FreshSector" for row in written)
    assert report.results[0].detail.get("enrichment_backfilled") in (None, 0)


def test_run_records_named_constituent_changes(tmp_path):
    """The report should pair added/removed symbols with company names."""
    current = _sp500_rows(450)            # T000..T449
    proposed = _sp500_rows(451)[1:]       # T001..T450 (drops T000, adds T450)
    _write_constituents(tmp_path / "data" / "sp500_constituents.csv", current)
    runner = _runner(tmp_path, {"sp500_constituents": lambda: proposed})

    report = runner.run(tasks=["sp500_constituents"], dry_run=True)

    changes = report.results[0].detail["changes"]
    assert changes["added"] == [{"symbol": "T450", "security": "Test Company 450"}]
    assert changes["removed"] == [{"symbol": "T000", "security": "Test Company 0"}]

    from web.maintenance.reports import render_markdown_report

    markdown = render_markdown_report(report)
    assert "T450 (Test Company 450)" in markdown
    assert "T000 (Test Company 0)" in markdown


def test_run_without_membership_change_records_no_changes(tmp_path):
    """No added/removed symbols means no changes block is emitted."""
    rows = _sp500_rows(450)
    _write_constituents(tmp_path / "data" / "sp500_constituents.csv", rows)
    runner = _runner(tmp_path, {"sp500_constituents": lambda: _sp500_rows(450)})

    report = runner.run(tasks=["sp500_constituents"], dry_run=True)

    result = report.results[0]
    assert result.added == []
    assert result.removed == []
    assert "changes" not in result.detail


def test_maintenance_page_loads(client):
    response = client.get("/maintenance")

    assert response.status_code == 200
    assert b"System Maintenance" in response.data


def test_maintenance_nav_link_registered_in_main_js(client):
    response = client.get("/static/js/main.js")

    assert response.status_code == 200
    assert b"/maintenance" in response.data
    assert b"Maintenance" in response.data


def test_maintenance_status_api_loads(client):
    response = client.get("/api/maintenance/status")

    assert response.status_code == 200
    data = response.get_json()
    assert "constituents" in data


def _runner(tmp_path, source_loaders):
    return MaintenanceRunner(
        repo_root=tmp_path,
        source_loaders=source_loaders,
        report_dir=tmp_path / "reports" / "maintenance",
    )


def _disable_cache_invalidation(monkeypatch):
    def fake_invalidate(self, task_name, result):
        result.detail["cache_invalidated"] = True
    monkeypatch.setattr(MaintenanceRunner, "_invalidate_screener_cache", fake_invalidate)


def _sp500_rows(count):
    return [
        {
            "symbol": f"T{i:03d}",
            "security": f"Test Company {i}",
            "sector": "Technology",
            "sub_industry": "Software",
        }
        for i in range(count)
    ]


def _write_constituents(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=["symbol", "security", "sector", "sub_industry"])
        writer.writeheader()
        writer.writerows(rows)


def _write_sti_constituents(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = ["symbol", "display_symbol", "security", "sector", "sub_industry"]
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _read_symbols(path):
    with path.open(newline="", encoding="utf-8") as fh:
        return [row["symbol"] for row in csv.DictReader(fh)]


def _read_rows(path):
    with path.open(newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))
