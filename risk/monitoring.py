"""
Real-time Risk Monitoring & Alert System

This module provides comprehensive real-time monitoring of all risk components,
generating alerts and providing dashboard data for risk visualization.

Author: Risk Management System
Date: November 2025
Week 3 Day 5: Real-time Monitoring & Alerts
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from enum import Enum
import logging

from .risk_manager import RiskManager, RiskMetrics
from .drawdown_control import DrawdownMonitor, DrawdownMetrics
from .correlation_analyzer import CorrelationAnalyzer, CorrelationMetrics, PositionInfo


# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class AlertLevel(Enum):
    """Alert severity levels"""
    INFO = "INFO"           # Informational, no action required
    WARNING = "WARNING"     # Caution, monitor closely
    CRITICAL = "CRITICAL"   # Immediate attention required


class AlertCategory(Enum):
    """Alert categories for organization"""
    POSITION_SIZE = "POSITION_SIZE"
    PORTFOLIO_RISK = "PORTFOLIO_RISK"
    DRAWDOWN = "DRAWDOWN"
    CORRELATION = "CORRELATION"
    CONCENTRATION = "CONCENTRATION"
    SECTOR_RISK = "SECTOR_RISK"
    DAILY_LOSS = "DAILY_LOSS"


@dataclass
class Alert:
    """Risk alert representation"""
    timestamp: datetime
    level: AlertLevel
    category: AlertCategory
    message: str
    details: Dict
    source: str  # Which component generated the alert
    
    def __str__(self) -> str:
        return f"[{self.level.value}] {self.category.value}: {self.message}"


@dataclass
class RiskStatus:
    """Overall risk status snapshot"""
    timestamp: datetime
    
    # Overall health
    overall_health: str  # "HEALTHY", "CAUTION", "CRITICAL"
    health_score: float  # 0-100
    
    # Component metrics
    risk_metrics: RiskMetrics
    drawdown_metrics: Optional[DrawdownMetrics]
    correlation_metrics: Optional[CorrelationMetrics]
    
    # Active alerts
    active_alerts: List[Alert] = field(default_factory=list)
    
    # Risk limits status
    limits_status: Dict = field(default_factory=dict)
    
    def get_critical_alerts(self) -> List[Alert]:
        """Get all critical alerts"""
        return [a for a in self.active_alerts if a.level == AlertLevel.CRITICAL]
    
    def get_warning_alerts(self) -> List[Alert]:
        """Get all warning alerts"""
        return [a for a in self.active_alerts if a.level == AlertLevel.WARNING]
    
    def has_critical_issues(self) -> bool:
        """Check if there are any critical alerts"""
        return len(self.get_critical_alerts()) > 0


class RiskMonitor:
    """
    Real-time risk monitoring system that integrates all risk components
    and generates alerts based on configured thresholds.
    """
    
    def __init__(
        self,
        risk_manager: RiskManager,
        drawdown_monitor: Optional[DrawdownMonitor] = None,
        correlation_analyzer: Optional[CorrelationAnalyzer] = None,
        # Alert thresholds
        critical_drawdown_threshold: float = 0.15,  # 15% drawdown is critical
        warning_drawdown_threshold: float = 0.10,   # 10% drawdown is warning
        critical_daily_loss_threshold: float = 0.05,  # 5% daily loss is critical
        warning_daily_loss_threshold: float = 0.03,   # 3% daily loss is warning
        critical_position_size_threshold: float = 0.25,  # 25% position is critical
        warning_position_size_threshold: float = 0.20,   # 20% position is warning
        critical_correlation_threshold: float = 0.90,
        warning_correlation_threshold: float = 0.80,
        alert_retention_hours: int = 24,
    ):
        """
        Initialize risk monitor
        
        Args:
            risk_manager: Core risk management system
            drawdown_monitor: Optional drawdown monitoring system
            correlation_analyzer: Optional correlation analysis system
            critical_drawdown_threshold: Drawdown level triggering critical alert
            warning_drawdown_threshold: Drawdown level triggering warning alert
            critical_daily_loss_threshold: Daily loss triggering critical alert
            warning_daily_loss_threshold: Daily loss triggering warning alert
            critical_position_size_threshold: Position size triggering critical alert
            warning_position_size_threshold: Position size triggering warning alert
            critical_correlation_threshold: Correlation triggering critical alert
            warning_correlation_threshold: Correlation triggering warning alert
            alert_retention_hours: How long to keep alerts in history
        """
        self.risk_manager = risk_manager
        self.drawdown_monitor = drawdown_monitor
        self.correlation_analyzer = correlation_analyzer
        
        # Thresholds
        self.critical_drawdown_threshold = critical_drawdown_threshold
        self.warning_drawdown_threshold = warning_drawdown_threshold
        self.critical_daily_loss_threshold = critical_daily_loss_threshold
        self.warning_daily_loss_threshold = warning_daily_loss_threshold
        self.critical_position_size_threshold = critical_position_size_threshold
        self.warning_position_size_threshold = warning_position_size_threshold
        self.critical_correlation_threshold = critical_correlation_threshold
        self.warning_correlation_threshold = warning_correlation_threshold
        self.alert_retention_hours = alert_retention_hours
        
        # Alert tracking
        self.active_alerts: List[Alert] = []
        self.alert_history: List[Alert] = []
        self.last_check_time: Optional[datetime] = None
        
        # Alert deduplication (avoid duplicate alerts)
        self._alert_cache: Dict[Tuple[AlertCategory, str], datetime] = {}
        self._alert_cooldown_minutes = 15  # Don't repeat same alert within 15 minutes
    
    def check_all_risks(
        self,
        current_equity: float,
        positions: Optional[List[PositionInfo]] = None,
        returns_data: Optional[Dict[str, List[float]]] = None,
        timestamp: Optional[datetime] = None
    ) -> RiskStatus:
        """
        Perform comprehensive risk check across all components
        
        Args:
            current_equity: Current account equity
            positions: Optional list of current positions for correlation analysis
            returns_data: Optional historical returns for correlation calculation
            timestamp: Optional timestamp for the check
            
        Returns:
            RiskStatus with comprehensive risk assessment
        """
        if timestamp is None:
            timestamp = datetime.now()
        
        self.last_check_time = timestamp
        
        # Clear old alerts
        self._clear_old_alerts(timestamp)
        
        # Get risk metrics from core risk manager
        # Note: RiskManager.update() requires positions dict and current_date
        # For now, create empty positions dict if none provided
        from .risk_manager import Position
        positions_dict = {}
        risk_metrics = self.risk_manager.update(current_equity, positions_dict, timestamp)
        
        # Check risk manager alerts
        self._check_risk_manager_alerts(risk_metrics, timestamp)
        
        # Check drawdown if monitor is available
        drawdown_metrics = None
        if self.drawdown_monitor is not None:
            drawdown_metrics = self.drawdown_monitor.update(current_equity, timestamp)
            self._check_drawdown_alerts(drawdown_metrics, timestamp)
        
        # Check correlation if analyzer is available and positions provided
        correlation_metrics = None
        if self.correlation_analyzer is not None and positions is not None:
            # Add returns data to positions if available
            if returns_data:
                for pos in positions:
                    if pos.symbol in returns_data:
                        pos.returns = returns_data[pos.symbol]
            
            correlation_metrics = self.correlation_analyzer.analyze(positions, timestamp)
            self._check_correlation_alerts(correlation_metrics, timestamp)
        
        # Calculate overall health
        health_score, health_status = self._calculate_overall_health(
            risk_metrics, drawdown_metrics, correlation_metrics
        )
        
        # Build limits status
        limits_status = self._build_limits_status(
            risk_metrics, drawdown_metrics, correlation_metrics
        )
        
        # Create risk status
        status = RiskStatus(
            timestamp=timestamp,
            overall_health=health_status,
            health_score=health_score,
            risk_metrics=risk_metrics,
            drawdown_metrics=drawdown_metrics,
            correlation_metrics=correlation_metrics,
            active_alerts=self.active_alerts.copy(),
            limits_status=limits_status
        )
        
        return status
    
    def _check_risk_manager_alerts(
        self,
        metrics: RiskMetrics,
        timestamp: datetime
    ) -> None:
        """Check for alerts from risk manager metrics"""
        
        # Check position sizes
        for symbol, size_pct in metrics.position_sizes.items():
            if size_pct >= self.critical_position_size_threshold:
                self._add_alert(
                    timestamp=timestamp,
                    level=AlertLevel.CRITICAL,
                    category=AlertCategory.POSITION_SIZE,
                    message=f"Critical position size: {symbol} is {size_pct:.1%} of portfolio",
                    details={
                        'symbol': symbol,
                        'size_pct': size_pct,
                        'threshold': self.critical_position_size_threshold
                    },
                    source='risk_manager'
                )
            elif size_pct >= self.warning_position_size_threshold:
                self._add_alert(
                    timestamp=timestamp,
                    level=AlertLevel.WARNING,
                    category=AlertCategory.POSITION_SIZE,
                    message=f"Large position size: {symbol} is {size_pct:.1%} of portfolio",
                    details={
                        'symbol': symbol,
                        'size_pct': size_pct,
                        'threshold': self.warning_position_size_threshold
                    },
                    source='risk_manager'
                )
        
        # Check portfolio heat
        if metrics.portfolio_heat >= 0.90:  # 90% of max heat
            self._add_alert(
                timestamp=timestamp,
                level=AlertLevel.CRITICAL,
                category=AlertCategory.PORTFOLIO_RISK,
                message=f"Critical portfolio heat: {metrics.portfolio_heat:.1%}",
                details={
                    'portfolio_heat': metrics.portfolio_heat,
                    'available_risk': 1.0 - metrics.portfolio_heat
                },
                source='risk_manager'
            )
        elif metrics.portfolio_heat >= 0.75:  # 75% of max heat
            self._add_alert(
                timestamp=timestamp,
                level=AlertLevel.WARNING,
                category=AlertCategory.PORTFOLIO_RISK,
                message=f"High portfolio heat: {metrics.portfolio_heat:.1%}",
                details={
                    'portfolio_heat': metrics.portfolio_heat,
                    'available_risk': 1.0 - metrics.portfolio_heat
                },
                source='risk_manager'
            )
        
        # Check daily loss
        if metrics.daily_loss_pct >= self.critical_daily_loss_threshold:
            self._add_alert(
                timestamp=timestamp,
                level=AlertLevel.CRITICAL,
                category=AlertCategory.DAILY_LOSS,
                message=f"Critical daily loss: {metrics.daily_loss_pct:.1%}",
                details={
                    'daily_loss_pct': metrics.daily_loss_pct,
                    'daily_loss_amount': metrics.daily_loss,
                    'threshold': self.critical_daily_loss_threshold
                },
                source='risk_manager'
            )
        elif metrics.daily_loss_pct >= self.warning_daily_loss_threshold:
            self._add_alert(
                timestamp=timestamp,
                level=AlertLevel.WARNING,
                category=AlertCategory.DAILY_LOSS,
                message=f"Significant daily loss: {metrics.daily_loss_pct:.1%}",
                details={
                    'daily_loss_pct': metrics.daily_loss_pct,
                    'daily_loss_amount': metrics.daily_loss,
                    'threshold': self.warning_daily_loss_threshold
                },
                source='risk_manager'
            )
    
    def _check_drawdown_alerts(
        self,
        metrics: DrawdownMetrics,
        timestamp: datetime
    ) -> None:
        """Check for alerts from drawdown monitor"""
        
        if metrics is None:
            return
        
        # Check current drawdown
        if metrics.current_drawdown_pct >= self.critical_drawdown_threshold:
            self._add_alert(
                timestamp=timestamp,
                level=AlertLevel.CRITICAL,
                category=AlertCategory.DRAWDOWN,
                message=f"Critical drawdown: {metrics.current_drawdown_pct:.1%}",
                details={
                    'drawdown_pct': metrics.current_drawdown_pct,
                    'drawdown_amount': metrics.current_drawdown,
                    'threshold': self.critical_drawdown_threshold,
                    'in_protection': metrics.in_protection_mode,
                    'trading_allowed': metrics.trading_allowed
                },
                source='drawdown_monitor'
            )
        elif metrics.current_drawdown_pct >= self.warning_drawdown_threshold:
            self._add_alert(
                timestamp=timestamp,
                level=AlertLevel.WARNING,
                category=AlertCategory.DRAWDOWN,
                message=f"Significant drawdown: {metrics.current_drawdown_pct:.1%}",
                details={
                    'drawdown_pct': metrics.current_drawdown_pct,
                    'drawdown_amount': metrics.current_drawdown,
                    'threshold': self.warning_drawdown_threshold,
                    'in_protection': metrics.in_protection_mode
                },
                source='drawdown_monitor'
            )
        
        # Check protection mode
        if metrics.in_protection_mode:
            self._add_alert(
                timestamp=timestamp,
                level=AlertLevel.WARNING,
                category=AlertCategory.DRAWDOWN,
                message="Drawdown protection mode active",
                details={
                    'protection_mode': metrics.protection_level,
                    'max_position_pct': metrics.max_position_pct,
                    'trading_allowed': metrics.trading_allowed,
                    'recovery_target': metrics.recovery_target
                },
                source='drawdown_monitor'
            )
    
    def _check_correlation_alerts(
        self,
        metrics: CorrelationMetrics,
        timestamp: datetime
    ) -> None:
        """Check for alerts from correlation analyzer"""
        
        if metrics is None:
            return
        
        # Check concentration
        if metrics.is_concentrated:
            level = AlertLevel.CRITICAL if metrics.herfindahl_index > 0.35 else AlertLevel.WARNING
            self._add_alert(
                timestamp=timestamp,
                level=level,
                category=AlertCategory.CONCENTRATION,
                message=f"Portfolio concentration detected (HHI: {metrics.herfindahl_index:.3f})",
                details={
                    'herfindahl_index': metrics.herfindahl_index,
                    'top_position_pct': metrics.top_position_pct,
                    'top_3_positions_pct': metrics.top_3_positions_pct,
                    'effective_positions': metrics.effective_positions,
                    'diversification_score': metrics.diversification_score
                },
                source='correlation_analyzer'
            )
        
        # Check high correlations
        if metrics.has_high_correlations:
            level = (AlertLevel.CRITICAL 
                    if metrics.max_correlation >= self.critical_correlation_threshold 
                    else AlertLevel.WARNING)
            self._add_alert(
                timestamp=timestamp,
                level=level,
                category=AlertCategory.CORRELATION,
                message=f"High correlation detected (max: {metrics.max_correlation:.2f})",
                details={
                    'max_correlation': metrics.max_correlation,
                    'avg_correlation': metrics.avg_correlation,
                    'high_correlation_pairs': metrics.high_correlation_pairs
                },
                source='correlation_analyzer'
            )
        
        # Check sector risk
        if metrics.sector_risk:
            top_sector = max(metrics.sector_concentration.items(), key=lambda x: x[1])
            self._add_alert(
                timestamp=timestamp,
                level=AlertLevel.WARNING,
                category=AlertCategory.SECTOR_RISK,
                message=f"Sector concentration: {top_sector[0]} is {top_sector[1]:.1%}",
                details={
                    'sector': top_sector[0],
                    'concentration': top_sector[1],
                    'sector_breakdown': metrics.sector_concentration
                },
                source='correlation_analyzer'
            )
        
        # Check low diversification score
        if metrics.diversification_score < 50:
            self._add_alert(
                timestamp=timestamp,
                level=AlertLevel.WARNING,
                category=AlertCategory.CONCENTRATION,
                message=f"Low diversification score: {metrics.diversification_score:.0f}/100",
                details={
                    'diversification_score': metrics.diversification_score,
                    'num_positions': metrics.num_positions,
                    'herfindahl_index': metrics.herfindahl_index
                },
                source='correlation_analyzer'
            )
    
    def _add_alert(
        self,
        timestamp: datetime,
        level: AlertLevel,
        category: AlertCategory,
        message: str,
        details: Dict,
        source: str
    ) -> None:
        """Add alert with deduplication"""
        
        # Check if we recently alerted on this same issue
        cache_key = (category, message)
        if cache_key in self._alert_cache:
            last_alert_time = self._alert_cache[cache_key]
            minutes_since = (timestamp - last_alert_time).total_seconds() / 60
            if minutes_since < self._alert_cooldown_minutes:
                return  # Skip duplicate alert
        
        # Create and add alert
        alert = Alert(
            timestamp=timestamp,
            level=level,
            category=category,
            message=message,
            details=details,
            source=source
        )
        
        self.active_alerts.append(alert)
        self.alert_history.append(alert)
        self._alert_cache[cache_key] = timestamp
        
        # Log alert
        log_level = {
            AlertLevel.INFO: logging.INFO,
            AlertLevel.WARNING: logging.WARNING,
            AlertLevel.CRITICAL: logging.CRITICAL
        }[level]
        logger.log(log_level, str(alert))
    
    def _clear_old_alerts(self, current_time: datetime) -> None:
        """Remove alerts older than retention period"""
        
        cutoff_time = current_time.timestamp() - (self.alert_retention_hours * 3600)
        
        # Filter active alerts
        self.active_alerts = [
            a for a in self.active_alerts 
            if a.timestamp.timestamp() > cutoff_time
        ]
        
        # Clean alert cache
        self._alert_cache = {
            k: v for k, v in self._alert_cache.items()
            if v.timestamp() > cutoff_time
        }
    
    def _calculate_overall_health(
        self,
        risk_metrics: RiskMetrics,
        drawdown_metrics: Optional[DrawdownMetrics],
        correlation_metrics: Optional[CorrelationMetrics]
    ) -> Tuple[float, str]:
        """
        Calculate overall portfolio health score and status
        
        Returns:
            (health_score, health_status) where score is 0-100 and status is
            "HEALTHY", "CAUTION", or "CRITICAL"
        """
        
        score = 100.0
        
        # Deduct for portfolio heat (0-20 points)
        score -= risk_metrics.portfolio_heat * 20
        
        # Deduct for daily loss (0-20 points)
        if risk_metrics.daily_loss_pct > 0:
            score -= min(risk_metrics.daily_loss_pct * 400, 20)  # Max 20 points
        
        # Deduct for drawdown if available (0-25 points)
        if drawdown_metrics is not None:
            score -= min(drawdown_metrics.current_drawdown_pct * 100, 25)
        
        # Deduct for poor diversification if available (0-20 points)
        if correlation_metrics is not None:
            diversification_penalty = (100 - correlation_metrics.diversification_score) / 5
            score -= min(diversification_penalty, 20)
        
        # Deduct for critical alerts (0-15 points)
        critical_count = len([a for a in self.active_alerts if a.level == AlertLevel.CRITICAL])
        score -= min(critical_count * 5, 15)
        
        # Ensure score is in valid range
        score = max(0.0, min(100.0, score))
        
        # Determine status
        if score >= 80:
            status = "HEALTHY"
        elif score >= 60:
            status = "CAUTION"
        else:
            status = "CRITICAL"
        
        return score, status
    
    def _build_limits_status(
        self,
        risk_metrics: RiskMetrics,
        drawdown_metrics: Optional[DrawdownMetrics],
        correlation_metrics: Optional[CorrelationMetrics]
    ) -> Dict:
        """Build detailed limits status for dashboard"""
        
        status = {
            'risk_manager': {
                'portfolio_heat': {
                    'current': risk_metrics.portfolio_heat,
                    'limit': 1.0,
                    'utilization': risk_metrics.portfolio_heat,
                    'status': self._get_utilization_status(risk_metrics.portfolio_heat)
                },
                'daily_loss': {
                    'current': risk_metrics.daily_loss_pct,
                    'warning_threshold': self.warning_daily_loss_threshold,
                    'critical_threshold': self.critical_daily_loss_threshold,
                    'status': self._get_threshold_status(
                        risk_metrics.daily_loss_pct,
                        self.warning_daily_loss_threshold,
                        self.critical_daily_loss_threshold
                    )
                }
            }
        }
        
        if drawdown_metrics is not None:
            status['drawdown_monitor'] = {
                'current_drawdown': {
                    'current': drawdown_metrics.current_drawdown_pct,
                    'warning_threshold': self.warning_drawdown_threshold,
                    'critical_threshold': self.critical_drawdown_threshold,
                    'status': self._get_threshold_status(
                        drawdown_metrics.current_drawdown_pct,
                        self.warning_drawdown_threshold,
                        self.critical_drawdown_threshold
                    )
                },
                'protection_mode': {
                    'active': drawdown_metrics.in_protection_mode,
                    'level': drawdown_metrics.protection_level if drawdown_metrics.in_protection_mode else None
                }
            }
        
        if correlation_metrics is not None:
            status['correlation_analyzer'] = {
                'diversification_score': {
                    'current': correlation_metrics.diversification_score,
                    'target': 60.0,
                    'status': 'GOOD' if correlation_metrics.diversification_score >= 70 else
                             'FAIR' if correlation_metrics.diversification_score >= 50 else 'POOR'
                },
                'concentration': {
                    'herfindahl_index': correlation_metrics.herfindahl_index,
                    'threshold': 0.25,
                    'is_concentrated': correlation_metrics.is_concentrated
                },
                'correlation': {
                    'max_correlation': correlation_metrics.max_correlation,
                    'high_pairs': correlation_metrics.high_correlation_pairs,
                    'has_high_correlations': correlation_metrics.has_high_correlations
                }
            }
        
        return status
    
    def _get_utilization_status(self, utilization: float) -> str:
        """Get status based on utilization percentage"""
        if utilization >= 0.90:
            return "CRITICAL"
        elif utilization >= 0.75:
            return "HIGH"
        elif utilization >= 0.50:
            return "MODERATE"
        else:
            return "LOW"
    
    def _get_threshold_status(
        self,
        value: float,
        warning_threshold: float,
        critical_threshold: float
    ) -> str:
        """Get status based on threshold comparison"""
        if value >= critical_threshold:
            return "CRITICAL"
        elif value >= warning_threshold:
            return "WARNING"
        else:
            return "OK"
    
    def get_active_alerts(
        self,
        level: Optional[AlertLevel] = None,
        category: Optional[AlertCategory] = None
    ) -> List[Alert]:
        """
        Get active alerts, optionally filtered by level or category
        
        Args:
            level: Optional alert level to filter by
            category: Optional alert category to filter by
            
        Returns:
            List of matching alerts
        """
        alerts = self.active_alerts
        
        if level is not None:
            alerts = [a for a in alerts if a.level == level]
        
        if category is not None:
            alerts = [a for a in alerts if a.category == category]
        
        return alerts
    
    def get_alert_summary(self) -> Dict:
        """Get summary of active alerts"""
        
        return {
            'total': len(self.active_alerts),
            'critical': len([a for a in self.active_alerts if a.level == AlertLevel.CRITICAL]),
            'warning': len([a for a in self.active_alerts if a.level == AlertLevel.WARNING]),
            'info': len([a for a in self.active_alerts if a.level == AlertLevel.INFO]),
            'by_category': {
                category.value: len([a for a in self.active_alerts if a.category == category])
                for category in AlertCategory
            }
        }
    
    def get_dashboard_data(self) -> Dict:
        """
        Get comprehensive dashboard data for risk visualization
        
        Returns:
            Dictionary with all risk data formatted for dashboard display
        """
        
        if self.last_check_time is None:
            return {'error': 'No risk check performed yet'}
        
        # Perform a fresh check to get latest status
        status = self.check_all_risks(
            current_equity=self.risk_manager.current_equity,
            positions=None,  # Will use cached if needed
            timestamp=datetime.now()
        )
        
        return {
            'timestamp': status.timestamp.isoformat(),
            'overall_health': {
                'status': status.overall_health,
                'score': status.health_score
            },
            'alerts': {
                'summary': self.get_alert_summary(),
                'critical': [
                    {
                        'timestamp': a.timestamp.isoformat(),
                        'category': a.category.value,
                        'message': a.message,
                        'details': a.details
                    }
                    for a in status.get_critical_alerts()
                ],
                'warnings': [
                    {
                        'timestamp': a.timestamp.isoformat(),
                        'category': a.category.value,
                        'message': a.message,
                        'details': a.details
                    }
                    for a in status.get_warning_alerts()
                ]
            },
            'limits_status': status.limits_status,
            'risk_metrics': {
                'portfolio_heat': status.risk_metrics.portfolio_heat,
                'daily_loss_pct': status.risk_metrics.daily_loss_pct,
                'daily_loss': status.risk_metrics.daily_loss,
                'num_positions': status.risk_metrics.num_positions,
                'largest_position': max(status.risk_metrics.position_sizes.values()) 
                                   if status.risk_metrics.position_sizes else 0.0
            },
            'drawdown_metrics': {
                'current_drawdown_pct': status.drawdown_metrics.current_drawdown_pct,
                'max_drawdown_pct': status.drawdown_metrics.max_drawdown_pct,
                'in_protection_mode': status.drawdown_metrics.in_protection_mode,
                'trading_allowed': status.drawdown_metrics.trading_allowed
            } if status.drawdown_metrics else None,
            'correlation_metrics': {
                'diversification_score': status.correlation_metrics.diversification_score,
                'herfindahl_index': status.correlation_metrics.herfindahl_index,
                'num_positions': status.correlation_metrics.num_positions,
                'is_concentrated': status.correlation_metrics.is_concentrated,
                'has_high_correlations': status.correlation_metrics.has_high_correlations,
                'sector_concentration': status.correlation_metrics.sector_concentration
            } if status.correlation_metrics else None
        }
    
    def clear_alerts(self, category: Optional[AlertCategory] = None) -> int:
        """
        Clear alerts, optionally filtering by category
        
        Args:
            category: Optional category to clear. If None, clears all alerts
            
        Returns:
            Number of alerts cleared
        """
        if category is None:
            count = len(self.active_alerts)
            self.active_alerts = []
            self._alert_cache = {}
            return count
        else:
            initial_count = len(self.active_alerts)
            self.active_alerts = [a for a in self.active_alerts if a.category != category]
            # Clean cache for this category
            self._alert_cache = {
                k: v for k, v in self._alert_cache.items()
                if k[0] != category
            }
            return initial_count - len(self.active_alerts)
