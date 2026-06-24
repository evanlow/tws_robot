#!/usr/bin/env python3
"""Compatibility wrapper for refreshing S&P 500 constituents.

The maintained implementation now lives in ``web.maintenance`` so refreshes are
validated, backed up, cache-invalidated, and reported consistently.
"""

import json
import sys

from web.maintenance.runner import MaintenanceRunner
from web.maintenance.tasks import STATUS_FAILED


def main() -> int:
    report = MaintenanceRunner().run(tasks=["sp500_constituents"], dry_run=False)
    print(json.dumps(report.to_dict(), indent=2, sort_keys=True))
    return 1 if report.status == STATUS_FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
