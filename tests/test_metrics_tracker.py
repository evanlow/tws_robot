"""
Tests for Paper Trading Metrics Tracker

Tests PaperMetricsTracker class functionality including:
- Trade recording and retrieval
- Daily snapshot storage
- Metric calculations (Sharpe, win rate, drawdown, profit factor)
- Database persistence and recovery
- Edge cases and error handling

Author: TWS Robot Development Team
Date: November 23, 2025
Sprint 2 Task 2
"""

import pytest
import tempfile
import os
from datetime import datetime, date, timedelta
from pathlib import Path

from strategy.metrics_tracker import (
    PaperMetricsTracker, Trade, DailySnapshot, MetricsSnapshot
)


@pytest.fixture
def temp_db():
    """Create temporary database for testing"""
    fd, path = tempfile.mkstemp(suffix='.db')
    os.close(fd)
    yield path
    # Cleanup
    if os.path.exists(path):
        os.unlink(path)


@pytest.fixture
def tracker(temp_db):
    """Create metrics tracker instance"""
    return PaperMetricsTracker(temp_db, "test_strategy", initial_capital=100000.0)


class TestPaperMetricsTrackerInitialization:
    """Test tracker initialization and setup"""
    
    def test_initialization(self, temp_db):
        """Test basic initialization"""
        tracker = PaperMetricsTracker(temp_db, "test_strategy", initial_capital=50000.0)
        
        assert tracker.strategy_name == "test_strategy"
        assert tracker.initial_capital == 50000.0
        assert tracker.start_date == date.today()
        assert tracker._peak_value == 50000.0
        assert tracker._max_drawdown == 0.0
        assert tracker._consecutive_losses == 0
    
    def test_database_creation(self, temp_db):
        """Test database tables are created"""
        tracker = PaperMetricsTracker(temp_db, "test_strategy")
        
        # Verify database file exists
        assert os.path.exists(temp_db)
        
        # Verify tables exist by querying them
        import sqlite3
        conn = sqlite3.connect(temp_db)
        cursor = conn.cursor()
        
        # Check trades table
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='strategy_trades'")
        assert cursor.fetchone() is not None
        
        # Check snapshots table
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='strategy_snapshots'")
        assert cursor.fetchone() is not None
        
        # Check metadata table
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='strategy_metadata'")
        assert cursor.fetchone() is not None
        
        conn.close()
    
    def test_persistence_across_instances(self, temp_db):
        """Test data persists across tracker instances"""
        # Create first instance and record trade
        tracker1 = PaperMetricsTracker(temp_db, "test_strategy", initial_capital=100000.0)
        trade = tracker1.record_trade(
            symbol="AAPL",
            side="BUY",
            quantity=100,
            entry_price=150.0,
            exit_price=155.0,
            entry_time=datetime(2025, 1, 1, 10, 0),
            exit_time=datetime(2025, 1, 1, 15, 0),
            commission=2.0
        )
        
        # Create second instance - should load existing data
        tracker2 = PaperMetricsTracker(temp_db, "test_strategy")
        
        assert tracker2.initial_capital == 100000.0
        assert len(tracker2.get_all_trades()) == 1
        assert tracker2.get_all_trades()[0].symbol == "AAPL"


class TestTradeRecording:
    """Test trade recording functionality"""
    
    def test_record_buy_trade_profit(self, tracker):
        """Test recording profitable buy trade"""
        trade = tracker.record_trade(
            symbol="AAPL",
            side="BUY",
            quantity=100,
            entry_price=150.0,
            exit_price=155.0,
            entry_time=datetime(2025, 1, 1, 10, 0),
            exit_time=datetime(2025, 1, 1, 15, 0),
            commission=2.0
        )
        
        assert trade.symbol == "AAPL"
        assert trade.side == "BUY"
        assert trade.quantity == 100
        assert trade.entry_price == 150.0
        assert trade.exit_price == 155.0
        assert trade.pnl == 500.0  # (155 - 150) * 100
        assert trade.net_pnl == 498.0  # 500 - 2
        assert trade.is_winner is True
    
    def test_record_buy_trade_loss(self, tracker):
        """Test recording losing buy trade"""
        trade = tracker.record_trade(
            symbol="MSFT",
            side="BUY",
            quantity=50,
            entry_price=200.0,
            exit_price=195.0,
            entry_time=datetime(2025, 1, 2, 10, 0),
            exit_time=datetime(2025, 1, 2, 15, 0),
            commission=1.5
        )
        
        assert trade.pnl == -250.0  # (195 - 200) * 50
        assert trade.net_pnl == -251.5  # -250 - 1.5
        assert trade.is_winner is False
    
    def test_record_sell_trade_profit(self, tracker):
        """Test recording profitable short trade"""
        trade = tracker.record_trade(
            symbol="TSLA",
            side="SELL",
            quantity=20,
            entry_price=800.0,
            exit_price=750.0,
            entry_time=datetime(2025, 1, 3, 10, 0),
            exit_time=datetime(2025, 1, 3, 15, 0),
            commission=3.0
        )
        
        assert trade.pnl == 1000.0  # (800 - 750) * 20
        assert trade.net_pnl == 997.0
        assert trade.is_winner is True
    
    def test_record_sell_trade_loss(self, tracker):
        """Test recording losing short trade"""
        trade = tracker.record_trade(
            symbol="GOOGL",
            side="SELL",
            quantity=10,
            entry_price=100.0,
            exit_price=110.0,
            entry_time=datetime(2025, 1, 4, 10, 0),
            exit_time=datetime(2025, 1, 4, 15, 0),
            commission=1.0
        )
        
        assert trade.pnl == -100.0  # (100 - 110) * 10
        assert trade.net_pnl == -101.0
        assert trade.is_winner is False
    
    def test_consecutive_losses_tracking(self, tracker):
        """Test consecutive losses counter"""
        # Win - resets counter
        tracker.record_trade("AAPL", "BUY", 100, 150.0, 155.0,
                           datetime(2025, 1, 1, 10, 0), datetime(2025, 1, 1, 15, 0))
        assert tracker._consecutive_losses == 0
        
        # Loss 1
        tracker.record_trade("MSFT", "BUY", 50, 200.0, 195.0,
                           datetime(2025, 1, 2, 10, 0), datetime(2025, 1, 2, 15, 0))
        assert tracker._consecutive_losses == 1
        
        # Loss 2
        tracker.record_trade("GOOGL", "BUY", 30, 100.0, 95.0,
                           datetime(2025, 1, 3, 10, 0), datetime(2025, 1, 3, 15, 0))
        assert tracker._consecutive_losses == 2
        
        # Win - resets
        tracker.record_trade("TSLA", "SELL", 20, 800.0, 750.0,
                           datetime(2025, 1, 4, 10, 0), datetime(2025, 1, 4, 15, 0))
        assert tracker._consecutive_losses == 0
    
    def test_get_all_trades(self, tracker):
        """Test retrieving all trades"""
        # Record multiple trades
        for i in range(5):
            tracker.record_trade(
                symbol=f"STOCK{i}",
                side="BUY",
                quantity=100,
                entry_price=100.0 + i,
                exit_price=105.0 + i,
                entry_time=datetime(2025, 1, i+1, 10, 0),
                exit_time=datetime(2025, 1, i+1, 15, 0)
            )
        
        trades = tracker.get_all_trades()
        assert len(trades) == 5
        assert all(isinstance(t, Trade) for t in trades)
        assert trades[0].symbol == "STOCK0"
        assert trades[4].symbol == "STOCK4"
    
    def test_get_recent_trades(self, tracker):
        """Test retrieving recent trades"""
        # Record 10 trades
        for i in range(10):
            tracker.record_trade(
                symbol=f"STOCK{i}",
                side="BUY",
                quantity=100,
                entry_price=100.0,
                exit_price=105.0,
                entry_time=datetime(2025, 1, i+1, 10, 0),
                exit_time=datetime(2025, 1, i+1, 15, 0)
            )
        
        # Get last 3
        recent = tracker.get_recent_trades(3)
        assert len(recent) == 3
        assert recent[0].symbol == "STOCK7"
        assert recent[2].symbol == "STOCK9"


class TestDailySnapshots:
    """Test daily snapshot functionality"""
    
    def test_record_snapshot(self, tracker):
        """Test recording daily snapshot"""
        snapshot_date = date(2025, 1, 1)
        
        tracker.record_daily_snapshot(
            snapshot_date=snapshot_date,
            portfolio_value=105000.0,
            cash=50000.0,
            positions_value=55000.0,
            daily_pnl=1500.0,
            trade_count=3,
            realized_pnl=1200.0,
            unrealized_pnl=300.0
        )
        
        snapshots = tracker.get_daily_snapshots()
        assert len(snapshots) == 1
        
        snap = snapshots[0]
        assert snap.snapshot_date == snapshot_date
        assert snap.portfolio_value == 105000.0
        assert snap.cash == 50000.0
        assert snap.positions_value == 55000.0
        assert snap.daily_pnl == 1500.0
        assert snap.cumulative_pnl == 5000.0  # 105000 - 100000
        assert snap.trade_count == 3
    
    def test_snapshot_updates_peak_and_drawdown(self, tracker):
        """Test snapshots update peak value and max drawdown"""
        # Day 1: Portfolio goes up (new peak)
        tracker.record_daily_snapshot(
            snapshot_date=date(2025, 1, 1),
            portfolio_value=110000.0,
            cash=60000.0,
            positions_value=50000.0,
            daily_pnl=10000.0
        )
        
        assert tracker._peak_value == 110000.0
        assert tracker._max_drawdown == 0.0
        
        # Day 2: Portfolio drops (drawdown)
        tracker.record_daily_snapshot(
            snapshot_date=date(2025, 1, 2),
            portfolio_value=100000.0,
            cash=50000.0,
            positions_value=50000.0,
            daily_pnl=-10000.0
        )
        
        assert tracker._peak_value == 110000.0  # Peak unchanged
        expected_dd = (110000.0 - 100000.0) / 110000.0  # ~9.09%
        assert abs(tracker._max_drawdown - expected_dd) < 0.0001
        
        # Day 3: Portfolio recovers but doesn't beat peak
        tracker.record_daily_snapshot(
            snapshot_date=date(2025, 1, 3),
            portfolio_value=108000.0,
            cash=58000.0,
            positions_value=50000.0,
            daily_pnl=8000.0
        )
        
        assert tracker._peak_value == 110000.0
        assert abs(tracker._max_drawdown - expected_dd) < 0.0001  # Max DD unchanged
        
        # Day 4: New all-time high
        tracker.record_daily_snapshot(
            snapshot_date=date(2025, 1, 4),
            portfolio_value=115000.0,
            cash=65000.0,
            positions_value=50000.0,
            daily_pnl=7000.0
        )
        
        assert tracker._peak_value == 115000.0  # New peak
        assert abs(tracker._max_drawdown - expected_dd) < 0.0001  # Max DD still from day 2
    
    def test_snapshot_replacement(self, tracker):
        """Test that snapshots for same date replace each other"""
        snapshot_date = date(2025, 1, 1)
        
        # First snapshot
        tracker.record_daily_snapshot(
            snapshot_date=snapshot_date,
            portfolio_value=105000.0,
            cash=55000.0,
            positions_value=50000.0,
            daily_pnl=5000.0
        )
        
        # Second snapshot (same date) - should replace
        tracker.record_daily_snapshot(
            snapshot_date=snapshot_date,
            portfolio_value=106000.0,
            cash=56000.0,
            positions_value=50000.0,
            daily_pnl=6000.0
        )
        
        snapshots = tracker.get_daily_snapshots()
        assert len(snapshots) == 1
        assert snapshots[0].portfolio_value == 106000.0
        assert snapshots[0].daily_pnl == 6000.0
    
    def test_multiple_snapshots_ordered(self, tracker):
        """Test multiple snapshots are ordered by date"""
        dates = [date(2025, 1, 5), date(2025, 1, 1), date(2025, 1, 3)]
        
        for d in dates:
            tracker.record_daily_snapshot(
                snapshot_date=d,
                portfolio_value=100000.0 + d.day * 1000,
                cash=50000.0,
                positions_value=50000.0,
                daily_pnl=1000.0
            )
        
        snapshots = tracker.get_daily_snapshots()
        assert len(snapshots) == 3
        
        # Should be sorted by date
        assert snapshots[0].snapshot_date == date(2025, 1, 1)
        assert snapshots[1].snapshot_date == date(2025, 1, 3)
        assert snapshots[2].snapshot_date == date(2025, 1, 5)


class TestMetricCalculations:
    """Test metric calculation methods"""
    
    def test_win_rate_calculation(self, tracker):
        """Test win rate calculation"""
        # No trades
        assert tracker.calculate_win_rate() == 0.0
        
        # 3 wins, 2 losses = 60%
        tracker.record_trade("AAPL", "BUY", 100, 150.0, 155.0,
                           datetime(2025, 1, 1, 10, 0), datetime(2025, 1, 1, 15, 0))  # Win
        tracker.record_trade("MSFT", "BUY", 50, 200.0, 195.0,
                           datetime(2025, 1, 2, 10, 0), datetime(2025, 1, 2, 15, 0))  # Loss
        tracker.record_trade("GOOGL", "BUY", 30, 100.0, 105.0,
                           datetime(2025, 1, 3, 10, 0), datetime(2025, 1, 3, 15, 0))  # Win
        tracker.record_trade("TSLA", "BUY", 20, 800.0, 795.0,
                           datetime(2025, 1, 4, 10, 0), datetime(2025, 1, 4, 15, 0))  # Loss
        tracker.record_trade("NVDA", "BUY", 40, 300.0, 310.0,
                           datetime(2025, 1, 5, 10, 0), datetime(2025, 1, 5, 15, 0))  # Win
        
        assert tracker.calculate_win_rate() == 0.6  # 3/5
    
    def test_profit_factor_calculation(self, tracker):
        """Test profit factor calculation"""
        # No trades
        assert tracker.calculate_profit_factor() == 0.0
        
        # Gross profit: 500 + 400 = 900
        # Gross loss: 250 + 100 = 350
        # Profit factor: 900 / 350 = 2.57
        
        tracker.record_trade("AAPL", "BUY", 100, 150.0, 155.0,
                           datetime(2025, 1, 1, 10, 0), datetime(2025, 1, 1, 15, 0))  # +500
        tracker.record_trade("MSFT", "BUY", 50, 200.0, 195.0,
                           datetime(2025, 1, 2, 10, 0), datetime(2025, 1, 2, 15, 0))  # -250
        tracker.record_trade("GOOGL", "BUY", 40, 100.0, 110.0,
                           datetime(2025, 1, 3, 10, 0), datetime(2025, 1, 3, 15, 0))  # +400
        tracker.record_trade("TSLA", "BUY", 10, 800.0, 790.0,
                           datetime(2025, 1, 4, 10, 0), datetime(2025, 1, 4, 15, 0))  # -100
        
        pf = tracker.calculate_profit_factor()
        assert abs(pf - 2.571428) < 0.001
    
    def test_profit_factor_only_winners(self, tracker):
        """Test profit factor with only winning trades"""
        tracker.record_trade("AAPL", "BUY", 100, 150.0, 155.0,
                           datetime(2025, 1, 1, 10, 0), datetime(2025, 1, 1, 15, 0))  # +500
        tracker.record_trade("MSFT", "BUY", 50, 200.0, 210.0,
                           datetime(2025, 1, 2, 10, 0), datetime(2025, 1, 2, 15, 0))  # +500
        
        # Should return total profit when no losses
        pf = tracker.calculate_profit_factor()
        assert pf == 1000.0
    
    def test_max_drawdown_calculation(self, tracker):
        """Test max drawdown calculation"""
        assert tracker.calculate_max_drawdown() == 0.0
        
        # Peak at 110k
        tracker.record_daily_snapshot(
            snapshot_date=date(2025, 1, 1),
            portfolio_value=110000.0,
            cash=60000.0,
            positions_value=50000.0,
            daily_pnl=10000.0
        )
        
        # Drop to 95k = 13.6% drawdown
        tracker.record_daily_snapshot(
            snapshot_date=date(2025, 1, 2),
            portfolio_value=95000.0,
            cash=45000.0,
            positions_value=50000.0,
            daily_pnl=-15000.0
        )
        
        dd = tracker.calculate_max_drawdown()
        expected = (110000.0 - 95000.0) / 110000.0
        assert abs(dd - expected) < 0.0001
    
    def test_sharpe_ratio_calculation(self, tracker):
        """Test Sharpe ratio calculation"""
        # Not enough data
        assert tracker.calculate_sharpe_ratio() == 0.0
        
        # Add snapshots with varying returns
        base_value = 100000.0
        returns = [0.01, -0.005, 0.015, 0.02, -0.01, 0.008]  # Daily returns
        
        for i, ret in enumerate(returns):
            value = base_value * (1 + ret)
            tracker.record_daily_snapshot(
                snapshot_date=date(2025, 1, i+1),
                portfolio_value=value,
                cash=50000.0,
                positions_value=value - 50000.0,
                daily_pnl=value - base_value
            )
            base_value = value
        
        sharpe = tracker.calculate_sharpe_ratio()
        # With positive average returns and low volatility, should be positive
        assert sharpe > 0
    
    def test_sharpe_ratio_zero_volatility(self, tracker):
        """Test Sharpe ratio with zero volatility (flat returns)"""
        # All returns identical - zero std dev
        for i in range(5):
            tracker.record_daily_snapshot(
                snapshot_date=date(2025, 1, i+1),
                portfolio_value=100000.0,
                cash=50000.0,
                positions_value=50000.0,
                daily_pnl=0.0
            )
        
        # Should return 0.0 when std dev is zero
        assert tracker.calculate_sharpe_ratio() == 0.0
    
    def test_days_running_calculation(self, tracker):
        """Test days running calculation"""
        # Should be 0 on same day as start
        assert tracker.get_days_running() == 0
        
        # Manually set start date to past
        tracker.start_date = date.today() - timedelta(days=15)
        tracker._update_metadata()
        
        assert tracker.get_days_running() == 15


class TestMetricsSnapshot:
    """Test metrics snapshot generation"""
    
    def test_empty_snapshot(self, tracker):
        """Test snapshot with no data"""
        snapshot = tracker.get_metrics_snapshot()
        
        assert snapshot.strategy_name == "test_strategy"
        assert snapshot.days_running == 0
        assert snapshot.total_trades == 0
        assert snapshot.winning_trades == 0
        assert snapshot.losing_trades == 0
        assert snapshot.win_rate == 0.0
        assert snapshot.sharpe_ratio == 0.0
        assert snapshot.max_drawdown == 0.0
        assert snapshot.profit_factor == 0.0
        assert snapshot.consecutive_losses == 0
        assert snapshot.total_pnl == 0.0
    
    def test_snapshot_with_trades(self, tracker):
        """Test snapshot with trade data"""
        # Record trades: 3 wins, 2 losses
        tracker.record_trade("AAPL", "BUY", 100, 150.0, 160.0,
                           datetime(2025, 1, 1, 10, 0), datetime(2025, 1, 1, 15, 0))  # +1000
        tracker.record_trade("MSFT", "BUY", 50, 200.0, 190.0,
                           datetime(2025, 1, 2, 10, 0), datetime(2025, 1, 2, 15, 0))  # -500
        tracker.record_trade("GOOGL", "BUY", 30, 100.0, 115.0,
                           datetime(2025, 1, 3, 10, 0), datetime(2025, 1, 3, 15, 0))  # +450
        tracker.record_trade("TSLA", "BUY", 20, 800.0, 790.0,
                           datetime(2025, 1, 4, 10, 0), datetime(2025, 1, 4, 15, 0))  # -200
        tracker.record_trade("NVDA", "BUY", 40, 300.0, 312.0,
                           datetime(2025, 1, 5, 10, 0), datetime(2025, 1, 5, 15, 0))  # +480
        
        snapshot = tracker.get_metrics_snapshot()
        
        assert snapshot.total_trades == 5
        assert snapshot.winning_trades == 3
        assert snapshot.losing_trades == 2
        assert snapshot.win_rate == 0.6
        assert snapshot.total_pnl == 1230.0  # 1000 - 500 + 450 - 200 + 480
        assert snapshot.average_win == (1000 + 450 + 480) / 3
        assert snapshot.average_loss == (-500 - 200) / 2
        assert snapshot.largest_win == 1000.0
        assert snapshot.largest_loss == -500.0
        assert snapshot.consecutive_losses == 0  # Last trade was win
    
    def test_snapshot_after_consecutive_losses(self, tracker):
        """Test snapshot tracks consecutive losses"""
        # 2 wins, then 3 losses
        tracker.record_trade("AAPL", "BUY", 100, 150.0, 155.0,
                           datetime(2025, 1, 1, 10, 0), datetime(2025, 1, 1, 15, 0))  # Win
        tracker.record_trade("MSFT", "BUY", 50, 200.0, 205.0,
                           datetime(2025, 1, 2, 10, 0), datetime(2025, 1, 2, 15, 0))  # Win
        tracker.record_trade("GOOGL", "BUY", 30, 100.0, 95.0,
                           datetime(2025, 1, 3, 10, 0), datetime(2025, 1, 3, 15, 0))  # Loss 1
        tracker.record_trade("TSLA", "BUY", 20, 800.0, 790.0,
                           datetime(2025, 1, 4, 10, 0), datetime(2025, 1, 4, 15, 0))  # Loss 2
        tracker.record_trade("NVDA", "BUY", 40, 300.0, 295.0,
                           datetime(2025, 1, 5, 10, 0), datetime(2025, 1, 5, 15, 0))  # Loss 3
        
        snapshot = tracker.get_metrics_snapshot()
        assert snapshot.consecutive_losses == 3


class TestDataPersistence:
    """Test database persistence and recovery"""
    
    def test_trades_persist_across_instances(self, temp_db):
        """Test trades survive tracker restart"""
        # Instance 1: Record trades
        tracker1 = PaperMetricsTracker(temp_db, "test_strategy")
        tracker1.record_trade("AAPL", "BUY", 100, 150.0, 155.0,
                            datetime(2025, 1, 1, 10, 0), datetime(2025, 1, 1, 15, 0))
        tracker1.record_trade("MSFT", "BUY", 50, 200.0, 195.0,
                            datetime(2025, 1, 2, 10, 0), datetime(2025, 1, 2, 15, 0))
        
        # Instance 2: Load and verify
        tracker2 = PaperMetricsTracker(temp_db, "test_strategy")
        trades = tracker2.get_all_trades()
        
        assert len(trades) == 2
        assert trades[0].symbol == "AAPL"
        assert trades[1].symbol == "MSFT"
    
    def test_snapshots_persist_across_instances(self, temp_db):
        """Test snapshots survive tracker restart"""
        # Instance 1: Record snapshots
        tracker1 = PaperMetricsTracker(temp_db, "test_strategy")
        tracker1.record_daily_snapshot(
            snapshot_date=date(2025, 1, 1),
            portfolio_value=105000.0,
            cash=50000.0,
            positions_value=55000.0,
            daily_pnl=5000.0
        )
        tracker1.record_daily_snapshot(
            snapshot_date=date(2025, 1, 2),
            portfolio_value=107000.0,
            cash=52000.0,
            positions_value=55000.0,
            daily_pnl=2000.0
        )
        
        # Instance 2: Load and verify
        tracker2 = PaperMetricsTracker(temp_db, "test_strategy")
        snapshots = tracker2.get_daily_snapshots()
        
        assert len(snapshots) == 2
        assert snapshots[0].portfolio_value == 105000.0
        assert snapshots[1].portfolio_value == 107000.0
    
    def test_metadata_persists(self, temp_db):
        """Test metadata (peak, drawdown, etc.) persists"""
        # Instance 1: Create state
        tracker1 = PaperMetricsTracker(temp_db, "test_strategy", initial_capital=50000.0)
        tracker1.record_daily_snapshot(
            snapshot_date=date(2025, 1, 1),
            portfolio_value=60000.0,
            cash=30000.0,
            positions_value=30000.0,
            daily_pnl=10000.0
        )
        tracker1.record_daily_snapshot(
            snapshot_date=date(2025, 1, 2),
            portfolio_value=55000.0,
            cash=25000.0,
            positions_value=30000.0,
            daily_pnl=-5000.0
        )
        
        peak1 = tracker1._peak_value
        dd1 = tracker1._max_drawdown
        
        # Instance 2: Load and verify
        tracker2 = PaperMetricsTracker(temp_db, "test_strategy")
        
        assert tracker2.initial_capital == 50000.0
        assert tracker2._peak_value == peak1
        assert tracker2._max_drawdown == dd1


class TestEdgeCases:
    """Test edge cases and error conditions"""
    
    def test_clear_all_data(self, tracker):
        """Test clearing all data"""
        # Add some data
        tracker.record_trade("AAPL", "BUY", 100, 150.0, 155.0,
                           datetime(2025, 1, 1, 10, 0), datetime(2025, 1, 1, 15, 0))
        tracker.record_daily_snapshot(
            snapshot_date=date(2025, 1, 1),
            portfolio_value=105000.0,
            cash=50000.0,
            positions_value=55000.0,
            daily_pnl=5000.0
        )
        
        # Clear
        tracker.clear_all_data()
        
        # Verify empty
        assert len(tracker.get_all_trades()) == 0
        assert len(tracker.get_daily_snapshots()) == 0
        assert tracker._peak_value == tracker.initial_capital
        assert tracker._max_drawdown == 0.0
        assert tracker._consecutive_losses == 0
    
    def test_get_recent_trades_fewer_than_requested(self, tracker):
        """Test getting recent trades when fewer exist"""
        # Record 2 trades
        tracker.record_trade("AAPL", "BUY", 100, 150.0, 155.0,
                           datetime(2025, 1, 1, 10, 0), datetime(2025, 1, 1, 15, 0))
        tracker.record_trade("MSFT", "BUY", 50, 200.0, 205.0,
                           datetime(2025, 1, 2, 10, 0), datetime(2025, 1, 2, 15, 0))
        
        # Request 10 - should get 2
        recent = tracker.get_recent_trades(10)
        assert len(recent) == 2
    
    def test_get_recent_trades_empty(self, tracker):
        """Test getting recent trades when none exist"""
        recent = tracker.get_recent_trades(5)
        assert recent == []
    
    def test_multiple_strategies_same_database(self, temp_db):
        """Test multiple strategies can coexist in same database"""
        tracker1 = PaperMetricsTracker(temp_db, "strategy_a", initial_capital=100000.0)
        tracker2 = PaperMetricsTracker(temp_db, "strategy_b", initial_capital=50000.0)
        
        # Record trades for each
        tracker1.record_trade("AAPL", "BUY", 100, 150.0, 155.0,
                            datetime(2025, 1, 1, 10, 0), datetime(2025, 1, 1, 15, 0))
        tracker2.record_trade("MSFT", "BUY", 50, 200.0, 205.0,
                            datetime(2025, 1, 1, 10, 0), datetime(2025, 1, 1, 15, 0))
        
        # Verify isolation
        assert len(tracker1.get_all_trades()) == 1
        assert len(tracker2.get_all_trades()) == 1
        assert tracker1.get_all_trades()[0].symbol == "AAPL"
        assert tracker2.get_all_trades()[0].symbol == "MSFT"
        assert tracker1.initial_capital == 100000.0
        assert tracker2.initial_capital == 50000.0


class TestTradeProperties:
    """Test Trade dataclass properties"""
    
    def test_trade_net_pnl(self):
        """Test net P&L calculation"""
        trade = Trade(
            trade_id=1,
            strategy_name="test",
            symbol="AAPL",
            side="BUY",
            quantity=100,
            entry_price=150.0,
            exit_price=155.0,
            entry_time=datetime(2025, 1, 1, 10, 0),
            exit_time=datetime(2025, 1, 1, 15, 0),
            pnl=500.0,
            commission=10.0
        )
        
        assert trade.net_pnl == 490.0
    
    def test_trade_is_winner(self):
        """Test winner/loser classification"""
        winner = Trade(
            trade_id=1,
            strategy_name="test",
            symbol="AAPL",
            side="BUY",
            quantity=100,
            entry_price=150.0,
            exit_price=155.0,
            entry_time=datetime(2025, 1, 1, 10, 0),
            exit_time=datetime(2025, 1, 1, 15, 0),
            pnl=500.0,
            commission=10.0
        )
        
        loser = Trade(
            trade_id=2,
            strategy_name="test",
            symbol="MSFT",
            side="BUY",
            quantity=50,
            entry_price=200.0,
            exit_price=195.0,
            entry_time=datetime(2025, 1, 1, 10, 0),
            exit_time=datetime(2025, 1, 1, 15, 0),
            pnl=-250.0,
            commission=5.0
        )
        
        assert winner.is_winner is True
        assert loser.is_winner is False
    
    def test_trade_holding_period(self):
        """Test holding period calculation"""
        trade = Trade(
            trade_id=1,
            strategy_name="test",
            symbol="AAPL",
            side="BUY",
            quantity=100,
            entry_price=150.0,
            exit_price=155.0,
            entry_time=datetime(2025, 1, 1, 10, 0),
            exit_time=datetime(2025, 1, 1, 15, 30),  # 5.5 hours later
            pnl=500.0
        )
        
        assert trade.holding_period_hours == 5.5
