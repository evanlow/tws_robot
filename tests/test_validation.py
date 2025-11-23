"""
Tests for strategy validation enforcement.

Comprehensive testing of ValidationEnforcer including:
- Individual criterion checks
- Combined validation logic
- Edge cases (exactly at threshold)
- Report generation
- Integration with PaperMetricsTracker
"""

import pytest
import tempfile
from datetime import datetime, date, timedelta

from strategy.validation import ValidationEnforcer, ValidationReport, ValidationCheck
from strategy.lifecycle import ValidationCriteria, StrategyMetrics
from strategy.metrics_tracker import PaperMetricsTracker


@pytest.fixture
def temp_db():
    """Create temporary database file"""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        yield f.name


@pytest.fixture
def tracker(temp_db):
    """Create metrics tracker with temp database"""
    return PaperMetricsTracker(temp_db, "test_strategy", initial_capital=100000.0)


@pytest.fixture
def enforcer():
    """Create validation enforcer with default criteria"""
    return ValidationEnforcer()


@pytest.fixture
def custom_enforcer():
    """Create validation enforcer with custom criteria"""
    criteria = ValidationCriteria(
        min_days=10,
        min_trades=5,
        min_sharpe_ratio=0.5,
        max_drawdown=0.15,  # 15%
        min_win_rate=0.40,  # 40%
        min_profit_factor=1.2,
        max_consecutive_losses=3
    )
    return ValidationEnforcer(criteria)


class TestValidationEnforcerInitialization:
    """Test enforcer initialization"""
    
    def test_default_initialization(self):
        """Test enforcer with default criteria"""
        enforcer = ValidationEnforcer()
        
        assert enforcer.criteria.min_days == 30
        assert enforcer.criteria.min_trades == 20
        assert enforcer.criteria.min_sharpe_ratio == 1.0
        assert enforcer.criteria.max_drawdown == 0.10
        assert enforcer.criteria.min_win_rate == 0.50
        assert enforcer.criteria.min_profit_factor == 1.5
        assert enforcer.criteria.max_consecutive_losses == 5
    
    def test_custom_initialization(self, custom_enforcer):
        """Test enforcer with custom criteria"""
        assert custom_enforcer.criteria.min_days == 10
        assert custom_enforcer.criteria.min_trades == 5
        assert custom_enforcer.criteria.min_sharpe_ratio == 0.5
        assert custom_enforcer.criteria.max_drawdown == 0.15
        assert custom_enforcer.criteria.min_win_rate == 0.40


class TestIndividualCriteria:
    """Test individual validation criteria"""
    
    def test_minimum_days_fail(self, tracker, enforcer):
        """Test minimum days criterion - fail"""
        # No trades, so days_running = 0
        assert not enforcer.check_criterion(tracker, "minimum_days")
    
    def test_minimum_days_pass(self, tracker, custom_enforcer):
        """Test minimum days criterion - pass"""
        # Set start date to 11 days ago
        tracker.start_date = date.today() - timedelta(days=11)
        tracker._update_metadata()
        
        assert custom_enforcer.check_criterion(tracker, "minimum_days")
    
    def test_minimum_days_exact_threshold(self, tracker, custom_enforcer):
        """Test minimum days at exact threshold"""
        # Set start date to exactly 10 days ago
        tracker.start_date = date.today() - timedelta(days=10)
        tracker._update_metadata()
        
        assert custom_enforcer.check_criterion(tracker, "minimum_days")
    
    def test_minimum_trades_fail(self, tracker, enforcer):
        """Test minimum trades criterion - fail"""
        # No trades recorded
        assert not enforcer.check_criterion(tracker, "minimum_trades")
    
    def test_minimum_trades_pass(self, tracker, enforcer):
        """Test minimum trades criterion - pass"""
        # Record 20 trades
        entry_time = datetime.now()
        exit_time = entry_time + timedelta(hours=1)
        
        for i in range(20):
            tracker.record_trade(
                symbol=f"STOCK{i}",
                side="BUY",
                quantity=100,
                entry_price=100.0,
                exit_price=105.0,  # Profit
                entry_time=entry_time,
                exit_time=exit_time,
                commission=2.0
            )
        
        assert enforcer.check_criterion(tracker, "minimum_trades")
    
    def test_sharpe_ratio_fail(self, tracker, enforcer):
        """Test Sharpe ratio criterion - fail"""
        # No snapshots, so Sharpe = 0
        assert not enforcer.check_criterion(tracker, "sharpe_ratio")
    
    def test_sharpe_ratio_pass(self, tracker, custom_enforcer):
        """Test Sharpe ratio criterion - pass"""
        # Record snapshots with positive returns
        base_date = date.today() - timedelta(days=30)
        
        for i in range(30):
            snapshot_date = base_date + timedelta(days=i)
            portfolio_value = 100000 + i * 500  # Steady growth
            
            tracker.record_daily_snapshot(
                snapshot_date=snapshot_date,
                portfolio_value=portfolio_value,
                cash=50000,
                positions_value=portfolio_value - 50000,
                daily_pnl=500,
                realized_pnl=500,
                unrealized_pnl=0,
                trade_count=1
            )
        
        # Should have positive Sharpe ratio > 0.5
        assert custom_enforcer.check_criterion(tracker, "sharpe_ratio")
    
    def test_max_drawdown_fail(self, tracker, enforcer):
        """Test max drawdown criterion - fail"""
        # Record snapshots with large drawdown
        tracker.record_daily_snapshot(
            snapshot_date=date.today() - timedelta(days=2),
            portfolio_value=110000,  # Peak
            cash=55000,
            positions_value=55000,
            daily_pnl=10000,
            realized_pnl=10000,
            unrealized_pnl=0,
            trade_count=1
        )
        
        tracker.record_daily_snapshot(
            snapshot_date=date.today() - timedelta(days=1),
            portfolio_value=95000,  # Drawdown: 13.6%
            cash=47500,
            positions_value=47500,
            daily_pnl=-15000,
            realized_pnl=-15000,
            unrealized_pnl=0,
            trade_count=0
        )
        
        # Drawdown 13.6% > 10% limit
        assert not enforcer.check_criterion(tracker, "max_drawdown")
    
    def test_max_drawdown_pass(self, tracker, enforcer):
        """Test max drawdown criterion - pass"""
        # Record snapshots with small drawdown
        tracker.record_daily_snapshot(
            snapshot_date=date.today() - timedelta(days=2),
            portfolio_value=105000,  # Peak
            cash=52500,
            positions_value=52500,
            daily_pnl=5000,
            realized_pnl=5000,
            unrealized_pnl=0,
            trade_count=1
        )
        
        tracker.record_daily_snapshot(
            snapshot_date=date.today() - timedelta(days=1),
            portfolio_value=100000,  # Drawdown: 4.8%
            cash=50000,
            positions_value=50000,
            daily_pnl=-5000,
            realized_pnl=-5000,
            unrealized_pnl=0,
            trade_count=0
        )
        
        # Drawdown 4.8% < 10% limit
        assert enforcer.check_criterion(tracker, "max_drawdown")
    
    def test_win_rate_fail(self, tracker, enforcer):
        """Test win rate criterion - fail"""
        entry_time = datetime.now()
        exit_time = entry_time + timedelta(hours=1)
        
        # Record 2 winners, 3 losers = 40% win rate
        for i in range(2):
            tracker.record_trade(
                symbol=f"WIN{i}",
                side="BUY",
                quantity=100,
                entry_price=100.0,
                exit_price=105.0,  # Winner
                entry_time=entry_time,
                exit_time=exit_time,
                commission=2.0
            )
        
        for i in range(3):
            tracker.record_trade(
                symbol=f"LOSS{i}",
                side="BUY",
                quantity=100,
                entry_price=100.0,
                exit_price=95.0,  # Loser
                entry_time=entry_time,
                exit_time=exit_time,
                commission=2.0
            )
        
        # 40% < 50% requirement
        assert not enforcer.check_criterion(tracker, "win_rate")
    
    def test_win_rate_pass(self, tracker, enforcer):
        """Test win rate criterion - pass"""
        entry_time = datetime.now()
        exit_time = entry_time + timedelta(hours=1)
        
        # Record 3 winners, 2 losers = 60% win rate
        for i in range(3):
            tracker.record_trade(
                symbol=f"WIN{i}",
                side="BUY",
                quantity=100,
                entry_price=100.0,
                exit_price=105.0,  # Winner
                entry_time=entry_time,
                exit_time=exit_time,
                commission=2.0
            )
        
        for i in range(2):
            tracker.record_trade(
                symbol=f"LOSS{i}",
                side="BUY",
                quantity=100,
                entry_price=100.0,
                exit_price=95.0,  # Loser
                entry_time=entry_time,
                exit_time=exit_time,
                commission=2.0
            )
        
        # 60% >= 50% requirement
        assert enforcer.check_criterion(tracker, "win_rate")
    
    def test_profit_factor_fail(self, tracker, enforcer):
        """Test profit factor criterion - fail"""
        entry_time = datetime.now()
        exit_time = entry_time + timedelta(hours=1)
        
        # Gross profit: $500, Gross loss: $500, PF = 1.0
        tracker.record_trade(
            symbol="WIN",
            side="BUY",
            quantity=100,
            entry_price=100.0,
            exit_price=107.0,  # +$700 gross, -$2 comm = $698 net
            entry_time=entry_time,
            exit_time=exit_time,
            commission=2.0
        )
        
        tracker.record_trade(
            symbol="LOSS",
            side="BUY",
            quantity=100,
            entry_price=100.0,
            exit_price=93.0,  # -$700 gross, -$2 comm = -$702 net
            entry_time=entry_time,
            exit_time=exit_time,
            commission=2.0
        )
        
        # PF = 698/702 ≈ 0.99 < 1.5 requirement
        assert not enforcer.check_criterion(tracker, "profit_factor")
    
    def test_profit_factor_pass(self, tracker, enforcer):
        """Test profit factor criterion - pass"""
        entry_time = datetime.now()
        exit_time = entry_time + timedelta(hours=1)
        
        # Gross profit: $1500, Gross loss: $500, PF = 3.0
        tracker.record_trade(
            symbol="WIN",
            side="BUY",
            quantity=100,
            entry_price=100.0,
            exit_price=117.0,  # +$1700 gross, -$2 comm = $1698 net
            entry_time=entry_time,
            exit_time=exit_time,
            commission=2.0
        )
        
        tracker.record_trade(
            symbol="LOSS",
            side="BUY",
            quantity=100,
            entry_price=100.0,
            exit_price=95.0,  # -$500 gross, -$2 comm = -$502 net
            entry_time=entry_time,
            exit_time=exit_time,
            commission=2.0
        )
        
        # PF = 1698/502 ≈ 3.38 > 1.5 requirement
        assert enforcer.check_criterion(tracker, "profit_factor")
    
    def test_consecutive_losses_fail(self, tracker, enforcer):
        """Test consecutive losses criterion - fail"""
        entry_time = datetime.now()
        exit_time = entry_time + timedelta(hours=1)
        
        # Record 6 consecutive losses
        for i in range(6):
            tracker.record_trade(
                symbol=f"LOSS{i}",
                side="BUY",
                quantity=100,
                entry_price=100.0,
                exit_price=95.0,  # Loser
                entry_time=entry_time,
                exit_time=exit_time,
                commission=2.0
            )
        
        # 6 > 5 max
        assert not enforcer.check_criterion(tracker, "consecutive_losses")
    
    def test_consecutive_losses_pass(self, tracker, enforcer):
        """Test consecutive losses criterion - pass"""
        entry_time = datetime.now()
        exit_time = entry_time + timedelta(hours=1)
        
        # Record 3 losses, 1 win (resets counter), 2 losses
        for i in range(3):
            tracker.record_trade(
                symbol=f"LOSS{i}",
                side="BUY",
                quantity=100,
                entry_price=100.0,
                exit_price=95.0,  # Loser
                entry_time=entry_time,
                exit_time=exit_time,
                commission=2.0
            )
        
        # Winner resets counter
        tracker.record_trade(
            symbol="WIN",
            side="BUY",
            quantity=100,
            entry_price=100.0,
            exit_price=105.0,
            entry_time=entry_time,
            exit_time=exit_time,
            commission=2.0
        )
        
        for i in range(2):
            tracker.record_trade(
                symbol=f"LOSS2_{i}",
                side="BUY",
                quantity=100,
                entry_price=100.0,
                exit_price=95.0,
                entry_time=entry_time,
                exit_time=exit_time,
                commission=2.0
            )
        
        # Max streak = 3, then reset, current = 2 (all < 5)
        assert enforcer.check_criterion(tracker, "consecutive_losses")
    
    def test_invalid_criterion(self, tracker, enforcer):
        """Test checking invalid criterion raises ValueError"""
        with pytest.raises(ValueError, match="Invalid criterion"):
            enforcer.check_criterion(tracker, "invalid_criterion")


class TestCombinedValidation:
    """Test combined validation logic"""
    
    def test_empty_tracker_fails(self, tracker, enforcer):
        """Test validation fails with no data"""
        assert not enforcer.can_validate(tracker)
    
    def test_all_criteria_pass(self, tracker, custom_enforcer):
        """Test validation passes when all criteria met"""
        # Set up tracker to pass all criteria
        tracker.start_date = date.today() - timedelta(days=15)
        
        entry_time = datetime.now()
        exit_time = entry_time + timedelta(hours=1)
        
        # Record 10 winners, 2 losers = 83% win rate
        for i in range(10):
            tracker.record_trade(
                symbol=f"WIN{i}",
                side="BUY",
                quantity=100,
                entry_price=100.0,
                exit_price=107.0,  # +$698 net
                entry_time=entry_time,
                exit_time=exit_time,
                commission=2.0
            )
        
        for i in range(2):
            tracker.record_trade(
                symbol=f"LOSS{i}",
                side="BUY",
                quantity=100,
                entry_price=100.0,
                exit_price=97.0,  # -$302 net
                entry_time=entry_time,
                exit_time=exit_time,
                commission=2.0
            )
        
        # Record snapshots with positive returns
        base_date = date.today() - timedelta(days=15)
        for i in range(15):
            snapshot_date = base_date + timedelta(days=i)
            portfolio_value = 100000 + i * 400
            
            tracker.record_daily_snapshot(
                snapshot_date=snapshot_date,
                portfolio_value=portfolio_value,
                cash=50000,
                positions_value=portfolio_value - 50000,
                daily_pnl=400,
                realized_pnl=400,
                unrealized_pnl=0,
                trade_count=1
            )
        
        # Should pass all custom criteria
        assert custom_enforcer.can_validate(tracker)
    
    def test_one_criterion_fails(self, tracker, custom_enforcer):
        """Test validation fails if even one criterion not met"""
        # Meet all criteria except days
        tracker.start_date = date.today() - timedelta(days=5)  # Only 5 days, need 10
        
        entry_time = datetime.now()
        exit_time = entry_time + timedelta(hours=1)
        
        # Record enough trades with good performance
        for i in range(10):
            tracker.record_trade(
                symbol=f"WIN{i}",
                side="BUY",
                quantity=100,
                entry_price=100.0,
                exit_price=107.0,
                entry_time=entry_time,
                exit_time=exit_time,
                commission=2.0
            )
        
        # Should fail due to insufficient days
        assert not custom_enforcer.can_validate(tracker)


class TestValidationReport:
    """Test validation report generation"""
    
    def test_report_with_no_data(self, tracker, enforcer):
        """Test report generation with empty tracker"""
        report = enforcer.get_validation_report(tracker)
        
        assert report.strategy_name == "test_strategy"
        assert report.report_date == date.today()
        assert not report.overall_passed
        assert len(report.checks) == 7
        assert report.days_remaining == 30
        assert report.trades_remaining == 20
    
    def test_report_all_pass(self, tracker, custom_enforcer):
        """Test report when all criteria pass"""
        # Set up passing scenario
        tracker.start_date = date.today() - timedelta(days=15)
        
        entry_time = datetime.now()
        exit_time = entry_time + timedelta(hours=1)
        
        for i in range(10):
            tracker.record_trade(
                symbol=f"WIN{i}",
                side="BUY",
                quantity=100,
                entry_price=100.0,
                exit_price=107.0,
                entry_time=entry_time,
                exit_time=exit_time,
                commission=2.0
            )
        
        for i in range(2):
            tracker.record_trade(
                symbol=f"LOSS{i}",
                side="BUY",
                quantity=100,
                entry_price=100.0,
                exit_price=97.0,
                entry_time=entry_time,
                exit_time=exit_time,
                commission=2.0
            )
        
        base_date = date.today() - timedelta(days=15)
        for i in range(15):
            snapshot_date = base_date + timedelta(days=i)
            portfolio_value = 100000 + i * 400
            
            tracker.record_daily_snapshot(
                snapshot_date=snapshot_date,
                portfolio_value=portfolio_value,
                cash=50000,
                positions_value=portfolio_value - 50000,
                daily_pnl=400,
                realized_pnl=400,
                unrealized_pnl=0,
                trade_count=1
            )
        
        report = custom_enforcer.get_validation_report(tracker)
        
        assert report.overall_passed
        assert all(check.passed for check in report.checks)
        assert report.days_remaining == 0
        assert report.trades_remaining == 0
    
    def test_report_partial_pass(self, tracker, enforcer):
        """Test report with some criteria passing"""
        entry_time = datetime.now()
        exit_time = entry_time + timedelta(hours=1)
        
        # Record 25 trades (passes trades requirement)
        for i in range(15):
            tracker.record_trade(
                symbol=f"WIN{i}",
                side="BUY",
                quantity=100,
                entry_price=100.0,
                exit_price=105.0,
                entry_time=entry_time,
                exit_time=exit_time,
                commission=2.0
            )
        
        for i in range(10):
            tracker.record_trade(
                symbol=f"LOSS{i}",
                side="BUY",
                quantity=100,
                entry_price=100.0,
                exit_price=95.0,
                entry_time=entry_time,
                exit_time=exit_time,
                commission=2.0
            )
        
        report = enforcer.get_validation_report(tracker)
        
        assert not report.overall_passed
        
        # Check individual criteria
        trades_check = next(c for c in report.checks if c.criterion == "minimum_trades")
        assert trades_check.passed  # 25 >= 20
        
        days_check = next(c for c in report.checks if c.criterion == "minimum_days")
        assert not days_check.passed  # 0 < 30
    
    def test_report_summary_format(self, tracker, enforcer):
        """Test report summary string formatting"""
        report = enforcer.get_validation_report(tracker)
        summary = report.summary()
        
        assert "VALIDATION REPORT" in summary
        assert "test_strategy" in summary
        assert "FAILED" in summary
        assert "VALIDATION CRITERIA:" in summary
        assert "PROGRESS:" in summary
        assert "Days remaining:" in summary
    
    def test_report_to_dict(self, tracker, enforcer):
        """Test report conversion to dictionary"""
        report = enforcer.get_validation_report(tracker)
        report_dict = report.to_dict()
        
        assert report_dict["strategy_name"] == "test_strategy"
        assert isinstance(report_dict["report_date"], str)
        assert report_dict["overall_passed"] is False
        assert len(report_dict["checks"]) == 7
        assert "days_remaining" in report_dict
        assert "trades_remaining" in report_dict
    
    def test_validation_check_str(self):
        """Test ValidationCheck string representation"""
        check_pass = ValidationCheck(
            criterion="test",
            passed=True,
            current_value=10,
            required_value=5,
            message="Test passed"
        )
        
        check_fail = ValidationCheck(
            criterion="test",
            passed=False,
            current_value=3,
            required_value=5,
            message="Test failed"
        )
        
        assert "✓ PASS" in str(check_pass)
        assert "✗ FAIL" in str(check_fail)


class TestFailedCriteriaTracking:
    """Test tracking of failed criteria"""
    
    def test_get_failed_criteria_all_fail(self, tracker, enforcer):
        """Test getting failed criteria when all fail"""
        failed = enforcer.get_failed_criteria(tracker)
        
        # Empty tracker fails 5 criteria (days, trades, sharpe, win_rate, profit_factor)
        # max_drawdown passes (0.0 <= 0.10) and consecutive_losses passes (0 <= 5)
        assert len(failed) == 5
        assert "minimum_days" in failed
        assert "minimum_trades" in failed
        assert "sharpe_ratio" in failed
        # max_drawdown NOT in failed - 0% drawdown passes
        assert "win_rate" in failed
        assert "profit_factor" in failed
        # consecutive_losses NOT in failed - 0 losses passes
    
    def test_get_failed_criteria_some_fail(self, tracker, enforcer):
        """Test getting failed criteria when some pass"""
        entry_time = datetime.now()
        exit_time = entry_time + timedelta(hours=1)
        
        # Record 25 good trades
        for i in range(25):
            tracker.record_trade(
                symbol=f"WIN{i}",
                side="BUY",
                quantity=100,
                entry_price=100.0,
                exit_price=105.0,
                entry_time=entry_time,
                exit_time=exit_time,
                commission=2.0
            )
        
        failed = enforcer.get_failed_criteria(tracker)
        
        # Should pass: minimum_trades, win_rate, profit_factor, consecutive_losses
        # Should fail: minimum_days, sharpe_ratio (no snapshots), max_drawdown
        assert "minimum_trades" not in failed
        assert "win_rate" not in failed
        assert "minimum_days" in failed
    
    def test_get_failed_criteria_none_fail(self, tracker, custom_enforcer):
        """Test getting failed criteria when all pass"""
        # Set up passing scenario
        tracker.start_date = date.today() - timedelta(days=15)
        
        entry_time = datetime.now()
        exit_time = entry_time + timedelta(hours=1)
        
        for i in range(10):
            tracker.record_trade(
                symbol=f"WIN{i}",
                side="BUY",
                quantity=100,
                entry_price=100.0,
                exit_price=107.0,
                entry_time=entry_time,
                exit_time=exit_time,
                commission=2.0
            )
        
        for i in range(2):
            tracker.record_trade(
                symbol=f"LOSS{i}",
                side="BUY",
                quantity=100,
                entry_price=100.0,
                exit_price=97.0,
                entry_time=entry_time,
                exit_time=exit_time,
                commission=2.0
            )
        
        base_date = date.today() - timedelta(days=15)
        for i in range(15):
            snapshot_date = base_date + timedelta(days=i)
            portfolio_value = 100000 + i * 400
            
            tracker.record_daily_snapshot(
                snapshot_date=snapshot_date,
                portfolio_value=portfolio_value,
                cash=50000,
                positions_value=portfolio_value - 50000,
                daily_pnl=400,
                realized_pnl=400,
                unrealized_pnl=0,
                trade_count=1
            )
        
        failed = custom_enforcer.get_failed_criteria(tracker)
        
        assert len(failed) == 0


class TestEdgeCases:
    """Test edge cases and boundary conditions"""
    
    def test_exactly_at_threshold_days(self, tracker, enforcer):
        """Test exactly at minimum days threshold"""
        tracker.start_date = date.today() - timedelta(days=30)
        tracker._update_metadata()
        
        assert enforcer.check_criterion(tracker, "minimum_days")
    
    def test_exactly_at_threshold_trades(self, tracker, enforcer):
        """Test exactly at minimum trades threshold"""
        entry_time = datetime.now()
        exit_time = entry_time + timedelta(hours=1)
        
        # Record exactly 20 trades
        for i in range(20):
            tracker.record_trade(
                symbol=f"STOCK{i}",
                side="BUY",
                quantity=100,
                entry_price=100.0,
                exit_price=105.0,
                entry_time=entry_time,
                exit_time=exit_time,
                commission=2.0
            )
        
        assert enforcer.check_criterion(tracker, "minimum_trades")
    
    def test_exactly_at_threshold_drawdown(self, tracker, enforcer):
        """Test exactly at max drawdown threshold"""
        # Record snapshots with exactly 10% drawdown
        tracker.record_daily_snapshot(
            snapshot_date=date.today() - timedelta(days=2),
            portfolio_value=100000,  # Peak
            cash=50000,
            positions_value=50000,
            daily_pnl=0,
            realized_pnl=0,
            unrealized_pnl=0,
            trade_count=0
        )
        
        tracker.record_daily_snapshot(
            snapshot_date=date.today() - timedelta(days=1),
            portfolio_value=90000,  # Exactly 10% down
            cash=45000,
            positions_value=45000,
            daily_pnl=-10000,
            realized_pnl=-10000,
            unrealized_pnl=0,
            trade_count=0
        )
        
        # Should pass (10% <= 10% limit)
        assert enforcer.check_criterion(tracker, "max_drawdown")
    
    def test_zero_sharpe_with_flat_returns(self, tracker, enforcer):
        """Test Sharpe ratio with flat returns (zero volatility)"""
        base_date = date.today() - timedelta(days=10)
        
        # Record snapshots with no change (flat returns)
        for i in range(10):
            snapshot_date = base_date + timedelta(days=i)
            
            tracker.record_daily_snapshot(
                snapshot_date=snapshot_date,
                portfolio_value=100000,  # No change
                cash=50000,
                positions_value=50000,
                daily_pnl=0,
                realized_pnl=0,
                unrealized_pnl=0,
                trade_count=0
            )
        
        # Sharpe should be 0 (zero volatility case)
        sharpe = tracker.calculate_sharpe_ratio()
        assert sharpe == 0.0
        assert not enforcer.check_criterion(tracker, "sharpe_ratio")
    
    def test_only_winners_profit_factor(self, tracker, enforcer):
        """Test profit factor with only winning trades"""
        entry_time = datetime.now()
        exit_time = entry_time + timedelta(hours=1)
        
        # Record only winners
        for i in range(5):
            tracker.record_trade(
                symbol=f"WIN{i}",
                side="BUY",
                quantity=100,
                entry_price=100.0,
                exit_price=105.0,
                entry_time=entry_time,
                exit_time=exit_time,
                commission=2.0
            )
        
        # Profit factor should be total profit (no losses to divide by)
        pf = tracker.calculate_profit_factor()
        assert pf > 0
