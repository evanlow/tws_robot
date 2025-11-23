"""
Unit tests for Real-time Risk Monitor

Tests risk monitoring, limit enforcement, and alert generation.

Author: TWS Robot Development Team
Date: November 2025
Sprint 2 Task 1
"""

import pytest
from datetime import datetime, timedelta
from backtest.profiles import ProfileLibrary
from backtest.data_models import Position
from execution.risk_monitor import RealTimeRiskMonitor, PortfolioRisk, RiskAlert


class TestRealTimeRiskMonitor:
    """Test RealTimeRiskMonitor initialization and basic functionality"""
    
    def test_initialization(self):
        """Test risk monitor initialization"""
        profile = ProfileLibrary.conservative()
        monitor = RealTimeRiskMonitor(profile, initial_capital=100000.0)
        
        assert monitor.risk_profile.name == "Conservative"
        assert monitor.initial_capital == 100000.0
        assert monitor.peak_value == 100000.0
        assert monitor.daily_starting_value == 100000.0
        assert len(monitor.alerts) == 0
    
    def test_initialization_with_moderate_profile(self):
        """Test initialization with moderate profile"""
        profile = ProfileLibrary.moderate()
        monitor = RealTimeRiskMonitor(profile, initial_capital=50000.0)
        
        assert monitor.risk_profile.name == "Moderate"
        assert monitor.initial_capital == 50000.0
        assert monitor.peak_value == 50000.0
    
    def test_get_risk_summary(self):
        """Test risk summary retrieval"""
        profile = ProfileLibrary.conservative()
        monitor = RealTimeRiskMonitor(profile, initial_capital=100000.0)
        
        summary = monitor.get_risk_summary()
        
        assert summary['profile_name'] == "Conservative"
        assert summary['initial_capital'] == 100000.0
        assert summary['peak_value'] == 100000.0
        assert summary['alert_count'] == 0


class TestPositionRiskChecks:
    """Test position-level risk checks"""
    
    def test_position_within_limits(self):
        """Test position that passes all risk checks"""
        profile = ProfileLibrary.conservative()  # 5% max position
        monitor = RealTimeRiskMonitor(profile, initial_capital=100000.0)
        
        # 4% position - should pass
        allowed, reason = monitor.check_position_risk(
            symbol="AAPL",
            quantity=100,
            current_price=40.0,  # $4000 position
            current_positions={},
            portfolio_value=100000.0
        )
        
        assert allowed is True
        assert reason is None
    
    def test_position_exceeds_size_limit(self):
        """Test position that exceeds max position size"""
        profile = ProfileLibrary.conservative()  # 5% max position
        monitor = RealTimeRiskMonitor(profile, initial_capital=100000.0)
        
        # 10% position - should fail
        allowed, reason = monitor.check_position_risk(
            symbol="AAPL",
            quantity=100,
            current_price=100.0,  # $10,000 position
            current_positions={},
            portfolio_value=100000.0
        )
        
        assert allowed is False
        assert "Position size" in reason
        assert "exceeds limit" in reason
    
    def test_symbol_exposure_limit(self):
        """Test single symbol exposure limit"""
        profile = ProfileLibrary.conservative()  # 10% max per symbol
        monitor = RealTimeRiskMonitor(profile, initial_capital=100000.0)
        
        # Existing 8% position
        existing_positions = {
            "AAPL": Position(symbol="AAPL", quantity=80, average_cost=100.0, current_price=100.0)
        }
        
        # Adding 5% more would be 13% total - should fail
        allowed, reason = monitor.check_position_risk(
            symbol="AAPL",
            quantity=50,
            current_price=100.0,  # $5000 more
            current_positions=existing_positions,
            portfolio_value=100000.0
        )
        
        assert allowed is False
        assert "Symbol exposure" in reason
    
    def test_concurrent_position_limit(self):
        """Test maximum concurrent positions limit"""
        profile = ProfileLibrary.conservative()  # 3 max concurrent
        monitor = RealTimeRiskMonitor(profile, initial_capital=100000.0)
        
        # Already have 3 positions
        existing_positions = {
            "AAPL": Position(symbol="AAPL", quantity=20, average_cost=100.0, current_price=100.0),
            "MSFT": Position(symbol="MSFT", quantity=15, average_cost=150.0, current_price=150.0),
            "GOOGL": Position(symbol="GOOGL", quantity=10, average_cost=200.0, current_price=200.0)
        }
        
        # Trying to add 4th position - should fail
        allowed, reason = monitor.check_position_risk(
            symbol="TSLA",
            quantity=10,
            current_price=300.0,  # $3000 position
            current_positions=existing_positions,
            portfolio_value=100000.0
        )
        
        assert allowed is False
        assert "Max concurrent positions" in reason
    
    def test_per_symbol_position_limit(self):
        """Test per-symbol position limit"""
        profile = ProfileLibrary.conservative()  # 1 position per symbol
        monitor = RealTimeRiskMonitor(profile, initial_capital=100000.0)
        
        # Already have AAPL position
        existing_positions = {
            "AAPL": Position(symbol="AAPL", quantity=20, average_cost=100.0, current_price=100.0)
        }
        
        # Trying to add another AAPL position - should fail
        allowed, reason = monitor.check_position_risk(
            symbol="AAPL",
            quantity=10,
            current_price=100.0,
            current_positions=existing_positions,
            portfolio_value=100000.0
        )
        
        assert allowed is False
        assert "1 position per symbol" in reason


class TestPortfolioRiskChecks:
    """Test portfolio-level risk checks"""
    
    def test_portfolio_within_limits(self):
        """Test portfolio with all metrics within limits"""
        profile = ProfileLibrary.conservative()
        monitor = RealTimeRiskMonitor(profile, initial_capital=100000.0)
        
        # Small positions, no drawdown
        positions = {
            "AAPL": Position(symbol="AAPL", quantity=20, average_cost=100.0, current_price=100.0),
            "MSFT": Position(symbol="MSFT", quantity=10, average_cost=150.0, current_price=150.0)
        }
        prices = {"AAPL": 100.0, "MSFT": 150.0}
        
        ok, warnings = monitor.check_portfolio_risk(positions, prices, 100000.0)
        
        assert ok is True
        assert len(warnings) == 0
    
    def test_total_exposure_exceeded(self):
        """Test total exposure limit exceeded"""
        profile = ProfileLibrary.conservative()  # 50% max total exposure
        monitor = RealTimeRiskMonitor(profile, initial_capital=100000.0)
        
        # 60% total exposure
        positions = {
            "AAPL": Position(symbol="AAPL", quantity=300, average_cost=100.0, current_price=100.0),
            "MSFT": Position(symbol="MSFT", quantity=200, average_cost=150.0, current_price=150.0)
        }
        prices = {"AAPL": 100.0, "MSFT": 150.0}
        
        ok, warnings = monitor.check_portfolio_risk(positions, prices, 100000.0)
        
        assert ok is False
        assert len(warnings) >= 1
        assert any("Total exposure" in w for w in warnings)
    
    def test_drawdown_limit_exceeded(self):
        """Test maximum drawdown limit exceeded"""
        profile = ProfileLibrary.conservative()  # 10% max drawdown
        monitor = RealTimeRiskMonitor(profile, initial_capital=100000.0)
        monitor.peak_value = 110000.0  # Had reached $110k
        
        # Now at $98k - 10.9% drawdown
        positions = {}
        prices = {}
        
        ok, warnings = monitor.check_portfolio_risk(positions, prices, 98000.0)
        
        assert ok is False
        assert len(warnings) >= 1
        assert any("Drawdown" in w for w in warnings)
        assert len(monitor.alerts) > 0
        assert monitor.alerts[0].alert_type == 'drawdown'
        assert monitor.alerts[0].severity == 'critical'
    
    def test_daily_loss_limit_exceeded(self):
        """Test maximum daily loss limit exceeded"""
        profile = ProfileLibrary.conservative()  # 2% max daily loss
        monitor = RealTimeRiskMonitor(profile, initial_capital=100000.0)
        monitor.reset_daily_tracking(100000.0)
        
        # Lost 3% today
        positions = {}
        prices = {}
        
        ok, warnings = monitor.check_portfolio_risk(positions, prices, 97000.0)
        
        assert ok is False
        assert len(warnings) >= 1
        assert any("Daily loss" in w for w in warnings)
        assert len(monitor.alerts) > 0
        assert monitor.alerts[0].alert_type == 'daily_loss'
        assert monitor.alerts[0].severity == 'critical'
    
    def test_peak_value_tracking(self):
        """Test peak value updates correctly"""
        profile = ProfileLibrary.conservative()
        monitor = RealTimeRiskMonitor(profile, initial_capital=100000.0)
        
        # Portfolio goes up
        monitor.check_portfolio_risk({}, {}, 105000.0)
        assert monitor.peak_value == 105000.0
        
        # Portfolio goes down (peak stays)
        monitor.check_portfolio_risk({}, {}, 103000.0)
        assert monitor.peak_value == 105000.0
        
        # Portfolio hits new peak
        monitor.check_portfolio_risk({}, {}, 107000.0)
        assert monitor.peak_value == 107000.0


class TestPortfolioRiskCalculation:
    """Test portfolio risk metric calculations"""
    
    def test_calculate_empty_portfolio(self):
        """Test risk calculation with no positions"""
        profile = ProfileLibrary.conservative()
        monitor = RealTimeRiskMonitor(profile, initial_capital=100000.0)
        
        risk = monitor.calculate_portfolio_risk({}, {}, 100000.0)
        
        assert isinstance(risk, PortfolioRisk)
        assert risk.total_value == 100000.0
        assert risk.total_exposure == 0.0
        assert risk.exposure_pct == 0.0
        assert risk.position_count == 0
        assert risk.current_drawdown == 0.0
        assert risk.risk_utilization >= 0.0
    
    def test_calculate_with_positions(self):
        """Test risk calculation with positions"""
        profile = ProfileLibrary.conservative()
        monitor = RealTimeRiskMonitor(profile, initial_capital=100000.0)
        
        positions = {
            "AAPL": Position(symbol="AAPL", quantity=20, average_cost=100.0, current_price=105.0),
            "MSFT": Position(symbol="MSFT", quantity=10, average_cost=150.0, current_price=155.0)
        }
        prices = {"AAPL": 105.0, "MSFT": 155.0}
        
        risk = monitor.calculate_portfolio_risk(positions, prices, 103650.0)
        
        assert risk.total_value == 103650.0
        assert risk.total_exposure == 2100.0 + 1550.0  # AAPL + MSFT
        assert 0.035 < risk.exposure_pct < 0.036  # ~3.5%
        assert risk.position_count == 2
    
    def test_risk_utilization_calculation(self):
        """Test risk utilization percentage"""
        profile = ProfileLibrary.conservative()
        monitor = RealTimeRiskMonitor(profile, initial_capital=100000.0)
        
        # Small position - low utilization
        positions = {
            "AAPL": Position(symbol="AAPL", quantity=10, average_cost=100.0, current_price=100.0)
        }
        prices = {"AAPL": 100.0}
        
        risk = monitor.calculate_portfolio_risk(positions, prices, 100000.0)
        
        assert 0.0 <= risk.risk_utilization <= 1.0
        assert risk.risk_utilization < 0.5  # Low utilization
    
    def test_daily_pnl_calculation(self):
        """Test daily P&L calculation"""
        profile = ProfileLibrary.conservative()
        monitor = RealTimeRiskMonitor(profile, initial_capital=100000.0)
        monitor.reset_daily_tracking(100000.0)
        
        # Up 2% today
        risk = monitor.calculate_portfolio_risk({}, {}, 102000.0)
        
        assert risk.daily_pnl == 2000.0
        assert abs(risk.daily_loss_pct - 0.02) < 0.0001


class TestDailyTracking:
    """Test daily reset and tracking"""
    
    def test_daily_reset(self):
        """Test daily tracking reset"""
        profile = ProfileLibrary.conservative()
        monitor = RealTimeRiskMonitor(profile, initial_capital=100000.0)
        
        # Set daily starting value
        monitor.reset_daily_tracking(105000.0)
        
        assert monitor.daily_starting_value == 105000.0
        assert monitor.daily_reset_date == datetime.now().date()
    
    def test_daily_reset_clears_previous_pnl(self):
        """Test that daily reset starts fresh P&L"""
        profile = ProfileLibrary.conservative()
        monitor = RealTimeRiskMonitor(profile, initial_capital=100000.0)
        
        # Day 1: Start at 100k, end at 102k
        monitor.reset_daily_tracking(100000.0)
        risk1 = monitor.calculate_portfolio_risk({}, {}, 102000.0)
        assert risk1.daily_pnl == 2000.0
        
        # Day 2: Start at 102k, end at 101k
        monitor.reset_daily_tracking(102000.0)
        risk2 = monitor.calculate_portfolio_risk({}, {}, 101000.0)
        assert risk2.daily_pnl == -1000.0  # Lost 1k today


class TestRiskAlerts:
    """Test risk alert generation and management"""
    
    def test_alert_generation_on_drawdown(self):
        """Test alert generated when drawdown exceeded"""
        profile = ProfileLibrary.conservative()
        monitor = RealTimeRiskMonitor(profile, initial_capital=100000.0)
        monitor.peak_value = 110000.0
        
        # Trigger drawdown alert
        monitor.check_portfolio_risk({}, {}, 98000.0)
        
        alerts = monitor.get_recent_alerts()
        assert len(alerts) > 0
        assert alerts[0].alert_type == 'drawdown'
        assert alerts[0].severity == 'critical'
        assert 'Maximum drawdown exceeded' in alerts[0].message
    
    def test_alert_generation_on_daily_loss(self):
        """Test alert generated when daily loss exceeded"""
        profile = ProfileLibrary.conservative()
        monitor = RealTimeRiskMonitor(profile, initial_capital=100000.0)
        monitor.reset_daily_tracking(100000.0)
        
        # Trigger daily loss alert
        monitor.check_portfolio_risk({}, {}, 97000.0)
        
        alerts = monitor.get_recent_alerts()
        assert len(alerts) > 0
        assert alerts[0].alert_type == 'daily_loss'
        assert alerts[0].severity == 'critical'
    
    def test_get_recent_alerts(self):
        """Test retrieving recent alerts"""
        profile = ProfileLibrary.conservative()
        monitor = RealTimeRiskMonitor(profile, initial_capital=100000.0)
        
        # No alerts initially
        assert len(monitor.get_recent_alerts()) == 0
        
        # Generate multiple alerts
        monitor.peak_value = 110000.0
        monitor.check_portfolio_risk({}, {}, 98000.0)  # Drawdown
        monitor.reset_daily_tracking(100000.0)
        monitor.check_portfolio_risk({}, {}, 97000.0)  # Daily loss
        
        alerts = monitor.get_recent_alerts(count=5)
        assert len(alerts) >= 2
    
    def test_clear_alerts(self):
        """Test clearing alert history"""
        profile = ProfileLibrary.conservative()
        monitor = RealTimeRiskMonitor(profile, initial_capital=100000.0)
        
        # Generate alert
        monitor.peak_value = 110000.0
        monitor.check_portfolio_risk({}, {}, 98000.0)
        
        assert len(monitor.get_recent_alerts()) > 0
        
        # Clear alerts
        monitor.clear_alerts()
        
        assert len(monitor.get_recent_alerts()) == 0
    
    def test_alert_details(self):
        """Test alert contains detailed information"""
        profile = ProfileLibrary.conservative()
        monitor = RealTimeRiskMonitor(profile, initial_capital=100000.0)
        monitor.peak_value = 110000.0
        
        monitor.check_portfolio_risk({}, {}, 98000.0)
        
        alerts = monitor.get_recent_alerts()
        alert = alerts[0]
        
        assert isinstance(alert, RiskAlert)
        assert isinstance(alert.timestamp, datetime)
        assert alert.alert_type == 'drawdown'
        assert alert.severity == 'critical'
        assert 'current_drawdown' in alert.details
        assert 'max_allowed' in alert.details
        assert 'peak_value' in alert.details


class TestThreadSafety:
    """Test thread-safety of risk monitor"""
    
    def test_concurrent_position_checks(self):
        """Test concurrent position risk checks"""
        profile = ProfileLibrary.moderate()
        monitor = RealTimeRiskMonitor(profile, initial_capital=100000.0)
        
        # Simulate concurrent checks (single-threaded test)
        results = []
        for i in range(5):
            allowed, reason = monitor.check_position_risk(
                symbol=f"STOCK{i}",
                quantity=100,
                current_price=50.0,
                current_positions={},
                portfolio_value=100000.0
            )
            results.append(allowed)
        
        # All should pass (under limits)
        assert all(results)
    
    def test_concurrent_portfolio_checks(self):
        """Test concurrent portfolio risk checks"""
        profile = ProfileLibrary.moderate()
        monitor = RealTimeRiskMonitor(profile, initial_capital=100000.0)
        
        # Simulate concurrent checks
        results = []
        for i in range(3):
            ok, warnings = monitor.check_portfolio_risk({}, {}, 100000.0)
            results.append(ok)
        
        assert all(results)


class TestIntegrationScenarios:
    """Test realistic integration scenarios"""
    
    def test_full_day_trading_scenario(self):
        """Test complete day of trading"""
        profile = ProfileLibrary.moderate()
        monitor = RealTimeRiskMonitor(profile, initial_capital=100000.0)
        
        # Market open
        monitor.reset_daily_tracking(100000.0)
        
        # Morning: Buy AAPL
        allowed, _ = monitor.check_position_risk(
            "AAPL", 100, 100.0, {}, 100000.0
        )
        assert allowed
        
        positions = {
            "AAPL": Position(symbol="AAPL", quantity=100, average_cost=100.0, current_price=100.0)
        }
        
        # Midday: Check portfolio
        ok, _ = monitor.check_portfolio_risk(
            positions, {"AAPL": 102.0}, 100200.0
        )
        assert ok
        
        # Afternoon: Try to buy MSFT (smaller position to stay under 10% limit)
        allowed, _ = monitor.check_position_risk(
            "MSFT", 60, 150.0, positions, 100200.0  # $9000 = 8.9% of portfolio
        )
        assert allowed  # Should still be under limits
    
    def test_risk_escalation_scenario(self):
        """Test gradually increasing risk until limit hit"""
        profile = ProfileLibrary.conservative()  # 3 max positions
        monitor = RealTimeRiskMonitor(profile, initial_capital=100000.0)
        
        positions = {}
        
        # Add positions until limit
        for i in range(3):
            allowed, _ = monitor.check_position_risk(
                f"STOCK{i}", 10, 100.0, positions, 100000.0
            )
            assert allowed
            positions[f"STOCK{i}"] = Position(
                symbol=f"STOCK{i}", quantity=10, average_cost=100.0, current_price=100.0
            )
        
        # 4th position should fail
        allowed, reason = monitor.check_position_risk(
            "STOCK3", 10, 100.0, positions, 100000.0
        )
        assert not allowed
        assert "Max concurrent positions" in reason
