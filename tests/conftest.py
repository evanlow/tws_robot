"""Shared pytest fixtures for the tws_robot test suite."""

import pytest


@pytest.fixture(autouse=True)
def _isolate_stop_file(tmp_path, monkeypatch):
    """Redirect EMERGENCY_STOP_FILE to tmp_path so tests don't pollute CWD."""
    from web.routes import api_autonomous, api_emergency

    monkeypatch.setattr(api_emergency, "EMERGENCY_STOP_FILE", tmp_path / "EMERGENCY_STOP")
    monkeypatch.setattr(api_autonomous, "EMERGENCY_STOP_FILE", tmp_path / "EMERGENCY_STOP")
