"""
Sprint 3 Task 5: Strategy Health Monitoring
Real-time health tracking, degradation detection, and alert generation.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional
from enum import Enum
from collections import deque
import statistics


logger = logging.getLogger(__name__)


# ============================================================================
# Enums
# ============================================================================

class HealthStatus(Enum):
    """Overall health status of a strategy."""
    HEALTHY = "healthy"
    WARNING = "warning"
    CRITICAL = "critical"
    UNKNOWN = "unknown"


class AlertLevel(Enum):
    """Alert severity levels."""
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


# ============================================================================
# Data Classes
# ============================================================================

@dataclass
class HealthMetrics:
    """
    Strategy health metrics at a point in time.
    
    Attributes:
        timestamp: When metrics were recorded
        win_rate: Win rate (0.0-1.0)
        sharpe_ratio: Sharpe ratio
        max_drawdown: Maximum drawdown (0.0-1.0)
        profit_factor: Profit factor
        total_trades: Total number of trades
        avg_trade_duration: Average trade duration (hours)
        daily_pnl: Daily P&L
        volatility: Return volatility
    """
    timestamp: datetime
    win_rate: float
    sharpe_ratio: float
    max_drawdown: float
    profit_factor: float
    total_trades: int = 0
    avg_trade_duration: float = 0.0
    daily_pnl: float = 0.0
    volatility: float = 0.0
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'HealthMetrics':
        """Create HealthMetrics from dictionary."""
        return cls(
            timestamp=data.get("timestamp", datetime.now()),
            win_rate=data.get("win_rate", 0.0),
            sharpe_ratio=data.get("sharpe_ratio", 0.0),
            max_drawdown=data.get("max_drawdown", 0.0),
            profit_factor=data.get("profit_factor", 0.0),
            total_trades=data.get("total_trades", 0),
            avg_trade_duration=data.get("avg_trade_duration", 0.0),
            daily_pnl=data.get("daily_pnl", 0.0),
            volatility=data.get("volatility", 0.0)
        )
    
    def to_dict(self) -> Dict:
        """Convert to dictionary."""
        return {
            "timestamp": self.timestamp,
            "win_rate": self.win_rate,
            "sharpe_ratio": self.sharpe_ratio,
            "max_drawdown": self.max_drawdown,
            "profit_factor": self.profit_factor,
            "total_trades": self.total_trades,
            "avg_trade_duration": self.avg_trade_duration,
            "daily_pnl": self.daily_pnl,
            "volatility": self.volatility
        }
    
    def calculate_health_score(self) -> float:
        """
        Calculate overall health score (0-100).
        
        Weights:
        - Win rate: 25%
        - Sharpe ratio: 25%
        - Max drawdown: 25%
        - Profit factor: 25%
        """
        # Win rate component (0-25 points)
        win_rate_score = min(self.win_rate * 50, 25)  # 0.5 = 25 points
        
        # Sharpe ratio component (0-25 points)
        sharpe_score = min(self.sharpe_ratio * 12.5, 25)  # 2.0 = 25 points
        
        # Max drawdown component (0-25 points, inverted)
        drawdown_score = max(25 - (self.max_drawdown * 250), 0)  # 0.1 = 0 points
        
        # Profit factor component (0-25 points)
        pf_score = min(self.profit_factor * 12.5, 25)  # 2.0 = 25 points
        
        total_score = win_rate_score + sharpe_score + drawdown_score + pf_score
        return total_score


@dataclass
class HealthAlert:
    """
    Health monitoring alert.
    
    Attributes:
        level: Alert severity level
        message: Alert message
        metric_name: Name of metric that triggered alert
        current_value: Current metric value
        threshold_value: Threshold value that was breached
        timestamp: When alert was created
    """
    level: AlertLevel
    message: str
    metric_name: str
    current_value: float
    threshold_value: float
    timestamp: datetime = field(default_factory=datetime.now)
    
    def to_dict(self) -> Dict:
        """Convert to dictionary."""
        return {
            "level": self.level.value.upper(),
            "message": self.message,
            "metric_name": self.metric_name,
            "current_value": self.current_value,
            "threshold_value": self.threshold_value,
            "timestamp": self.timestamp
        }


# ============================================================================
# Degradation Detector
# ============================================================================

class DegradationDetector:
    """
    Detects performance degradation using statistical analysis.
    
    Analyzes metric trends over time to identify declining performance
    before it becomes critical.
    """
    
    def __init__(
        self,
        lookback_window: int = 20,
        min_samples: int = 10,
        threshold: float = 0.20
    ):
        """
        Initialize degradation detector.
        
        Args:
            lookback_window: Number of samples to analyze
            min_samples: Minimum samples required for detection
            threshold: Degradation threshold (percentage decline)
        """
        self.lookback_window = lookback_window
        self.min_samples = min_samples
        self.threshold = threshold
        
        # Store metric histories
        self.metric_histories: Dict[str, deque] = {}
        
        logger.debug(f"DegradationDetector initialized: window={lookback_window}, min_samples={min_samples}, threshold={threshold}")
    
    def add_metric_value(self, metric_name: str, value: float) -> None:
        """Add a metric value to history."""
        if metric_name not in self.metric_histories:
            self.metric_histories[metric_name] = deque(maxlen=self.lookback_window)
        
        self.metric_histories[metric_name].append(value)
        logger.debug(f"Added {metric_name}={value:.4f}, history size={len(self.metric_histories[metric_name])}")
    
    def get_metric_history(self, metric_name: str) -> List[float]:
        """Get metric history."""
        if metric_name not in self.metric_histories:
            return []
        return list(self.metric_histories[metric_name])
    
    def detect_degradation(self, metric_name: str) -> bool:
        """
        Detect if metric is degrading.
        
        Args:
            metric_name: Name of metric to check
        
        Returns:
            True if degradation detected, False otherwise
        """
        history = self.get_metric_history(metric_name)
        
        # Need enough samples
        if len(history) < self.min_samples:
            return False
        
        # Calculate trend
        trend = self.calculate_trend(metric_name)
        
        # Calculate percentage decline from peak
        peak = max(history)
        current = history[-1]
        
        if peak == 0:
            return False
        
        decline_pct = (peak - current) / peak
        
        # Degradation if negative trend and significant decline
        degraded = (trend < 0) and (decline_pct > self.threshold)
        
        if degraded:
            logger.warning(f"{metric_name} degradation detected: trend={trend:.4f}, decline={decline_pct:.1%}")
        
        return degraded
    
    def calculate_trend(self, metric_name: str) -> float:
        """
        Calculate linear trend (slope) of metric.
        
        Args:
            metric_name: Name of metric
        
        Returns:
            Trend slope (positive = improving, negative = degrading)
        """
        history = self.get_metric_history(metric_name)
        
        if len(history) < 2:
            return 0.0
        
        # Simple linear regression
        n = len(history)
        x = list(range(n))
        y = history
        
        x_mean = statistics.mean(x)
        y_mean = statistics.mean(y)
        
        numerator = sum((x[i] - x_mean) * (y[i] - y_mean) for i in range(n))
        denominator = sum((x[i] - x_mean) ** 2 for i in range(n))
        
        if denominator == 0:
            return 0.0
        
        slope = numerator / denominator
        return slope
    
    def get_metric_statistics(self, metric_name: str) -> Dict:
        """Get statistical summary of metric."""
        history = self.get_metric_history(metric_name)
        
        if not history:
            return {
                "count": 0,
                "mean": 0.0,
                "std": 0.0,
                "min": 0.0,
                "max": 0.0
            }
        
        return {
            "count": len(history),
            "mean": statistics.mean(history),
            "std": statistics.stdev(history) if len(history) > 1 else 0.0,
            "min": min(history),
            "max": max(history)
        }


# ============================================================================
# Health Monitor
# ============================================================================

class HealthMonitor:
    """
    Real-time strategy health monitoring system.
    
    Tracks performance metrics, detects degradation, and generates alerts
    when health indicators fall below acceptable thresholds.
    """
    
    def __init__(
        self,
        strategy_name: str,
        check_interval_seconds: int = 60,
        degradation_threshold: float = 0.15
    ):
        """
        Initialize health monitor.
        
        Args:
            strategy_name: Name of strategy to monitor
            check_interval_seconds: How often to check health
            degradation_threshold: Degradation detection threshold
        """
        self.strategy_name = strategy_name
        self.check_interval_seconds = check_interval_seconds
        self.degradation_threshold = degradation_threshold
        
        # Metrics history
        self.metrics_history: List[HealthMetrics] = []
        
        # Alerts
        self.alerts_history: List[HealthAlert] = []
        
        # Degradation detector
        self.degradation_detector = DegradationDetector(
            lookback_window=20,
            min_samples=10,
            threshold=degradation_threshold
        )
        
        logger.info(f"HealthMonitor initialized for '{strategy_name}': check_interval={check_interval_seconds}s, threshold={degradation_threshold}")
    
    def record_metrics(self, metrics_dict: Dict) -> None:
        """
        Record health metrics snapshot.
        
        Args:
            metrics_dict: Dictionary of metrics
        """
        metrics = HealthMetrics.from_dict(metrics_dict)
        self.metrics_history.append(metrics)
        
        # Update degradation detector
        self.degradation_detector.add_metric_value("win_rate", metrics.win_rate)
        self.degradation_detector.add_metric_value("sharpe_ratio", metrics.sharpe_ratio)
        self.degradation_detector.add_metric_value("max_drawdown", metrics.max_drawdown)
        self.degradation_detector.add_metric_value("profit_factor", metrics.profit_factor)
        
        logger.debug(f"Recorded metrics for '{self.strategy_name}': win_rate={metrics.win_rate:.2f}, sharpe={metrics.sharpe_ratio:.2f}")
    
    def get_metrics_history(self, limit: Optional[int] = None) -> List[HealthMetrics]:
        """Get metrics history."""
        if limit is None:
            return self.metrics_history
        return self.metrics_history[-limit:]
    
    def get_current_metrics(self) -> Optional[HealthMetrics]:
        """Get most recent metrics."""
        if not self.metrics_history:
            return None
        return self.metrics_history[-1]
    
    def get_current_status(self) -> HealthStatus:
        """
        Get current health status.
        
        Returns:
            HealthStatus based on current metrics
        """
        metrics = self.get_current_metrics()
        
        if metrics is None:
            return HealthStatus.UNKNOWN
        
        score = metrics.calculate_health_score()
        
        if score >= 70:
            return HealthStatus.HEALTHY
        elif score >= 50:
            return HealthStatus.WARNING
        else:
            return HealthStatus.CRITICAL
    
    def check_health(self) -> List[HealthAlert]:
        """
        Check current health and generate alerts.
        
        Returns:
            List of health alerts
        """
        metrics = self.get_current_metrics()
        
        if metrics is None:
            return []
        
        alerts = []
        
        # Check win rate
        if metrics.win_rate < 0.40:
            alerts.append(HealthAlert(
                level=AlertLevel.CRITICAL,
                message=f"Win rate critically low: {metrics.win_rate:.1%}",
                metric_name="win_rate",
                current_value=metrics.win_rate,
                threshold_value=0.40
            ))
        elif metrics.win_rate < 0.50:
            alerts.append(HealthAlert(
                level=AlertLevel.WARNING,
                message=f"Win rate below target: {metrics.win_rate:.1%}",
                metric_name="win_rate",
                current_value=metrics.win_rate,
                threshold_value=0.50
            ))
        
        # Check Sharpe ratio
        if metrics.sharpe_ratio < 0.5:
            alerts.append(HealthAlert(
                level=AlertLevel.CRITICAL,
                message=f"Sharpe ratio critically low: {metrics.sharpe_ratio:.2f}",
                metric_name="sharpe_ratio",
                current_value=metrics.sharpe_ratio,
                threshold_value=0.5
            ))
        elif metrics.sharpe_ratio < 1.0:
            alerts.append(HealthAlert(
                level=AlertLevel.WARNING,
                message=f"Sharpe ratio below target: {metrics.sharpe_ratio:.2f}",
                metric_name="sharpe_ratio",
                current_value=metrics.sharpe_ratio,
                threshold_value=1.0
            ))
        
        # Check max drawdown
        if metrics.max_drawdown > 0.20:
            alerts.append(HealthAlert(
                level=AlertLevel.CRITICAL,
                message=f"Max drawdown exceeded: {metrics.max_drawdown:.1%}",
                metric_name="max_drawdown",
                current_value=metrics.max_drawdown,
                threshold_value=0.20
            ))
        elif metrics.max_drawdown > 0.15:
            alerts.append(HealthAlert(
                level=AlertLevel.WARNING,
                message=f"Max drawdown elevated: {metrics.max_drawdown:.1%}",
                metric_name="max_drawdown",
                current_value=metrics.max_drawdown,
                threshold_value=0.15
            ))
        
        # Check profit factor
        if metrics.profit_factor < 1.0:
            alerts.append(HealthAlert(
                level=AlertLevel.CRITICAL,
                message=f"Profit factor below 1.0: {metrics.profit_factor:.2f}",
                metric_name="profit_factor",
                current_value=metrics.profit_factor,
                threshold_value=1.0
            ))
        elif metrics.profit_factor < 1.5:
            alerts.append(HealthAlert(
                level=AlertLevel.WARNING,
                message=f"Profit factor low: {metrics.profit_factor:.2f}",
                metric_name="profit_factor",
                current_value=metrics.profit_factor,
                threshold_value=1.5
            ))
        
        # Store alerts
        self.alerts_history.extend(alerts)
        
        if alerts:
            logger.warning(f"Health check for '{self.strategy_name}' generated {len(alerts)} alerts")
        
        return alerts
    
    def detect_degradation(self) -> bool:
        """
        Detect performance degradation.
        
        Returns:
            True if degradation detected, False otherwise
        """
        if len(self.metrics_history) < 10:
            return False
        
        # Check for degradation in key metrics
        degradation_detected = (
            self.degradation_detector.detect_degradation("win_rate") or
            self.degradation_detector.detect_degradation("sharpe_ratio") or
            self.degradation_detector.detect_degradation("profit_factor")
        )
        
        if degradation_detected:
            logger.warning(f"Performance degradation detected for '{self.strategy_name}'")
        
        return degradation_detected
    
    def get_alerts_history(self, limit: Optional[int] = None) -> List[HealthAlert]:
        """Get alerts history."""
        if limit is None:
            return self.alerts_history
        return self.alerts_history[-limit:]
    
    def clear_alerts(self) -> None:
        """Clear alerts history."""
        self.alerts_history.clear()
        logger.debug(f"Cleared alerts for '{self.strategy_name}'")
    
    def generate_report(self) -> str:
        """
        Generate health monitoring report.
        
        Returns:
            Formatted report string
        """
        lines = []
        lines.append("=" * 60)
        lines.append(f"HEALTH MONITOR REPORT: {self.strategy_name}")
        lines.append("=" * 60)
        lines.append("")
        
        # Current status
        status = self.get_current_status()
        metrics = self.get_current_metrics()
        
        lines.append(f"Health Status:    {status.value.upper()}")
        
        if metrics:
            score = metrics.calculate_health_score()
            lines.append(f"Health Score:     {score:.1f}/100")
            lines.append("")
            
            # Current metrics
            lines.append("Current Metrics:")
            lines.append(f"  Win Rate:       {metrics.win_rate:.1%}")
            lines.append(f"  Sharpe Ratio:   {metrics.sharpe_ratio:.2f}")
            lines.append(f"  Max Drawdown:   {metrics.max_drawdown:.1%}")
            lines.append(f"  Profit Factor:  {metrics.profit_factor:.2f}")
            lines.append(f"  Total Trades:   {metrics.total_trades}")
        
        lines.append("")
        
        # Recent alerts
        recent_alerts = self.get_alerts_history(limit=5)
        if recent_alerts:
            lines.append("Recent Alerts:")
            for alert in recent_alerts:
                lines.append(f"  [{alert.level.value.upper()}] {alert.message}")
        else:
            lines.append("No recent alerts")
        
        lines.append("")
        
        # Degradation status
        degraded = self.detect_degradation()
        lines.append(f"Degradation Detected: {'YES' if degraded else 'NO'}")
        
        lines.append("")
        lines.append("=" * 60)
        
        report = "\n".join(lines)
        logger.info(f"Generated health report for '{self.strategy_name}'")
        return report


# ============================================================================
# Module Exports
# ============================================================================

__all__ = [
    'HealthMonitor',
    'HealthMetrics',
    'HealthStatus',
    'HealthAlert',
    'AlertLevel',
    'DegradationDetector'
]
