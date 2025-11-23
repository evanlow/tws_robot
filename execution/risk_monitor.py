"""
Real-time Risk Monitor

Monitors positions and portfolio risk in real-time during paper/live trading.
Enforces RiskProfile limits and generates alerts when limits are breached.

Features:
- Position-level risk checks (before order placement)
- Portfolio-level risk aggregation
- Real-time P&L and drawdown tracking
- Risk limit breach detection
- Integration with PaperTradingAdapter

Author: TWS Robot Development Team
Date: November 2025
Sprint 2 Task 1
"""

import logging
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime
from threading import Lock

from backtest.profiles import RiskProfile
from backtest.data_models import Position

logger = logging.getLogger(__name__)


@dataclass
class RiskAlert:
    """Risk alert notification"""
    timestamp: datetime
    alert_type: str  # 'position_limit', 'portfolio_risk', 'drawdown', 'daily_loss'
    severity: str  # 'warning', 'critical'
    message: str
    details: Dict


@dataclass
class PortfolioRisk:
    """Portfolio risk snapshot"""
    total_value: float
    total_exposure: float
    exposure_pct: float
    margin_used: float
    margin_pct: float
    current_drawdown: float
    daily_pnl: float
    daily_loss_pct: float
    position_count: int
    risk_utilization: float  # 0.0 to 1.0


class RealTimeRiskMonitor:
    """
    Real-time risk monitor for paper/live trading
    
    Monitors positions and portfolio against RiskProfile limits.
    Enforces risk controls and generates alerts when limits are breached.
    
    Thread-safe for concurrent order placement.
    """
    
    def __init__(self, risk_profile: RiskProfile, initial_capital: float = 100000.0):
        """
        Initialize risk monitor
        
        Args:
            risk_profile: RiskProfile with risk limits
            initial_capital: Starting capital for calculations
        """
        self.risk_profile = risk_profile
        self.initial_capital = initial_capital
        
        # Portfolio tracking
        self.peak_value = initial_capital
        self.daily_starting_value = initial_capital
        self.daily_reset_date: Optional[datetime] = None
        
        # Alert history
        self.alerts: List[RiskAlert] = []
        
        # Thread safety
        self._lock = Lock()
        
        logger.info(f"RealTimeRiskMonitor initialized with {risk_profile.name} profile (capital: ${initial_capital:,.2f})")
    
    def check_position_risk(
        self,
        symbol: str,
        quantity: int,
        current_price: float,
        current_positions: Dict[str, Position],
        portfolio_value: float
    ) -> Tuple[bool, Optional[str]]:
        """
        Check if a new position would violate risk limits
        
        Args:
            symbol: Stock symbol
            quantity: Number of shares to buy/sell
            current_price: Current market price
            current_positions: Dict of current positions
            portfolio_value: Current portfolio value
            
        Returns:
            (allowed, reason) - True if position allowed, reason if rejected
        """
        with self._lock:
            position_value = abs(quantity * current_price)
            position_pct = position_value / portfolio_value if portfolio_value > 0 else 0
            
            # Check 1: Position size limit
            if position_pct > self.risk_profile.max_position_size:
                reason = (
                    f"Position size {position_pct:.1%} exceeds limit "
                    f"{self.risk_profile.max_position_size:.1%}"
                )
                logger.warning(f"Position risk check FAILED: {symbol} - {reason}")
                return False, reason
            
            # Check 2: Single symbol exposure
            existing_position = current_positions.get(symbol)
            if existing_position:
                existing_value = abs(existing_position.quantity * current_price)
                total_exposure = (existing_value + position_value) / portfolio_value
                
                if total_exposure > self.risk_profile.max_single_exposure:
                    reason = (
                        f"Symbol exposure {total_exposure:.1%} exceeds limit "
                        f"{self.risk_profile.max_single_exposure:.1%}"
                    )
                    logger.warning(f"Position risk check FAILED: {symbol} - {reason}")
                    return False, reason
            
            # Check 3: Concurrent position limit
            position_count = len(current_positions)
            if symbol not in current_positions:  # Would be new position
                if position_count >= self.risk_profile.max_concurrent_positions:
                    reason = (
                        f"Max concurrent positions ({self.risk_profile.max_concurrent_positions}) "
                        f"already reached"
                    )
                    logger.warning(f"Position risk check FAILED: {symbol} - {reason}")
                    return False, reason
            
            # Check 4: Per-symbol position limit
            if existing_position and self.risk_profile.max_positions_per_symbol == 1:
                reason = "Only 1 position per symbol allowed"
                logger.warning(f"Position risk check FAILED: {symbol} - {reason}")
                return False, reason
            
            logger.debug(f"Position risk check PASSED: {symbol} (size: {position_pct:.1%})")
            return True, None
    
    def check_portfolio_risk(
        self,
        current_positions: Dict[str, Position],
        current_prices: Dict[str, float],
        portfolio_value: float
    ) -> Tuple[bool, List[str]]:
        """
        Check portfolio-level risk metrics
        
        Args:
            current_positions: Dict of current positions
            current_prices: Dict of current market prices
            portfolio_value: Current portfolio value
            
        Returns:
            (ok, warnings) - True if within limits, list of warnings
        """
        with self._lock:
            warnings = []
            
            # Calculate total exposure
            total_exposure = 0.0
            for symbol, position in current_positions.items():
                if symbol in current_prices:
                    exposure = abs(position.quantity * current_prices[symbol])
                    total_exposure += exposure
            
            exposure_pct = total_exposure / portfolio_value if portfolio_value > 0 else 0
            
            # Check 1: Total exposure limit
            if exposure_pct > self.risk_profile.max_total_exposure:
                warning = (
                    f"Total exposure {exposure_pct:.1%} exceeds limit "
                    f"{self.risk_profile.max_total_exposure:.1%}"
                )
                warnings.append(warning)
                logger.warning(f"Portfolio risk: {warning}")
            
            # Check 2: Drawdown limit
            if portfolio_value > self.peak_value:
                self.peak_value = portfolio_value
            
            current_drawdown = (self.peak_value - portfolio_value) / self.peak_value
            if current_drawdown > self.risk_profile.max_drawdown:
                warning = (
                    f"Drawdown {current_drawdown:.1%} exceeds limit "
                    f"{self.risk_profile.max_drawdown:.1%}"
                )
                warnings.append(warning)
                logger.error(f"Portfolio risk: {warning}")
                
                self._generate_alert(
                    alert_type='drawdown',
                    severity='critical',
                    message=f"Maximum drawdown exceeded: {current_drawdown:.1%}",
                    details={
                        'current_drawdown': current_drawdown,
                        'max_allowed': self.risk_profile.max_drawdown,
                        'peak_value': self.peak_value,
                        'current_value': portfolio_value
                    }
                )
            
            # Check 3: Daily loss limit
            self._check_daily_reset()
            daily_pnl = portfolio_value - self.daily_starting_value
            daily_loss_pct = abs(daily_pnl / self.daily_starting_value) if daily_pnl < 0 else 0
            
            if daily_loss_pct > self.risk_profile.max_daily_loss:
                warning = (
                    f"Daily loss {daily_loss_pct:.1%} exceeds limit "
                    f"{self.risk_profile.max_daily_loss:.1%}"
                )
                warnings.append(warning)
                logger.error(f"Portfolio risk: {warning}")
                
                self._generate_alert(
                    alert_type='daily_loss',
                    severity='critical',
                    message=f"Maximum daily loss exceeded: {daily_loss_pct:.1%}",
                    details={
                        'daily_loss_pct': daily_loss_pct,
                        'max_allowed': self.risk_profile.max_daily_loss,
                        'daily_starting_value': self.daily_starting_value,
                        'current_value': portfolio_value
                    }
                )
            
            if warnings:
                logger.warning(f"Portfolio risk check: {len(warnings)} warnings")
            else:
                logger.debug("Portfolio risk check PASSED")
            
            return len(warnings) == 0, warnings
    
    def calculate_portfolio_risk(
        self,
        current_positions: Dict[str, Position],
        current_prices: Dict[str, float],
        portfolio_value: float
    ) -> PortfolioRisk:
        """
        Calculate portfolio risk metrics
        
        Args:
            current_positions: Dict of current positions
            current_prices: Dict of current market prices
            portfolio_value: Current portfolio value
            
        Returns:
            PortfolioRisk snapshot
        """
        with self._lock:
            # Calculate exposure
            total_exposure = 0.0
            for symbol, position in current_positions.items():
                if symbol in current_prices:
                    exposure = abs(position.quantity * current_prices[symbol])
                    total_exposure += exposure
            
            exposure_pct = total_exposure / portfolio_value if portfolio_value > 0 else 0
            
            # Calculate margin (simplified - actual exposure as margin)
            margin_used = total_exposure
            margin_pct = margin_used / portfolio_value if portfolio_value > 0 else 0
            
            # Calculate drawdown
            if portfolio_value > self.peak_value:
                self.peak_value = portfolio_value
            
            current_drawdown = (self.peak_value - portfolio_value) / self.peak_value
            
            # Calculate daily P&L
            self._check_daily_reset()
            daily_pnl = portfolio_value - self.daily_starting_value
            daily_loss_pct = (daily_pnl / self.daily_starting_value) if self.daily_starting_value > 0 else 0
            
            # Calculate risk utilization (worst case of all limits)
            utilizations = [
                exposure_pct / self.risk_profile.max_total_exposure,
                current_drawdown / self.risk_profile.max_drawdown,
                abs(daily_loss_pct) / self.risk_profile.max_daily_loss if daily_pnl < 0 else 0,
                len(current_positions) / self.risk_profile.max_concurrent_positions
            ]
            risk_utilization = max(utilizations)
            
            return PortfolioRisk(
                total_value=portfolio_value,
                total_exposure=total_exposure,
                exposure_pct=exposure_pct,
                margin_used=margin_used,
                margin_pct=margin_pct,
                current_drawdown=current_drawdown,
                daily_pnl=daily_pnl,
                daily_loss_pct=daily_loss_pct,
                position_count=len(current_positions),
                risk_utilization=min(risk_utilization, 1.0)
            )
    
    def _check_daily_reset(self):
        """Check if we need to reset daily tracking"""
        today = datetime.now().date()
        
        if self.daily_reset_date is None or self.daily_reset_date != today:
            # New trading day - reset daily tracking
            self.daily_reset_date = today
            # Note: daily_starting_value should be set externally at market open
            logger.debug(f"Daily reset: {today}")
    
    def reset_daily_tracking(self, current_portfolio_value: float):
        """
        Reset daily tracking (call at market open)
        
        Args:
            current_portfolio_value: Portfolio value at market open
        """
        with self._lock:
            self.daily_starting_value = current_portfolio_value
            self.daily_reset_date = datetime.now().date()
            logger.info(f"Daily tracking reset: ${current_portfolio_value:,.2f}")
    
    def _generate_alert(
        self,
        alert_type: str,
        severity: str,
        message: str,
        details: Dict
    ):
        """Generate risk alert"""
        alert = RiskAlert(
            timestamp=datetime.now(),
            alert_type=alert_type,
            severity=severity,
            message=message,
            details=details
        )
        
        self.alerts.append(alert)
        
        if severity == 'critical':
            logger.error(f"RISK ALERT [{alert_type}]: {message}")
        else:
            logger.warning(f"Risk alert [{alert_type}]: {message}")
    
    def get_recent_alerts(self, count: int = 10) -> List[RiskAlert]:
        """
        Get recent risk alerts
        
        Args:
            count: Number of recent alerts to return
            
        Returns:
            List of RiskAlert objects
        """
        with self._lock:
            return self.alerts[-count:] if self.alerts else []
    
    def clear_alerts(self):
        """Clear alert history"""
        with self._lock:
            self.alerts.clear()
            logger.info("Risk alerts cleared")
    
    def get_risk_summary(self) -> Dict:
        """
        Get risk monitoring summary
        
        Returns:
            Dictionary with risk monitoring state
        """
        with self._lock:
            return {
                'profile_name': self.risk_profile.name,
                'initial_capital': self.initial_capital,
                'peak_value': self.peak_value,
                'daily_starting_value': self.daily_starting_value,
                'alert_count': len(self.alerts),
                'daily_reset_date': str(self.daily_reset_date) if self.daily_reset_date else None
            }
