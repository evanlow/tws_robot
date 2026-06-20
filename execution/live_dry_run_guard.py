"""Runtime guardrails for live dry-run execution.

The default live dry-run path intentionally avoids attaching a live TWS adapter
because no order should leave the process.  ``OrderExecutor`` still runs the
same safety pipeline, including portfolio reconciliation.  Without this guard,
a dry-run executor with ``tws_adapter=None`` can fail before reaching the
``DRY_RUN`` outcome.

This guard makes that rehearsal path explicit:

* dry-run + no adapter: skip broker reconciliation because no live order will be
  submitted;
* non-dry-run + no adapter: fail closed instead of raising an AttributeError.

The guard is installed by the Flask application factory so web-triggered live
rehearsals exercise the full non-ordering pipeline safely.
"""

from __future__ import annotations

import logging
from typing import Any, Dict

from execution.order_executor import OrderExecutor

logger = logging.getLogger(__name__)


_ORIGINAL_ATTR = "_original_reconcile_portfolio_before_dry_run_guard"
_INSTALLED_ATTR = "_live_dry_run_reconciliation_guard_installed"


def install_live_dry_run_reconciliation_guard() -> None:
    """Install a fail-closed reconciliation guard on :class:`OrderExecutor`.

    This function is idempotent.  It avoids changing normal paper/live
    reconciliation semantics when an adapter is present.
    """

    if getattr(OrderExecutor, _INSTALLED_ATTR, False):
        return

    original = OrderExecutor._reconcile_portfolio

    def _reconcile_portfolio_with_dry_run_guard(
        self: OrderExecutor,
        positions: Dict[str, Any],
    ) -> bool:
        if self.tws_adapter is None:
            if self.dry_run:
                logger.info(
                    "Skipping TWS portfolio reconciliation for dry-run executor "
                    "with no TWS adapter attached; no order can be submitted."
                )
                return True

            logger.error(
                "Portfolio reconciliation failed closed: non-dry-run executor "
                "has no TWS adapter attached."
            )
            return False

        return original(self, positions)

    setattr(OrderExecutor, _ORIGINAL_ATTR, original)
    OrderExecutor._reconcile_portfolio = _reconcile_portfolio_with_dry_run_guard
    setattr(OrderExecutor, _INSTALLED_ATTR, True)
