"""
Emergency Controls & Circuit Breakers

This module provides emergency stop functionality and circuit breakers to protect
against catastrophic losses and system failures.

Author: Risk Management System
Date: November 2025
Week 3 Day 6: Emergency Controls
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Callable
from enum import Enum
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class EmergencyLevel(Enum):
    """Emergency severity levels"""
    NONE = "NONE"           # Normal operation
    WARNING = "WARNING"     # Caution, monitoring closely
    ALERT = "ALERT"         # Protective measures engaged
    CRITICAL = "CRITICAL"   # Circuit breaker triggered
    SHUTDOWN = "SHUTDOWN"   # Complete system shutdown


class TriggerReason(Enum):
    """Reasons for emergency trigger"""
    MANUAL = "MANUAL"                       # Manual user trigger
    DRAWDOWN_LIMIT = "DRAWDOWN_LIMIT"       # Max drawdown exceeded
    DAILY_LOSS = "DAILY_LOSS"               # Daily loss limit exceeded
    POSITION_LOSS = "POSITION_LOSS"         # Single position loss limit
    CORRELATION_SPIKE = "CORRELATION_SPIKE" # Sudden correlation increase
    MARKET_VOLATILITY = "MARKET_VOLATILITY" # Extreme volatility detected
    SYSTEM_ERROR = "SYSTEM_ERROR"           # System malfunction
    CONNECTION_LOSS = "CONNECTION_LOSS"     # Lost connection to broker
    DATA_ANOMALY = "DATA_ANOMALY"           # Suspicious data detected


@dataclass
class CircuitBreakerConfig:
    """Configuration for a circuit breaker"""
    name: str
    threshold: float
    cooldown_minutes: int = 15
    auto_resume: bool = False
    max_triggers_per_day: int = 3
    description: str = ""


@dataclass
class EmergencyEvent:
    """Record of an emergency event"""
    timestamp: datetime
    level: EmergencyLevel
    reason: TriggerReason
    trigger_value: float
    threshold: float
    message: str
    auto_triggered: bool
    positions_closed: int = 0
    orders_cancelled: int = 0
    
    def __str__(self) -> str:
        return f"[{self.level.value}] {self.reason.value}: {self.message}"


@dataclass
class EmergencyStatus:
    """Current emergency control status"""
    timestamp: datetime
    level: EmergencyLevel
    is_active: bool
    trading_allowed: bool
    new_positions_allowed: bool
    position_increases_allowed: bool
    
    # Active triggers
    active_breakers: List[str] = field(default_factory=list)
    
    # Event history
    recent_events: List[EmergencyEvent] = field(default_factory=list)
    
    # Recovery info
    can_resume: bool = False
    resume_time: Optional[datetime] = None
    manual_intervention_required: bool = False
    
    def get_status_message(self) -> str:
        """Get human-readable status message"""
        if not self.is_active:
            return "Normal operation - all systems operational"
        
        if self.level == EmergencyLevel.SHUTDOWN:
            return "EMERGENCY SHUTDOWN - Manual intervention required"
        elif self.level == EmergencyLevel.CRITICAL:
            return f"CRITICAL - Circuit breakers active: {', '.join(self.active_breakers)}"
        elif self.level == EmergencyLevel.ALERT:
            return "ALERT - Protective measures engaged"
        elif self.level == EmergencyLevel.WARNING:
            return "WARNING - Monitoring closely"
        
        return "Unknown status"


class CircuitBreaker:
    """
    Individual circuit breaker that monitors a specific condition
    and triggers when threshold is exceeded.
    """
    
    def __init__(self, config: CircuitBreakerConfig):
        """
        Initialize circuit breaker
        
        Args:
            config: Circuit breaker configuration
        """
        self.config = config
        self.is_tripped = False
        self.trip_time: Optional[datetime] = None
        self.trip_count_today = 0
        self.last_reset_date: Optional[datetime] = None
        self.trip_history: List[datetime] = []
    
    def check(self, current_value: float, timestamp: datetime) -> bool:
        """
        Check if circuit breaker should trip
        
        Args:
            current_value: Current value to check
            timestamp: Current timestamp
            
        Returns:
            True if breaker tripped, False otherwise
        """
        # Reset daily counter if new day
        if self.last_reset_date is None or timestamp.date() != self.last_reset_date:
            self.trip_count_today = 0
            self.last_reset_date = timestamp.date()
        
        # Check if already at daily limit
        if self.trip_count_today >= self.config.max_triggers_per_day:
            logger.warning(
                f"Circuit breaker '{self.config.name}' at daily limit "
                f"({self.trip_count_today} trips)"
            )
            return False
        
        # Check if in cooldown period
        if self.is_tripped and self.trip_time is not None:
            cooldown_end = self.trip_time + timedelta(minutes=self.config.cooldown_minutes)
            if timestamp < cooldown_end:
                return False  # Still in cooldown
            elif self.config.auto_resume:
                self.reset()
        
        # Check threshold
        if current_value >= self.config.threshold:
            if not self.is_tripped:
                self.trip(timestamp)
                return True
        
        return False
    
    def trip(self, timestamp: datetime) -> None:
        """Trip the circuit breaker"""
        self.is_tripped = True
        self.trip_time = timestamp
        self.trip_count_today += 1
        self.trip_history.append(timestamp)
        
        logger.critical(
            f"⚠️  CIRCUIT BREAKER TRIPPED: {self.config.name} "
            f"(Trip #{self.trip_count_today} today)"
        )
    
    def reset(self) -> None:
        """Reset the circuit breaker"""
        if self.is_tripped:
            logger.info(f"Circuit breaker '{self.config.name}' reset")
        self.is_tripped = False
        self.trip_time = None
    
    def can_auto_resume(self, timestamp: datetime) -> bool:
        """Check if breaker can automatically resume"""
        if not self.is_tripped or self.trip_time is None:
            return True
        
        if not self.config.auto_resume:
            return False
        
        cooldown_end = self.trip_time + timedelta(minutes=self.config.cooldown_minutes)
        return timestamp >= cooldown_end


class EmergencyController:
    """
    Emergency control system with circuit breakers, kill switch,
    and panic button functionality.
    """
    
    def __init__(
        self,
        # Drawdown limits
        max_drawdown_pct: float = 0.20,         # 20% max drawdown
        critical_drawdown_pct: float = 0.15,    # 15% critical drawdown
        
        # Loss limits
        max_daily_loss_pct: float = 0.05,       # 5% max daily loss
        max_position_loss_pct: float = 0.10,    # 10% max single position loss
        
        # Circuit breaker settings
        cooldown_minutes: int = 30,
        max_daily_triggers: int = 3,
        
        # Auto-recovery settings
        auto_resume_enabled: bool = False,
        require_manual_review: bool = True,
        
        # Callbacks
        on_emergency_callback: Optional[Callable] = None,
        on_resume_callback: Optional[Callable] = None,
    ):
        """
        Initialize emergency controller
        
        Args:
            max_drawdown_pct: Maximum drawdown before shutdown
            critical_drawdown_pct: Drawdown triggering circuit breaker
            max_daily_loss_pct: Maximum daily loss before shutdown
            max_position_loss_pct: Maximum single position loss
            cooldown_minutes: Minutes before auto-resume possible
            max_daily_triggers: Max circuit breaker trips per day
            auto_resume_enabled: Allow automatic recovery
            require_manual_review: Require manual approval for resume
            on_emergency_callback: Callback when emergency triggered
            on_resume_callback: Callback when operations resume
        """
        self.max_drawdown_pct = max_drawdown_pct
        self.critical_drawdown_pct = critical_drawdown_pct
        self.max_daily_loss_pct = max_daily_loss_pct
        self.max_position_loss_pct = max_position_loss_pct
        self.cooldown_minutes = cooldown_minutes
        self.max_daily_triggers = max_daily_triggers
        self.auto_resume_enabled = auto_resume_enabled
        self.require_manual_review = require_manual_review
        
        # Callbacks
        self.on_emergency_callback = on_emergency_callback
        self.on_resume_callback = on_resume_callback
        
        # State
        self.current_level = EmergencyLevel.NONE
        self.is_shutdown = False
        self.shutdown_time: Optional[datetime] = None
        self.shutdown_reason: Optional[TriggerReason] = None
        
        # Circuit breakers
        self.breakers: Dict[str, CircuitBreaker] = {}
        self._initialize_breakers()
        
        # Event tracking
        self.event_history: List[EmergencyEvent] = []
        self.active_events: List[EmergencyEvent] = []
        
        # Manual controls
        self.manual_override_active = False
        self.kill_switch_activated = False
        
        logger.info("Emergency Controller initialized")
        logger.info(f"  Max Drawdown: {max_drawdown_pct:.1%}")
        logger.info(f"  Critical Drawdown: {critical_drawdown_pct:.1%}")
        logger.info(f"  Max Daily Loss: {max_daily_loss_pct:.1%}")
        logger.info(f"  Auto-resume: {auto_resume_enabled}")
    
    def _initialize_breakers(self) -> None:
        """Initialize circuit breakers"""
        
        # Drawdown circuit breaker
        self.breakers['drawdown'] = CircuitBreaker(
            CircuitBreakerConfig(
                name='drawdown',
                threshold=self.critical_drawdown_pct,
                cooldown_minutes=self.cooldown_minutes,
                auto_resume=self.auto_resume_enabled,
                max_triggers_per_day=self.max_daily_triggers,
                description='Portfolio drawdown protection'
            )
        )
        
        # Daily loss circuit breaker
        self.breakers['daily_loss'] = CircuitBreaker(
            CircuitBreakerConfig(
                name='daily_loss',
                threshold=self.max_daily_loss_pct * 0.8,  # Trigger at 80% of max
                cooldown_minutes=self.cooldown_minutes,
                auto_resume=self.auto_resume_enabled,
                max_triggers_per_day=self.max_daily_triggers,
                description='Daily loss protection'
            )
        )
        
        # Position loss circuit breaker
        self.breakers['position_loss'] = CircuitBreaker(
            CircuitBreakerConfig(
                name='position_loss',
                threshold=self.max_position_loss_pct,
                cooldown_minutes=self.cooldown_minutes // 2,  # Shorter cooldown
                auto_resume=False,  # Require manual review
                max_triggers_per_day=self.max_daily_triggers,
                description='Single position loss protection'
            )
        )
        
        # Volatility circuit breaker
        self.breakers['volatility'] = CircuitBreaker(
            CircuitBreakerConfig(
                name='volatility',
                threshold=3.0,  # 3x normal volatility
                cooldown_minutes=self.cooldown_minutes,
                auto_resume=self.auto_resume_enabled,
                max_triggers_per_day=5,  # Allow more triggers
                description='Market volatility protection'
            )
        )
    
    def check_emergency_conditions(
        self,
        current_equity: float,
        starting_equity: float,
        daily_starting_equity: float,
        peak_equity: float,
        positions: Optional[Dict] = None,
        timestamp: Optional[datetime] = None
    ) -> EmergencyStatus:
        """
        Check all emergency conditions and update status
        
        Args:
            current_equity: Current account equity
            starting_equity: Starting equity (for total drawdown)
            daily_starting_equity: Starting equity for today
            peak_equity: All-time peak equity
            positions: Optional current positions
            timestamp: Current timestamp
            
        Returns:
            Emergency status
        """
        if timestamp is None:
            timestamp = datetime.now()
        
        # If already shutdown, maintain shutdown state
        if self.is_shutdown:
            return self._get_status(timestamp)
        
        # Check kill switch
        if self.kill_switch_activated:
            self._trigger_emergency(
                level=EmergencyLevel.SHUTDOWN,
                reason=TriggerReason.MANUAL,
                message="Kill switch activated",
                trigger_value=0.0,
                threshold=0.0,
                timestamp=timestamp,
                auto_triggered=False
            )
            return self._get_status(timestamp)
        
        # Calculate metrics
        total_drawdown = (peak_equity - current_equity) / peak_equity if peak_equity > 0 else 0
        daily_loss_pct = (daily_starting_equity - current_equity) / daily_starting_equity if daily_starting_equity > 0 else 0
        
        # Check for immediate shutdown conditions
        if total_drawdown >= self.max_drawdown_pct:
            self._trigger_emergency(
                level=EmergencyLevel.SHUTDOWN,
                reason=TriggerReason.DRAWDOWN_LIMIT,
                message=f"Maximum drawdown exceeded: {total_drawdown:.1%}",
                trigger_value=total_drawdown,
                threshold=self.max_drawdown_pct,
                timestamp=timestamp
            )
            return self._get_status(timestamp)
        
        if daily_loss_pct >= self.max_daily_loss_pct:
            self._trigger_emergency(
                level=EmergencyLevel.SHUTDOWN,
                reason=TriggerReason.DAILY_LOSS,
                message=f"Maximum daily loss exceeded: {daily_loss_pct:.1%}",
                trigger_value=daily_loss_pct,
                threshold=self.max_daily_loss_pct,
                timestamp=timestamp
            )
            return self._get_status(timestamp)
        
        # Check circuit breakers
        breakers_tripped = []
        
        if self.breakers['drawdown'].check(total_drawdown, timestamp):
            breakers_tripped.append('drawdown')
            self._trigger_emergency(
                level=EmergencyLevel.CRITICAL,
                reason=TriggerReason.DRAWDOWN_LIMIT,
                message=f"Drawdown circuit breaker tripped: {total_drawdown:.1%}",
                trigger_value=total_drawdown,
                threshold=self.critical_drawdown_pct,
                timestamp=timestamp
            )
        
        if self.breakers['daily_loss'].check(daily_loss_pct, timestamp):
            breakers_tripped.append('daily_loss')
            self._trigger_emergency(
                level=EmergencyLevel.CRITICAL,
                reason=TriggerReason.DAILY_LOSS,
                message=f"Daily loss circuit breaker tripped: {daily_loss_pct:.1%}",
                trigger_value=daily_loss_pct,
                threshold=self.max_daily_loss_pct * 0.8,
                timestamp=timestamp
            )
        
        # Check position losses if provided
        if positions:
            for symbol, position in positions.items():
                if hasattr(position, 'unrealized_pnl_pct'):
                    loss_pct = abs(position.unrealized_pnl_pct) if position.unrealized_pnl_pct < 0 else 0
                    if self.breakers['position_loss'].check(loss_pct, timestamp):
                        breakers_tripped.append(f'position_{symbol}')
                        self._trigger_emergency(
                            level=EmergencyLevel.CRITICAL,
                            reason=TriggerReason.POSITION_LOSS,
                            message=f"Position loss breaker tripped: {symbol} down {loss_pct:.1%}",
                            trigger_value=loss_pct,
                            threshold=self.max_position_loss_pct,
                            timestamp=timestamp
                        )
        
        # Update emergency level based on active breakers
        if breakers_tripped:
            self.current_level = EmergencyLevel.CRITICAL
        elif total_drawdown >= self.critical_drawdown_pct * 0.75:
            self.current_level = EmergencyLevel.ALERT
        elif total_drawdown >= self.critical_drawdown_pct * 0.5 or daily_loss_pct >= self.max_daily_loss_pct * 0.5:
            self.current_level = EmergencyLevel.WARNING
        else:
            self.current_level = EmergencyLevel.NONE
        
        return self._get_status(timestamp)
    
    def _trigger_emergency(
        self,
        level: EmergencyLevel,
        reason: TriggerReason,
        message: str,
        trigger_value: float,
        threshold: float,
        timestamp: datetime,
        auto_triggered: bool = True
    ) -> None:
        """Trigger emergency condition"""
        
        event = EmergencyEvent(
            timestamp=timestamp,
            level=level,
            reason=reason,
            trigger_value=trigger_value,
            threshold=threshold,
            message=message,
            auto_triggered=auto_triggered
        )
        
        self.event_history.append(event)
        self.active_events.append(event)
        
        # Log emergency
        log_level = logging.CRITICAL if level == EmergencyLevel.SHUTDOWN else logging.ERROR
        logger.log(log_level, f"🚨 EMERGENCY: {event}")
        
        # Update state
        if level == EmergencyLevel.SHUTDOWN:
            self.is_shutdown = True
            self.shutdown_time = timestamp
            self.shutdown_reason = reason
        
        self.current_level = level
        
        # Execute callback
        if self.on_emergency_callback:
            try:
                self.on_emergency_callback(event)
            except Exception as e:
                logger.error(f"Error in emergency callback: {e}")
    
    def _get_status(self, timestamp: datetime) -> EmergencyStatus:
        """Get current emergency status"""
        
        # Determine trading permissions
        trading_allowed = not self.is_shutdown and self.current_level not in [
            EmergencyLevel.SHUTDOWN, EmergencyLevel.CRITICAL
        ]
        
        new_positions_allowed = trading_allowed and self.current_level not in [
            EmergencyLevel.ALERT
        ]
        
        position_increases_allowed = trading_allowed and self.current_level == EmergencyLevel.NONE
        
        # Check if can resume
        can_resume = False
        resume_time = None
        
        if self.is_shutdown and self.auto_resume_enabled and not self.require_manual_review:
            if self.shutdown_time:
                cooldown_end = self.shutdown_time + timedelta(minutes=self.cooldown_minutes)
                can_resume = timestamp >= cooldown_end
                resume_time = cooldown_end
        
        # Get active breakers
        active_breakers = [
            name for name, breaker in self.breakers.items()
            if breaker.is_tripped
        ]
        
        # Get recent events (last 10)
        recent_events = self.event_history[-10:] if self.event_history else []
        
        return EmergencyStatus(
            timestamp=timestamp,
            level=self.current_level,
            is_active=self.current_level != EmergencyLevel.NONE or self.is_shutdown,
            trading_allowed=trading_allowed,
            new_positions_allowed=new_positions_allowed,
            position_increases_allowed=position_increases_allowed,
            active_breakers=active_breakers,
            recent_events=recent_events,
            can_resume=can_resume,
            resume_time=resume_time,
            manual_intervention_required=self.require_manual_review and self.is_shutdown
        )
    
    def activate_kill_switch(self, reason: str = "Manual activation") -> None:
        """
        Activate kill switch - immediately stops all trading
        
        Args:
            reason: Reason for activation
        """
        logger.critical("🔴 KILL SWITCH ACTIVATED")
        logger.critical(f"   Reason: {reason}")
        
        self.kill_switch_activated = True
        self._trigger_emergency(
            level=EmergencyLevel.SHUTDOWN,
            reason=TriggerReason.MANUAL,
            message=f"Kill switch: {reason}",
            trigger_value=0.0,
            threshold=0.0,
            timestamp=datetime.now(),
            auto_triggered=False
        )
    
    def panic_button(self) -> EmergencyStatus:
        """
        Panic button - immediate emergency stop
        
        Returns:
            Emergency status after panic button
        """
        logger.critical("🆘 PANIC BUTTON PRESSED")
        
        self.activate_kill_switch("Panic button pressed")
        return self._get_status(datetime.now())
    
    def request_resume(
        self,
        approved_by: str,
        reason: str,
        timestamp: Optional[datetime] = None
    ) -> bool:
        """
        Request to resume trading after emergency
        
        Args:
            approved_by: Who approved the resume
            reason: Reason for resuming
            timestamp: Optional timestamp
            
        Returns:
            True if resume successful, False otherwise
        """
        if timestamp is None:
            timestamp = datetime.now()
        
        if not self.is_shutdown:
            logger.info("Resume requested but system not shut down")
            return True
        
        # Check cooldown period
        if self.shutdown_time:
            cooldown_end = self.shutdown_time + timedelta(minutes=self.cooldown_minutes)
            if timestamp < cooldown_end:
                remaining = (cooldown_end - timestamp).total_seconds() / 60
                logger.warning(f"Cannot resume: {remaining:.1f} minutes remaining in cooldown")
                return False
        
        # Reset state
        logger.info(f"🟢 RESUMING OPERATIONS")
        logger.info(f"   Approved by: {approved_by}")
        logger.info(f"   Reason: {reason}")
        
        self.is_shutdown = False
        self.kill_switch_activated = False
        self.manual_override_active = False
        self.current_level = EmergencyLevel.NONE
        self.active_events = []
        
        # Reset circuit breakers
        for breaker in self.breakers.values():
            breaker.reset()
        
        # Execute callback
        if self.on_resume_callback:
            try:
                self.on_resume_callback(approved_by, reason)
            except Exception as e:
                logger.error(f"Error in resume callback: {e}")
        
        return True
    
    def reset_circuit_breaker(self, breaker_name: str) -> bool:
        """
        Manually reset a specific circuit breaker
        
        Args:
            breaker_name: Name of breaker to reset
            
        Returns:
            True if reset successful
        """
        if breaker_name in self.breakers:
            self.breakers[breaker_name].reset()
            logger.info(f"Circuit breaker '{breaker_name}' manually reset")
            return True
        else:
            logger.warning(f"Circuit breaker '{breaker_name}' not found")
            return False
    
    def get_breaker_status(self) -> Dict:
        """Get status of all circuit breakers"""
        return {
            name: {
                'is_tripped': breaker.is_tripped,
                'trip_time': breaker.trip_time.isoformat() if breaker.trip_time else None,
                'trip_count_today': breaker.trip_count_today,
                'can_auto_resume': breaker.can_auto_resume(datetime.now()),
                'config': {
                    'threshold': breaker.config.threshold,
                    'cooldown_minutes': breaker.config.cooldown_minutes,
                    'auto_resume': breaker.config.auto_resume,
                    'max_daily_triggers': breaker.config.max_triggers_per_day,
                    'description': breaker.config.description
                }
            }
            for name, breaker in self.breakers.items()
        }
    
    def get_emergency_summary(self) -> Dict:
        """Get comprehensive emergency control summary"""
        status = self._get_status(datetime.now())
        
        return {
            'current_status': {
                'level': status.level.value,
                'is_active': status.is_active,
                'is_shutdown': self.is_shutdown,
                'kill_switch_active': self.kill_switch_activated,
                'status_message': status.get_status_message()
            },
            'permissions': {
                'trading_allowed': status.trading_allowed,
                'new_positions_allowed': status.new_positions_allowed,
                'position_increases_allowed': status.position_increases_allowed
            },
            'recovery': {
                'can_resume': status.can_resume,
                'resume_time': status.resume_time.isoformat() if status.resume_time else None,
                'manual_intervention_required': status.manual_intervention_required
            },
            'circuit_breakers': self.get_breaker_status(),
            'recent_events': [
                {
                    'timestamp': event.timestamp.isoformat(),
                    'level': event.level.value,
                    'reason': event.reason.value,
                    'message': event.message,
                    'trigger_value': event.trigger_value,
                    'threshold': event.threshold
                }
                for event in status.recent_events
            ],
            'statistics': {
                'total_events': len(self.event_history),
                'active_breakers': len(status.active_breakers),
                'shutdown_time': self.shutdown_time.isoformat() if self.shutdown_time else None,
                'shutdown_reason': self.shutdown_reason.value if self.shutdown_reason else None
            }
        }
