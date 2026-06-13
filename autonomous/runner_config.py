"""Configuration for the autonomous runners (paper and live).

These defaults are deliberately conservative.  The runners are intended
to be invoked manually (one ``run_once`` call at a time) and any
future scheduler must remain opt-in.

Hard rules baked into the paper defaults:

* ``runner_enabled = False`` — no background loop starts automatically.
* ``paper_only = True`` — runner refuses to act unless connected to
  the IBKR paper account.
* ``buy_shares_only = True`` — only ``BUY_SHARES`` trades are
  eligible for autonomous entry/exit in this MVP.

Hard rules baked into the live defaults:

* ``live_enabled = False`` — live mode is OFF by default.
* ``live_continuous_enabled = False`` — continuous live mode is OFF by default.
* ``live_dry_run = False`` — full live orders are OFF by default; set to
  ``True`` to rehearse the full live lifecycle without sending orders.
* ``live_limit_orders_only = True`` — market orders are never used.
* ``live_require_account_confirmation = True`` — explicit account ID
  confirmation is required before any live order is sent.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Optional


def _env_bool(name: str, default: bool) -> bool:
    """Parse a boolean environment variable.

    Accepts ``1/true/yes/on`` (case-insensitive) as truthy values.
    Any unrecognised value falls back to ``default`` so a typo in the
    operator's shell never silently flips a safety flag.
    """
    raw = os.environ.get(name)
    if raw is None:
        return default
    val = raw.strip().lower()
    if val in {"1", "true", "yes", "on"}:
        return True
    if val in {"0", "false", "no", "off", ""}:
        return False
    return default


@dataclass
class AutonomousRunnerConfig:
    """Runtime configuration for :class:`AutonomousPaperRunner`."""

    # ---- Safety toggles -----------------------------------------------
    runner_enabled: bool = False
    paper_only: bool = True
    buy_shares_only: bool = True

    # ---- Sizing / concurrency limits ----------------------------------
    max_new_trades_per_run: int = 1
    max_open_autonomous_trades: int = 1
    max_holding_days: int = 5

    # ---- Market-hours guard rails (informational; not currently enforced
    # by the runner — these fields are reserved for future use) ----------
    run_during_market_hours_only: bool = True
    avoid_first_minutes_after_open: int = 15
    avoid_last_minutes_before_close: int = 15

    # ---- Persistence --------------------------------------------------
    trade_store_path: str = "logs/autonomous_trades.jsonl"

    def to_dict(self) -> dict:
        return {
            "runner_enabled": self.runner_enabled,
            "paper_only": self.paper_only,
            "buy_shares_only": self.buy_shares_only,
            "max_new_trades_per_run": self.max_new_trades_per_run,
            "max_open_autonomous_trades": self.max_open_autonomous_trades,
            "max_holding_days": self.max_holding_days,
            "run_during_market_hours_only": self.run_during_market_hours_only,
            "avoid_first_minutes_after_open": self.avoid_first_minutes_after_open,
            "avoid_last_minutes_before_close": self.avoid_last_minutes_before_close,
            "trade_store_path": self.trade_store_path,
        }

    @classmethod
    def from_env(cls) -> "AutonomousRunnerConfig":
        """Build a config, allowing ``AUTONOMOUS_RUNNER_ENABLED`` to opt in.

        The runner stays off unless the operator explicitly sets
        ``AUTONOMOUS_RUNNER_ENABLED=true`` (or ``1``/``yes``/``on``) in
        the environment, or supplies an
        ``autonomous_runner_config`` override in the Flask app config.
        All other defaults remain the safe values defined above.
        """
        return cls(runner_enabled=_env_bool("AUTONOMOUS_RUNNER_ENABLED", False))


def _env_float(name: str, default: float) -> float:
    """Parse a float environment variable, falling back to ``default``."""
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        return float(raw.strip())
    except (ValueError, AttributeError):
        return default


def _env_int(name: str, default: int) -> int:
    """Parse an integer environment variable, falling back to ``default``."""
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        return int(raw.strip())
    except (ValueError, AttributeError):
        return default


@dataclass
class AutonomousLiveRunnerConfig:
    """Runtime configuration for :class:`AutonomousLiveRunner`.

    All live-mode flags default to **OFF / conservative** so that live
    trading requires explicit opt-in at every layer.

    Environment variables (all optional — safe defaults are used when unset):

    ``AUTONOMOUS_LIVE_ENABLED``
        Master switch for the live runner.  Defaults to ``false``.
    ``AUTONOMOUS_LIVE_CONTINUOUS_ENABLED``
        Allows repeated live cycles.  Defaults to ``false``.
    ``AUTONOMOUS_MAX_DEPLOYABLE_CASH_PCT``
        Fraction of deployable cash that may be deployed per trade.
        Default ``0.10`` (10 %).  Must be in ``(0, 1]``.
    ``AUTONOMOUS_MIN_DEPLOYABLE_CASH``
        Minimum deployable-cash balance below which live trading is
        refused.  Default ``1000.0``.
    ``AUTONOMOUS_MAX_OPEN_LIVE_TRADES``
        Maximum number of concurrent open autonomous live trades.
        Default ``1``.
    ``AUTONOMOUS_MAX_LIVE_TRADES_PER_DAY``
        Daily cap on live autonomous entries.  Default ``1``.
    ``AUTONOMOUS_LIVE_LIMIT_ORDERS_ONLY``
        When ``true`` (default), market orders are refused.
    ``AUTONOMOUS_LIVE_REQUIRE_ACCOUNT_CONFIRMATION``
        When ``true`` (default), the caller must supply a matching
        ``expected_account_id`` before any live order is placed.
    ``AUTONOMOUS_LIVE_DRY_RUN``
        When ``true``, the full live lifecycle runs but no order is sent
        to TWS.  Defaults to ``false``.
    """

    # ---- Master live-mode switches ------------------------------------
    live_enabled: bool = False
    live_continuous_enabled: bool = False

    # ---- Deployable-cash sizing cap ----------------------------------
    max_deployable_cash_pct: float = 0.10   # fraction, e.g. 0.10 = 10 %
    min_deployable_cash: float = 1000.0

    # ---- Concurrency / frequency limits ------------------------------
    max_open_live_trades: int = 1
    max_live_trades_per_day: int = 1

    # ---- Order safety rules ------------------------------------------
    live_limit_orders_only: bool = True
    live_require_account_confirmation: bool = True

    # ---- Dry-run (rehearsal) mode ------------------------------------
    live_dry_run: bool = False

    # ---- Shared with paper runner ------------------------------------
    buy_shares_only: bool = True
    max_holding_days: int = 5
    trade_store_path: str = "logs/autonomous_live_trades.jsonl"

    # ---- Expected account ID (set at activation time) ----------------
    expected_account_id: Optional[str] = None

    def __post_init__(self) -> None:
        if not (0 < self.max_deployable_cash_pct <= 1):
            raise ValueError(
                "max_deployable_cash_pct must be in (0, 1]; got "
                f"{self.max_deployable_cash_pct!r}"
            )
        if self.min_deployable_cash < 0:
            raise ValueError(
                "min_deployable_cash must be >= 0; got "
                f"{self.min_deployable_cash!r}"
            )
        if self.max_open_live_trades < 1:
            raise ValueError(
                "max_open_live_trades must be >= 1; got "
                f"{self.max_open_live_trades!r}"
            )
        if self.max_live_trades_per_day < 0:
            raise ValueError(
                "max_live_trades_per_day must be >= 0; got "
                f"{self.max_live_trades_per_day!r}"
            )

    def to_dict(self) -> dict:
        return {
            "live_enabled": self.live_enabled,
            "live_continuous_enabled": self.live_continuous_enabled,
            "max_deployable_cash_pct": self.max_deployable_cash_pct,
            "min_deployable_cash": self.min_deployable_cash,
            "max_open_live_trades": self.max_open_live_trades,
            "max_live_trades_per_day": self.max_live_trades_per_day,
            "live_limit_orders_only": self.live_limit_orders_only,
            "live_require_account_confirmation": self.live_require_account_confirmation,
            "live_dry_run": self.live_dry_run,
            "buy_shares_only": self.buy_shares_only,
            "max_holding_days": self.max_holding_days,
            "trade_store_path": self.trade_store_path,
            "expected_account_id": self.expected_account_id,
        }

    @classmethod
    def from_env(cls) -> "AutonomousLiveRunnerConfig":
        """Build a config from environment variables.

        Every live-mode toggle defaults to ``false``/off unless the
        operator explicitly opts in.  Numeric thresholds fall back to the
        conservative defaults defined on the class.
        """
        return cls(
            live_enabled=_env_bool("AUTONOMOUS_LIVE_ENABLED", False),
            live_continuous_enabled=_env_bool(
                "AUTONOMOUS_LIVE_CONTINUOUS_ENABLED", False
            ),
            max_deployable_cash_pct=_env_float(
                "AUTONOMOUS_MAX_DEPLOYABLE_CASH_PCT", 0.10
            ),
            min_deployable_cash=_env_float(
                "AUTONOMOUS_MIN_DEPLOYABLE_CASH", 1000.0
            ),
            max_open_live_trades=_env_int("AUTONOMOUS_MAX_OPEN_LIVE_TRADES", 1),
            max_live_trades_per_day=_env_int(
                "AUTONOMOUS_MAX_LIVE_TRADES_PER_DAY", 1
            ),
            live_limit_orders_only=_env_bool(
                "AUTONOMOUS_LIVE_LIMIT_ORDERS_ONLY", True
            ),
            live_require_account_confirmation=_env_bool(
                "AUTONOMOUS_LIVE_REQUIRE_ACCOUNT_CONFIRMATION", True
            ),
            live_dry_run=_env_bool("AUTONOMOUS_LIVE_DRY_RUN", False),
        )
