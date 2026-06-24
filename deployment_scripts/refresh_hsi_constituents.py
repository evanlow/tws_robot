#!/usr/bin/env python3
"""Compatibility wrapper for refreshing HSI constituents.

The maintained implementation now lives in ``web.maintenance`` so refreshes are
validated, backed up, cache-invalidated, and reported consistently.
"""

from pathlib import Path
import json
import sys

# Allow direct execution via ``python deployment_scripts/refresh_hsi_constituents.py``
# without requiring the package to be installed first.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from web.maintenance.runner import MaintenanceRunner  # noqa: E402
from web.maintenance.tasks import STATUS_FAILED  # noqa: E402


def main() -> int:
    report = MaintenanceRunner().run(tasks=["hsi_constituents"], dry_run=False)
    print(json.dumps(report.to_dict(), indent=2, sort_keys=True))
    return 1 if report.status == STATUS_FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
