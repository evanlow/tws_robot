"""Run the core smoke test suite.

Usage:
    Scripts/python.exe tests/run_all_smoke.py
    Scripts/python.exe tests/run_all_smoke.py -k emergency
    Scripts/python.exe tests/run_all_smoke.py -- -x

By default, this script runs tests marked ``smoke``. The smoke inventory lives
in ``tests/smoke_manifest.py`` and is applied during pytest collection.
"""

from __future__ import annotations

from pathlib import Path
import sys

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tests.smoke_manifest import SMOKE_TEST_MODULES


def main() -> int:
    pytest_args = _normalise_pytest_args(sys.argv[1:])
    pytest_cmd = ["-m", "smoke"]
    if not _requests_coverage(pytest_args):
        pytest_cmd.append("--no-cov")
    pytest_cmd.extend(pytest_args)

    print(f"Running smoke suite from {len(SMOKE_TEST_MODULES)} marked modules.")
    if pytest_args:
        print("Extra pytest args:", " ".join(pytest_args))

    return pytest.main(pytest_cmd)


def _normalise_pytest_args(args: list[str]) -> list[str]:
    """Allow both ``run_all_smoke.py -k x`` and ``run_all_smoke.py -- -k x``."""

    if args and args[0] == "--":
        return args[1:]
    return args


def _requests_coverage(args: list[str]) -> bool:
    return any(
        arg == "--cov" or arg == "--no-cov" or arg.startswith("--cov=")
        for arg in args
    )


if __name__ == "__main__":
    raise SystemExit(main())
