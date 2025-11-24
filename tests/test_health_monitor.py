"""
Sprint 3 Task 5: Strategy Health Monitoring Tests
Tests for real-time health tracking, degradation detection, and alert generation.
"""

import pytest
from datetime import datetime, timedelta
from typing import Dict, List
import logging

from strategies.health_monitor import (
    HealthMonitor,
    HealthMetrics,
    HealthStatus,
    HealthAlert,
    AlertLevel,
    DegradationDetector
)


# ============================================================================
# Test Fixtures
# ============================================================================

@pytest.fixture
def sample_metrics():
    """Create sample health metrics for testing."""
    return {
        "win_rate": 0.65,
        "sharpe_ratio": 1.8,
        "max_drawdown": 0.08,
        "profit_factor": 2.5,
        "total_trades": 150,
        "avg_trade_duration": 4.5,
        "daily_pnl": 500.00,
        "volatility": 0.02
    }


@pytest.fixture
def health_monitor():
    """Create a health monitor instance for testing."""
    return HealthMonitor(
        strategy_name="TestStrategy",
        check_interval_seconds=60,
        degradation_threshold=0.15
    )


@pytest.fixture
def degradation_detector():
    """Create a degradation detector instance."""
    return DegradationDetector(
        lookback_window=20,
        min_samples=10,
        threshold=0.20
    )


# ============================================================================
# HealthMetrics Tests
# ============================================================================

class TestHealthMetrics:
    """Test the HealthMetrics data class."""
    
    def test_metrics_creation(self):
        """Test creating health metrics."""
        metrics = HealthMetrics(
            timestamp=datetime.now(),
            win_rate=0.60,
            sharpe_ratio=1.5,
            max_drawdown=0.10,
            profit_factor=2.0
        )
        
        assert metrics.win_rate == 0.60
        assert metrics.sharpe_ratio == 1.5
        assert metrics.max_drawdown == 0.10
        assert metrics.profit_factor == 2.0
    
    def test_metrics_from_dict(self, sample_metrics):
        """Test creating metrics from dictionary."""
        metrics = HealthMetrics.from_dict(sample_metrics)
        
        assert metrics.win_rate == 0.65
        assert metrics.sharpe_ratio == 1.8
        assert metrics.max_drawdown == 0.08
        assert metrics.profit_factor == 2.5
    
    def test_metrics_to_dict(self, sample_metrics):
        """Test converting metrics to dictionary."""
        metrics = HealthMetrics.from_dict(sample_metrics)
        data = metrics.to_dict()
        
        assert data["win_rate"] == 0.65
        assert data["sharpe_ratio"] == 1.8
        assert data["max_drawdown"] == 0.08
    
    def test_calculate_health_score_excellent(self):
        """Test health score calculation for excellent performance."""
        metrics = HealthMetrics(
            timestamp=datetime.now(),
            win_rate=0.70,
            sharpe_ratio=2.0,
            max_drawdown=0.05,
            profit_factor=3.0
        )
        
        score = metrics.calculate_health_score()
        assert score >= 80.0  # Excellent performance
    
    def test_calculate_health_score_poor(self):
        """Test health score calculation for poor performance."""
        metrics = HealthMetrics(
            timestamp=datetime.now(),
            win_rate=0.30,
            sharpe_ratio=0.5,
            max_drawdown=0.25,
            profit_factor=0.8
        )
        
        score = metrics.calculate_health_score()
        assert score < 50.0  # Poor performance


# ============================================================================
# HealthAlert Tests
# ============================================================================

class TestHealthAlert:
    """Test the HealthAlert data class."""
    
    def test_alert_creation(self):
        """Test creating a health alert."""
        alert = HealthAlert(
            level=AlertLevel.WARNING,
            message="Win rate declining",
            metric_name="win_rate",
            current_value=0.45,
            threshold_value=0.50
        )
        
        assert alert.level == AlertLevel.WARNING
        assert alert.message == "Win rate declining"
        assert alert.metric_name == "win_rate"
        assert alert.current_value == 0.45
        assert alert.threshold_value == 0.50
    
    def test_alert_to_dict(self):
        """Test converting alert to dictionary."""
        alert = HealthAlert(
            level=AlertLevel.CRITICAL,
            message="Max drawdown exceeded",
            metric_name="max_drawdown",
            current_value=0.15,
            threshold_value=0.10
        )
        
        data = alert.to_dict()
        assert data["level"] == "CRITICAL"
        assert data["message"] == "Max drawdown exceeded"
        assert data["metric_name"] == "max_drawdown"


# ============================================================================
# HealthMonitor Tests
# ============================================================================

class TestHealthMonitor:
    """Test the HealthMonitor class."""
    
    def test_monitor_initialization(self, health_monitor):
        """Test basic health monitor initialization."""
        assert health_monitor.strategy_name == "TestStrategy"
        assert health_monitor.check_interval_seconds == 60
        assert health_monitor.degradation_threshold == 0.15
    
    def test_record_metrics(self, health_monitor, sample_metrics):
        """Test recording health metrics."""
        health_monitor.record_metrics(sample_metrics)
        
        history = health_monitor.get_metrics_history()
        assert len(history) == 1
        assert history[0].win_rate == 0.65
    
    def test_record_multiple_metrics(self, health_monitor, sample_metrics):
        """Test recording multiple metric snapshots."""
        for i in range(5):
            metrics = sample_metrics.copy()
            metrics["win_rate"] = 0.65 - (i * 0.01)
            health_monitor.record_metrics(metrics)
        
        history = health_monitor.get_metrics_history()
        assert len(history) == 5
    
    def test_get_current_metrics(self, health_monitor, sample_metrics):
        """Test retrieving current metrics."""
        health_monitor.record_metrics(sample_metrics)
        
        current = health_monitor.get_current_metrics()
        assert current is not None
        assert current.win_rate == 0.65
    
    def test_get_current_metrics_empty(self, health_monitor):
        """Test retrieving current metrics when no data."""
        current = health_monitor.get_current_metrics()
        assert current is None
    
    def test_get_current_status(self, health_monitor, sample_metrics):
        """Test getting current health status."""
        health_monitor.record_metrics(sample_metrics)
        
        status = health_monitor.get_current_status()
        assert status in [HealthStatus.HEALTHY, HealthStatus.WARNING, HealthStatus.CRITICAL]
    
    def test_check_health_healthy(self, health_monitor):
        """Test health check with healthy metrics."""
        metrics = {
            "win_rate": 0.70,
            "sharpe_ratio": 2.0,
            "max_drawdown": 0.05,
            "profit_factor": 3.0
        }
        
        health_monitor.record_metrics(metrics)
        alerts = health_monitor.check_health()
        
        # Should have few or no alerts for healthy metrics
        critical_alerts = [a for a in alerts if a.level == AlertLevel.CRITICAL]
        assert len(critical_alerts) == 0
    
    def test_check_health_warning(self, health_monitor):
        """Test health check with marginal metrics."""
        metrics = {
            "win_rate": 0.48,
            "sharpe_ratio": 0.9,
            "max_drawdown": 0.12,
            "profit_factor": 1.2
        }
        
        health_monitor.record_metrics(metrics)
        alerts = health_monitor.check_health()
        
        # Should have some warnings
        assert len(alerts) > 0
    
    def test_check_health_critical(self, health_monitor):
        """Test health check with poor metrics."""
        metrics = {
            "win_rate": 0.30,
            "sharpe_ratio": 0.3,
            "max_drawdown": 0.25,
            "profit_factor": 0.7
        }
        
        health_monitor.record_metrics(metrics)
        alerts = health_monitor.check_health()
        
        # Should have critical alerts
        critical_alerts = [a for a in alerts if a.level == AlertLevel.CRITICAL]
        assert len(critical_alerts) > 0
    
    def test_detect_degradation_no_history(self, health_monitor):
        """Test degradation detection with insufficient history."""
        detected = health_monitor.detect_degradation()
        assert detected is False
    
    def test_detect_degradation_stable(self, health_monitor):
        """Test degradation detection with stable performance."""
        for i in range(15):
            metrics = {
                "win_rate": 0.60 + (i * 0.001),  # Slight improvement
                "sharpe_ratio": 1.5,
                "max_drawdown": 0.10,
                "profit_factor": 2.0
            }
            health_monitor.record_metrics(metrics)
        
        detected = health_monitor.detect_degradation()
        assert detected is False
    
    def test_detect_degradation_declining(self, health_monitor):
        """Test degradation detection with declining performance."""
        for i in range(15):
            metrics = {
                "win_rate": 0.70 - (i * 0.03),  # Significant decline
                "sharpe_ratio": 2.0 - (i * 0.1),
                "max_drawdown": 0.05 + (i * 0.01),
                "profit_factor": 3.0 - (i * 0.15)
            }
            health_monitor.record_metrics(metrics)
        
        detected = health_monitor.detect_degradation()
        assert detected is True
    
    def test_get_alerts_history(self, health_monitor, sample_metrics):
        """Test retrieving alerts history."""
        health_monitor.record_metrics(sample_metrics)
        health_monitor.check_health()
        
        alerts = health_monitor.get_alerts_history()
        assert isinstance(alerts, list)
    
    def test_clear_alerts(self, health_monitor, sample_metrics):
        """Test clearing alerts."""
        health_monitor.record_metrics(sample_metrics)
        health_monitor.check_health()
        
        health_monitor.clear_alerts()
        alerts = health_monitor.get_alerts_history()
        assert len(alerts) == 0
    
    def test_generate_report(self, health_monitor, sample_metrics):
        """Test generating health report."""
        health_monitor.record_metrics(sample_metrics)
        
        report = health_monitor.generate_report()
        assert report is not None
        assert "TestStrategy" in report
        assert "Health Status" in report


# ============================================================================
# DegradationDetector Tests
# ============================================================================

class TestDegradationDetector:
    """Test the DegradationDetector class."""
    
    def test_detector_initialization(self, degradation_detector):
        """Test degradation detector initialization."""
        assert degradation_detector.lookback_window == 20
        assert degradation_detector.min_samples == 10
        assert degradation_detector.threshold == 0.20
    
    def test_add_metric_value(self, degradation_detector):
        """Test adding metric values."""
        degradation_detector.add_metric_value("win_rate", 0.65)
        degradation_detector.add_metric_value("win_rate", 0.63)
        
        values = degradation_detector.get_metric_history("win_rate")
        assert len(values) == 2
    
    def test_detect_degradation_insufficient_data(self, degradation_detector):
        """Test detection with insufficient data."""
        for i in range(5):
            degradation_detector.add_metric_value("win_rate", 0.60 - (i * 0.01))
        
        detected = degradation_detector.detect_degradation("win_rate")
        assert detected is False  # Not enough samples
    
    def test_detect_degradation_stable_metric(self, degradation_detector):
        """Test detection with stable metric."""
        for i in range(15):
            degradation_detector.add_metric_value("win_rate", 0.60 + (i * 0.001))
        
        detected = degradation_detector.detect_degradation("win_rate")
        assert detected is False
    
    def test_detect_degradation_declining_metric(self, degradation_detector):
        """Test detection with declining metric."""
        for i in range(15):
            degradation_detector.add_metric_value("win_rate", 0.70 - (i * 0.03))
        
        detected = degradation_detector.detect_degradation("win_rate")
        assert detected is True
    
    def test_calculate_trend(self, degradation_detector):
        """Test trend calculation."""
        # Add upward trending data
        for i in range(10):
            degradation_detector.add_metric_value("sharpe_ratio", 1.0 + (i * 0.1))
        
        trend = degradation_detector.calculate_trend("sharpe_ratio")
        assert trend > 0  # Positive trend
    
    def test_calculate_trend_downward(self, degradation_detector):
        """Test downward trend calculation."""
        # Add downward trending data
        for i in range(10):
            degradation_detector.add_metric_value("sharpe_ratio", 2.0 - (i * 0.1))
        
        trend = degradation_detector.calculate_trend("sharpe_ratio")
        assert trend < 0  # Negative trend
    
    def test_get_metric_statistics(self, degradation_detector):
        """Test getting metric statistics."""
        values = [0.60, 0.62, 0.64, 0.61, 0.63, 0.65, 0.62, 0.64, 0.66, 0.63]
        for val in values:
            degradation_detector.add_metric_value("win_rate", val)
        
        stats = degradation_detector.get_metric_statistics("win_rate")
        
        assert "mean" in stats
        assert "std" in stats
        assert "min" in stats
        assert "max" in stats
        assert stats["count"] == 10


# ============================================================================
# HealthStatus Tests
# ============================================================================

class TestHealthStatus:
    """Test the HealthStatus enum."""
    
    def test_status_types_exist(self):
        """Test that all expected status types exist."""
        assert hasattr(HealthStatus, "HEALTHY")
        assert hasattr(HealthStatus, "WARNING")
        assert hasattr(HealthStatus, "CRITICAL")
        assert hasattr(HealthStatus, "UNKNOWN")


# ============================================================================
# AlertLevel Tests
# ============================================================================

class TestAlertLevel:
    """Test the AlertLevel enum."""
    
    def test_alert_levels_exist(self):
        """Test that all expected alert levels exist."""
        assert hasattr(AlertLevel, "INFO")
        assert hasattr(AlertLevel, "WARNING")
        assert hasattr(AlertLevel, "CRITICAL")


# ============================================================================
# Integration Tests
# ============================================================================

class TestHealthMonitorIntegration:
    """Test complete health monitoring workflows."""
    
    def test_full_monitoring_workflow(self, health_monitor):
        """Test complete health monitoring workflow."""
        # Record initial healthy metrics
        metrics = {
            "win_rate": 0.65,
            "sharpe_ratio": 1.8,
            "max_drawdown": 0.08,
            "profit_factor": 2.5
        }
        health_monitor.record_metrics(metrics)
        
        # Check health
        alerts = health_monitor.check_health()
        
        # Verify status
        status = health_monitor.get_current_status()
        assert status in [HealthStatus.HEALTHY, HealthStatus.WARNING]
        
        # Generate report
        report = health_monitor.generate_report()
        assert report is not None
    
    def test_degradation_detection_workflow(self, health_monitor):
        """Test degradation detection over time."""
        # Record declining performance
        for i in range(20):
            metrics = {
                "win_rate": 0.70 - (i * 0.02),
                "sharpe_ratio": 2.0 - (i * 0.08),
                "max_drawdown": 0.05 + (i * 0.008),
                "profit_factor": 3.0 - (i * 0.12)
            }
            health_monitor.record_metrics(metrics)
        
        # Detect degradation
        degraded = health_monitor.detect_degradation()
        assert degraded is True
        
        # Check for alerts
        alerts = health_monitor.check_health()
        assert len(alerts) > 0
    
    def test_alert_escalation_workflow(self, health_monitor):
        """Test alert escalation as performance worsens."""
        # Start with marginal performance
        metrics = {
            "win_rate": 0.48,
            "sharpe_ratio": 0.9,
            "max_drawdown": 0.12,
            "profit_factor": 1.2
        }
        health_monitor.record_metrics(metrics)
        alerts1 = health_monitor.check_health()
        
        # Worsen performance
        metrics = {
            "win_rate": 0.35,
            "sharpe_ratio": 0.4,
            "max_drawdown": 0.22,
            "profit_factor": 0.8
        }
        health_monitor.record_metrics(metrics)
        alerts2 = health_monitor.check_health()
        
        # Should have more critical alerts in second check
        critical1 = sum(1 for a in alerts1 if a.level == AlertLevel.CRITICAL)
        critical2 = sum(1 for a in alerts2 if a.level == AlertLevel.CRITICAL)
        assert critical2 >= critical1
