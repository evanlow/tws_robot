"""Run the core smoke test suite.

Usage:
    Scripts/python.exe tests/run_all_smoke.py
    Scripts/python.exe tests/run_all_smoke.py -k emergency
    Scripts/python.exe tests/run_all_smoke.py -- -x

By default, this script runs smoke-focused test modules that cover critical
safety, auth, API, and execution paths.
"""

from __future__ import annotations

import argparse
import sys

import pytest


DEFAULT_SMOKE_TARGETS = [
    "tests/test_safety_regression.py",
    "tests/test_web_api.py",
    "tests/test_portfolio_analysis.py",
    "tests/test_auth.py",
    "tests/test_config_security.py",
    "tests/test_order_executor.py",
    "tests/test_tws_bridge.py",
    "tests/test_fx_research.py",
]


def parse_args() -> tuple[argparse.Namespace, list[str]]:
    parser = argparse.ArgumentParser(
        description="Run the TWS Robot smoke suite.",
    )
    parser.add_argument(
        "pytest_args",
        nargs="*",
        help="Optional extra pytest args (for example: -k emergency -x).",
    )
    # Allow direct pytest flags (for example: -q, -k, -x) without forcing
    # users to add "--" in front of them.
    return parser.parse_known_args()


def main() -> int:
    args, passthrough = parse_args()

    pytest_cmd = [*DEFAULT_SMOKE_TARGETS, *args.pytest_args, *passthrough]
    print("Running smoke suite:")
    for target in DEFAULT_SMOKE_TARGETS:
        print(f"  - {target}")
    extra_args = [*args.pytest_args, *passthrough]
    if extra_args:
        print("Extra pytest args:", " ".join(extra_args))

    return pytest.main(pytest_cmd)


if __name__ == "__main__":
    raise SystemExit(main())
