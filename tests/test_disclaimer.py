"""Tests for the Risk & Liability Disclaimer gate.

Covers:
- Disclaimer module (is_accepted, save_acceptance, get_acceptance_record)
- /api/disclaimer/status  GET
- /api/disclaimer/accept  POST
- /api/connection/connect blocked until disclaimer is accepted
"""

import json
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

from web import create_app
from web.disclaimer import (
    RISK_DISCLAIMER_VERSION,
    get_acceptance_record,
    is_accepted,
    save_acceptance,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_acceptance_file(tmp_path: Path, *, version: str = RISK_DISCLAIMER_VERSION) -> Path:
    """Write a valid acceptance record to a temp file and return its path."""
    p = tmp_path / "disclaimer_acceptance.json"
    p.write_text(
        json.dumps(
            {
                "accepted_disclaimer": True,
                "disclaimer_version": version,
                "accepted_at": datetime.now(timezone.utc).isoformat(),
                "app_version": "test",
            }
        ),
        encoding="utf-8",
    )
    return p


# ---------------------------------------------------------------------------
# Unit tests — disclaimer module
# ---------------------------------------------------------------------------


class TestDisclaimerModule:
    def test_not_accepted_when_file_missing(self, tmp_path):
        assert is_accepted(file_path=tmp_path / "nonexistent.json") is False

    def test_not_accepted_when_version_mismatch(self, tmp_path):
        p = _make_acceptance_file(tmp_path, version="risk_disclaimer_v0")
        assert is_accepted(file_path=p) is False

    def test_accepted_when_current_version(self, tmp_path):
        p = _make_acceptance_file(tmp_path)
        assert is_accepted(file_path=p) is True

    def test_not_accepted_when_flag_false(self, tmp_path):
        p = tmp_path / "disclaimer_acceptance.json"
        p.write_text(
            json.dumps(
                {
                    "accepted_disclaimer": False,
                    "disclaimer_version": RISK_DISCLAIMER_VERSION,
                }
            ),
            encoding="utf-8",
        )
        assert is_accepted(file_path=p) is False

    def test_save_acceptance_creates_file(self, tmp_path):
        p = tmp_path / "disc.json"
        save_acceptance(app_version="1.0.0", file_path=p)
        assert p.exists()
        data = json.loads(p.read_text(encoding="utf-8"))
        assert data["accepted_disclaimer"] is True
        assert data["disclaimer_version"] == RISK_DISCLAIMER_VERSION
        assert data["app_version"] == "1.0.0"
        assert "accepted_at" in data

    def test_save_acceptance_overwrites_existing(self, tmp_path):
        p = _make_acceptance_file(tmp_path, version="risk_disclaimer_v0")
        save_acceptance(file_path=p)
        data = json.loads(p.read_text(encoding="utf-8"))
        assert data["disclaimer_version"] == RISK_DISCLAIMER_VERSION

    def test_get_acceptance_record_empty_when_missing(self, tmp_path):
        assert get_acceptance_record(file_path=tmp_path / "nope.json") == {}

    def test_get_acceptance_record_returns_data(self, tmp_path):
        p = _make_acceptance_file(tmp_path)
        record = get_acceptance_record(file_path=p)
        assert record["accepted_disclaimer"] is True
        assert record["disclaimer_version"] == RISK_DISCLAIMER_VERSION

    def test_version_constant_format(self):
        assert RISK_DISCLAIMER_VERSION.startswith("risk_disclaimer_v")


# ---------------------------------------------------------------------------
# Flask app fixture
# ---------------------------------------------------------------------------


@pytest.fixture
def app(monkeypatch):
    monkeypatch.setattr(
        "web.services.ServiceManager._start_market_events_refresh",
        lambda self: None,
    )
    return create_app({"TESTING": True, "LOGIN_DISABLED": True, "WTF_CSRF_ENABLED": False})


@pytest.fixture
def client(app):
    return app.test_client()


# ---------------------------------------------------------------------------
# API tests — /api/disclaimer/*
# ---------------------------------------------------------------------------


class TestDisclaimerAPI:
    def test_status_not_accepted(self, client, tmp_path, monkeypatch):
        """Status endpoint reports not-accepted when no file exists."""
        monkeypatch.setattr("web.disclaimer._DEFAULT_ACCEPTANCE_FILE", tmp_path / "disc.json")
        # Patch the imported reference in the route module too.
        import web.routes.api_disclaimer as route_mod
        monkeypatch.setattr(route_mod, "is_accepted", lambda: False)
        monkeypatch.setattr(route_mod, "get_acceptance_record", lambda: {})

        resp = client.get("/api/disclaimer/status")
        data = resp.get_json()
        assert resp.status_code == 200
        assert data["accepted"] is False
        assert data["current_version"] == RISK_DISCLAIMER_VERSION

    def test_status_accepted(self, client, tmp_path, monkeypatch):
        """Status endpoint reports accepted when file matches current version."""
        p = _make_acceptance_file(tmp_path)
        import web.routes.api_disclaimer as route_mod
        monkeypatch.setattr(route_mod, "is_accepted", lambda: True)
        monkeypatch.setattr(
            route_mod,
            "get_acceptance_record",
            lambda: {
                "accepted_disclaimer": True,
                "disclaimer_version": RISK_DISCLAIMER_VERSION,
                "accepted_at": "2025-01-01T00:00:00+00:00",
            },
        )

        resp = client.get("/api/disclaimer/status")
        data = resp.get_json()
        assert resp.status_code == 200
        assert data["accepted"] is True
        assert data["accepted_version"] == RISK_DISCLAIMER_VERSION

    def test_accept_saves_and_returns_accepted(self, client, tmp_path, monkeypatch):
        """POST /api/disclaimer/accept persists and returns status accepted."""
        saved = {}

        def _mock_save(app_version="unknown"):
            saved["app_version"] = app_version

        import web.routes.api_disclaimer as route_mod
        monkeypatch.setattr(route_mod, "save_acceptance", _mock_save)

        resp = client.post("/api/disclaimer/accept", json={"app_version": "1.2.3"})
        data = resp.get_json()
        assert resp.status_code == 200
        assert data["status"] == "accepted"
        assert data["disclaimer_version"] == RISK_DISCLAIMER_VERSION
        assert saved["app_version"] == "1.2.3"

    def test_accept_handles_save_error(self, client, monkeypatch):
        """POST /api/disclaimer/accept returns 500 when file cannot be written."""
        import web.routes.api_disclaimer as route_mod

        def _failing_save(app_version="unknown"):
            raise OSError("disk full")

        monkeypatch.setattr(route_mod, "save_acceptance", _failing_save)
        resp = client.post("/api/disclaimer/accept")
        assert resp.status_code == 500


# ---------------------------------------------------------------------------
# API tests — /api/connection/connect blocked by disclaimer
# ---------------------------------------------------------------------------


class TestConnectionDisclaimerGate:
    def test_connect_blocked_when_disclaimer_not_accepted(self, client, monkeypatch):
        """POST /api/connection/connect returns 403 when disclaimer not accepted."""
        import web.routes.api_connection as conn_mod
        monkeypatch.setattr(conn_mod, "is_accepted", lambda: False)

        resp = client.post("/api/connection/connect", json={"environment": "paper"})
        data = resp.get_json()
        assert resp.status_code == 403
        assert data["disclaimer_required"] is True
        assert data["required_version"] == RISK_DISCLAIMER_VERSION

    def test_connect_allowed_when_disclaimer_accepted(self, client, monkeypatch):
        """POST /api/connection/connect proceeds past the gate when disclaimer is accepted."""
        import web.routes.api_connection as conn_mod
        from web.services import ServiceManager

        monkeypatch.setattr(conn_mod, "is_accepted", lambda: True)

        def _connect_success(env, cfg, timeout=10):
            # Simulate successful TWS connection.
            from web import create_app as _ca
            pass  # No-op; we mock connect_tws below.

        with patch.object(ServiceManager, "connect_tws", return_value=False):
            # Even with connect_tws failing, we should get past the 403 gate.
            resp = client.post("/api/connection/connect", json={"environment": "paper"})

        # Should not be a 403 (disclaimer gate passed); 503 means TWS unreachable.
        assert resp.status_code != 403

    def test_changed_version_requires_reaccept(self, tmp_path):
        """A stored acceptance with an old version is not considered valid."""
        p = _make_acceptance_file(tmp_path, version="risk_disclaimer_v0")
        # New version not accepted yet.
        assert is_accepted(file_path=p) is False

    def test_current_version_is_accepted(self, tmp_path):
        """After saving acceptance, is_accepted returns True."""
        p = tmp_path / "disc.json"
        save_acceptance(file_path=p)
        assert is_accepted(file_path=p) is True
