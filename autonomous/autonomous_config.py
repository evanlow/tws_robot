"""Configuration for the Autonomous Trading module.

This config object holds **all** safety thresholds and feature flags for
``AutonomousTradingEngine``.  Defaults are deliberately conservative:

* Default mode is ``recommend_only`` (no orders ever placed).
* Live execution is disabled.
* User confirmation is required.
* Only one trade per day is allowed.
* Only limit orders are permitted.

All numeric thresholds are documented inline; callers may override any of
them when constructing ``AutonomousTradingConfig``.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional


class AutonomousMode(str, Enum):
    """Operating mode for the autonomous engine.

    * ``RECOMMEND_ONLY`` — return a trade plan but never place any order.
    * ``PAPER_EXECUTE`` — place the trade only via the paper-trading adapter.
    * ``ASSISTED_LIVE`` — may place a live order, *but* only when
      ``AutonomousTradingConfig.allow_live_execution`` is True **and** the
      caller passes ``confirm=True`` to the engine.
    """

    RECOMMEND_ONLY = "recommend_only"
    PAPER_EXECUTE = "paper_execute"
    ASSISTED_LIVE = "assisted_live"


@dataclass
class AutonomousTradingConfig:
    """Runtime configuration for the autonomous trading engine.

    Hard rule: live execution must default to disabled.  ``allow_live_execution``
    is False by default and must be explicitly opted into.
    """

    # ---- Mode and execution gating ------------------------------------
    mode: AutonomousMode = AutonomousMode.RECOMMEND_ONLY
    allow_live_execution: bool = False
    require_user_confirmation: bool = True

    # ---- Trade frequency / sizing -------------------------------------
    max_trades_per_day: int = 1
    max_new_position_pct: float = 0.10  # of equity
    min_deployable_cash: float = 1000.0

    # ---- Signal filter ------------------------------------------------
    min_signal_strength: int = 100
    required_signal_label: str = "Confirmed Rebound"

    # ---- Universe -----------------------------------------------------
    stock_universe: str = "sp500"

    # ---- Trade-type preferences --------------------------------------
    prefer_cash_secured_put: bool = True
    allow_share_buy: bool = True
    allow_short_put: bool = True

    # ---- Earnings avoidance ------------------------------------------
    avoid_earnings_within_days: int = 7

    # ---- Order style --------------------------------------------------
    use_limit_orders_only: bool = True

    # ---- Emergency stop file -----------------------------------------
    emergency_stop_file: str = "EMERGENCY_STOP"

    # ---- Audit log ---------------------------------------------------
    audit_log_dir: str = "logs"

    # ---- Symbol restrictions (optional) ------------------------------
    symbol_whitelist: Optional[List[str]] = None
    symbol_blacklist: List[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        # Normalise mode to enum if a string was provided.
        if isinstance(self.mode, str):
            self.mode = AutonomousMode(self.mode)

        # Defensive numeric guards.
        if self.max_new_position_pct <= 0 or self.max_new_position_pct > 1:
            raise ValueError(
                "max_new_position_pct must be in (0, 1]; got "
                f"{self.max_new_position_pct!r}"
            )
        if self.max_trades_per_day < 0:
            raise ValueError(
                "max_trades_per_day must be >= 0; got "
                f"{self.max_trades_per_day!r}"
            )
        if self.min_deployable_cash < 0:
            raise ValueError(
                "min_deployable_cash must be >= 0; got "
                f"{self.min_deployable_cash!r}"
            )
        if self.min_signal_strength < 0:
            raise ValueError(
                "min_signal_strength must be >= 0; got "
                f"{self.min_signal_strength!r}"
            )

    def to_dict(self) -> dict:
        """Return a JSON-serialisable representation (used in audit log)."""
        return {
            "mode": self.mode.value,
            "allow_live_execution": self.allow_live_execution,
            "require_user_confirmation": self.require_user_confirmation,
            "max_trades_per_day": self.max_trades_per_day,
            "max_new_position_pct": self.max_new_position_pct,
            "min_deployable_cash": self.min_deployable_cash,
            "min_signal_strength": self.min_signal_strength,
            "required_signal_label": self.required_signal_label,
            "stock_universe": self.stock_universe,
            "prefer_cash_secured_put": self.prefer_cash_secured_put,
            "allow_share_buy": self.allow_share_buy,
            "allow_short_put": self.allow_short_put,
            "avoid_earnings_within_days": self.avoid_earnings_within_days,
            "use_limit_orders_only": self.use_limit_orders_only,
            "emergency_stop_file": self.emergency_stop_file,
            "audit_log_dir": self.audit_log_dir,
            "symbol_whitelist": (
                list(self.symbol_whitelist)
                if self.symbol_whitelist is not None
                else None
            ),
            "symbol_blacklist": list(self.symbol_blacklist),
        }
