"""Configuration for the Autonomous Trading module."""

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional


class AutonomousMode(str, Enum):
    RECOMMEND_ONLY = "recommend_only"
    PAPER_EXECUTE = "paper_execute"
    ASSISTED_LIVE = "assisted_live"


@dataclass
class AutonomousTradingConfig:
    mode: AutonomousMode = AutonomousMode.RECOMMEND_ONLY
    allow_live_execution: bool = False
    require_user_confirmation: bool = True

    max_trades_per_day: int = 1
    max_new_position_pct: float = 0.10
    max_position_deployable_cash_pct: Optional[float] = None
    max_position_equity_pct: Optional[float] = None
    min_deployable_cash: float = 1000.0

    risk_per_trade_sizing_enabled: bool = True
    max_risk_per_trade_equity_pct: float = 0.002
    volatility_sizing_enabled: bool = True
    volatility_reference_pct: float = 0.02
    volatility_min_size_multiplier: float = 0.25

    fractional_edge_sizing_enabled: bool = False
    fractional_edge_fraction: float = 0.10
    fractional_edge_min_trades: int = 100
    fractional_edge_max_position_pct: float = 0.01
    fractional_edge_retirement_mode_max_pct: float = 0.005
    fractional_edge_allow_size_increase: bool = False
    fractional_edge_can_reduce_size: bool = True

    evidence_aware_sizing_enabled: bool = False
    evidence_aware_min_trades_for_tiny_live: int = 20
    evidence_aware_min_trades_for_normal: int = 100
    evidence_aware_tiny_live_max_position_pct: float = 0.001
    evidence_aware_reduced_size_multiplier: float = 0.50
    evidence_aware_min_confidence_for_normal: float = 0.60
    evidence_aware_strong_expected_r: float = 0.25
    evidence_aware_max_drawdown_r_for_normal: float = 8.00
    evidence_aware_max_slippage_bps_for_normal: float = 50.0
    evidence_aware_allow_size_increase: bool = False

    drawdown_governor_enabled: bool = True
    strategy_drawdown_pct: float = 0.0

    # Commission-aware minimum-profitability gate.  When enabled, a planned
    # share buy is rejected before submission if its expected net profit at
    # target (gross profit minus estimated round-trip commission) falls below
    # the configured minimum.  Disabled by default so existing behavior is
    # unchanged until an operator opts in.
    commission_aware_sizing_enabled: bool = False
    estimated_commission_per_order: float = 1.0
    min_net_profit_usd: float = 0.0
    min_net_profit_pct_of_trade: float = 0.0

    execution_quality_guard_enabled: bool = True
    execution_max_spread_pct: float = 0.003
    execution_max_slippage_pct: float = 0.005
    execution_max_price_move_pct: float = 0.01
    execution_block_on_missing_quote: bool = False
    market_data_health_guard_enabled: bool = True
    market_data_max_quote_age_seconds: float = 5.0
    market_data_max_spread_pct: float = 0.003
    market_data_max_last_mid_deviation_pct: float = 0.01
    market_data_block_stale_quotes_live: bool = True
    market_data_block_missing_bid_ask_live: bool = True
    market_data_block_missing_timestamp_live: bool = True
    market_data_block_feed_unhealthy_live: bool = True
    market_data_block_market_closed_live: bool = True
    live_market_data_required_source: str = "IBKR"
    live_market_data_require_live_type: bool = True
    allow_yahoo_for_live_trading: bool = False

    risk_lifecycle_guard_enabled: bool = True
    risk_lifecycle_recent_record_limit: int = 1000
    max_daily_loss_r: float = 2.0
    max_weekly_loss_r: float = 4.0
    max_monthly_loss_r: float = 6.0
    max_consecutive_losses: int = 3
    max_strategy_drawdown_r: float = 6.0

    edge_ranking_enabled: bool = True
    min_expected_r: float = -1.0
    min_edge_confidence: float = 0.0
    edge_score_weight: float = 10.0

    basket_enabled: bool = False
    basket_max_size: int = 3
    basket_total_deployable_cash_pct: float = 0.005
    basket_single_position_deployable_cash_pct: float = 0.002
    basket_max_same_sector_positions: int = 1
    basket_risk_allocator_enabled: bool = True
    max_basket_risk_equity_pct: float = 0.002
    basket_risk_allocation_mode: str = "equal_risk"
    basket_min_leg_risk_dollars: float = 20.0

    min_signal_strength: int = 100
    required_signal_label: str = "Confirmed Rebound"
    # Optional whitelist of acceptable ``signal_label`` values. When set (a
    # non-empty list), ``required_signal_label`` is ignored and a candidate
    # passes the label filter if its ``signal_label`` is a member of this
    # list. This lets alternate strategies (e.g. Opening Range Breakout,
    # which emits ``ORB_LONG_MODEL_A`` / ``ORB_LONG_MODEL_B`` labels) flow
    # through the ranker without forcing the ``Confirmed Rebound``
    # assumption. ``None`` (the default) preserves prior behaviour.
    allowed_signal_labels: Optional[List[str]] = None
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
            raise ValueError("max_new_position_pct must be in (0, 1]")
        for label, value in (
            ("max_position_deployable_cash_pct", self.max_position_deployable_cash_pct),
            ("max_position_equity_pct", self.max_position_equity_pct),
        ):
            if value is not None and (value <= 0 or value > 1):
                raise ValueError(f"{label} must be in (0, 1]")
        if self.max_trades_per_day < 0:
            raise ValueError("max_trades_per_day must be >= 0")
        if self.min_deployable_cash < 0:
            raise ValueError("min_deployable_cash must be >= 0")
        for label, value in (
            ("max_risk_per_trade_equity_pct", self.max_risk_per_trade_equity_pct),
            ("volatility_reference_pct", self.volatility_reference_pct),
            ("volatility_min_size_multiplier", self.volatility_min_size_multiplier),
            ("fractional_edge_fraction", self.fractional_edge_fraction),
            ("fractional_edge_max_position_pct", self.fractional_edge_max_position_pct),
            ("fractional_edge_retirement_mode_max_pct", self.fractional_edge_retirement_mode_max_pct),
            ("evidence_aware_tiny_live_max_position_pct", self.evidence_aware_tiny_live_max_position_pct),
            ("evidence_aware_reduced_size_multiplier", self.evidence_aware_reduced_size_multiplier),
            ("evidence_aware_min_confidence_for_normal", self.evidence_aware_min_confidence_for_normal),
            ("vix_caution_size_multiplier", self.vix_caution_size_multiplier),
            ("vix_high_size_multiplier", self.vix_high_size_multiplier),
        ):
            if value <= 0 or value > 1:
                raise ValueError(f"{label} must be in (0, 1]")
        if self.fractional_edge_min_trades < 0:
            raise ValueError("fractional_edge_min_trades must be >= 0")
        if self.evidence_aware_min_trades_for_tiny_live < 0:
            raise ValueError("evidence_aware_min_trades_for_tiny_live must be >= 0")
        if self.evidence_aware_min_trades_for_normal < self.evidence_aware_min_trades_for_tiny_live:
            raise ValueError("evidence_aware_min_trades_for_normal must be >= tiny-live threshold")
        for label, value in (
            ("evidence_aware_strong_expected_r", self.evidence_aware_strong_expected_r),
            ("evidence_aware_max_drawdown_r_for_normal", self.evidence_aware_max_drawdown_r_for_normal),
            ("evidence_aware_max_slippage_bps_for_normal", self.evidence_aware_max_slippage_bps_for_normal),
        ):
            if value < 0:
                raise ValueError(f"{label} must be >= 0")
        if self.strategy_drawdown_pct < 0 or self.strategy_drawdown_pct > 1:
            raise ValueError("strategy_drawdown_pct must be in [0, 1]")
        if self.estimated_commission_per_order < 0:
            raise ValueError("estimated_commission_per_order must be >= 0")
        if self.min_net_profit_usd < 0:
            raise ValueError("min_net_profit_usd must be >= 0")
        if self.min_net_profit_pct_of_trade < 0 or self.min_net_profit_pct_of_trade > 1:
            raise ValueError("min_net_profit_pct_of_trade must be in [0, 1]")
        for label, value in (
            ("execution_max_spread_pct", self.execution_max_spread_pct),
            ("execution_max_slippage_pct", self.execution_max_slippage_pct),
            ("execution_max_price_move_pct", self.execution_max_price_move_pct),
            ("market_data_max_spread_pct", self.market_data_max_spread_pct),
            ("market_data_max_last_mid_deviation_pct", self.market_data_max_last_mid_deviation_pct),
        ):
            if value < 0 or value > 1:
                raise ValueError(f"{label} must be in [0, 1]")
        if self.market_data_max_quote_age_seconds < 0:
            raise ValueError("market_data_max_quote_age_seconds must be >= 0")
        if not str(self.live_market_data_required_source or "").strip():
            raise ValueError("live_market_data_required_source must be non-empty")
        if self.risk_lifecycle_recent_record_limit < 1:
            raise ValueError("risk_lifecycle_recent_record_limit must be >= 1")
        for label, value in (
            ("max_daily_loss_r", self.max_daily_loss_r),
            ("max_weekly_loss_r", self.max_weekly_loss_r),
            ("max_monthly_loss_r", self.max_monthly_loss_r),
            ("max_strategy_drawdown_r", self.max_strategy_drawdown_r),
        ):
            if value < 0:
                raise ValueError(f"{label} must be >= 0")
        if self.max_consecutive_losses < 0:
            raise ValueError("max_consecutive_losses must be >= 0")
        if self.edge_score_weight < 0:
            raise ValueError("edge_score_weight must be >= 0")
        if self.min_edge_confidence < 0 or self.min_edge_confidence > 1:
            raise ValueError("min_edge_confidence must be in [0, 1]")
        if self.basket_max_size < 1 or self.basket_max_same_sector_positions < 1:
            raise ValueError("basket counts must be >= 1")
        for label, value in (
            ("basket_total_deployable_cash_pct", self.basket_total_deployable_cash_pct),
            ("basket_single_position_deployable_cash_pct", self.basket_single_position_deployable_cash_pct),
            ("max_basket_risk_equity_pct", self.max_basket_risk_equity_pct),
        ):
            if value <= 0 or value > 1:
                raise ValueError(f"{label} must be in (0, 1]")
        if self.basket_single_position_deployable_cash_pct > self.basket_total_deployable_cash_pct:
            raise ValueError("basket single-position pct must be <= basket total pct")
        if self.basket_risk_allocation_mode != "equal_risk":
            raise ValueError("basket_risk_allocation_mode must be 'equal_risk'")
        if self.basket_min_leg_risk_dollars < 0:
            raise ValueError("basket_min_leg_risk_dollars must be >= 0")
        if self.min_signal_strength < 0:
            raise ValueError("min_signal_strength must be >= 0")
        if self.support_resistance_lookback_days < 0:
            raise ValueError("support_resistance_lookback_days must be >= 0")
        if self.vix_caution_level <= 0 or self.vix_block_level <= 0:
            raise ValueError("VIX levels must be positive")
        if self.vix_caution_level > self.vix_block_level:
            raise ValueError("vix_caution_level must be <= vix_block_level")
        if self.vix_caution_intraday_rise_pct < 0 or self.vix_block_intraday_rise_pct < 0:
            raise ValueError("VIX rise thresholds must be >= 0")
        if self.vix_caution_intraday_rise_pct > self.vix_block_intraday_rise_pct:
            raise ValueError("VIX caution rise threshold must be <= block threshold")

    def deployable_cash_cap_pct(self) -> float:
        return self.max_position_deployable_cash_pct if self.max_position_deployable_cash_pct is not None else self.max_new_position_pct

    def equity_cap_pct(self) -> float:
        return self.max_position_equity_pct if self.max_position_equity_pct is not None else self.max_new_position_pct

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
            "evidence_aware_sizing_enabled": self.evidence_aware_sizing_enabled,
            "evidence_aware_min_trades_for_tiny_live": self.evidence_aware_min_trades_for_tiny_live,
            "evidence_aware_min_trades_for_normal": self.evidence_aware_min_trades_for_normal,
            "evidence_aware_tiny_live_max_position_pct": self.evidence_aware_tiny_live_max_position_pct,
            "evidence_aware_reduced_size_multiplier": self.evidence_aware_reduced_size_multiplier,
            "evidence_aware_min_confidence_for_normal": self.evidence_aware_min_confidence_for_normal,
            "evidence_aware_strong_expected_r": self.evidence_aware_strong_expected_r,
            "evidence_aware_max_drawdown_r_for_normal": self.evidence_aware_max_drawdown_r_for_normal,
            "evidence_aware_max_slippage_bps_for_normal": self.evidence_aware_max_slippage_bps_for_normal,
            "evidence_aware_allow_size_increase": self.evidence_aware_allow_size_increase,
            "drawdown_governor_enabled": self.drawdown_governor_enabled,
            "strategy_drawdown_pct": self.strategy_drawdown_pct,
            "commission_aware_sizing_enabled": self.commission_aware_sizing_enabled,
            "estimated_commission_per_order": self.estimated_commission_per_order,
            "min_net_profit_usd": self.min_net_profit_usd,
            "min_net_profit_pct_of_trade": self.min_net_profit_pct_of_trade,
            "execution_quality_guard_enabled": self.execution_quality_guard_enabled,
            "execution_max_spread_pct": self.execution_max_spread_pct,
            "execution_max_slippage_pct": self.execution_max_slippage_pct,
            "execution_max_price_move_pct": self.execution_max_price_move_pct,
            "execution_block_on_missing_quote": self.execution_block_on_missing_quote,
            "market_data_health_guard_enabled": self.market_data_health_guard_enabled,
            "market_data_max_quote_age_seconds": self.market_data_max_quote_age_seconds,
            "market_data_max_spread_pct": self.market_data_max_spread_pct,
            "market_data_max_last_mid_deviation_pct": self.market_data_max_last_mid_deviation_pct,
            "market_data_block_stale_quotes_live": self.market_data_block_stale_quotes_live,
            "market_data_block_missing_bid_ask_live": self.market_data_block_missing_bid_ask_live,
            "market_data_block_missing_timestamp_live": self.market_data_block_missing_timestamp_live,
            "market_data_block_feed_unhealthy_live": self.market_data_block_feed_unhealthy_live,
            "market_data_block_market_closed_live": self.market_data_block_market_closed_live,
            "live_market_data_required_source": self.live_market_data_required_source,
            "live_market_data_require_live_type": self.live_market_data_require_live_type,
            "allow_yahoo_for_live_trading": self.allow_yahoo_for_live_trading,
            "risk_lifecycle_guard_enabled": self.risk_lifecycle_guard_enabled,
            "risk_lifecycle_recent_record_limit": self.risk_lifecycle_recent_record_limit,
            "max_daily_loss_r": self.max_daily_loss_r,
            "max_weekly_loss_r": self.max_weekly_loss_r,
            "max_monthly_loss_r": self.max_monthly_loss_r,
            "max_consecutive_losses": self.max_consecutive_losses,
            "max_strategy_drawdown_r": self.max_strategy_drawdown_r,
            "edge_ranking_enabled": self.edge_ranking_enabled,
            "min_expected_r": self.min_expected_r,
            "min_edge_confidence": self.min_edge_confidence,
            "edge_score_weight": self.edge_score_weight,
            "basket_enabled": self.basket_enabled,
            "basket_max_size": self.basket_max_size,
            "basket_total_deployable_cash_pct": self.basket_total_deployable_cash_pct,
            "basket_single_position_deployable_cash_pct": self.basket_single_position_deployable_cash_pct,
            "basket_max_same_sector_positions": self.basket_max_same_sector_positions,
            "basket_risk_allocator_enabled": self.basket_risk_allocator_enabled,
            "max_basket_risk_equity_pct": self.max_basket_risk_equity_pct,
            "basket_risk_allocation_mode": self.basket_risk_allocation_mode,
            "basket_min_leg_risk_dollars": self.basket_min_leg_risk_dollars,
            "min_signal_strength": self.min_signal_strength,
            "required_signal_label": self.required_signal_label,
            "allowed_signal_labels": list(self.allowed_signal_labels) if self.allowed_signal_labels else None,
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
