"""
Tests for risk management module
"""

import pytest
from datetime import datetime, timedelta
from backtesting.risk_manager import RiskManager
from backtesting.backtest_engine import BacktestPosition


@pytest.fixture
def risk_manager():
    """Default risk manager"""
    return RiskManager(
        max_positions=5,
        max_drawdown_pct=0.20,
        daily_loss_limit=0.05,
        max_position_pct=0.25,
        max_leverage=1.0
    )


@pytest.fixture
def sample_positions():
    """Sample positions for testing"""
    return {
        'AAPL': BacktestPosition('AAPL', 100, 150.0, 155.0, 500.0, 0.0),
        'GOOGL': BacktestPosition('GOOGL', 50, 100.0, 105.0, 250.0, 0.0),
        'MSFT': BacktestPosition('MSFT', 75, 200.0, 195.0, -375.0, 0.0)
    }


class TestRiskManager:
    """Test suite for RiskManager"""
    
    def test_initialization(self):
        """Test risk manager initialization"""
        rm = RiskManager(
            max_positions=10,
            max_drawdown_pct=0.15,
            daily_loss_limit=0.03,
            max_position_pct=0.20,
            max_leverage=2.0
        )
        
        assert rm.max_positions == 10
        assert rm.max_drawdown_pct == 0.15
        assert rm.daily_loss_limit == 0.03
        assert rm.max_position_pct == 0.20
        assert rm.max_leverage == 2.0
        
        # Check initial state
        assert rm.peak_equity == 0.0
        assert rm.daily_start_equity == 0.0
        assert rm.drawdown_breached is False
        assert rm.daily_limit_breached is False
    
    def test_update_equity(self, risk_manager):
        """Test equity update"""
        current_date = datetime(2024, 1, 1)
        
        # Initial update
        risk_manager.update(100000.0, current_date)
        assert risk_manager.peak_equity == 100000.0
        assert risk_manager.daily_start_equity == 100000.0
        
        # Update with higher equity
        risk_manager.update(105000.0, current_date)
        assert risk_manager.peak_equity == 105000.0
        
        # Update with lower equity (still above start)
        risk_manager.update(102000.0, current_date)
        assert risk_manager.peak_equity == 105000.0  # Peak unchanged
    
    def test_drawdown_tracking(self, risk_manager):
        """Test drawdown calculation and tracking"""
        current_date = datetime(2024, 1, 1)
        
        # Set peak
        risk_manager.update(100000.0, current_date)
        assert risk_manager.drawdown_breached is False
        
        # Small drawdown (10%) - should not breach
        risk_manager.update(90000.0, current_date)
        assert risk_manager.drawdown_breached is False
        
        # Large drawdown (25%) - should breach 20% limit
        risk_manager.update(75000.0, current_date)
        assert risk_manager.drawdown_breached is True
    
    def test_daily_loss_tracking(self, risk_manager):
        """Test daily loss limit tracking"""
        day1 = datetime(2024, 1, 1)
        day2 = datetime(2024, 1, 2)
        
        # Start day 1
        risk_manager.update(100000.0, day1)
        assert risk_manager.daily_limit_breached is False
        
        # Small loss (3%) - should not breach 5% limit
        risk_manager.update(97000.0, day1)
        assert risk_manager.daily_limit_breached is False
        
        # Large loss (7%) - should breach 5% limit
        risk_manager.update(93000.0, day1)
        assert risk_manager.daily_limit_breached is True
        
        # New day - should reset daily tracking
        risk_manager.update(93000.0, day2)
        assert risk_manager.daily_limit_breached is False
        assert risk_manager.daily_start_equity == 93000.0
    
    def test_can_open_position_max_positions(self, risk_manager, sample_positions):
        """Test position count limit"""
        equity = 100000.0
        
        # With 3 positions and limit of 5, should be allowed
        can_open, reason = risk_manager.can_open_position('TSLA', equity, sample_positions)
        assert can_open is True
        
        # Add more positions to reach limit
        for i in range(3):
            sample_positions[f'SYM{i}'] = BacktestPosition(
                f'SYM{i}', 100, 100.0, 100.0, 0.0, 0.0
            )
        
        # Now at limit (6 positions, limit is 5), should not be allowed
        can_open, reason = risk_manager.can_open_position('NEW', equity, sample_positions)
        assert can_open is False
        assert "maximum number of positions" in reason.lower()
    
    def test_can_open_position_existing_symbol(self, risk_manager, sample_positions):
        """Test cannot open duplicate position"""
        equity = 100000.0
        
        # Try to open position in symbol we already have
        can_open, reason = risk_manager.can_open_position('AAPL', equity, sample_positions)
        assert can_open is False
        assert "already have a position" in reason.lower()
    
    def test_can_open_position_drawdown_breached(self, risk_manager):
        """Test cannot open position when drawdown limit breached"""
        current_date = datetime(2024, 1, 1)
        
        # Set peak and breach drawdown
        risk_manager.update(100000.0, current_date)
        risk_manager.update(75000.0, current_date)  # 25% drawdown
        
        # Should not allow new positions
        can_open, reason = risk_manager.can_open_position('AAPL', 75000.0, {})
        assert can_open is False
        assert "drawdown limit" in reason.lower()
    
    def test_can_open_position_daily_limit_breached(self, risk_manager):
        """Test cannot open position when daily loss limit breached"""
        current_date = datetime(2024, 1, 1)
        
        # Set start of day and breach daily limit
        risk_manager.update(100000.0, current_date)
        risk_manager.update(93000.0, current_date)  # 7% loss
        
        # Should not allow new positions
        can_open, reason = risk_manager.can_open_position('AAPL', 93000.0, {})
        assert can_open is False
        assert "daily loss limit" in reason.lower()
    
    def test_can_increase_position(self, risk_manager, sample_positions):
        """Test position increase limits"""
        equity = 100000.0
        
        # AAPL position value: 100 shares * $155 = $15,500 (15.5% of equity)
        # Can increase to max 25% ($25,000), so $9,500 more allowed
        can_increase, reason = risk_manager.can_increase_position(
            'AAPL',
            5000.0,  # Add $5,000 worth (within limit)
            equity,
            sample_positions
        )
        assert can_increase is True
        
        # Try to add too much (would exceed 25% limit)
        can_increase, reason = risk_manager.can_increase_position(
            'AAPL',
            15000.0,  # Would bring to $30,500 (30.5%)
            equity,
            sample_positions
        )
        assert can_increase is False
        assert "position size limit" in reason.lower()
    
    def test_can_increase_position_risk_breached(self, risk_manager):
        """Test cannot increase when risk limits breached"""
        current_date = datetime(2024, 1, 1)
        
        # Breach drawdown limit
        risk_manager.update(100000.0, current_date)
        risk_manager.update(75000.0, current_date)
        
        positions = {
            'AAPL': BacktestPosition('AAPL', 100, 150.0, 155.0, 500.0, 0.0)
        }
        
        can_increase, reason = risk_manager.can_increase_position(
            'AAPL',
            1000.0,
            75000.0,
            positions
        )
        assert can_increase is False
        assert "risk limit" in reason.lower()
    
    def test_check_leverage(self, risk_manager):
        """Test leverage checking"""
        equity = 100000.0
        
        # Total position value below equity (no leverage)
        ok, reason = risk_manager.check_leverage(90000.0, equity)
        assert ok is True
        
        # Total position value equal to equity (1.0x leverage)
        ok, reason = risk_manager.check_leverage(100000.0, equity)
        assert ok is True
        
        # Total position value exceeds equity (>1.0x leverage)
        ok, reason = risk_manager.check_leverage(120000.0, equity)
        assert ok is False
        assert "leverage" in reason.lower()
    
    def test_check_leverage_with_higher_limit(self):
        """Test leverage checking with higher limit"""
        rm = RiskManager(max_leverage=2.0)
        equity = 100000.0
        
        # 1.5x leverage should be ok with 2.0x limit
        ok, reason = rm.check_leverage(150000.0, equity)
        assert ok is True
        
        # 2.5x leverage should exceed 2.0x limit
        ok, reason = rm.check_leverage(250000.0, equity)
        assert ok is False
    
    def test_should_reduce_positions_drawdown(self, risk_manager):
        """Test position reduction trigger from drawdown"""
        current_date = datetime(2024, 1, 1)
        
        # Set peak
        risk_manager.update(100000.0, current_date)
        
        # Small drawdown - should not reduce
        risk_manager.update(95000.0, current_date)  # 5% drawdown
        assert risk_manager.should_reduce_positions(95000.0) is False
        
        # Approaching limit (18% of 20% limit = 90%) - should reduce
        risk_manager.update(82000.0, current_date)  # 18% drawdown
        assert risk_manager.should_reduce_positions(82000.0) is True
    
    def test_should_reduce_positions_daily_loss(self, risk_manager):
        """Test position reduction trigger from daily loss"""
        current_date = datetime(2024, 1, 1)
        
        # Set start of day
        risk_manager.update(100000.0, current_date)
        
        # Small loss - should not reduce
        risk_manager.update(98000.0, current_date)  # 2% loss
        assert risk_manager.should_reduce_positions(98000.0) is False
        
        # Approaching daily limit (4.5% of 5% limit = 90%) - should reduce
        risk_manager.update(95500.0, current_date)  # 4.5% loss
        assert risk_manager.should_reduce_positions(95500.0) is True
    
    def test_reset(self, risk_manager):
        """Test risk manager reset"""
        current_date = datetime(2024, 1, 1)
        
        # Set some state
        risk_manager.update(100000.0, current_date)
        risk_manager.update(75000.0, current_date)  # Breach drawdown
        
        assert risk_manager.peak_equity == 100000.0
        assert risk_manager.drawdown_breached is True
        
        # Reset
        risk_manager.reset()
        
        assert risk_manager.peak_equity == 0.0
        assert risk_manager.daily_start_equity == 0.0
        assert risk_manager.drawdown_breached is False
        assert risk_manager.daily_limit_breached is False
    
    def test_get_status(self, risk_manager):
        """Test status reporting"""
        current_date = datetime(2024, 1, 1)
        
        # Update with some equity
        risk_manager.update(100000.0, current_date)
        risk_manager.update(90000.0, current_date)
        
        status = risk_manager.get_status()
        
        # Check status contains expected keys
        assert 'peak_equity' in status
        assert 'current_drawdown_pct' in status
        assert 'daily_loss_pct' in status
        assert 'drawdown_breached' in status
        assert 'daily_limit_breached' in status
        
        # Check values
        assert status['peak_equity'] == 100000.0
        assert status['current_drawdown_pct'] == 0.10  # 10% drawdown
        assert status['drawdown_breached'] is False
    
    def test_multiple_day_tracking(self, risk_manager):
        """Test tracking across multiple days"""
        day1 = datetime(2024, 1, 1)
        day2 = datetime(2024, 1, 2)
        day3 = datetime(2024, 1, 3)
        
        # Day 1: Start at 100k, lose to 95k
        risk_manager.update(100000.0, day1)
        risk_manager.update(95000.0, day1)
        assert risk_manager.daily_start_equity == 100000.0
        
        # Day 2: Start at 95k (carry over), gain to 98k
        risk_manager.update(95000.0, day2)
        assert risk_manager.daily_start_equity == 95000.0
        risk_manager.update(98000.0, day2)
        
        # Day 3: Start at 98k, lose to 92k (6.12% loss - breach 5% limit)
        risk_manager.update(98000.0, day3)
        assert risk_manager.daily_start_equity == 98000.0
        risk_manager.update(92000.0, day3)
        assert risk_manager.daily_limit_breached is True
    
    def test_peak_equity_progression(self, risk_manager):
        """Test peak equity only increases"""
        current_date = datetime(2024, 1, 1)
        
        risk_manager.update(100000.0, current_date)
        assert risk_manager.peak_equity == 100000.0
        
        risk_manager.update(110000.0, current_date)
        assert risk_manager.peak_equity == 110000.0
        
        risk_manager.update(105000.0, current_date)
        assert risk_manager.peak_equity == 110000.0  # Unchanged
        
        risk_manager.update(95000.0, current_date)
        assert risk_manager.peak_equity == 110000.0  # Still unchanged
        
        risk_manager.update(120000.0, current_date)
        assert risk_manager.peak_equity == 120000.0  # New peak


class TestRiskManagerEdgeCases:
    """Test edge cases and boundary conditions"""
    
    def test_zero_equity(self):
        """Test handling of zero equity"""
        rm = RiskManager()
        current_date = datetime(2024, 1, 1)
        
        # Update with zero should not crash
        rm.update(0.0, current_date)
        assert rm.peak_equity == 0.0
        
        status = rm.get_status()
        assert status['current_drawdown_pct'] == 0.0
    
    def test_negative_equity(self):
        """Test handling of negative equity (bankruptcy)"""
        rm = RiskManager()
        current_date = datetime(2024, 1, 1)
        
        rm.update(100000.0, current_date)
        rm.update(-10000.0, current_date)
        
        # Drawdown should be 110% (lost all capital plus margin)
        status = rm.get_status()
        assert status['current_drawdown_pct'] > 1.0
        assert rm.drawdown_breached is True
    
    def test_exact_limit_values(self):
        """Test behavior at exact limit boundaries"""
        rm = RiskManager(max_drawdown_pct=0.20, daily_loss_limit=0.05)
        current_date = datetime(2024, 1, 1)
        
        # Exactly at drawdown limit
        rm.update(100000.0, current_date)
        rm.update(80000.0, current_date)  # Exactly 20%
        assert rm.drawdown_breached is False  # Should not breach at exactly limit
        
        # Just over the limit
        rm.reset()
        rm.update(100000.0, current_date)
        rm.update(79999.0, current_date)  # Just over 20%
        assert rm.drawdown_breached is True
    
    def test_empty_positions(self):
        """Test with empty positions dict"""
        rm = RiskManager()
        
        can_open, reason = rm.can_open_position('AAPL', 100000.0, {})
        assert can_open is True


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
