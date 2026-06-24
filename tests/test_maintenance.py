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


def test_maintenance_page_loads(client):
    response = client.get("/maintenance")

    assert response.status_code == 200
    assert b"System Maintenance" in response.data


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


def _read_symbols(path):
    with path.open(newline="", encoding="utf-8") as fh:
        return [row["symbol"] for row in csv.DictReader(fh)]
