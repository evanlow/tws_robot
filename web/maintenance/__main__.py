"""CLI entrypoint for system maintenance.

Usage examples:

    python -m web.maintenance run --dry-run
    python -m web.maintenance run --task hsi_constituents --apply
    python -m web.maintenance validate
"""

from __future__ import annotations

import argparse
import json
import sys

from web.maintenance.runner import MaintenanceRunner
from web.maintenance.tasks import STATUS_FAILED


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m web.maintenance")
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("run", help="Run maintenance tasks")
    run_parser.add_argument("--task", action="append", dest="tasks", help="Task to run; can be repeated")
    run_parser.add_argument("--dry-run", action="store_true", default=False, help="Preview changes without writes")
    run_parser.add_argument("--apply", action="store_true", default=False, help="Apply validated changes")
    run_parser.add_argument("--symbol", action="append", dest="symbols", help="Event symbol to refresh; can be repeated")
    run_parser.add_argument("--days", type=int, default=28, help="Market-events days ahead")
    run_parser.add_argument("--allow-large-change", action="store_true", help="Allow >25%% constituent count change")

    validate_parser = subparsers.add_parser("validate", help="Validate local metadata files only")
    validate_parser.add_argument("--json", action="store_true", dest="json_output", help="Print full JSON report")

    args = parser.parse_args(argv)
    runner = MaintenanceRunner()

    if args.command == "validate":
        report = runner.run(tasks=["metadata_validation"], dry_run=True)
        if args.json_output:
            print(json.dumps(report.to_dict(), indent=2, sort_keys=True))
        else:
            print(f"{report.report_id}: {report.status}")
        return 1 if report.status == STATUS_FAILED else 0

    dry_run = True
    if args.apply:
        dry_run = False
    elif args.dry_run:
        dry_run = True

    report = runner.run(
        tasks=args.tasks,
        dry_run=dry_run,
        event_symbols=args.symbols,
        days_ahead=args.days,
        allow_large_change=args.allow_large_change,
    )
    print(json.dumps(report.to_dict(), indent=2, sort_keys=True))
    return 1 if report.status == STATUS_FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
