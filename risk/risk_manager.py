"""
Enhanced Risk Manager for live trading and backtesting.

Features:
- Pre-trade risk checks
- Position size validation
- Portfolio exposure calculation
- Real-time P&L tracking
- VaR (Value at Risk) calculation
- Concentration risk monitoring
- Emergency stop functionality

Week 3 Day 1 Implementation.
"""

import logging
from typing import Dict, List, Optional, Tuple
from datetime import datetime
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)


class RiskStatus(str, Enum):
    """Risk status levels."""
    NORMAL = "NORMAL"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"
    EMERGENCY_STOP = "EMERGENCY_STOP"


@dataclass
class Position:
    """Position information for risk calculations."""
    symbol: str
    quantity: int
    entry_price: float
    current_price: float
    side: str  # 'LONG' or 'SHORT'
    
    @property
    def market_value(self) -> float:
        """Current market value of position."""
        return abs(self.quantity * self.current_price)
    
    @property
    def unrealized_pnl(self) -> float:
        """Unrealized P&L."""
        if self.side == 'LONG':
            return self.quantity * (self.current_price - self.entry_price)
        else:  # SHORT
            return self.quantity * (self.entry_price - self.current_price)
    
    @property
    def unrealized_pnl_pct(self) -> float:
        """Unrealized P&L as percentage."""
        if self.entry_price == 0:
            return 0.0
        if self.side == 'LONG':
            return (self.current_price - self.entry_price) / self.entry_price
        else:
            return (self.entry_price - self.current_price) / self.entry_price


@dataclass
class RiskMetrics:
    """Current risk metrics snapshot."""
    timestamp: datetime
    equity: float
    cash: float
    total_position_value: float
    leverage: float
    num_positions: int
    largest_position_pct: float
    concentration_risk: float
    unrealized_pnl: float
    unrealized_pnl_pct: float
    daily_pnl: float
    daily_pnl_pct: float
    drawdown: float
    drawdown_pct: float
    risk_status: RiskStatus
    position_sizes: Dict[str, float] = field(default_factory=dict)
    portfolio_heat: float = field(default=0.0)   # total positions / equity (0-1+)
    daily_loss_pct: float = field(default=0.0)   # magnitude of daily loss as decimal
    daily_loss: float = field(default=0.0)        # dollar amount of daily loss
    # Strategy-aware drawdown fields
    stock_drawdown: float = field(default=0.0)           # $ drawdown for stock/long-only equity
    stock_drawdown_pct: float = field(default=0.0)       # % drawdown for stock/long-only equity
    premium_retention_pct: float = field(default=1.0)    # fraction of collected premium retained (0-1)
    short_options_premium_collected: float = field(default=0.0)  # total premium collected from short options
    short_options_current_liability: float = field(default=0.0)  # current mark-to-market of short options


class RiskManager:
    """
    Enhanced risk manager for comprehensive portfolio risk management.
    
    Features:
    - Pre-trade risk validation
    - Position size limits
    - Portfolio exposure monitoring
    - Drawdown tracking
    - Real-time risk metrics
    - Emergency stop functionality
    
    Example:
        >>> risk_mgr = RiskManager(
        ...     initial_capital=100000,
        ...     max_positions=5,
        ...     max_position_pct=0.20,
        ...     max_drawdown_pct=0.15
        ... )
        >>> 
        >>> # Check if trade is allowed
        >>> can_trade, reason = risk_mgr.check_trade_risk(signal, positions)
        >>> if can_trade:
        ...     size = risk_mgr.calculate_position_size(signal, equity)
    """
    
    def __init__(
        self,
        initial_capital: float = 100000.0,
        max_positions: int = 10,
        max_position_pct: float = 0.25,  # 25% max per position
        max_drawdown_pct: float = 0.20,  # 20% max drawdown
        daily_loss_limit_pct: float = 0.05,  # 5% daily loss limit
        max_leverage: float = 1.0,  # No leverage by default
        max_correlation: float = 0.70,  # Max 0.70 correlation between positions
        concentration_limit: float = 0.50,  # Max 50% in any sector/category
        var_confidence: float = 0.95,  # 95% confidence for VaR
        emergency_stop_enabled: bool = True
    ):
        """
        Initialize enhanced risk manager.
        
        Args:
            initial_capital: Starting capital
            max_positions: Maximum concurrent positions
            max_position_pct: Maximum position size as % of equity
            max_drawdown_pct: Maximum drawdown before emergency stop
            daily_loss_limit_pct: Maximum daily loss
            max_leverage: Maximum leverage allowed
            max_correlation: Maximum correlation between positions
            concentration_limit: Maximum concentration in sector/category
            var_confidence: Confidence level for VaR calculation
            emergency_stop_enabled: Enable emergency stop functionality
        """
        # Configuration
        self.initial_capital = initial_capital
        self.max_positions = max_positions
        self.max_position_pct = max_position_pct
        self.max_drawdown_pct = max_drawdown_pct
        self.daily_loss_limit_pct = daily_loss_limit_pct
        self.max_leverage = max_leverage
        self.max_correlation = max_correlation
        self.concentration_limit = concentration_limit
        self.var_confidence = var_confidence
        self.emergency_stop_enabled = emergency_stop_enabled
        
        # State tracking
        self.peak_equity = initial_capital
        self.current_equity = initial_capital
        self.daily_start_equity = initial_capital
        self.current_date = None
        self.risk_status = RiskStatus.NORMAL
        self.emergency_stop_active = False
        
        # Strategy-aware equity tracking (stock-only, excludes short options)
        self.stock_equity = initial_capital       # cash + long stock value only
        self.peak_stock_equity = initial_capital   # peak of stock-only equity
        self._stock_equity_from_positions = False  # True once recompute_strategy_metrics sets it
        
        # Short options premium tracking
        self.short_options_premium_collected = 0.0   # total premium received
        self.short_options_current_liability = 0.0   # current mark-to-market cost
        
        # Risk metrics history
        self.equity_history: List[float] = [initial_capital]
        self.daily_returns: List[float] = []
        
        # Breach tracking
        self.drawdown_breached = False
        self.daily_limit_breached = False
        
        logger.info(f"Enhanced RiskManager initialized:")
        logger.info(f"  Initial Capital: ${initial_capital:,.2f}")
        logger.info(f"  Max Positions: {max_positions}")
        logger.info(f"  Max Position: {max_position_pct:.1%}")
        logger.info(f"  Max Drawdown: {max_drawdown_pct:.1%}")
        logger.info(f"  Daily Loss Limit: {daily_loss_limit_pct:.1%}")
        logger.info(f"  Max Leverage: {max_leverage:.2f}x")
    
    def update(
        self,
        equity: float,
        positions: Dict[str, Position],
        current_date: datetime
    ) -> RiskMetrics:
        """
        Update risk manager with current state.
        
        Args:
            equity: Current total equity
            positions: Dictionary of current positions
            current_date: Current timestamp
            
        Returns:
            Current risk metrics
        """
        self.current_equity = equity
        
        # Update peak equity
        if equity > self.peak_equity:
            self.peak_equity = equity
        
        # Fallback: if stock_equity has not been set via position-level
        # breakdown (recompute_strategy_metrics), keep it in sync with
        # total equity so drawdown checks work correctly.
        if not self._stock_equity_from_positions:
            self.stock_equity = equity
            if equity > self.peak_stock_equity:
                self.peak_stock_equity = equity
        
        # Reset daily tracking on new day
        if self.current_date is None or current_date.date() != self.current_date.date():
            if self.daily_start_equity > 0:
                daily_return = (equity - self.daily_start_equity) / self.daily_start_equity
                self.daily_returns.append(daily_return)
            
            self.current_date = current_date
            self.daily_start_equity = equity
            self.daily_limit_breached = False
        
        # Track equity history
        self.equity_history.append(equity)
        
        # Calculate risk metrics
        metrics = self._calculate_risk_metrics(equity, positions, current_date)
        
        # Check risk limits
        self._check_risk_limits(metrics)
        
        # Update risk status
        self._update_risk_status(metrics)
        
        return metrics
    
    def check_trade_risk(
        self,
        symbol: str,
        side: str,
        quantity: int,
        price: float,
        positions: Dict[str, Position]
    ) -> Tuple[bool, str]:
        """
        Check if a trade passes all risk checks.
        
        Args:
            symbol: Trading symbol
            side: 'LONG' or 'SHORT'
            quantity: Number of shares
            price: Entry price
            positions: Current positions
            
        Returns:
            Tuple of (approved, reason)
        """
        # Emergency stop check
        if self.emergency_stop_active:
            return False, "Emergency stop active - all trading halted"
        
        # Risk limit breaches
        if self.drawdown_breached:
            return False, f"Maximum drawdown limit ({self.max_drawdown_pct:.1%}) breached"
        
        if self.daily_limit_breached:
            return False, f"Daily loss limit ({self.daily_loss_limit_pct:.1%}) breached"
        
        # Position count limit
        active_positions = len([p for p in positions.values() if p.quantity != 0])
        if active_positions >= self.max_positions:
            # Allow closing positions even at limit
            if symbol in positions and positions[symbol].quantity != 0:
                # Check if this is a closing trade
                if (positions[symbol].side == 'LONG' and side == 'SHORT') or \
                   (positions[symbol].side == 'SHORT' and side == 'LONG'):
                    return True, "Closing existing position"
            return False, f"Maximum positions ({self.max_positions}) reached"
        
        # Position size check
        position_value = abs(quantity * price)
        position_pct = position_value / self.current_equity if self.current_equity > 0 else 0
        
        if position_pct > self.max_position_pct:
            return False, f"Position size ({position_pct:.1%}) exceeds limit ({self.max_position_pct:.1%})"
        
        # Leverage check
        total_position_value = sum(p.market_value for p in positions.values())
        new_total_value = total_position_value + position_value
        new_leverage = new_total_value / self.current_equity if self.current_equity > 0 else 0
        
        if new_leverage > self.max_leverage:
            return False, f"Trade would exceed leverage limit ({self.max_leverage:.2f}x)"
        
        return True, "Trade approved"
    
    def calculate_position_size(
        self,
        symbol: str,
        price: float,
        strategy: str = "fixed_percent",
        **kwargs
    ) -> int:
        """
        Calculate appropriate position size.
        
        Args:
            symbol: Trading symbol
            price: Entry price
            strategy: Sizing strategy ('fixed_percent', 'kelly', 'risk_based')
            **kwargs: Additional parameters for sizing strategy
            
        Returns:
            Number of shares to trade
        """
        if self.current_equity <= 0 or price <= 0:
            return 0
        
        if strategy == "fixed_percent":
            # Use max_position_pct as default
            pct = kwargs.get('position_pct', self.max_position_pct)
            position_value = self.current_equity * pct
            shares = int(position_value / price)
            
        elif strategy == "risk_based":
            # Size based on risk per trade
            risk_per_trade = kwargs.get('risk_pct', 0.02)  # 2% default
            stop_loss_pct = kwargs.get('stop_loss_pct', 0.05)  # 5% default
            
            risk_amount = self.current_equity * risk_per_trade
            risk_per_share = price * stop_loss_pct
            shares = int(risk_amount / risk_per_share) if risk_per_share > 0 else 0
            
        elif strategy == "kelly":
            # Kelly criterion (simplified)
            win_rate = kwargs.get('win_rate', 0.50)
            avg_win = kwargs.get('avg_win', 0.02)
            avg_loss = kwargs.get('avg_loss', 0.01)
            
            if avg_loss > 0:
                win_loss_ratio = avg_win / avg_loss
                kelly_fraction = (win_rate * win_loss_ratio - (1 - win_rate)) / win_loss_ratio
                kelly_fraction = max(0, min(kelly_fraction, 0.25))  # Cap at 25%
                
                # Use half-Kelly for safety
                kelly_fraction *= 0.5
                
                position_value = self.current_equity * kelly_fraction
                shares = int(position_value / price)
            else:
                shares = 0
        else:
            logger.warning(f"Unknown sizing strategy: {strategy}, using fixed_percent")
            position_value = self.current_equity * self.max_position_pct
            shares = int(position_value / price)
        
        # Ensure position doesn't exceed limits
        max_value = self.current_equity * self.max_position_pct
        max_shares = int(max_value / price)
        shares = min(shares, max_shares)
        
        return max(0, shares)
    
    def trigger_emergency_stop(self, reason: str = "Manual trigger"):
        """
        Trigger emergency stop - halt all trading.
        
        Args:
            reason: Reason for emergency stop
        """
        if not self.emergency_stop_enabled:
            logger.warning("Emergency stop triggered but not enabled")
            return
        
        self.emergency_stop_active = True
        self.risk_status = RiskStatus.EMERGENCY_STOP
        logger.critical(f"🚨 EMERGENCY STOP ACTIVATED: {reason}")
        logger.critical("All trading has been halted")
    
    def release_emergency_stop(self, reason: str = "Manual release"):
        """
        Release emergency stop - resume trading.
        
        Args:
            reason: Reason for releasing stop
        """
        self.emergency_stop_active = False
        self.risk_status = RiskStatus.NORMAL
        logger.info(f"✅ Emergency stop released: {reason}")
        logger.info("Trading can resume")
    
    def _calculate_risk_metrics(
        self,
        equity: float,
        positions: Dict[str, Position],
        timestamp: datetime
    ) -> RiskMetrics:
        """Calculate current risk metrics."""
        
        # Position metrics
        total_position_value = sum(p.market_value for p in positions.values())
        num_positions = len([p for p in positions.values() if p.quantity != 0])
        
        # Leverage
        leverage = total_position_value / equity if equity > 0 else 0.0
        
        # Largest position
        largest_position_pct = 0.0
        if positions and equity > 0:
            largest_value = max((p.market_value for p in positions.values()), default=0)
            largest_position_pct = largest_value / equity
        
        # Concentration (simplified - could be by sector)
        concentration_risk = largest_position_pct
        
        # P&L metrics
        unrealized_pnl = sum(p.unrealized_pnl for p in positions.values())
        unrealized_pnl_pct = unrealized_pnl / equity if equity > 0 else 0.0
        
        daily_pnl = equity - self.daily_start_equity
        daily_pnl_pct = daily_pnl / self.daily_start_equity if self.daily_start_equity > 0 else 0.0
        
        # Drawdown (total portfolio — kept for backward compatibility)
        drawdown = self.peak_equity - equity
        drawdown_pct = drawdown / self.peak_equity if self.peak_equity > 0 else 0.0
        
        # Stock-only drawdown (excludes short options mark-to-market)
        stock_dd = self.peak_stock_equity - self.stock_equity
        stock_dd_pct = stock_dd / self.peak_stock_equity if self.peak_stock_equity > 0 else 0.0
        
        # Premium retention for short options
        prem_collected = self.short_options_premium_collected
        prem_liability = self.short_options_current_liability
        if prem_collected > 0:
            prem_retention = max(0.0, (prem_collected - prem_liability) / prem_collected)
        else:
            prem_retention = 1.0
        
        # Cash (simplified - equity minus position value)
        cash = equity - total_position_value
        
        return RiskMetrics(
            timestamp=timestamp,
            equity=equity,
            cash=cash,
            total_position_value=total_position_value,
            leverage=leverage,
            num_positions=num_positions,
            largest_position_pct=largest_position_pct,
            concentration_risk=concentration_risk,
            unrealized_pnl=unrealized_pnl,
            unrealized_pnl_pct=unrealized_pnl_pct,
            daily_pnl=daily_pnl,
            daily_pnl_pct=daily_pnl_pct,
            drawdown=drawdown,
            drawdown_pct=drawdown_pct,
            risk_status=self.risk_status,
            position_sizes={symbol: p.market_value / equity for symbol, p in positions.items() if equity > 0},
            portfolio_heat=total_position_value / equity if equity > 0 else 0.0,
            daily_loss_pct=max(0.0, -daily_pnl_pct),
            daily_loss=max(0.0, -daily_pnl),
            stock_drawdown=stock_dd,
            stock_drawdown_pct=stock_dd_pct,
            premium_retention_pct=prem_retention,
            short_options_premium_collected=prem_collected,
            short_options_current_liability=prem_liability,
        )
    
    def _check_risk_limits(self, metrics: RiskMetrics):
        """Check if any risk limits are breached.
        
        Uses stock-only drawdown for breach checks so that short option
        mark-to-market fluctuations don't trigger emergency stops.
        """
        
        # Check drawdown — use stock-only drawdown (excludes short options)
        if metrics.stock_drawdown_pct >= self.max_drawdown_pct:
            if not self.drawdown_breached:
                self.drawdown_breached = True
                logger.error(f"❌ Maximum stock drawdown breached: {metrics.stock_drawdown_pct:.2%}")
                
                if self.emergency_stop_enabled:
                    self.trigger_emergency_stop(
                        f"Maximum stock drawdown ({self.max_drawdown_pct:.1%}) exceeded"
                    )
        
        # Check daily loss limit
        if metrics.daily_pnl_pct <= -self.daily_loss_limit_pct:
            if not self.daily_limit_breached:
                self.daily_limit_breached = True
                logger.error(f"❌ Daily loss limit breached: {metrics.daily_pnl_pct:.2%}")
        
        # Check leverage
        if metrics.leverage > self.max_leverage:
            logger.warning(f"⚠️  Leverage ({metrics.leverage:.2f}x) exceeds limit ({self.max_leverage:.2f}x)")
        
        # Check concentration
        if metrics.concentration_risk > self.concentration_limit:
            logger.warning(f"⚠️  Concentration risk ({metrics.concentration_risk:.1%}) exceeds limit ({self.concentration_limit:.1%})")
    
    def _update_risk_status(self, metrics: RiskMetrics):
        """Update overall risk status.
        
        Uses stock-only drawdown so short option volatility doesn't
        artificially inflate the risk level.
        """
        
        if self.emergency_stop_active:
            self.risk_status = RiskStatus.EMERGENCY_STOP
            return
        
        # Check for critical conditions (based on stock drawdown)
        if metrics.stock_drawdown_pct >= self.max_drawdown_pct * 0.95:
            self.risk_status = RiskStatus.CRITICAL
        elif metrics.stock_drawdown_pct >= self.max_drawdown_pct * 0.80 or \
             abs(metrics.daily_pnl_pct) >= self.daily_loss_limit_pct * 0.80:
            self.risk_status = RiskStatus.WARNING
        else:
            self.risk_status = RiskStatus.NORMAL
    
    def get_risk_summary(self) -> Dict:
        """
        Get summary of current risk status.
        
        Returns:
            Dictionary with risk summary
        """
        # Stock-only drawdown
        stock_dd_pct = (
            (self.peak_stock_equity - self.stock_equity) / self.peak_stock_equity
            if self.peak_stock_equity > 0 else 0.0
        )
        # Premium retention
        if self.short_options_premium_collected > 0:
            prem_retention = max(
                0.0,
                (self.short_options_premium_collected - self.short_options_current_liability)
                / self.short_options_premium_collected,
            )
        else:
            prem_retention = 1.0

        return {
            'risk_status': self.risk_status.value,
            'emergency_stop_active': self.emergency_stop_active,
            'current_equity': self.current_equity,
            'peak_equity': self.peak_equity,
            'daily_start_equity': self.daily_start_equity,
            'drawdown_pct': (self.peak_equity - self.current_equity) / self.peak_equity if self.peak_equity > 0 else 0.0,
            'daily_pnl_pct': (self.current_equity - self.daily_start_equity) / self.daily_start_equity if self.daily_start_equity > 0 else 0.0,
            'drawdown_breached': self.drawdown_breached,
            'daily_limit_breached': self.daily_limit_breached,
            # Strategy-aware drawdown
            'stock_drawdown_pct': stock_dd_pct,
            'stock_equity': self.stock_equity,
            'peak_stock_equity': self.peak_stock_equity,
            'premium_retention_pct': prem_retention,
            'short_options_premium_collected': self.short_options_premium_collected,
            'short_options_current_liability': self.short_options_current_liability,
            'limits': {
                'max_positions': self.max_positions,
                'max_position_pct': self.max_position_pct,
                'max_drawdown_pct': self.max_drawdown_pct,
                'daily_loss_limit_pct': self.daily_loss_limit_pct,
                'max_leverage': self.max_leverage,
            }
        }
    
    def reset(self):
        """Reset risk manager state (for backtesting)."""
        self.peak_equity = self.initial_capital
        self.current_equity = self.initial_capital
        self.daily_start_equity = self.initial_capital
        self.current_date = None
        self.risk_status = RiskStatus.NORMAL
        self.emergency_stop_active = False
        self.drawdown_breached = False
        self.daily_limit_breached = False
        self.equity_history = [self.initial_capital]
        self.daily_returns = []
        # Reset strategy-aware tracking
        self.stock_equity = self.initial_capital
        self.peak_stock_equity = self.initial_capital
        self._stock_equity_from_positions = False
        self.short_options_premium_collected = 0.0
        self.short_options_current_liability = 0.0
        logger.debug("RiskManager reset to initial state")
