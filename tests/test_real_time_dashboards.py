"""
Sprint 4 Task 3: Real-Time Monitoring Dashboards Integration Tests

Tests complete monitoring dashboard functionality including:
- Live strategy monitoring with PaperMonitor
- Validation tracking with ValidationMonitor
- Health monitoring integration
- Alert generation and display
- Performance visualization
- Multi-monitor orchestration

Author: TWS Robot Development Team
Date: November 25, 2025
Sprint 4 Task 3
"""

import pytest
from datetime import datetime, timedelta
from io import StringIO
from typing import Dict, List

from rich.console import Console

from monitoring.paper_monitor import PaperMonitor, StrategySnapshot, RiskSnapshot
from monitoring.validation_monitor import (
    ValidationMonitor,
    Alert,
    AlertLevel,
    ValidationStatus,
    create_validation_alert
)
from strategies.health_monitor import (
    HealthMonitor,
    HealthMetrics,
    HealthStatus,
    HealthAlert,
    AlertLevel as HealthAlertLevel
)
from strategy.lifecycle import StrategyState, StrategyMetrics
from strategy.validation import ValidationReport, ValidationCheck
from strategy.promotion import ApprovalGate
from backtest.data_models import Position
from execution.paper_adapter import PendingOrder


# ============================================================================
# Test Fixtures
# ============================================================================

@pytest.fixture
def test_console():
    """Create test console that captures output"""
    return Console(file=StringIO(), width=120)


@pytest.fixture
def paper_monitor(test_console):
    """Create PaperMonitor instance"""
    return PaperMonitor(console=test_console)


@pytest.fixture
def validation_monitor(test_console):
    """Create ValidationMonitor instance"""
    return ValidationMonitor(console=test_console)


@pytest.fixture
def health_monitor():
    """Create HealthMonitor instance"""
    return HealthMonitor(
        strategy_name="TestStrategy",
        check_interval_seconds=60,
        degradation_threshold=0.15
    )


@pytest.fixture
def sample_strategy_snapshot():
    """Create sample strategy snapshot"""
    return StrategySnapshot(
        name="MA_Cross_Strategy",
        state=StrategyState.PAPER,
        start_time=datetime.now() - timedelta(hours=2),
        positions={
            "AAPL": Position(symbol="AAPL", quantity=100, average_cost=150.0, current_price=152.0),
            "GOOGL": Position(symbol="GOOGL", quantity=50, average_cost=2800.0, current_price=2850.0)
        },
        session_pnl=450.0,
        total_pnl=2500.0,
        metrics=StrategyMetrics(
            days_running=30,
            total_trades=75,
            sharpe_ratio=1.6,
            max_drawdown=0.07,
            win_rate=0.62,
            profit_factor=2.1,
            consecutive_losses=1,
            total_pnl=2500.0
        )
    )


@pytest.fixture
def sample_risk_snapshot():
    """Create sample risk snapshot"""
    return RiskSnapshot(
        portfolio_value=125000.0,
        margin_used=35000.0,
        margin_available=90000.0,
        max_drawdown=0.07,
        position_count=2,
        risk_limit_utilization=0.55
    )


@pytest.fixture
def sample_validation_report():
    """Create sample validation report"""
    from datetime import date
    checks = [
        ValidationCheck(
            criterion="minimum_days",
            passed=True,
            current_value=30.0,
            required_value=30.0,
            message="30 days vs 30 required"
        ),
        ValidationCheck(
            criterion="minimum_trades",
            passed=True,
            current_value=75.0,
            required_value=20.0,
            message="75 trades vs 20 required"
        ),
        ValidationCheck(
            criterion="sharpe_ratio",
            passed=True,
            current_value=1.6,
            required_value=1.0,
            message="1.60 vs 1.00 required"
        ),
        ValidationCheck(
            criterion="max_drawdown",
            passed=True,
            current_value=0.07,
            required_value=0.10,
            message="7.0% vs 10.0% limit"
        )
    ]
    return ValidationReport(
        strategy_name="MA_Cross_Strategy",
        report_date=date.today(),
        overall_passed=True,
        checks=checks,
        days_remaining=0,
        trades_remaining=0
    )


# ============================================================================
# Live Strategy Monitoring Tests (PaperMonitor)
# ============================================================================

class TestLiveStrategyMonitoring:
    """Test live strategy monitoring with PaperMonitor"""
    
    def test_monitor_initialization(self, paper_monitor):
        """Test PaperMonitor initializes correctly"""
        assert paper_monitor is not None
        assert paper_monitor.console is not None
        assert len(paper_monitor._strategy_snapshots) == 0
    
    def test_single_strategy_display(self, paper_monitor, sample_strategy_snapshot):
        """Test displaying single active strategy"""
        paper_monitor.update_strategy(sample_strategy_snapshot)
        
        assert len(paper_monitor._strategy_snapshots) == 1
        assert "MA_Cross_Strategy" in paper_monitor._strategy_snapshots
        
        # Should render without error
        layout = paper_monitor.render()
        assert layout is not None
    
    def test_multiple_strategies_display(self, paper_monitor, sample_strategy_snapshot):
        """Test displaying multiple active strategies"""
        # Add first strategy
        paper_monitor.update_strategy(sample_strategy_snapshot)
        
        # Add second strategy
        snapshot2 = StrategySnapshot(
            name="Bollinger_Bands",
            state=StrategyState.PAPER,
            start_time=datetime.now() - timedelta(hours=1),
            positions={},
            session_pnl=150.0,
            total_pnl=800.0,
            metrics=StrategyMetrics(
                days_running=15,
                total_trades=30,
                sharpe_ratio=1.2,
                max_drawdown=0.05,
                win_rate=0.55,
                profit_factor=1.7
            )
        )
        paper_monitor.update_strategy(snapshot2)
        
        assert len(paper_monitor._strategy_snapshots) == 2
        layout = paper_monitor.render()
        assert layout is not None
    
    def test_risk_metrics_display(self, paper_monitor, sample_risk_snapshot):
        """Test risk metrics panel displays correctly"""
        paper_monitor.update_risk(sample_risk_snapshot)
        
        assert paper_monitor._risk_snapshot is not None
        assert paper_monitor._risk_snapshot.portfolio_value == 125000.0
        
        layout = paper_monitor.render()
        assert layout is not None
    
    def test_order_activity_tracking(self, paper_monitor):
        """Test order activity feed"""
        orders = [
            PendingOrder(
                order_id=1001,
                symbol="AAPL",
                action="BUY",
                quantity=100,
                order_type="MKT",
                status="FILLED",
                filled_qty=100,
                avg_fill_price=150.25
            ),
            PendingOrder(
                order_id=1002,
                symbol="GOOGL",
                action="SELL",
                quantity=50,
                order_type="LMT",
                limit_price=2850.0,
                status="PENDING",
                filled_qty=0,
                avg_fill_price=0.0
            )
        ]
        
        for order in orders:
            paper_monitor.add_order(order)
        
        assert len(paper_monitor._recent_orders) == 2
        layout = paper_monitor.render()
        assert layout is not None
    
    def test_performance_summary_aggregation(self, paper_monitor, sample_strategy_snapshot, sample_risk_snapshot):
        """Test performance summary aggregates across strategies"""
        paper_monitor.update_strategy(sample_strategy_snapshot)
        paper_monitor.update_risk(sample_risk_snapshot)
        
        layout = paper_monitor.render()
        assert layout is not None
    
    def test_real_time_updates(self, paper_monitor, sample_strategy_snapshot):
        """Test monitor handles rapid updates"""
        for i in range(10):
            snapshot = StrategySnapshot(
                name="MA_Cross_Strategy",
                state=StrategyState.PAPER,
                start_time=sample_strategy_snapshot.start_time,
                positions=sample_strategy_snapshot.positions,
                session_pnl=450.0 + (i * 10),
                total_pnl=2500.0 + (i * 10),
                metrics=sample_strategy_snapshot.metrics
            )
            paper_monitor.update_strategy(snapshot)
        
        # Should handle rapid updates
        current = paper_monitor._strategy_snapshots["MA_Cross_Strategy"]
        assert current.session_pnl == 540.0  # Last update
    
    def test_dashboard_layout_structure(self, paper_monitor):
        """Test dashboard has correct 2x2 layout"""
        layout = paper_monitor.render()
        
        assert layout is not None
        assert layout["top"] is not None
        assert layout["bottom"] is not None


# ============================================================================
# Validation Tracking Tests (ValidationMonitor)
# ============================================================================

class TestValidationTracking:
    """Test validation tracking with ValidationMonitor"""
    
    def test_validation_monitor_initialization(self, validation_monitor):
        """Test ValidationMonitor initializes correctly"""
        assert validation_monitor is not None
        assert len(validation_monitor._validation_statuses) == 0
        assert len(validation_monitor._alerts) == 0
    
    def test_validation_status_display(self, validation_monitor, sample_validation_report):
        """Test validation status panel displays progress"""
        validation_monitor.update_validation_status(
            strategy_name="MA_Cross_Strategy",
            report=sample_validation_report,
            days_remaining=0,
            trades_remaining=0,
            promotion_gate=ApprovalGate.GATE_1_VALIDATION
        )
        
        assert "MA_Cross_Strategy" in validation_monitor._validation_statuses
        layout = validation_monitor.render()
        assert layout is not None
    
    def test_partial_validation_display(self, validation_monitor):
        """Test display of partially met validation criteria"""
        from datetime import date
        checks = [
            ValidationCheck(
                criterion="minimum_days",
                passed=True,
                current_value=30.0,
                required_value=30.0,
                message="30 days vs 30 required"
            ),
            ValidationCheck(
                criterion="minimum_trades",
                passed=False,
                current_value=15.0,
                required_value=20.0,
                message="15 trades vs 20 required"
            ),
            ValidationCheck(
                criterion="sharpe_ratio",
                passed=True,
                current_value=1.5,
                required_value=1.0,
                message="1.50 vs 1.00 required"
            )
        ]
        report = ValidationReport(
            strategy_name="TestStrategy",
            report_date=date.today(),
            overall_passed=False,
            checks=checks,
            days_remaining=0,
            trades_remaining=5
        )
        
        validation_monitor.update_validation_status(
            strategy_name="TestStrategy",
            report=report,
            days_remaining=0,
            trades_remaining=5
        )
        
        layout = validation_monitor.render()
        assert layout is not None
    
    def test_equity_curve_visualization(self, validation_monitor):
        """Test equity curve sparkline display"""
        # Simulate equity curve updates
        equity_values = [100000, 101000, 102500, 103000, 104500, 105000]
        for value in equity_values:
            validation_monitor.update_equity_curve("TestStrategy", value)
        
        assert "TestStrategy" in validation_monitor._equity_curves
        assert len(validation_monitor._equity_curves["TestStrategy"]) == 6
        
        layout = validation_monitor.render()
        assert layout is not None
    
    def test_multiple_strategy_validation(self, validation_monitor, sample_validation_report):
        """Test tracking validation for multiple strategies"""
        for i in range(3):
            strategy_name = f"Strategy_{i+1}"
            validation_monitor.update_validation_status(
                strategy_name=strategy_name,
                report=sample_validation_report,
                days_remaining=i * 5,
                trades_remaining=i * 10
            )
        
        assert len(validation_monitor._validation_statuses) == 3
    
    def test_promotion_gate_display(self, validation_monitor, sample_validation_report):
        """Test promotion workflow gate display"""
        gates = [
            ApprovalGate.GATE_1_VALIDATION,
            ApprovalGate.GATE_2_LIVE_APPROVAL,
            ApprovalGate.GATE_3_LIVE_ACTIVATION
        ]
        
        for gate in gates:
            validation_monitor.update_validation_status(
                strategy_name=f"Strategy_{gate.value}",
                report=sample_validation_report,
                days_remaining=0,
                trades_remaining=0,
                promotion_gate=gate
            )
        
        assert len(validation_monitor._validation_statuses) == 3
    
    def test_validation_monitor_layout(self, validation_monitor):
        """Test ValidationMonitor has 3-row layout"""
        layout = validation_monitor.render()
        
        assert layout is not None
        assert layout["top"] is not None
        assert layout["middle"] is not None
        assert layout["bottom"] is not None


# ============================================================================
# Alert System Tests
# ============================================================================

class TestAlertSystem:
    """Test alert generation and display"""
    
    def test_info_alert_creation(self, validation_monitor):
        """Test creating INFO level alert"""
        alert = create_validation_alert(
            strategy_name="TestStrategy",
            level=AlertLevel.INFO,
            message="Milestone reached: 50 trades completed"
        )
        
        validation_monitor.add_alert(alert)
        
        assert len(validation_monitor._alerts) == 1
        assert validation_monitor._alerts[0].level == AlertLevel.INFO
    
    def test_warning_alert_creation(self, validation_monitor):
        """Test creating WARNING level alert"""
        alert = create_validation_alert(
            strategy_name="TestStrategy",
            level=AlertLevel.WARNING,
            message="Win rate declining: 52%"
        )
        
        validation_monitor.add_alert(alert)
        
        assert len(validation_monitor._alerts) == 1
        assert validation_monitor._alerts[0].level == AlertLevel.WARNING
    
    def test_critical_alert_creation(self, validation_monitor):
        """Test creating CRITICAL level alert"""
        alert = create_validation_alert(
            strategy_name="TestStrategy",
            level=AlertLevel.CRITICAL,
            message="Max drawdown exceeded: 12%",
            action_required=True
        )
        
        validation_monitor.add_alert(alert)
        
        assert len(validation_monitor._alerts) == 1
        assert validation_monitor._alerts[0].level == AlertLevel.CRITICAL
        assert validation_monitor._alerts[0].action_required is True
    
    def test_alert_ordering(self, validation_monitor):
        """Test alerts are displayed newest first"""
        alerts = [
            create_validation_alert("Test", AlertLevel.INFO, "First"),
            create_validation_alert("Test", AlertLevel.WARNING, "Second"),
            create_validation_alert("Test", AlertLevel.CRITICAL, "Third")
        ]
        
        for alert in alerts:
            validation_monitor.add_alert(alert)
        
        assert validation_monitor._alerts[0].message == "Third"
        assert validation_monitor._alerts[2].message == "First"
    
    def test_alert_limit(self, validation_monitor):
        """Test alert list is limited to max display"""
        for i in range(15):
            alert = create_validation_alert(
                "Test",
                AlertLevel.INFO,
                f"Alert {i}"
            )
            validation_monitor.add_alert(alert)
        
        assert len(validation_monitor._alerts) == validation_monitor._max_alerts_display
    
    def test_alerts_panel_display(self, validation_monitor):
        """Test alerts panel renders correctly"""
        alert = create_validation_alert(
            "TestStrategy",
            AlertLevel.WARNING,
            "Test alert message"
        )
        validation_monitor.add_alert(alert)
        
        layout = validation_monitor.render()
        assert layout is not None


# ============================================================================
# Health Monitoring Integration Tests
# ============================================================================

class TestHealthMonitoringIntegration:
    """Test integration with HealthMonitor"""
    
    def test_health_monitor_initialization(self, health_monitor):
        """Test HealthMonitor initializes correctly"""
        assert health_monitor.strategy_name == "TestStrategy"
        assert health_monitor.check_interval_seconds == 60
    
    def test_healthy_metrics_tracking(self, health_monitor):
        """Test tracking healthy performance metrics"""
        metrics = {
            "win_rate": 0.65,
            "sharpe_ratio": 1.8,
            "max_drawdown": 0.06,
            "profit_factor": 2.3
        }
        
        health_monitor.record_metrics(metrics)
        
        current = health_monitor.get_current_metrics()
        assert current is not None
        assert current.win_rate == 0.65
        
        status = health_monitor.get_current_status()
        assert status == HealthStatus.HEALTHY
    
    def test_warning_level_detection(self, health_monitor):
        """Test detection of marginal performance"""
        metrics = {
            "win_rate": 0.48,
            "sharpe_ratio": 0.9,
            "max_drawdown": 0.12,
            "profit_factor": 1.3
        }
        
        health_monitor.record_metrics(metrics)
        alerts = health_monitor.check_health()
        
        assert len(alerts) > 0
        status = health_monitor.get_current_status()
        assert status in [HealthStatus.WARNING, HealthStatus.CRITICAL]
    
    def test_critical_level_detection(self, health_monitor):
        """Test detection of critical performance degradation"""
        metrics = {
            "win_rate": 0.35,
            "sharpe_ratio": 0.4,
            "max_drawdown": 0.22,
            "profit_factor": 0.8
        }
        
        health_monitor.record_metrics(metrics)
        alerts = health_monitor.check_health()
        
        critical_alerts = [a for a in alerts if a.level == HealthAlertLevel.CRITICAL]
        assert len(critical_alerts) > 0
        
        status = health_monitor.get_current_status()
        assert status == HealthStatus.CRITICAL
    
    def test_degradation_detection(self, health_monitor):
        """Test detection of performance degradation over time"""
        # Record declining performance
        for i in range(15):
            metrics = {
                "win_rate": 0.70 - (i * 0.02),
                "sharpe_ratio": 2.0 - (i * 0.08),
                "max_drawdown": 0.05 + (i * 0.008),
                "profit_factor": 3.0 - (i * 0.12)
            }
            health_monitor.record_metrics(metrics)
        
        degraded = health_monitor.detect_degradation()
        assert degraded is True
    
    def test_health_report_generation(self, health_monitor):
        """Test generating health report"""
        metrics = {
            "win_rate": 0.60,
            "sharpe_ratio": 1.5,
            "max_drawdown": 0.08,
            "profit_factor": 2.0
        }
        
        health_monitor.record_metrics(metrics)
        report = health_monitor.generate_report()
        
        assert report is not None
        assert "TestStrategy" in report
        assert "Health Status" in report


# ============================================================================
# Performance Visualization Tests
# ============================================================================

class TestPerformanceVisualization:
    """Test performance charts and sparklines"""
    
    def test_sparkline_generation_upward_trend(self, validation_monitor):
        """Test sparkline shows upward trend"""
        values = [100, 105, 110, 115, 120, 125, 130]
        sparkline = validation_monitor._create_sparkline(values, width=7)
        
        assert len(sparkline) == 7
        # Should contain higher blocks toward end
        assert any(char in "▆▇█" for char in sparkline[-2:])
    
    def test_sparkline_generation_downward_trend(self, validation_monitor):
        """Test sparkline shows downward trend"""
        values = [130, 125, 120, 115, 110, 105, 100]
        sparkline = validation_monitor._create_sparkline(values, width=7)
        
        assert len(sparkline) == 7
        # Should contain lower blocks toward end
        assert any(char in " ▁▂▃" for char in sparkline[-2:])
    
    def test_sparkline_flat_values(self, validation_monitor):
        """Test sparkline with flat values"""
        values = [100] * 10
        sparkline = validation_monitor._create_sparkline(values, width=10)
        
        assert sparkline == "─" * 10
    
    def test_sparkline_empty_data(self, validation_monitor):
        """Test sparkline with empty data"""
        sparkline = validation_monitor._create_sparkline([], width=10)
        
        assert sparkline == "─" * 10
    
    def test_equity_curve_point_limit(self, validation_monitor):
        """Test equity curve maintains point limit"""
        # Add more than max points
        for i in range(50):
            validation_monitor.update_equity_curve("TestStrategy", 100000.0 + (i * 1000))
        
        curve = validation_monitor._equity_curves["TestStrategy"]
        assert len(curve) == validation_monitor._max_sparkline_points
    
    def test_multi_strategy_equity_curves(self, validation_monitor):
        """Test tracking equity curves for multiple strategies"""
        strategies = ["Strategy_A", "Strategy_B", "Strategy_C"]
        
        for strategy in strategies:
            for i in range(10):
                validation_monitor.update_equity_curve(strategy, 100000.0 + (i * 500))
        
        assert len(validation_monitor._equity_curves) == 3
        for strategy in strategies:
            assert len(validation_monitor._equity_curves[strategy]) == 10


# ============================================================================
# Complete Workflow Integration Tests
# ============================================================================

class TestCompleteWorkflowIntegration:
    """Test complete monitoring workflows"""
    
    def test_paper_trading_monitoring_workflow(self, paper_monitor, sample_strategy_snapshot, sample_risk_snapshot):
        """Test complete paper trading monitoring"""
        # Initialize monitoring
        paper_monitor.update_strategy(sample_strategy_snapshot)
        paper_monitor.update_risk(sample_risk_snapshot)
        
        # Add some orders
        order = PendingOrder(
            order_id=1001,
            symbol="AAPL",
            action="BUY",
            quantity=100,
            order_type="MKT",
            status="FILLED",
            filled_qty=100,
            avg_fill_price=150.25
        )
        paper_monitor.add_order(order)
        
        # Render dashboard
        layout = paper_monitor.render()
        assert layout is not None
        
        # Display (should not crash)
        paper_monitor.display()
    
    def test_validation_monitoring_workflow(
        self,
        validation_monitor,
        sample_strategy_snapshot,
        sample_risk_snapshot,
        sample_validation_report
    ):
        """Test complete validation monitoring"""
        # Setup strategy monitoring
        validation_monitor.update_strategy(sample_strategy_snapshot)
        validation_monitor.update_risk(sample_risk_snapshot)
        
        # Setup validation tracking
        validation_monitor.update_validation_status(
            strategy_name="MA_Cross_Strategy",
            report=sample_validation_report,
            days_remaining=0,
            trades_remaining=0,
            promotion_gate=ApprovalGate.GATE_1_VALIDATION
        )
        
        # Add equity curve
        for i in range(15):
            validation_monitor.update_equity_curve("MA_Cross_Strategy", 125000.0 + (i * 500))
        
        # Add alert
        alert = create_validation_alert(
            "MA_Cross_Strategy",
            AlertLevel.INFO,
            "Validation complete - Ready for promotion"
        )
        validation_monitor.add_alert(alert)
        
        # Render and display
        layout = validation_monitor.render()
        assert layout is not None
        validation_monitor.display()
    
    def test_health_monitoring_integration_workflow(
        self,
        validation_monitor,
        health_monitor,
        sample_strategy_snapshot
    ):
        """Test integration of health monitoring with dashboard"""
        # Monitor strategy
        validation_monitor.update_strategy(sample_strategy_snapshot)
        
        # Track health metrics
        metrics = {
            "win_rate": 0.62,
            "sharpe_ratio": 1.6,
            "max_drawdown": 0.07,
            "profit_factor": 2.1
        }
        health_monitor.record_metrics(metrics)
        
        # Check health
        health_alerts = health_monitor.check_health()
        
        # Convert health alerts to validation alerts if needed
        for health_alert in health_alerts:
            if health_alert.level == HealthAlertLevel.CRITICAL:
                alert = create_validation_alert(
                    "MA_Cross_Strategy",
                    AlertLevel.CRITICAL,
                    health_alert.message,
                    action_required=True
                )
                validation_monitor.add_alert(alert)
        
        # Render combined view
        layout = validation_monitor.render()
        assert layout is not None
    
    def test_multi_strategy_comprehensive_monitoring(
        self,
        validation_monitor,
        sample_validation_report
    ):
        """Test monitoring multiple strategies with all features"""
        strategies = ["MA_Cross", "Bollinger_Bands", "Mean_Reversion"]
        
        for i, strategy_name in enumerate(strategies):
            # Add strategy
            snapshot = StrategySnapshot(
                name=strategy_name,
                state=StrategyState.PAPER,
                start_time=datetime.now() - timedelta(hours=i+1),
                positions={},
                session_pnl=100.0 * (i + 1),
                total_pnl=1000.0 * (i + 1),
                metrics=StrategyMetrics(
                    days_running=20 + (i * 5),
                    total_trades=50 + (i * 10),
                    sharpe_ratio=1.5 + (i * 0.2),
                    max_drawdown=0.08 - (i * 0.01),
                    win_rate=0.60 + (i * 0.02)
                )
            )
            validation_monitor.update_strategy(snapshot)
            
            # Add validation status
            validation_monitor.update_validation_status(
                strategy_name=strategy_name,
                report=sample_validation_report,
                days_remaining=i * 5,
                trades_remaining=i * 10
            )
            
            # Add equity curve
            for j in range(10):
                validation_monitor.update_equity_curve(
                    strategy_name,
                    100000.0 + (j * 500) + (i * 10000)
                )
        
        # Add alerts
        for strategy_name in strategies:
            alert = create_validation_alert(
                strategy_name,
                AlertLevel.INFO,
                f"{strategy_name} milestone reached"
            )
            validation_monitor.add_alert(alert)
        
        # Verify state
        assert len(validation_monitor._strategy_snapshots) == 3
        assert len(validation_monitor._validation_statuses) == 3
        assert len(validation_monitor._equity_curves) == 3
        assert len(validation_monitor._alerts) >= 3
        
        # Render comprehensive view
        layout = validation_monitor.render()
        assert layout is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
