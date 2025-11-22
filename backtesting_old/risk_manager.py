"""
Risk management controls for backtesting.

Provides risk limits, position management, and drawdown controls.
"""

import logging
from typing import Dict, Optional
from datetime import datetime

logger = logging.getLogger(__name__)


class RiskManager:
    """
    Manage risk controls during backtesting.
    
    Features:
    - Maximum position limits
    - Maximum drawdown limits
    - Daily loss limits
    - Position concentration limits
    - Leverage limits
    
    Example:
        >>> risk_mgr = RiskManager(
        ...     max_positions=5,
        ...     max_drawdown_pct=0.20,
        ...     daily_loss_limit=0.05
        ... )
        >>> 
        >>> # Check if order is allowed
        >>> if risk_mgr.can_open_position(symbol, equity):
        ...     # Place order
        ...     pass
    """
    
    def __init__(
        self,
        max_positions: int = 10,
        max_drawdown_pct: float = 0.20,  # 20%
        daily_loss_limit: float = 0.05,  # 5% per day
        max_position_pct: float = 0.25,  # 25% per position
        max_leverage: float = 1.0,  # No leverage by default
        max_correlation: float = 0.7  # Max correlation between positions
    ):
        """
        Initialize risk manager.
        
        Args:
            max_positions: Maximum number of concurrent positions
            max_drawdown_pct: Maximum drawdown before stopping (as decimal)
            daily_loss_limit: Maximum daily loss (as decimal)
            max_position_pct: Maximum position size as % of equity
            max_leverage: Maximum leverage allowed
            max_correlation: Maximum correlation between positions
        """
        self.max_positions = max_positions
        self.max_drawdown_pct = max_drawdown_pct
        self.daily_loss_limit = daily_loss_limit
        self.max_position_pct = max_position_pct
        self.max_leverage = max_leverage
        self.max_correlation = max_correlation
        
        # State tracking
        self.peak_equity = 0.0
        self.daily_start_equity = 0.0
        self.current_date = None
        self.drawdown_breached = False
        self.daily_limit_breached = False
        
        logger.info(f"RiskManager initialized: max_pos={max_positions}, "
                   f"max_dd={max_drawdown_pct:.1%}, daily_limit={daily_loss_limit:.1%}")
    
    def update(self, equity: float, current_date: datetime):
        """
        Update risk manager state.
        
        Args:
            equity: Current equity
            current_date: Current date
        """
        # Update peak equity
        if equity > self.peak_equity:
            self.peak_equity = equity
        
        # Reset daily tracking on new day
        if self.current_date is None or current_date.date() != self.current_date.date():
            self.current_date = current_date
            self.daily_start_equity = equity
            self.daily_limit_breached = False
        
        # Check drawdown
        if self.peak_equity > 0:
            drawdown_pct = (self.peak_equity - equity) / self.peak_equity
            if drawdown_pct >= self.max_drawdown_pct:
                if not self.drawdown_breached:
                    self.drawdown_breached = True
                    logger.warning(f"Maximum drawdown breached: {drawdown_pct:.2%}")
        
        # Check daily loss limit
        if self.daily_start_equity > 0:
            daily_loss_pct = (self.daily_start_equity - equity) / self.daily_start_equity
            if daily_loss_pct >= self.daily_loss_limit:
                if not self.daily_limit_breached:
                    self.daily_limit_breached = True
                    logger.warning(f"Daily loss limit breached: {daily_loss_pct:.2%}")
    
    def can_open_position(
        self,
        symbol: str,
        equity: float,
        positions: Dict
    ) -> tuple[bool, str]:
        """
        Check if new position can be opened.
        
        Args:
            symbol: Trading symbol
            equity: Current equity
            positions: Current positions dict
            
        Returns:
            Tuple of (can_open, reason)
        """
        # Check if already breached limits
        if self.drawdown_breached:
            return False, "Maximum drawdown limit breached"
        
        if self.daily_limit_breached:
            return False, "Daily loss limit breached"
        
        # Check position count
        active_positions = sum(1 for pos in positions.values() if pos.quantity != 0)
        if active_positions >= self.max_positions:
            return False, f"Maximum positions ({self.max_positions}) reached"
        
        # Check if already have position in this symbol
        if symbol in positions and positions[symbol].quantity != 0:
            return False, f"Already have position in {symbol}"
        
        return True, "OK"
    
    def can_increase_position(
        self,
        symbol: str,
        current_position_value: float,
        new_position_value: float,
        equity: float
    ) -> tuple[bool, str]:
        """
        Check if position can be increased.
        
        Args:
            symbol: Trading symbol
            current_position_value: Current position value
            new_position_value: New position value after increase
            equity: Current equity
            
        Returns:
            Tuple of (can_increase, reason)
        """
        if self.drawdown_breached or self.daily_limit_breached:
            return False, "Risk limits breached"
        
        # Check position size limit
        new_pct = new_position_value / equity if equity > 0 else 0
        if new_pct > self.max_position_pct:
            return False, f"Position would exceed {self.max_position_pct:.1%} limit"
        
        return True, "OK"
    
    def check_leverage(self, total_position_value: float, equity: float) -> tuple[bool, str]:
        """
        Check if leverage is within limits.
        
        Args:
            total_position_value: Total value of all positions
            equity: Current equity
            
        Returns:
            Tuple of (within_limit, reason)
        """
        if equity == 0:
            return False, "Zero equity"
        
        leverage = total_position_value / equity
        if leverage > self.max_leverage:
            return False, f"Leverage {leverage:.2f}x exceeds limit {self.max_leverage:.2f}x"
        
        return True, "OK"
    
    def should_reduce_positions(self, equity: float) -> bool:
        """
        Check if positions should be reduced due to risk limits.
        
        Args:
            equity: Current equity
            
        Returns:
            True if positions should be reduced
        """
        # Reduce if drawdown is close to limit
        if self.peak_equity > 0:
            drawdown_pct = (self.peak_equity - equity) / self.peak_equity
            if drawdown_pct >= self.max_drawdown_pct * 0.9:  # 90% of limit
                return True
        
        # Reduce if daily loss is close to limit
        if self.daily_start_equity > 0:
            daily_loss_pct = (self.daily_start_equity - equity) / self.daily_start_equity
            if daily_loss_pct >= self.daily_loss_limit * 0.9:  # 90% of limit
                return True
        
        return False
    
    def reset(self):
        """Reset risk manager state"""
        self.peak_equity = 0.0
        self.daily_start_equity = 0.0
        self.current_date = None
        self.drawdown_breached = False
        self.daily_limit_breached = False
        logger.debug("RiskManager reset")
    
    def get_status(self) -> Dict:
        """
        Get current risk status.
        
        Returns:
            Dictionary with risk status
        """
        current_drawdown = 0.0
        if self.peak_equity > 0:
            # This would need current equity passed in
            pass
        
        return {
            'peak_equity': self.peak_equity,
            'drawdown_breached': self.drawdown_breached,
            'daily_limit_breached': self.daily_limit_breached,
            'max_positions': self.max_positions,
            'max_drawdown_pct': self.max_drawdown_pct,
            'daily_loss_limit': self.daily_loss_limit
        }
