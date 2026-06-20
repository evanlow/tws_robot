"""Configuration for the Autonomous Trading module.

This config object holds **all** safety thresholds and feature flags for
``AutonomousTradingEngine``.  Defaults are deliberately conservative:

* Default mode is ``recommend_only`` (no orders ever placed).
* Live execution is disabled.
* User confirmation is required.
* Only one trade per day is allowed.
* Only limit orders are permitted.
* The market-regime guard requires a bullish SPY backdrop and can reduce or
  block exposure when VIX indicates volatility stress.

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
    # Optional split caps.  When set, override max_new_position_pct on
    # the deployable-cash and equity sides independently so a single
    # high-priced share is not blocked by a tight deployable-cash cap
    # while a tight equity guard still protects total exposure.  Each
    # must be in (0, 1].  ``None`` falls back to max_new_position_pct.
    max_position_deployable_cash_pct: Optional[float] = None
    max_position_equity_pct: Optional[float] = None
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

    # ---- Market-regime guard ------------------------------------------
    # The existing SPY gate stays active whenever a provider is wired.
    # These VIX settings add a volatility/fear overlay to the same gate.
    vix_guard_enabled: bool = True
    vix_missing_blocks_trade: bool = False
    vix_caution_level: float = 20.0
    vix_block_level: float = 30.0
    vix_caution_intraday_rise_pct: float = 2.5
    vix_block_intraday_rise_pct: float = 5.0
    vix_caution_size_multiplier: float = 0.50
    vix_high_size_multiplier: float = 0.25
    apply_market_regime_size_multiplier: bool = True

    # ---- Exit target mode ---------------------------------------------
    exit_target_mode: str = "resistance"  # "resistance" | "percent" | "adr_intraday"
    take_profit_pct: float = 0.08  # fallback percent target
    adr_lookback_days: int = 0
    adr_target_fraction: float = 0.50
    adr_max_target_pct: float = 0.03
    adr_min_target_pct: float = 0.005
    adr_respect_resistance_cap: bool = True

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
        for label, value in (
            ("max_position_deployable_cash_pct", self.max_position_deployable_cash_pct),
            ("max_position_equity_pct", self.max_position_equity_pct),
        ):
            if value is None:
                continue
            if value <= 0 or value > 1:
                raise ValueError(
                    f"{label} must be in (0, 1]; got {value!r}"
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
        if self.vix_caution_level <= 0 or self.vix_block_level <= 0:
            raise ValueError("VIX levels must be positive")
        if self.vix_caution_level > self.vix_block_level:
            raise ValueError("vix_caution_level must be <= vix_block_level")
        for label, value in (
            ("vix_caution_intraday_rise_pct", self.vix_caution_intraday_rise_pct),
            ("vix_block_intraday_rise_pct", self.vix_block_intraday_rise_pct),
        ):
            if value < 0:
                raise ValueError(f"{label} must be >= 0; got {value!r}")
        if self.vix_caution_intraday_rise_pct > self.vix_block_intraday_rise_pct:
            raise ValueError(
                "vix_caution_intraday_rise_pct must be <= "
                "vix_block_intraday_rise_pct"
            )
        for label, value in (
            ("vix_caution_size_multiplier", self.vix_caution_size_multiplier),
            ("vix_high_size_multiplier", self.vix_high_size_multiplier),
        ):
            if value <= 0 or value > 1:
                raise ValueError(
                    f"{label} must be greater than 0 and at most 1; got {value!r}"
                )
        # A multiplier of exactly 1.0 is a valid no-op: the engine only applies
        # the multiplier when size_multiplier < 1.0, so 1.0 leaves deployable
        # cash unchanged while still being a legal configuration value.

    def deployable_cash_cap_pct(self) -> float:
        """Effective per-trade cap as a fraction of deployable cash."""
        if self.max_position_deployable_cash_pct is not None:
            return self.max_position_deployable_cash_pct
        return self.max_new_position_pct

    def equity_cap_pct(self) -> float:
        """Effective per-trade cap as a fraction of account equity."""
        if self.max_position_equity_pct is not None:
            return self.max_position_equity_pct
        return self.max_new_position_pct

    def to_dict(self) -> dict:
        """Return a JSON-serialisable representation (used in audit log)."""
        return {
            "mode": self.mode.value,
            "allow_live_execution": self.allow_live_execution,
            "require_user_confirmation": self.require_user_confirmation,
            "max_trades_per_day": self.max_trades_per_day,
            "max_new_position_pct": self.max_new_position_pct,
            "max_position_deployable_cash_pct": self.max_position_deployable_cash_pct,
            "max_position_equity_pct": self.max_position_equity_pct,
            "min_deployable_cash": self.min_deployable_cash,
            "min_signal_strength": self.min_signal_strength,
            "required_signal_label": self.required_signal_label,
            "stock_universe": self.stock_universe,
            "prefer_cash_secured_put": self.prefer_cash_secured_put,
            "allow_share_buy": self.allow_share_buy,
            "allow_short_put": self.allow_short_put,
            "avoid_earnings_within_days": self.avoid_earnings_within_days,
            "vix_guard_enabled": self.vix_guard_enabled,
            "vix_missing_blocks_trade": self.vix_missing_blocks_trade,
            "vix_caution_level": self.vix_caution_level,
            "vix_block_level": self.vix_block_level,
            "vix_caution_intraday_rise_pct": self.vix_caution_intraday_rise_pct,
            "vix_block_intraday_rise_pct": self.vix_block_intraday_rise_pct,
            "vix_caution_size_multiplier": self.vix_caution_size_multiplier,
            "vix_high_size_multiplier": self.vix_high_size_multiplier,
            "apply_market_regime_size_multiplier": self.apply_market_regime_size_multiplier,
            "exit_target_mode": self.exit_target_mode,
            "take_profit_pct": self.take_profit_pct,
            "adr_lookback_days": self.adr_lookback_days,
            "adr_target_fraction": self.adr_target_fraction,
            "adr_max_target_pct": self.adr_max_target_pct,
            "adr_min_target_pct": self.adr_min_target_pct,
            "adr_respect_resistance_cap": self.adr_respect_resistance_cap,
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
