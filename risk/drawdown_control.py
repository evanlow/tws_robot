"""
Drawdown Protection & Monitoring System

This module implements comprehensive drawdown monitoring and protection mechanisms
for risk management. It tracks peak equity, calculates real-time drawdown, and
implements protective measures including position scaling and trading halts.

Key Features:
- Real-time drawdown calculation from peak equity
- Daily, weekly, and maximum drawdown limits
- Automatic position scaling during drawdown periods
- Trading halt triggers and recovery mechanisms
- Detailed drawdown event logging

Author: Trading Bot Development Team
Date: November 21, 2025
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from enum import Enum


class DrawdownSeverity(Enum):
    """Severity levels for drawdown conditions"""
    NORMAL = "NORMAL"           # No significant drawdown
    MINOR = "MINOR"             # 5-10% drawdown
    MODERATE = "MODERATE"       # 10-15% drawdown
    SEVERE = "SEVERE"           # 15-20% drawdown
    CRITICAL = "CRITICAL"       # >20% drawdown


@dataclass
class DrawdownMetrics:
    """Comprehensive drawdown metrics and status"""
    timestamp: datetime
    current_equity: float
    peak_equity: float
    drawdown_amount: float
    drawdown_pct: float
    
    # Period-specific metrics
    daily_pnl: float
    daily_pnl_pct: float
    weekly_pnl: float
    weekly_pnl_pct: float
    
    # Status and controls
    severity: DrawdownSeverity
    position_scale_factor: float  # 0.0 to 1.0
    is_trading_halted: bool
    halt_reason: Optional[str]
    
    # Recovery tracking
    recovery_needed_pct: float    # % needed to return to peak
    bars_in_drawdown: int         # Number of periods in drawdown

    # Convenience / compatibility fields
    current_drawdown_pct: float = field(default=0.0)   # drawdown as decimal fraction (0-1)
    current_drawdown: float = field(default=0.0)        # drawdown amount in dollars (alias for drawdown_amount)
    in_protection_mode: bool = field(default=False)    # severity > MINOR
    protection_level: Optional[str] = field(default=None)  # severity label when in protection
    trading_allowed: bool = field(default=True)         # not is_trading_halted
    max_drawdown_pct: float = field(default=0.0)        # configured max drawdown (decimal)
    max_position_pct: float = field(default=1.0)        # max position pct allowed (position_scale_factor)
    recovery_target: float = field(default=0.0)         # equity target for recovery (peak_equity)
    
    def __str__(self) -> str:
        return (
            f"DrawdownMetrics("
            f"equity=${self.current_equity:,.2f}, "
            f"peak=${self.peak_equity:,.2f}, "
            f"DD={self.drawdown_pct:.2f}%, "
            f"severity={self.severity.value}, "
            f"scale={self.position_scale_factor:.2f}, "
            f"halted={self.is_trading_halted})"
        )


@dataclass
class DrawdownEvent:
    """Record of a significant drawdown event"""
    start_date: datetime
    end_date: Optional[datetime]
    start_equity: float
    peak_equity: float
    trough_equity: float
    max_drawdown_pct: float
    recovery_equity: Optional[float]
    duration_days: int
    is_recovered: bool
    
    def __str__(self) -> str:
        status = "Recovered" if self.is_recovered else "Ongoing"
        return (
            f"DrawdownEvent({status}, "
            f"max_DD={self.max_drawdown_pct:.2f}%, "
            f"duration={self.duration_days}d)"
        )


class DrawdownMonitor:
    """
    Comprehensive drawdown monitoring and protection system.
    
    This class tracks equity peaks and drawdowns in real-time, implementing
    protective measures including position scaling and trading halts. It
    monitors multiple timeframes (daily, weekly, maximum) and provides
    detailed metrics for risk management decisions.
    
    Parameters
    ----------
    initial_equity : float
        Starting account equity
    max_drawdown_pct : float
        Maximum allowed drawdown before emergency stop (default: 0.20 = 20%)
    daily_loss_limit_pct : float
        Maximum allowed daily loss (default: 0.05 = 5%)
    weekly_loss_limit_pct : float
        Maximum allowed weekly loss (default: 0.10 = 10%)
    scale_positions_on_drawdown : bool
        Whether to reduce position sizes during drawdown (default: True)
    minor_drawdown_threshold : float
        Threshold for minor drawdown severity (default: 0.05 = 5%)
    moderate_drawdown_threshold : float
        Threshold for moderate drawdown severity (default: 0.10 = 10%)
    severe_drawdown_threshold : float
        Threshold for severe drawdown severity (default: 0.15 = 15%)
    
    Example
    -------
    >>> monitor = DrawdownMonitor(initial_equity=100000)
    >>> metrics = monitor.update(current_equity=95000, current_date=datetime.now())
    >>> print(f"Drawdown: {metrics.drawdown_pct:.2f}%")
    >>> if metrics.is_trading_halted:
    ...     print(f"Trading halted: {metrics.halt_reason}")
    """
    
    def __init__(
        self,
        initial_equity: float = 100000,
        max_drawdown_pct: float = 0.20,
        daily_loss_limit_pct: float = 0.05,
        weekly_loss_limit_pct: float = 0.10,
        scale_positions_on_drawdown: bool = True,
        minor_drawdown_threshold: float = 0.05,
        moderate_drawdown_threshold: float = 0.10,
        severe_drawdown_threshold: float = 0.15,
    ):
        # Configuration
        self.initial_equity = initial_equity
        self.max_drawdown_pct = max_drawdown_pct
        self.daily_loss_limit_pct = daily_loss_limit_pct
        self.weekly_loss_limit_pct = weekly_loss_limit_pct
        self.scale_positions_on_drawdown = scale_positions_on_drawdown
        
        # Severity thresholds
        self.minor_threshold = minor_drawdown_threshold
        self.moderate_threshold = moderate_drawdown_threshold
        self.severe_threshold = severe_drawdown_threshold
        
        # State tracking
        self.peak_equity = initial_equity
        self.current_equity = initial_equity
        self.current_date = None
        
        # Daily tracking
        self.daily_start_equity = initial_equity
        self.last_update_date = None
        
        # Weekly tracking
        self.weekly_start_equity = initial_equity
        self.week_start_date = None
        
        # Drawdown tracking
        self.current_drawdown_start = None
        self.trough_equity = initial_equity
        self.bars_in_drawdown = 0
        
        # Trading controls
        self.is_trading_halted = False
        self.halt_reason = None
        self.halt_start_date = None
        
        # Event history
        self.drawdown_events: List[DrawdownEvent] = []
        self.metrics_history: List[DrawdownMetrics] = []
        
    def update(
        self,
        current_equity: float,
        current_date: datetime,
    ) -> DrawdownMetrics:
        """
        Update drawdown monitor with current equity and calculate metrics.
        
        This method should be called regularly (e.g., end of each trading day)
        to keep drawdown metrics current. It updates peak equity, calculates
        drawdowns, checks protective limits, and adjusts position scaling.
        
        Parameters
        ----------
        current_equity : float
            Current account equity
        current_date : datetime
            Current date/time
            
        Returns
        -------
        DrawdownMetrics
            Comprehensive drawdown metrics and status
        """
        # Save previous equity before updating
        previous_equity = self.current_equity
        
        self.current_equity = current_equity
        self.current_date = current_date
        
        # Initialize date tracking on first update
        if self.last_update_date is None:
            self.last_update_date = current_date
            self.week_start_date = current_date
            
        # Check for new day (reset daily tracking)
        if self._is_new_day(current_date):
            # Use previous day's end equity as new day's start
            self.daily_start_equity = previous_equity
            self.last_update_date = current_date
            
        # Check for new week (reset weekly tracking)
        if self._is_new_week(current_date):
            # Use previous week's end equity as new week's start
            self.weekly_start_equity = previous_equity
            self.week_start_date = current_date
            
        # Update peak equity if we've recovered
        if current_equity > self.peak_equity:
            self._handle_new_peak(current_equity, current_date)
        elif current_equity < self.peak_equity:
            # In drawdown - update trough and increment counter
            if current_equity < self.trough_equity:
                self.trough_equity = current_equity
            # Count total updates while in drawdown (including peak for reference)
            if self.bars_in_drawdown == 0:
                # First time in drawdown - count from peak
                self.bars_in_drawdown = 2  # Peak day + this day
            else:
                self.bars_in_drawdown += 1
            
        # Calculate current metrics
        metrics = self._calculate_metrics(current_date)
        
        # Check protective stops (may update halt status)
        self._check_protective_stops(metrics)
        
        # Recalculate metrics if halt status changed
        if self.is_trading_halted and not metrics.is_trading_halted:
            metrics = self._calculate_metrics(current_date)
        
        # Store metrics
        self.metrics_history.append(metrics)
        
        return metrics
    
    def _is_new_day(self, current_date: datetime) -> bool:
        """Check if we've moved to a new trading day"""
        if self.last_update_date is None:
            return True
        return current_date.date() > self.last_update_date.date()
    
    def _is_new_week(self, current_date: datetime) -> bool:
        """Check if we've moved to a new week"""
        if self.week_start_date is None:
            return True
        days_diff = (current_date - self.week_start_date).days
        return days_diff >= 7
    
    def _handle_new_peak(self, new_equity: float, current_date: datetime):
        """Handle reaching a new equity peak (recovery from drawdown)"""
        # If we were in a drawdown, record the event
        if self.current_drawdown_start is not None:
            event = DrawdownEvent(
                start_date=self.current_drawdown_start,
                end_date=current_date,
                start_equity=self.peak_equity,
                peak_equity=self.peak_equity,
                trough_equity=self.trough_equity,
                max_drawdown_pct=((self.peak_equity - self.trough_equity) / self.peak_equity) * 100,
                recovery_equity=new_equity,
                duration_days=(current_date - self.current_drawdown_start).days + 1,  # Inclusive count
                is_recovered=True,
            )
            self.drawdown_events.append(event)
            self.current_drawdown_start = None
            
        # Update peak
        self.peak_equity = new_equity
        self.trough_equity = new_equity
        self.bars_in_drawdown = 0
    
    def _calculate_metrics(self, current_date: datetime) -> DrawdownMetrics:
        """Calculate comprehensive drawdown metrics"""
        # Drawdown from peak
        drawdown_amount = self.peak_equity - self.current_equity
        drawdown_pct = (drawdown_amount / self.peak_equity) * 100 if self.peak_equity > 0 else 0
        
        # Daily P&L
        daily_pnl = self.current_equity - self.daily_start_equity
        daily_pnl_pct = (daily_pnl / self.daily_start_equity) * 100 if self.daily_start_equity > 0 else 0
        
        # Weekly P&L
        weekly_pnl = self.current_equity - self.weekly_start_equity
        weekly_pnl_pct = (weekly_pnl / self.weekly_start_equity) * 100 if self.weekly_start_equity > 0 else 0
        
        # Determine severity
        severity = self._determine_severity(drawdown_pct)
        
        # Calculate position scale factor
        position_scale_factor = self._calculate_position_scale(drawdown_pct)
        
        # Recovery needed
        recovery_needed_pct = ((self.peak_equity - self.current_equity) / self.current_equity) * 100 if self.current_equity > 0 else 0
        
        # Track drawdown start
        if drawdown_pct > 0 and self.current_drawdown_start is None:
            self.current_drawdown_start = current_date
        
        return DrawdownMetrics(
            timestamp=current_date,
            current_equity=self.current_equity,
            peak_equity=self.peak_equity,
            drawdown_amount=drawdown_amount,
            drawdown_pct=drawdown_pct,
            daily_pnl=daily_pnl,
            daily_pnl_pct=daily_pnl_pct,
            weekly_pnl=weekly_pnl,
            weekly_pnl_pct=weekly_pnl_pct,
            severity=severity,
            position_scale_factor=position_scale_factor,
            is_trading_halted=self.is_trading_halted,
            halt_reason=self.halt_reason,
            recovery_needed_pct=recovery_needed_pct,
            bars_in_drawdown=self.bars_in_drawdown,
            current_drawdown_pct=drawdown_pct / 100.0,
            current_drawdown=drawdown_amount,
            in_protection_mode=severity.value not in ('NORMAL', 'MINOR'),
            protection_level=severity.value if severity.value not in ('NORMAL', 'MINOR') else None,
            trading_allowed=not self.is_trading_halted,
            max_drawdown_pct=self.max_drawdown_pct,
            max_position_pct=position_scale_factor,
            recovery_target=self.peak_equity,
        )
    
    def _determine_severity(self, drawdown_pct: float) -> DrawdownSeverity:
        """Determine drawdown severity level"""
        if drawdown_pct >= self.max_drawdown_pct * 100:
            return DrawdownSeverity.CRITICAL
        elif drawdown_pct >= self.severe_threshold * 100:
            return DrawdownSeverity.SEVERE
        elif drawdown_pct >= self.moderate_threshold * 100:
            return DrawdownSeverity.MODERATE
        elif drawdown_pct >= self.minor_threshold * 100:
            return DrawdownSeverity.MINOR
        else:
            return DrawdownSeverity.NORMAL
    
    def _calculate_position_scale(self, drawdown_pct: float) -> float:
        """
        Calculate position sizing scale factor based on drawdown.
        
        Returns a factor between 0.0 (no trading) and 1.0 (full size).
        Gradually reduces position sizes as drawdown increases.
        """
        if not self.scale_positions_on_drawdown:
            return 1.0
        
        if self.is_trading_halted:
            return 0.0
        
        # No scaling if drawdown is minor
        if drawdown_pct < self.minor_threshold * 100:
            return 1.0
        
        # Linear scaling from minor to max drawdown
        # At minor threshold: 100% size
        # At max drawdown: 50% size (or 0% if halted)
        scale_range = (self.max_drawdown_pct - self.minor_threshold) * 100
        drawdown_above_minor = drawdown_pct - (self.minor_threshold * 100)
        
        # Scale from 1.0 to 0.5
        scale_factor = 1.0 - (0.5 * (drawdown_above_minor / scale_range))
        
        return max(0.5, min(1.0, scale_factor))
    
    def _check_protective_stops(self, metrics: DrawdownMetrics):
        """Check if any protective stops should be triggered"""
        # Check max drawdown limit
        if metrics.drawdown_pct >= self.max_drawdown_pct * 100:
            if not self.is_trading_halted:
                self._trigger_halt(
                    f"Maximum drawdown limit reached: {metrics.drawdown_pct:.2f}% >= {self.max_drawdown_pct*100:.2f}%"
                )
        
        # Check daily loss limit (compare absolute values)
        if abs(metrics.daily_pnl_pct) >= self.daily_loss_limit_pct * 100:
            if metrics.daily_pnl < 0 and not self.is_trading_halted:
                self._trigger_halt(
                    f"Daily loss limit exceeded: {metrics.daily_pnl_pct:.2f}% >= {self.daily_loss_limit_pct*100:.2f}%"
                )
        
        # Check weekly loss limit (compare absolute values)
        if abs(metrics.weekly_pnl_pct) >= self.weekly_loss_limit_pct * 100:
            if metrics.weekly_pnl < 0 and not self.is_trading_halted:
                self._trigger_halt(
                    f"Weekly loss limit exceeded: {metrics.weekly_pnl_pct:.2f}% >= {self.weekly_loss_limit_pct*100:.2f}%"
                )
    
    def _trigger_halt(self, reason: str):
        """Trigger a trading halt"""
        self.is_trading_halted = True
        self.halt_reason = reason
        self.halt_start_date = self.current_date
    
    def should_stop_trading(self) -> Tuple[bool, Optional[str]]:
        """
        Check if trading should be stopped.
        
        Returns
        -------
        tuple
            (should_stop: bool, reason: str or None)
        """
        return self.is_trading_halted, self.halt_reason
    
    def can_place_trade(self) -> bool:
        """Check if new trades are allowed"""
        return not self.is_trading_halted
    
    def get_position_scale_factor(self) -> float:
        """
        Get current position sizing scale factor.
        
        Returns
        -------
        float
            Scale factor between 0.0 (no trading) and 1.0 (full size)
        """
        if self.is_trading_halted:
            return 0.0
        
        if self.metrics_history:
            return self.metrics_history[-1].position_scale_factor
        
        metrics = self._calculate_metrics(self.current_date or datetime.now())
        return metrics.position_scale_factor
    
    def resume_trading(self, reason: str) -> bool:
        """
        Manually resume trading after a halt.
        
        Parameters
        ----------
        reason : str
            Reason for resuming trading
            
        Returns
        -------
        bool
            True if trading resumed, False if conditions not met
        """
        if not self.is_trading_halted:
            return False
        
        # Check if conditions have improved enough to resume
        metrics = self._calculate_metrics(self.current_date or datetime.now())
        
        # Only allow manual resume if drawdown has improved
        if metrics.drawdown_pct < self.max_drawdown_pct * 90:  # 90% of max
            self.is_trading_halted = False
            self.halt_reason = None
            self.halt_start_date = None
            return True
        
        return False
    
    def get_drawdown_summary(self) -> Dict:
        """Get summary of drawdown history and current status"""
        current_metrics = self.metrics_history[-1] if self.metrics_history else None
        
        # Calculate average drawdown
        avg_drawdown = sum(m.drawdown_pct for m in self.metrics_history) / len(self.metrics_history) if self.metrics_history else 0
        
        # Find max historical drawdown
        max_historical_dd = max((m.drawdown_pct for m in self.metrics_history), default=0)
        
        # Count events by severity
        recovered_events = [e for e in self.drawdown_events if e.is_recovered]
        avg_recovery_days = sum(e.duration_days for e in recovered_events) / len(recovered_events) if recovered_events else 0
        
        return {
            "current_equity": self.current_equity,
            "peak_equity": self.peak_equity,
            "current_drawdown_pct": current_metrics.drawdown_pct if current_metrics else 0,
            "current_severity": current_metrics.severity.value if current_metrics else "NORMAL",
            "is_trading_halted": self.is_trading_halted,
            "halt_reason": self.halt_reason,
            "position_scale_factor": current_metrics.position_scale_factor if current_metrics else 1.0,
            "historical_stats": {
                "total_drawdown_events": len(self.drawdown_events),
                "recovered_events": len(recovered_events),
                "max_drawdown_pct": max_historical_dd,
                "avg_drawdown_pct": avg_drawdown,
                "avg_recovery_days": avg_recovery_days,
            }
        }
    
    def get_recent_metrics(self, n: int = 10) -> List[DrawdownMetrics]:
        """Get the N most recent drawdown metrics"""
        return self.metrics_history[-n:] if len(self.metrics_history) >= n else self.metrics_history
    
    def reset(self, new_equity: float = None):
        """
        Reset the drawdown monitor.
        
        Parameters
        ----------
        new_equity : float, optional
            New starting equity (uses current equity if not provided)
        """
        if new_equity is not None:
            self.initial_equity = new_equity
            self.current_equity = new_equity
        
        self.peak_equity = self.current_equity
        self.daily_start_equity = self.current_equity
        self.weekly_start_equity = self.current_equity
        self.trough_equity = self.current_equity
        
        self.is_trading_halted = False
        self.halt_reason = None
        self.halt_start_date = None
        
        self.current_drawdown_start = None
        self.bars_in_drawdown = 0
