"""
Unit tests for ValidationMonitor

Tests validation dashboard enhancement including:
- Validation status panel
- Performance charts (sparklines)
- Alert panel
- Data updates and rendering

Author: TWS Robot Development Team
Date: November 23, 2025
Sprint 2 Task 5
"""

import pytest
from datetime import datetime, timedelta
from io import StringIO

from rich.console import Console

from monitoring.validation_monitor import (
    ValidationMonitor,
    Alert,
    AlertLevel,
    ValidationStatus,
    create_validation_alert
)
from monitoring.paper_monitor import StrategySnapshot, RiskSnapshot
from strategy.validation import ValidationReport, ValidationCheck, ValidationCriteria
from strategy.promotion import ApprovalGate
from strategy.lifecycle import StrategyState


@pytest.fixture
def console():
    """Create test console"""
    return Console(file=StringIO(), width=120)


@pytest.fixture
def monitor(console):
    """Create validation monitor"""
    return ValidationMonitor(console)


@pytest.fixture
def sample_validation_report():
    """Create sample validation report"""
    from datetime import date
    checks = [
        ValidationCheck(
            criterion="minimum_days",
            passed=True,
            current_value=35.0,
            required_value=30.0,
            message="35 days vs 30 required"
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
        ),
        ValidationCheck(
            criterion="max_drawdown",
            passed=True,
            current_value=0.08,
            required_value=0.10,
            message="8.0% vs 10.0% limit"
        )
    ]
    return ValidationReport(
        strategy_name="TestStrategy",
        report_date=date.today(),
        overall_passed=False,
        checks=checks,
        days_remaining=0,
        trades_remaining=5
    )


class TestValidationMonitor:
    """Test ValidationMonitor class"""
    
    def test_initialization(self, monitor):
        """Test monitor initialization"""
        assert monitor is not None
        assert monitor._validation_statuses == {}
        assert monitor._alerts == []
        assert monitor._equity_curves == {}
        assert monitor._max_alerts_display == 10
        assert monitor._max_sparkline_points == 30
    
    def test_custom_console(self):
        """Test custom console creation"""
        custom_console = Console()
        monitor = ValidationMonitor(custom_console)
        assert monitor.console == custom_console
    
    def test_update_validation_status(self, monitor, sample_validation_report):
        """Test validation status update"""
        monitor.update_validation_status(
            strategy_name="TestStrategy",
            report=sample_validation_report,
            days_remaining=0,
            trades_remaining=5,
            promotion_gate=ApprovalGate.GATE_1_VALIDATION
        )
        
        assert "TestStrategy" in monitor._validation_statuses
        status = monitor._validation_statuses["TestStrategy"]
        assert status.strategy_name == "TestStrategy"
        assert status.report == sample_validation_report
        assert status.days_remaining == 0
        assert status.trades_remaining == 5
        assert status.promotion_gate == ApprovalGate.GATE_1_VALIDATION
    
    def test_update_validation_status_multiple_strategies(self, monitor, sample_validation_report):
        """Test multiple strategy validation tracking"""
        monitor.update_validation_status(
            strategy_name="Strategy1",
            report=sample_validation_report,
            days_remaining=5,
            trades_remaining=0
        )
        
        monitor.update_validation_status(
            strategy_name="Strategy2",
            report=sample_validation_report,
            days_remaining=0,
            trades_remaining=10
        )
        
        assert len(monitor._validation_statuses) == 2
        assert "Strategy1" in monitor._validation_statuses
        assert "Strategy2" in monitor._validation_statuses
    
    def test_add_alert(self, monitor):
        """Test alert addition"""
        alert = Alert(
            level=AlertLevel.WARNING,
            timestamp=datetime.now(),
            strategy_name="TestStrategy",
            message="Test alert",
            action_required=False
        )
        
        monitor.add_alert(alert)
        
        assert len(monitor._alerts) == 1
        assert monitor._alerts[0] == alert
    
    def test_add_alert_ordering(self, monitor):
        """Test alerts are added to front (newest first)"""
        alert1 = Alert(
            level=AlertLevel.INFO,
            timestamp=datetime.now(),
            strategy_name="Test",
            message="First"
        )
        alert2 = Alert(
            level=AlertLevel.WARNING,
            timestamp=datetime.now(),
            strategy_name="Test",
            message="Second"
        )
        
        monitor.add_alert(alert1)
        monitor.add_alert(alert2)
        
        assert monitor._alerts[0].message == "Second"
        assert monitor._alerts[1].message == "First"
    
    def test_add_alert_max_limit(self, monitor):
        """Test alert list is limited"""
        # Add more than max
        for i in range(15):
            alert = Alert(
                level=AlertLevel.INFO,
                timestamp=datetime.now(),
                strategy_name="Test",
                message=f"Alert {i}"
            )
            monitor.add_alert(alert)
        
        # Should keep only most recent
        assert len(monitor._alerts) == monitor._max_alerts_display
        assert monitor._alerts[0].message == "Alert 14"  # Most recent
    
    def test_update_equity_curve(self, monitor):
        """Test equity curve update"""
        monitor.update_equity_curve("TestStrategy", 100000.0)
        monitor.update_equity_curve("TestStrategy", 101000.0)
        monitor.update_equity_curve("TestStrategy", 102000.0)
        
        assert "TestStrategy" in monitor._equity_curves
        assert len(monitor._equity_curves["TestStrategy"]) == 3
        assert monitor._equity_curves["TestStrategy"] == [100000.0, 101000.0, 102000.0]
    
    def test_update_equity_curve_max_points(self, monitor):
        """Test equity curve point limit"""
        # Add more than max
        for i in range(50):
            monitor.update_equity_curve("TestStrategy", 100000.0 + i * 1000)
        
        # Should keep only recent points
        assert len(monitor._equity_curves["TestStrategy"]) == monitor._max_sparkline_points
    
    def test_update_equity_curve_multiple_strategies(self, monitor):
        """Test multiple strategy equity curves"""
        monitor.update_equity_curve("Strategy1", 100000.0)
        monitor.update_equity_curve("Strategy2", 200000.0)
        monitor.update_equity_curve("Strategy1", 101000.0)
        
        assert "Strategy1" in monitor._equity_curves
        assert "Strategy2" in monitor._equity_curves
        assert len(monitor._equity_curves["Strategy1"]) == 2
        assert len(monitor._equity_curves["Strategy2"]) == 1
    
    def test_create_sparkline_normal(self, monitor):
        """Test sparkline creation with normal data"""
        values = [100, 110, 105, 115, 120, 118, 125, 130]
        sparkline = monitor._create_sparkline(values, width=8)
        
        assert len(sparkline) == 8
        assert isinstance(sparkline, str)
        # Should have variation (not all same character)
        assert len(set(sparkline)) > 1
    
    def test_create_sparkline_flat(self, monitor):
        """Test sparkline with flat values"""
        values = [100] * 10
        sparkline = monitor._create_sparkline(values, width=10)
        
        # Flat line should be dashes
        assert sparkline == "─" * 10
    
    def test_create_sparkline_empty(self, monitor):
        """Test sparkline with empty data"""
        sparkline = monitor._create_sparkline([], width=10)
        assert sparkline == "─" * 10
    
    def test_create_sparkline_single_value(self, monitor):
        """Test sparkline with single value"""
        sparkline = monitor._create_sparkline([100], width=10)
        assert sparkline == "─" * 10
    
    def test_create_sparkline_upward_trend(self, monitor):
        """Test sparkline shows upward trend"""
        values = list(range(0, 100, 10))
        sparkline = monitor._create_sparkline(values, width=10)
        
        # Should contain higher blocks toward the end
        # Unicode blocks: " ▁▂▃▄▅▆▇█"
        assert any(char in "▆▇█" for char in sparkline[-3:])
    
    def test_create_sparkline_downward_trend(self, monitor):
        """Test sparkline shows downward trend"""
        values = list(range(100, 0, -10))
        sparkline = monitor._create_sparkline(values, width=10)
        
        # Should contain lower blocks toward the end
        assert any(char in " ▁▂▃" for char in sparkline[-3:])
    
    def test_create_sparkline_width_sampling(self, monitor):
        """Test sparkline samples long data"""
        # Provide more values than width
        values = list(range(100))
        sparkline = monitor._create_sparkline(values, width=20)
        
        assert len(sparkline) == 20
    
    def test_create_validation_panel_no_data(self, monitor):
        """Test validation panel with no data"""
        panel = monitor._create_validation_panel()
        
        assert panel is not None
        # Render panel to string via console
        from io import StringIO
        string_io = StringIO()
        test_console = Console(file=string_io, width=80)
        test_console.print(panel)
        output = string_io.getvalue()
        assert "No validation data" in output or "validation" in output.lower()
    
    def test_create_validation_panel_with_data(self, monitor, sample_validation_report):
        """Test validation panel rendering"""
        monitor.update_validation_status(
            strategy_name="TestStrategy",
            report=sample_validation_report,
            days_remaining=0,
            trades_remaining=5,
            promotion_gate=ApprovalGate.GATE_1_VALIDATION
        )
        
        panel = monitor._create_validation_panel()
        
        assert panel is not None
        from io import StringIO
        string_io = StringIO()
        test_console = Console(file=string_io, width=120)
        test_console.print(panel)
        output = string_io.getvalue()
        assert "TestStrategy" in output
        assert "Minimum Days" in output or "minimum_days" in output.lower()
    
    def test_create_performance_charts_panel_no_data(self, monitor):
        """Test charts panel with no data"""
        panel = monitor._create_performance_charts_panel()
        
        assert panel is not None
        from io import StringIO
        string_io = StringIO()
        test_console = Console(file=string_io, width=80)
        test_console.print(panel)
        output = string_io.getvalue()
        assert "No performance data" in output or "performance" in output.lower() or "chart" in output.lower()
    
    def test_create_performance_charts_panel_with_data(self, monitor):
        """Test charts panel rendering"""
        # Add equity curve data
        for i in range(10):
            monitor.update_equity_curve("TestStrategy", 100000.0 + i * 1000)
        
        panel = monitor._create_performance_charts_panel()
        
        assert panel is not None
        from io import StringIO
        string_io = StringIO()
        test_console = Console(file=string_io, width=120)
        test_console.print(panel)
        output = string_io.getvalue()
        assert "TestStrategy" in output
    
    def test_create_alerts_panel_no_alerts(self, monitor):
        """Test alerts panel with no alerts"""
        panel = monitor._create_alerts_panel()
        
        assert panel is not None
        from io import StringIO
        string_io = StringIO()
        test_console = Console(file=string_io, width=80)
        test_console.print(panel)
        output = string_io.getvalue()
        assert "No alerts" in output or "alert" in output.lower()
    
    def test_create_alerts_panel_with_alerts(self, monitor):
        """Test alerts panel rendering"""
        alert = Alert(
            level=AlertLevel.WARNING,
            timestamp=datetime.now(),
            strategy_name="TestStrategy",
            message="Test warning",
            action_required=True
        )
        monitor.add_alert(alert)
        
        panel = monitor._create_alerts_panel()
        
        assert panel is not None
        from io import StringIO
        string_io = StringIO()
        test_console = Console(file=string_io, width=120)
        test_console.print(panel)
        output = string_io.getvalue()
        assert "TestStrategy" in output
        assert "Test warning" in output
    
    def test_render_layout(self, monitor):
        """Test full layout rendering"""
        from strategy.lifecycle import StrategyMetrics
        # Add some data
        monitor.update_strategy(StrategySnapshot(
            name="TestStrategy",
            state=StrategyState.PAPER,
            start_time=datetime.now(),
            positions={},  # Empty dict
            session_pnl=500.0,
            total_pnl=1500.0,
            metrics=StrategyMetrics(sharpe_ratio=1.5)
        ))
        
        layout = monitor.render()
        
        assert layout is not None
        # Should have 3 main sections
        child_names = [child.name for child in layout._children]
        assert "top" in child_names
        assert "middle" in child_names
        assert "bottom" in child_names
    
    def test_render_layout_structure(self, monitor):
        """Test layout has correct structure"""
        layout = monitor.render()
        
        # Top row should have strategy and risk
        top = layout["top"]
        child_names = [child.name for child in top._children]
        assert "strategy" in child_names
        assert "risk" in child_names
        
        # Middle row should have validation and charts
        middle = layout["middle"]
        child_names = [child.name for child in middle._children]
        assert "validation" in child_names
        assert "charts" in child_names
        
        # Bottom row should have orders and alerts
        bottom = layout["bottom"]
        child_names = [child.name for child in bottom._children]
        assert "orders" in child_names
        assert "alerts" in child_names


class TestAlertLevel:
    """Test AlertLevel enum"""
    
    def test_alert_levels_exist(self):
        """Test all alert levels are defined"""
        assert AlertLevel.INFO.value == "info"
        assert AlertLevel.WARNING.value == "warning"
        assert AlertLevel.CRITICAL.value == "critical"


class TestAlert:
    """Test Alert dataclass"""
    
    def test_alert_creation(self):
        """Test alert creation"""
        timestamp = datetime.now()
        alert = Alert(
            level=AlertLevel.WARNING,
            timestamp=timestamp,
            strategy_name="TestStrategy",
            message="Test alert"
        )
        
        assert alert.level == AlertLevel.WARNING
        assert alert.timestamp == timestamp
        assert alert.strategy_name == "TestStrategy"
        assert alert.message == "Test alert"
        assert alert.action_required is False
    
    def test_alert_with_action_required(self):
        """Test alert with action flag"""
        alert = Alert(
            level=AlertLevel.CRITICAL,
            timestamp=datetime.now(),
            strategy_name="Test",
            message="Critical issue",
            action_required=True
        )
        
        assert alert.action_required is True


class TestValidationStatus:
    """Test ValidationStatus dataclass"""
    
    def test_validation_status_creation(self, sample_validation_report):
        """Test validation status creation"""
        status = ValidationStatus(
            strategy_name="TestStrategy",
            report=sample_validation_report,
            days_remaining=5,
            trades_remaining=10,
            promotion_gate=ApprovalGate.GATE_1_VALIDATION
        )
        
        assert status.strategy_name == "TestStrategy"
        assert status.report == sample_validation_report
        assert status.days_remaining == 5
        assert status.trades_remaining == 10
        assert status.promotion_gate == ApprovalGate.GATE_1_VALIDATION
    
    def test_validation_status_no_gate(self, sample_validation_report):
        """Test validation status without promotion gate"""
        status = ValidationStatus(
            strategy_name="TestStrategy",
            report=sample_validation_report,
            days_remaining=0,
            trades_remaining=0,
            promotion_gate=None
        )
        
        assert status.promotion_gate is None


class TestCreateValidationAlert:
    """Test create_validation_alert helper"""
    
    def test_create_basic_alert(self):
        """Test basic alert creation"""
        alert = create_validation_alert(
            strategy_name="TestStrategy",
            level=AlertLevel.INFO,
            message="Test message"
        )
        
        assert isinstance(alert, Alert)
        assert alert.strategy_name == "TestStrategy"
        assert alert.level == AlertLevel.INFO
        assert alert.message == "Test message"
        assert alert.action_required is False
        assert isinstance(alert.timestamp, datetime)
    
    def test_create_alert_with_action(self):
        """Test alert with action required"""
        alert = create_validation_alert(
            strategy_name="TestStrategy",
            level=AlertLevel.CRITICAL,
            message="Critical error",
            action_required=True
        )
        
        assert alert.action_required is True
    
    def test_create_alert_timestamp(self):
        """Test alert timestamp is current"""
        before = datetime.now()
        alert = create_validation_alert(
            strategy_name="Test",
            level=AlertLevel.WARNING,
            message="Test"
        )
        after = datetime.now()
        
        assert before <= alert.timestamp <= after


class TestValidationMonitorIntegration:
    """Integration tests for complete workflows"""
    
    def test_full_validation_workflow(self, monitor, sample_validation_report):
        """Test complete validation monitoring workflow"""
        from strategy.lifecycle import StrategyMetrics
        # Setup strategy
        monitor.update_strategy(StrategySnapshot(
            name="TestStrategy",
            state=StrategyState.PAPER,
            start_time=datetime.now() - timedelta(days=35),
            positions={},
            session_pnl=200.0,
            total_pnl=1200.0,
            metrics=StrategyMetrics(sharpe_ratio=1.5, total_pnl=1200.0)
        ))
        
        # Update validation status
        monitor.update_validation_status(
            strategy_name="TestStrategy",
            report=sample_validation_report,
            days_remaining=0,
            trades_remaining=5,
            promotion_gate=ApprovalGate.GATE_1_VALIDATION
        )
        
        # Add equity curve
        for i in range(10):
            monitor.update_equity_curve("TestStrategy", 100000.0 + i * 500)
        
        # Add alert
        alert = create_validation_alert(
            strategy_name="TestStrategy",
            level=AlertLevel.INFO,
            message="5 trades remaining for validation"
        )
        monitor.add_alert(alert)
        
        # Render should work
        layout = monitor.render()
        assert layout is not None
    
    def test_multiple_strategy_monitoring(self, monitor, sample_validation_report):
        """Test monitoring multiple strategies"""
        from strategy.lifecycle import StrategyMetrics
        # Add two strategies
        for i in range(2):
            strategy_name = f"Strategy{i+1}"
            
            monitor.update_strategy(StrategySnapshot(
                name=strategy_name,
                state=StrategyState.PAPER,
                start_time=datetime.now(),
                positions={},
                session_pnl=float(i * 100),
                total_pnl=float(i * 1000),
                metrics=StrategyMetrics(sharpe_ratio=1.0 + i * 0.5)
            ))
            
            monitor.update_validation_status(
                strategy_name=strategy_name,
                report=sample_validation_report,
                days_remaining=i * 5,
                trades_remaining=i * 10
            )
            
            monitor.update_equity_curve(strategy_name, 100000.0 + i * 10000)
        
        assert len(monitor._strategy_snapshots) == 2
        assert len(monitor._validation_statuses) == 2
        assert len(monitor._equity_curves) == 2
    
    def test_alert_escalation(self, monitor):
        """Test alert level escalation"""
        # Add alerts of different levels
        monitor.add_alert(create_validation_alert(
            "TestStrategy", AlertLevel.INFO, "Info message"
        ))
        monitor.add_alert(create_validation_alert(
            "TestStrategy", AlertLevel.WARNING, "Warning message"
        ))
        monitor.add_alert(create_validation_alert(
            "TestStrategy", AlertLevel.CRITICAL, "Critical message"
        ))
        
        assert len(monitor._alerts) == 3
        # Most recent (critical) should be first
        assert monitor._alerts[0].level == AlertLevel.CRITICAL
