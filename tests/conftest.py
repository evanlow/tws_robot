"""Shared pytest fixtures for the tws_robot test suite."""

from pathlib import Path

import pytest

from tests.smoke_manifest import SMOKE_TEST_MODULES


@pytest.fixture(autouse=True)
def _isolate_stop_file(tmp_path, monkeypatch):
    """Redirect EMERGENCY_STOP_FILE to tmp_path so tests don't pollute CWD."""
    from web.routes import api_autonomous, api_emergency

    monkeypatch.setattr(api_emergency, "EMERGENCY_STOP_FILE", tmp_path / "EMERGENCY_STOP")
    monkeypatch.setattr(api_autonomous, "EMERGENCY_STOP_FILE", tmp_path / "EMERGENCY_STOP")


def pytest_collection_modifyitems(config, items):
    """Apply the smoke marker from the maintained smoke inventory."""

    for item in items:
        if Path(str(item.path)).name in SMOKE_TEST_MODULES:
            item.add_marker(pytest.mark.smoke)
