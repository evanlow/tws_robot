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
* ``max_deployable_cash_pct = 0.005`` — first live experiments are capped to
  0.5% of deployable cash unless the operator explicitly overrides it.
* ``require_plan_stop_for_live = True`` — planner-derived stop/invalidation
  levels are preferred for live entries.  If a live plan still reaches the
  runner without ``stop_price``, it falls back to the generic stop.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Optional


FIRST_LIVE_EXPERIMENT_MAX_DEPLOYABLE_CASH_PCT = 0.005


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
        Default ``0.005`` (0.5 %) for first live experiments. Must be in
        ``(0, 1]``. Operators can explicitly override this only after the
        first-live checklist is complete.
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
    ``AUTONOMOUS_REQUIRE_PLAN_STOP_FOR_LIVE``
        When ``true`` (default), actual live and live dry-run entries prefer
        a planner-provided ``stop_price``.  If a live plan still reaches the
        runner without it, the runner falls back to the generic stop derived
        from ``AUTONOMOUS_DEFAULT_STOP_PCT``.
    ``AUTONOMOUS_DEFAULT_STOP_PCT``
        Fallback stop-loss distance below the entry limit price used
        when a live plan reaches the runner without ``stop_price``.  Default
        ``0.05`` (5 %).  Must be in ``(0, 1)``.
    ``AUTONOMOUS_ORDER_LIFECYCLE_STORE_PATH``
        Append-only lifecycle event log for live autonomous broker orders.
        Default ``logs/autonomous_order_lifecycle.jsonl``.
    ``AUTONOMOUS_REQUIRE_BROKER_PROTECTION_CONFIRMATION``
        When ``true`` (default), open live autonomous positions must have a
        broker-visible protective stop/bracket order before new live entries
        are allowed.
    ``AUTONOMOUS_IDEMPOTENCY_STORE_PATH``
        Append-only idempotency lock log for live autonomous entries.
        Default ``logs/autonomous_idempotency.jsonl``.
    ``AUTONOMOUS_ALLOW_DUPLICATE_SYMBOL_LIVE_ENTRIES``
        When ``false`` (default), an open autonomous live trade or active
        idempotency lock for a symbol blocks another live entry for that
        symbol.
    ``AUTONOMOUS_IDEMPOTENCY_STALE_MINUTES``
        Age threshold used by stale-lock inspection helpers.  Default ``120``.
    ``LIVE_MARKET_DATA_PROVIDER``
        Required provider for live autonomous execution.  Default ``ibkr``.
    ``ALLOW_YAHOO_FOR_LIVE_TRADING``
        Defaults to ``false``.  Yahoo Finance may be advisory, but cannot
        satisfy live autonomous execution quote requirements.
    ``MAX_LIVE_QUOTE_AGE_SECONDS``
        Maximum age for live IBKR quote snapshots.  Default ``5`` seconds.
    """

    # ---- Master live-mode switches ------------------------------------
    live_enabled: bool = False
    live_continuous_enabled: bool = False

    # ---- Deployable-cash sizing cap ----------------------------------
    max_deployable_cash_pct: float = FIRST_LIVE_EXPERIMENT_MAX_DEPLOYABLE_CASH_PCT
    min_deployable_cash: float = 1000.0

    # ---- Concurrency / frequency limits ------------------------------
    max_open_live_trades: int = 1
    max_live_trades_per_day: int = 1

    # ---- Order safety rules ------------------------------------------
    live_limit_orders_only: bool = True
    live_require_account_confirmation: bool = True
    require_plan_stop_for_live: bool = True
    require_broker_protection_confirmation: bool = True
    allow_duplicate_symbol_live_entries: bool = False

    # ---- Dry-run (rehearsal) mode ------------------------------------
    live_dry_run: bool = False

    # ---- Bracket exit defaults ---------------------------------------
    # Fallback stop-loss distance below entry when the planner does not
    # supply a stop_price.
    default_stop_pct: float = 0.05

    # ---- Shared with paper runner ------------------------------------
    buy_shares_only: bool = True
    max_holding_days: int = 5
    trade_store_path: str = "logs/autonomous_live_trades.jsonl"
    order_lifecycle_store_path: str = "logs/autonomous_order_lifecycle.jsonl"
    idempotency_store_path: str = "logs/autonomous_idempotency.jsonl"
    idempotency_stale_minutes: int = 120
    live_market_data_provider: str = "ibkr"
    allow_yahoo_for_live_trading: bool = False
    max_live_quote_age_seconds: float = 5.0

    # ---- Expected account ID (set at activation time) ----------------
    expected_account_id: Optional[str] = None

    def __post_init__(self) -> None:
        # max_deployable_cash_pct must be in the range (0, 1].
        # Values above 0 and up to and including 1.0 (100%) are intentionally
        # allowed, but the default is deliberately tiny for first live tests.
        if not (0 < self.max_deployable_cash_pct <= 1):
            raise ValueError(
                "max_deployable_cash_pct must be in (0, 1] (exclusive of 0, "
                f"inclusive of 1.0); got {self.max_deployable_cash_pct!r}"
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
        if self.idempotency_stale_minutes < 0:
            raise ValueError(
                "idempotency_stale_minutes must be >= 0; got "
                f"{self.idempotency_stale_minutes!r}"
            )
        if not (0 < self.default_stop_pct < 1):
            raise ValueError(
                "default_stop_pct must be in (0, 1); got "
                f"{self.default_stop_pct!r}"
            )
        if str(self.live_market_data_provider or "").strip().lower() != "ibkr":
            raise ValueError("live_market_data_provider must be 'ibkr'")
        if self.max_live_quote_age_seconds < 0:
            raise ValueError("max_live_quote_age_seconds must be >= 0")

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
            "require_plan_stop_for_live": self.require_plan_stop_for_live,
            "require_broker_protection_confirmation": (
                self.require_broker_protection_confirmation
            ),
            "allow_duplicate_symbol_live_entries": self.allow_duplicate_symbol_live_entries,
            "live_dry_run": self.live_dry_run,
            "default_stop_pct": self.default_stop_pct,
            "buy_shares_only": self.buy_shares_only,
            "max_holding_days": self.max_holding_days,
            "trade_store_path": self.trade_store_path,
            "order_lifecycle_store_path": self.order_lifecycle_store_path,
            "idempotency_store_path": self.idempotency_store_path,
            "idempotency_stale_minutes": self.idempotency_stale_minutes,
            "live_market_data_provider": self.live_market_data_provider,
            "allow_yahoo_for_live_trading": self.allow_yahoo_for_live_trading,
            "max_live_quote_age_seconds": self.max_live_quote_age_seconds,
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
                "AUTONOMOUS_MAX_DEPLOYABLE_CASH_PCT",
                FIRST_LIVE_EXPERIMENT_MAX_DEPLOYABLE_CASH_PCT,
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
            require_plan_stop_for_live=_env_bool(
                "AUTONOMOUS_REQUIRE_PLAN_STOP_FOR_LIVE", True
            ),
            require_broker_protection_confirmation=_env_bool(
                "AUTONOMOUS_REQUIRE_BROKER_PROTECTION_CONFIRMATION", True
            ),
            allow_duplicate_symbol_live_entries=_env_bool(
                "AUTONOMOUS_ALLOW_DUPLICATE_SYMBOL_LIVE_ENTRIES", False
            ),
            live_dry_run=_env_bool("AUTONOMOUS_LIVE_DRY_RUN", False),
            default_stop_pct=_env_float("AUTONOMOUS_DEFAULT_STOP_PCT", 0.05),
            order_lifecycle_store_path=os.environ.get(
                "AUTONOMOUS_ORDER_LIFECYCLE_STORE_PATH",
                "logs/autonomous_order_lifecycle.jsonl",
            ),
            idempotency_store_path=os.environ.get(
                "AUTONOMOUS_IDEMPOTENCY_STORE_PATH",
                "logs/autonomous_idempotency.jsonl",
            ),
            idempotency_stale_minutes=_env_int(
                "AUTONOMOUS_IDEMPOTENCY_STALE_MINUTES", 120
            ),
            live_market_data_provider=os.environ.get(
                "LIVE_MARKET_DATA_PROVIDER",
                "ibkr",
            ).strip().lower() or "ibkr",
            allow_yahoo_for_live_trading=_env_bool(
                "ALLOW_YAHOO_FOR_LIVE_TRADING",
                False,
            ),
            max_live_quote_age_seconds=_env_float(
                "MAX_LIVE_QUOTE_AGE_SECONDS",
                5.0,
            ),
        )
