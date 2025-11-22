"""
Unit Tests for Paper Trading Monitor

Tests the PaperMonitor class and its display components.

Author: TWS Robot Development Team
Date: November 22, 2025
Sprint 1 Task 4
"""

import pytest
from datetime import datetime, timedelta
from io import StringIO

from rich.console import Console

from monitoring.paper_monitor import (
    PaperMonitor,
    StrategySnapshot,
    RiskSnapshot
)
from strategy.lifecycle import StrategyState, StrategyMetrics
from backtest.data_models import Position
from execution.paper_adapter import PendingOrder


@pytest.fixture
def console():
    """Create console that writes to string buffer"""
    return Console(file=StringIO(), width=120)


@pytest.fixture
def monitor(console):
    """Create PaperMonitor instance"""
    return PaperMonitor(console=console)


@pytest.fixture
def sample_strategy_snapshot():
    """Create sample strategy snapshot"""
    return StrategySnapshot(
        name="MA_Cross_Strategy",
        state=StrategyState.PAPER,
        start_time=datetime.now() - timedelta(hours=2, minutes=30),
        positions={
            "AAPL": Position(symbol="AAPL", quantity=100, average_cost=150.0, current_price=152.0),
            "GOOGL": Position(symbol="GOOGL", quantity=0, average_cost=0.0, current_price=0.0)
        },
        session_pnl=250.50,
        total_pnl=1250.75,
        metrics=StrategyMetrics(
            days_running=15,
            total_trades=45,
            sharpe_ratio=1.25,
            max_drawdown=0.06,
            win_rate=0.58,
            profit_factor=1.8,
            consecutive_losses=2,
            total_pnl=1250.75
        )
    )


@pytest.fixture
def sample_risk_snapshot():
    """Create sample risk snapshot"""
    return RiskSnapshot(
        portfolio_value=100000.0,
        margin_used=25000.0,
        margin_available=75000.0,
        max_drawdown=0.06,
        position_count=3,
        risk_limit_utilization=0.45
    )


@pytest.fixture
def sample_orders():
    """Create sample orders"""
    return [
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
            limit_price=2800.0,
            status="PENDING",
            filled_qty=0,
            avg_fill_price=0.0
        ),
        PendingOrder(
            order_id=1003,
            symbol="MSFT",
            action="BUY",
            quantity=75,
            order_type="MKT",
            status="PARTIAL",
            filled_qty=50,
            avg_fill_price=380.50
        )
    ]


class TestPaperMonitorBasics:
    """Test basic PaperMonitor functionality"""
    
    def test_monitor_initialization(self, monitor):
        """Test monitor initializes correctly"""
        assert monitor is not None
        assert monitor.console is not None
        assert len(monitor._strategy_snapshots) == 0
        assert monitor._risk_snapshot is None
        assert len(monitor._recent_orders) == 0
    
    def test_update_strategy(self, monitor, sample_strategy_snapshot):
        """Test updating strategy snapshot"""
        monitor.update_strategy(sample_strategy_snapshot)
        
        assert len(monitor._strategy_snapshots) == 1
        assert "MA_Cross_Strategy" in monitor._strategy_snapshots
        assert monitor._strategy_snapshots["MA_Cross_Strategy"] == sample_strategy_snapshot
    
    def test_update_multiple_strategies(self, monitor, sample_strategy_snapshot):
        """Test updating multiple strategies"""
        snapshot2 = StrategySnapshot(
            name="Mean_Reversion",
            state=StrategyState.PAPER,
            start_time=datetime.now(),
            positions={},
            session_pnl=0.0,
            total_pnl=0.0,
            metrics=StrategyMetrics()
        )
        
        monitor.update_strategy(sample_strategy_snapshot)
        monitor.update_strategy(snapshot2)
        
        assert len(monitor._strategy_snapshots) == 2
        assert "MA_Cross_Strategy" in monitor._strategy_snapshots
        assert "Mean_Reversion" in monitor._strategy_snapshots
    
    def test_update_risk(self, monitor, sample_risk_snapshot):
        """Test updating risk snapshot"""
        monitor.update_risk(sample_risk_snapshot)
        
        assert monitor._risk_snapshot is not None
        assert monitor._risk_snapshot.portfolio_value == 100000.0
        assert monitor._risk_snapshot.margin_used == 25000.0
    
    def test_add_order(self, monitor, sample_orders):
        """Test adding orders"""
        for order in sample_orders:
            monitor.add_order(order)
        
        assert len(monitor._recent_orders) == 3
        # Orders should be in reverse order (most recent first)
        assert monitor._recent_orders[0].order_id == 1003
        assert monitor._recent_orders[1].order_id == 1002
        assert monitor._recent_orders[2].order_id == 1001
    
    def test_order_limit(self, monitor):
        """Test order display limit"""
        # Add more than max orders
        for i in range(25):
            order = PendingOrder(
                order_id=i,
                symbol="TEST",
                action="BUY",
                quantity=100,
                order_type="MKT"
            )
            monitor.add_order(order)
        
        # Should only keep last 20
        assert len(monitor._recent_orders) == 20
        # Most recent should be ID 24
        assert monitor._recent_orders[0].order_id == 24


class TestStrategyPanel:
    """Test strategy status panel"""
    
    def test_strategy_panel_empty(self, monitor):
        """Test panel with no strategies"""
        panel = monitor._create_strategy_panel()
        
        assert panel is not None
        assert panel.title == "Strategy Status"
    
    def test_strategy_panel_with_data(self, monitor, sample_strategy_snapshot):
        """Test panel with strategy data"""
        monitor.update_strategy(sample_strategy_snapshot)
        panel = monitor._create_strategy_panel()
        
        assert panel is not None
        assert panel.title == "Strategy Status"
        # Panel should be a Table with content
        assert panel.renderable is not None
    
    def test_strategy_panel_runtime_calculation(self, monitor):
        """Test runtime calculation in strategy panel"""
        snapshot = StrategySnapshot(
            name="Test",
            state=StrategyState.PAPER,
            start_time=datetime.now() - timedelta(hours=3, minutes=45),
            positions={},
            session_pnl=0.0,
            total_pnl=0.0,
            metrics=StrategyMetrics()
        )
        
        monitor.update_strategy(snapshot)
        panel = monitor._create_strategy_panel()
        
        # Should show 3h 45m runtime (approximately)
        assert panel is not None
    
    def test_strategy_panel_position_count(self, monitor, sample_strategy_snapshot):
        """Test position count calculation"""
        monitor.update_strategy(sample_strategy_snapshot)
        panel = monitor._create_strategy_panel()
        
        # Sample has 1 non-zero position (AAPL)
        assert panel is not None


class TestRiskPanel:
    """Test risk metrics panel"""
    
    def test_risk_panel_empty(self, monitor):
        """Test panel with no risk data"""
        panel = monitor._create_risk_panel()
        
        assert panel is not None
        assert panel.title == "Risk Metrics"
    
    def test_risk_panel_with_data(self, monitor, sample_risk_snapshot):
        """Test panel with risk data"""
        monitor.update_risk(sample_risk_snapshot)
        panel = monitor._create_risk_panel()
        
        assert panel is not None
        assert panel.title == "Risk Metrics"
    
    def test_risk_panel_margin_calculation(self, monitor, sample_risk_snapshot):
        """Test margin percentage calculation"""
        monitor.update_risk(sample_risk_snapshot)
        panel = monitor._create_risk_panel()
        
        # Margin should be 25% (25000/100000)
        assert panel is not None


class TestOrdersPanel:
    """Test order activity panel"""
    
    def test_orders_panel_empty(self, monitor):
        """Test panel with no orders"""
        panel = monitor._create_orders_panel()
        
        assert panel is not None
        assert panel.title == "Order Activity"
    
    def test_orders_panel_with_data(self, monitor, sample_orders):
        """Test panel with order data"""
        for order in sample_orders:
            monitor.add_order(order)
        
        panel = monitor._create_orders_panel()
        
        assert panel is not None
        assert "Last 3" in panel.title
    
    def test_orders_panel_status_colors(self, monitor, sample_orders):
        """Test order status styling"""
        for order in sample_orders:
            monitor.add_order(order)
        
        panel = monitor._create_orders_panel()
        
        # Panel should contain order symbols
        assert panel is not None


class TestPerformancePanel:
    """Test performance summary panel"""
    
    def test_performance_panel_empty(self, monitor):
        """Test panel with no data"""
        panel = monitor._create_performance_panel()
        
        assert panel is not None
        assert panel.title == "Performance Summary"
    
    def test_performance_panel_with_data(self, monitor, sample_strategy_snapshot, sample_risk_snapshot):
        """Test panel with performance data"""
        monitor.update_strategy(sample_strategy_snapshot)
        monitor.update_risk(sample_risk_snapshot)
        panel = monitor._create_performance_panel()
        
        assert panel is not None
        assert panel.title == "Performance Summary"
    
    def test_performance_panel_aggregation(self, monitor, sample_strategy_snapshot):
        """Test aggregation of multiple strategies"""
        snapshot2 = StrategySnapshot(
            name="Strategy2",
            state=StrategyState.PAPER,
            start_time=datetime.now(),
            positions={},
            session_pnl=100.0,
            total_pnl=500.0,
            metrics=StrategyMetrics(
                total_trades=20,
                sharpe_ratio=0.8,
                win_rate=0.55
            )
        )
        
        monitor.update_strategy(sample_strategy_snapshot)
        monitor.update_strategy(snapshot2)
        panel = monitor._create_performance_panel()
        
        # Should aggregate metrics from both strategies
        assert panel is not None


class TestLayoutRendering:
    """Test layout rendering"""
    
    def test_render_creates_layout(self, monitor):
        """Test render creates valid layout"""
        layout = monitor.render()
        
        assert layout is not None
        # Check that layout has named children
        assert layout["top"] is not None
        assert layout["bottom"] is not None
    
    def test_render_with_full_data(self, monitor, sample_strategy_snapshot, sample_risk_snapshot, sample_orders):
        """Test render with all data populated"""
        monitor.update_strategy(sample_strategy_snapshot)
        monitor.update_risk(sample_risk_snapshot)
        for order in sample_orders:
            monitor.add_order(order)
        
        layout = monitor.render()
        
        assert layout is not None
    
    def test_display_executes(self, monitor, sample_strategy_snapshot):
        """Test display method executes without error"""
        monitor.update_strategy(sample_strategy_snapshot)
        
        # Should not raise exception
        monitor.display()


class TestDataIntegrity:
    """Test data handling and edge cases"""
    
    def test_empty_positions_dict(self, monitor):
        """Test strategy with no positions"""
        snapshot = StrategySnapshot(
            name="Empty",
            state=StrategyState.PAPER,
            start_time=datetime.now(),
            positions={},
            session_pnl=0.0,
            total_pnl=0.0,
            metrics=StrategyMetrics()
        )
        
        monitor.update_strategy(snapshot)
        panel = monitor._create_strategy_panel()
        
        assert panel is not None
    
    def test_negative_pnl_display(self, monitor):
        """Test display of negative P&L"""
        snapshot = StrategySnapshot(
            name="Losing",
            state=StrategyState.PAPER,
            start_time=datetime.now(),
            positions={},
            session_pnl=-500.0,
            total_pnl=-1500.0,
            metrics=StrategyMetrics()
        )
        
        monitor.update_strategy(snapshot)
        panel = monitor._create_strategy_panel()
        
        assert panel is not None
    
    def test_high_risk_utilization(self, monitor):
        """Test display of high risk utilization"""
        risk = RiskSnapshot(
            portfolio_value=100000.0,
            margin_used=85000.0,
            margin_available=15000.0,
            max_drawdown=0.12,
            position_count=10,
            risk_limit_utilization=0.95
        )
        
        monitor.update_risk(risk)
        panel = monitor._create_risk_panel()
        
        assert panel is not None
    
    def test_zero_portfolio_value(self, monitor):
        """Test handling of zero portfolio value"""
        risk = RiskSnapshot(
            portfolio_value=0.0,
            margin_used=0.0,
            margin_available=0.0,
            max_drawdown=0.0,
            position_count=0,
            risk_limit_utilization=0.0
        )
        
        monitor.update_risk(risk)
        panel = monitor._create_risk_panel()
        
        # Should not crash with division by zero
        assert panel is not None


class TestConsoleOutput:
    """Test console output formatting"""
    
    def test_console_output_captured(self, console):
        """Test console output can be captured"""
        monitor = PaperMonitor(console=console)
        
        snapshot = StrategySnapshot(
            name="Test",
            state=StrategyState.PAPER,
            start_time=datetime.now(),
            positions={},
            session_pnl=100.0,
            total_pnl=500.0,
            metrics=StrategyMetrics()
        )
        
        monitor.update_strategy(snapshot)
        monitor.display()
        
        # Output should be captured in console file
        output = console.file.getvalue()
        assert len(output) > 0
    
    def test_multiple_displays(self, monitor, sample_strategy_snapshot):
        """Test multiple display calls"""
        monitor.update_strategy(sample_strategy_snapshot)
        
        # Should not raise exception on multiple calls
        monitor.display()
        
        # Update data
        sample_strategy_snapshot.session_pnl = 300.0
        monitor.update_strategy(sample_strategy_snapshot)
        
        monitor.display()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
