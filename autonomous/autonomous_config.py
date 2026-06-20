"""Configuration for the Autonomous Trading module.

This config object holds **all** safety thresholds and feature flags for
``AutonomousTradingEngine``.  Defaults are deliberately conservative:

* Default mode is ``recommend_only`` (no orders ever placed).
* Live execution is disabled.
* User confirmation is required.
* Only one trade per day is allowed.
* Only limit orders are permitted.
* Assisted-live trade plans require a valid stop/invalidation level.
* Basket planning is disabled by default and must be explicitly enabled.
* Risk-per-trade, volatility, fractional-edge, and drawdown sizing can only
  reduce position size by default.
* Expected-edge ranking is transparent and cannot bypass hard filters.
* The market-regime guard requires a bullish SPY backdrop and can reduce or
  block exposure when VIX indicates volatility stress.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional


class AutonomousMode(str, Enum):
    """Operating mode for the autonomous engine."""

    RECOMMEND_ONLY = "recommend_only"
    PAPER_EXECUTE = "paper_execute"
    ASSISTED_LIVE = "assisted_live"


@dataclass
class AutonomousTradingConfig:
    """Runtime configuration for the autonomous trading engine."""

    mode: AutonomousMode = AutonomousMode.RECOMMEND_ONLY
    allow_live_execution: bool = False
    require_user_confirmation: bool = True

    max_trades_per_day: int = 1
    max_new_position_pct: float = 0.10
    max_position_deployable_cash_pct: Optional[float] = None
    max_position_equity_pct: Optional[float] = None
    min_deployable_cash: float = 1000.0

    # ---- Risk-per-trade / volatility sizing ----------------------------
    risk_per_trade_sizing_enabled: bool = True
    max_risk_per_trade_equity_pct: float = 0.002
    volatility_sizing_enabled: bool = True
    volatility_reference_pct: float = 0.02
    volatility_min_size_multiplier: float = 0.25

    # ---- Fractional edge sizing overlay --------------------------------
    fractional_edge_sizing_enabled: bool = False
    fractional_edge_fraction: float = 0.10
    fractional_edge_min_trades: int = 100
    fractional_edge_max_position_pct: float = 0.01
    fractional_edge_retirement_mode_max_pct: float = 0.005
    fractional_edge_allow_size_increase: bool = False
    fractional_edge_can_reduce_size: bool = True

    # ---- Drawdown governor ---------------------------------------------
    drawdown_governor_enabled: bool = True
    strategy_drawdown_pct: float = 0.0

    # ---- Edge estimation / ranking -------------------------------------
    edge_ranking_enabled: bool = True
    min_expected_r: float = -1.0
    min_edge_confidence: float = 0.0
    edge_score_weight: float = 10.0

    # ---- Basket planning -----------------------------------------------
    basket_enabled: bool = False
    basket_max_size: int = 3
    basket_total_deployable_cash_pct: float = 0.005
    basket_single_position_deployable_cash_pct: float = 0.002
    basket_max_same_sector_positions: int = 1

    min_signal_strength: int = 100
    required_signal_label: str = "Confirmed Rebound"
    stock_universe: str = "sp500"

    prefer_cash_secured_put: bool = True
    allow_share_buy: bool = True
    allow_short_put: bool = True
    avoid_earnings_within_days: int = 7

    vix_guard_enabled: bool = True
    vix_missing_blocks_trade: bool = False
    vix_caution_level: float = 20.0
    vix_block_level: float = 30.0
    vix_caution_intraday_rise_pct: float = 2.5
    vix_block_intraday_rise_pct: float = 5.0
    vix_caution_size_multiplier: float = 0.50
    vix_high_size_multiplier: float = 0.25
    apply_market_regime_size_multiplier: bool = True

    support_resistance_lookback_days: int = 30

    exit_target_mode: str = "resistance"
    take_profit_pct: float = 0.08
    adr_lookback_days: int = 0
    adr_target_fraction: float = 0.50
    adr_max_target_pct: float = 0.03
    adr_min_target_pct: float = 0.005
    adr_respect_resistance_cap: bool = True
    require_stop_price_for_assisted_live: bool = True

    use_limit_orders_only: bool = True
    emergency_stop_file: str = "EMERGENCY_STOP"
    audit_log_dir: str = "logs"

    symbol_whitelist: Optional[List[str]] = None
    symbol_blacklist: List[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if isinstance(self.mode, str):
            self.mode = AutonomousMode(self.mode)
        if self.max_new_position_pct <= 0 or self.max_new_position_pct > 1:
            raise ValueError(f"max_new_position_pct must be in (0, 1], got {self.max_new_position_pct}")
        for label, value in (
            ("max_position_deployable_cash_pct", self.max_position_deployable_cash_pct),
            ("max_position_equity_pct", self.max_position_equity_pct),
        ):
            if value is not None and (value <= 0 or value > 1):
                raise ValueError(f"{label} must be in (0, 1], got {value}")
        if self.max_trades_per_day < 0:
            raise ValueError("max_trades_per_day must be >= 0")
        if self.min_deployable_cash < 0:
            raise ValueError("min_deployable_cash must be >= 0")
        if self.max_risk_per_trade_equity_pct <= 0 or self.max_risk_per_trade_equity_pct > 1:
            raise ValueError("max_risk_per_trade_equity_pct must be in (0, 1]")
        if self.volatility_reference_pct <= 0:
            raise ValueError("volatility_reference_pct must be > 0")
        if self.volatility_min_size_multiplier <= 0 or self.volatility_min_size_multiplier > 1:
            raise ValueError("volatility_min_size_multiplier must be in (0, 1]")
        if self.fractional_edge_fraction <= 0 or self.fractional_edge_fraction > 1:
            raise ValueError("fractional_edge_fraction must be in (0, 1]")
        if self.fractional_edge_min_trades < 0:
            raise ValueError("fractional_edge_min_trades must be >= 0")
        for label, value in (
            ("fractional_edge_max_position_pct", self.fractional_edge_max_position_pct),
            ("fractional_edge_retirement_mode_max_pct", self.fractional_edge_retirement_mode_max_pct),
        ):
            if value <= 0 or value > 1:
                raise ValueError(f"{label} must be in (0, 1]")
        if self.strategy_drawdown_pct < 0:
            raise ValueError("strategy_drawdown_pct must be >= 0")
        if self.edge_score_weight < 0:
            raise ValueError("edge_score_weight must be >= 0")
        if self.min_edge_confidence < 0 or self.min_edge_confidence > 1:
            raise ValueError("min_edge_confidence must be in [0, 1]")
        if self.basket_max_size < 1:
            raise ValueError("basket_max_size must be >= 1")
        if self.basket_max_same_sector_positions < 1:
            raise ValueError("basket_max_same_sector_positions must be >= 1")
        for label, value in (
            ("basket_total_deployable_cash_pct", self.basket_total_deployable_cash_pct),
            ("basket_single_position_deployable_cash_pct", self.basket_single_position_deployable_cash_pct),
        ):
            if value <= 0 or value > 1:
                raise ValueError(f"{label} must be in (0, 1]")
        if self.basket_single_position_deployable_cash_pct > self.basket_total_deployable_cash_pct:
            raise ValueError("basket_single_position_deployable_cash_pct must be <= basket_total_deployable_cash_pct")
        if self.min_signal_strength < 0:
            raise ValueError("min_signal_strength must be >= 0")
        if self.support_resistance_lookback_days < 0:
            raise ValueError("support_resistance_lookback_days must be >= 0")
        if self.vix_caution_level <= 0 or self.vix_block_level <= 0:
            raise ValueError("VIX levels must be positive")
        if self.vix_caution_level > self.vix_block_level:
            raise ValueError("vix_caution_level must be <= vix_block_level")
        for label, value in (
            ("vix_caution_intraday_rise_pct", self.vix_caution_intraday_rise_pct),
            ("vix_block_intraday_rise_pct", self.vix_block_intraday_rise_pct),
        ):
            if value < 0:
                raise ValueError(f"{label} must be >= 0")
        if self.vix_caution_intraday_rise_pct > self.vix_block_intraday_rise_pct:
            raise ValueError("vix_caution_intraday_rise_pct must be <= vix_block_intraday_rise_pct")
        for label, value in (
            ("vix_caution_size_multiplier", self.vix_caution_size_multiplier),
            ("vix_high_size_multiplier", self.vix_high_size_multiplier),
        ):
            if value <= 0 or value > 1:
                raise ValueError(f"{label} must be greater than 0 and at most 1.0")

    def deployable_cash_cap_pct(self) -> float:
        if self.max_position_deployable_cash_pct is not None:
            return self.max_position_deployable_cash_pct
        return self.max_new_position_pct

    def equity_cap_pct(self) -> float:
        if self.max_position_equity_pct is not None:
            return self.max_position_equity_pct
        return self.max_new_position_pct

    def to_dict(self) -> dict:
        return {
            "mode": self.mode.value,
            "allow_live_execution": self.allow_live_execution,
            "require_user_confirmation": self.require_user_confirmation,
            "max_trades_per_day": self.max_trades_per_day,
            "max_new_position_pct": self.max_new_position_pct,
            "max_position_deployable_cash_pct": self.max_position_deployable_cash_pct,
            "max_position_equity_pct": self.max_position_equity_pct,
            "min_deployable_cash": self.min_deployable_cash,
            "risk_per_trade_sizing_enabled": self.risk_per_trade_sizing_enabled,
            "max_risk_per_trade_equity_pct": self.max_risk_per_trade_equity_pct,
            "volatility_sizing_enabled": self.volatility_sizing_enabled,
            "volatility_reference_pct": self.volatility_reference_pct,
            "volatility_min_size_multiplier": self.volatility_min_size_multiplier,
            "fractional_edge_sizing_enabled": self.fractional_edge_sizing_enabled,
            "fractional_edge_fraction": self.fractional_edge_fraction,
            "fractional_edge_min_trades": self.fractional_edge_min_trades,
            "fractional_edge_max_position_pct": self.fractional_edge_max_position_pct,
            "fractional_edge_retirement_mode_max_pct": self.fractional_edge_retirement_mode_max_pct,
            "fractional_edge_allow_size_increase": self.fractional_edge_allow_size_increase,
            "fractional_edge_can_reduce_size": self.fractional_edge_can_reduce_size,
            "drawdown_governor_enabled": self.drawdown_governor_enabled,
            "strategy_drawdown_pct": self.strategy_drawdown_pct,
            "edge_ranking_enabled": self.edge_ranking_enabled,
            "min_expected_r": self.min_expected_r,
            "min_edge_confidence": self.min_edge_confidence,
            "edge_score_weight": self.edge_score_weight,
            "basket_enabled": self.basket_enabled,
            "basket_max_size": self.basket_max_size,
            "basket_total_deployable_cash_pct": self.basket_total_deployable_cash_pct,
            "basket_single_position_deployable_cash_pct": self.basket_single_position_deployable_cash_pct,
            "basket_max_same_sector_positions": self.basket_max_same_sector_positions,
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
            "support_resistance_lookback_days": self.support_resistance_lookback_days,
            "exit_target_mode": self.exit_target_mode,
            "take_profit_pct": self.take_profit_pct,
            "adr_lookback_days": self.adr_lookback_days,
            "adr_target_fraction": self.adr_target_fraction,
            "adr_max_target_pct": self.adr_max_target_pct,
            "adr_min_target_pct": self.adr_min_target_pct,
            "adr_respect_resistance_cap": self.adr_respect_resistance_cap,
            "require_stop_price_for_assisted_live": self.require_stop_price_for_assisted_live,
            "use_limit_orders_only": self.use_limit_orders_only,
            "emergency_stop_file": self.emergency_stop_file,
            "audit_log_dir": self.audit_log_dir,
            "symbol_whitelist": list(self.symbol_whitelist) if self.symbol_whitelist is not None else None,
            "symbol_blacklist": list(self.symbol_blacklist),
        }
