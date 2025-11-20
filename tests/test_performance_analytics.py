"""
Tests for performance analytics module
"""

import pytest
from datetime import datetime, timedelta
from backtesting.performance_analytics import PerformanceAnalytics, DrawdownPeriod
from backtesting.backtest_engine import BacktestTrade


@pytest.fixture
def sample_equity_curve_profitable():
    """Sample profitable equity curve"""
    start = datetime(2024, 1, 1)
    curve = []
    equity = 100000.0
    
    for i in range(252):  # One year of trading days
        # Simulate upward trend with some volatility
        equity += equity * 0.001 * (1 + 0.5 * (i % 10 - 5) / 5)
        curve.append((start + timedelta(days=i), equity))
    
    return curve


@pytest.fixture
def sample_equity_curve_with_drawdown():
    """Sample equity curve with significant drawdown"""
    start = datetime(2024, 1, 1)
    curve = []
    equity = 100000.0
    
    # First 100 days: upward trend
    for i in range(100):
        equity += equity * 0.002
        curve.append((start + timedelta(days=i), equity))
    
    # Next 50 days: drawdown
    peak_equity = equity
    for i in range(50):
        equity -= peak_equity * 0.004  # -20% total drawdown
        curve.append((start + timedelta(days=100 + i), equity))
    
    # Next 102 days: recovery and new highs
    for i in range(102):
        equity += equity * 0.0015
        curve.append((start + timedelta(days=150 + i), equity))
    
    return curve


@pytest.fixture
def sample_trades_profitable():
    """Sample profitable trades"""
    trades = []
    
    for i in range(100):
        # 60% winners, 40% losers
        if i % 5 < 3:
            pnl = 500.0 + (i % 10) * 50  # Winners
        else:
            pnl = -200.0 - (i % 5) * 30  # Losers
        
        entry_time = datetime(2024, 1, 1) + timedelta(days=i)
        exit_time = datetime(2024, 1, 1) + timedelta(days=i, hours=6)
        
        trades.append(BacktestTrade(
            trade_id=i,
            symbol='AAPL',
            entry_time=entry_time,
            exit_time=exit_time,
            entry_price=150.0,
            exit_price=150.0 + pnl / 100,  # Approximate
            quantity=100,
            direction='LONG',
            pnl=pnl,
            pnl_percent=pnl / 100000,
            commission=1.0
        ))
    
    return trades


@pytest.fixture
def sample_trades_unprofitable():
    """Sample unprofitable trades"""
    trades = []
    
    for i in range(50):
        # 40% winners, 60% losers
        if i % 5 < 2:
            pnl = 300.0
        else:
            pnl = -400.0
        
        entry_time = datetime(2024, 1, 1) + timedelta(days=i)
        exit_time = datetime(2024, 1, 1) + timedelta(days=i, hours=6)
        
        trades.append(BacktestTrade(
            trade_id=i,
            symbol='AAPL',
            entry_time=entry_time,
            exit_time=exit_time,
            entry_price=150.0,
            exit_price=150.0 + pnl / 100,
            quantity=100,
            direction='LONG',
            pnl=pnl,
            pnl_percent=pnl / 100000,
            commission=1.0
        ))
    
    return trades


class TestPerformanceAnalytics:
    """Test suite for PerformanceAnalytics"""
    
    def test_initialization(self, sample_equity_curve_profitable, sample_trades_profitable):
        """Test analytics initialization"""
        analytics = PerformanceAnalytics()
        
        assert analytics.metrics == {}
        
        # Test calculation works
        metrics = analytics.calculate_metrics(
            sample_equity_curve_profitable,
            sample_trades_profitable,
            initial_capital=100000.0
        )
        
        assert metrics is not None
        assert len(metrics) > 0
    
    def test_calculate_metrics_profitable(self, sample_equity_curve_profitable, sample_trades_profitable):
        """Test metrics calculation on profitable strategy"""
        analytics = PerformanceAnalytics()
        
        metrics = analytics.calculate_metrics(
            sample_equity_curve_profitable,
            sample_trades_profitable,
            initial_capital=100000.0
        )
        
        # Check all required metrics are present
        assert 'total_return' in metrics
        assert 'total_return_pct' in metrics
        assert 'annualized_return' in metrics
        assert 'sharpe_ratio' in metrics
        assert 'sortino_ratio' in metrics
        assert 'calmar_ratio' in metrics
        assert 'max_drawdown' in metrics
        assert 'max_drawdown_pct' in metrics
        assert 'max_drawdown_duration' in metrics
        assert 'total_trades' in metrics
        assert 'winning_trades' in metrics
        assert 'losing_trades' in metrics
        assert 'win_rate' in metrics
        assert 'avg_win' in metrics
        assert 'avg_loss' in metrics
        assert 'profit_factor' in metrics
        assert 'expectancy' in metrics
        
        # Verify profitable strategy characteristics
        assert metrics['total_return'] > 0
        assert metrics['annualized_return'] > 0
        assert metrics['win_rate'] >= 0.5  # Should be around 60%
        assert metrics['profit_factor'] > 1.0
        assert metrics['expectancy'] > 0
    
    def test_calculate_metrics_unprofitable(self, sample_equity_curve_profitable, sample_trades_unprofitable):
        """Test metrics calculation on unprofitable strategy"""
        # Create losing equity curve
        start = datetime(2024, 1, 1)
        losing_curve = []
        equity = 100000.0
        
        for i in range(252):
            equity -= equity * 0.0005  # Gradual decline
            losing_curve.append((start + timedelta(days=i), equity))
        
        analytics = PerformanceAnalytics()
        
        metrics = analytics.calculate_metrics(
            losing_curve,
            sample_trades_unprofitable,
            initial_capital=100000.0
        )
        
        # Verify unprofitable strategy characteristics
        assert metrics['total_return'] < 0
        assert metrics['annualized_return'] < 0
        assert metrics['win_rate'] < 0.5  # 40% win rate
        assert metrics['profit_factor'] < 1.0
        assert metrics['expectancy'] < 0
    
    def test_sharpe_ratio(self, sample_equity_curve_profitable, sample_trades_profitable):
        """Test Sharpe ratio calculation"""
        analytics = PerformanceAnalytics()
        
        metrics = analytics.calculate_metrics(
            sample_equity_curve_profitable,
            sample_trades_profitable,
            initial_capital=100000.0,
            risk_free_rate=0.02
        )
        
        # Sharpe ratio should be positive for profitable strategy
        assert metrics['sharpe_ratio'] > 0
        
        # For a consistently profitable strategy, Sharpe should be > 1
        assert metrics['sharpe_ratio'] > 1.0
    
    def test_sortino_ratio(self, sample_equity_curve_profitable, sample_trades_profitable):
        """Test Sortino ratio calculation"""
        analytics = PerformanceAnalytics()
        
        metrics = analytics.calculate_metrics(
            sample_equity_curve_profitable,
            sample_trades_profitable,
            initial_capital=100000.0,
            risk_free_rate=0.02
        )
        
        # Sortino ratio should be positive for profitable strategy
        assert metrics['sortino_ratio'] > 0
        
        # Sortino is usually higher than Sharpe (only penalizes downside)
        assert metrics['sortino_ratio'] >= metrics['sharpe_ratio']
    
    def test_drawdown_identification(self, sample_equity_curve_with_drawdown, sample_trades_profitable):
        """Test drawdown period identification"""
        analytics = PerformanceAnalytics()
        
        metrics = analytics.calculate_metrics(
            sample_equity_curve_with_drawdown,
            sample_trades_profitable,
            initial_capital=100000.0
        )
        
        # Should identify the significant drawdown
        assert metrics['max_drawdown'] > 0
        assert metrics['max_drawdown_pct'] > 0.15  # Should be around 20%
        assert metrics['max_drawdown_pct'] < 0.25
        
        # Should have reasonable duration
        assert metrics['max_drawdown_duration'] > 0
        assert metrics['max_drawdown_duration'] < 100  # Should be around 50 days
        
        # Check drawdown periods
        assert 'drawdown_periods' in metrics
        assert len(metrics['drawdown_periods']) > 0
        
        # Verify largest drawdown period
        largest_dd = max(metrics['drawdown_periods'], key=lambda x: x['drawdown_pct'])
        assert largest_dd['drawdown_pct'] > 0.15
    
    def test_calmar_ratio(self, sample_equity_curve_profitable, sample_trades_profitable):
        """Test Calmar ratio calculation"""
        analytics = PerformanceAnalytics()
        
        metrics = analytics.calculate_metrics(
            sample_equity_curve_profitable,
            sample_trades_profitable,
            initial_capital=100000.0
        )
        
        # Calmar = annualized_return / max_drawdown_pct
        assert metrics['calmar_ratio'] > 0
        
        expected_calmar = metrics['annualized_return'] / metrics['max_drawdown_pct']
        assert abs(metrics['calmar_ratio'] - expected_calmar) < 0.01
    
    def test_trade_metrics(self, sample_equity_curve_profitable, sample_trades_profitable):
        """Test trade-based metrics"""
        analytics = PerformanceAnalytics()
        
        metrics = analytics.calculate_metrics(
            sample_equity_curve_profitable,
            sample_trades_profitable,
            initial_capital=100000.0
        )
        
        # Verify trade counts
        assert metrics['total_trades'] == 100
        assert metrics['winning_trades'] == 60  # 60% win rate
        assert metrics['losing_trades'] == 40
        
        # Verify win rate
        assert metrics['win_rate'] == 0.6
        
        # Verify averages
        assert metrics['avg_win'] > 0
        assert metrics['avg_loss'] < 0
        
        # Verify profit factor
        total_wins = metrics['winning_trades'] * metrics['avg_win']
        total_losses = abs(metrics['losing_trades'] * metrics['avg_loss'])
        expected_pf = total_wins / total_losses if total_losses > 0 else 0
        assert abs(metrics['profit_factor'] - expected_pf) < 0.01
        
        # Verify expectancy
        expected_expectancy = (
            metrics['win_rate'] * metrics['avg_win'] + 
            (1 - metrics['win_rate']) * metrics['avg_loss']
        )
        assert abs(metrics['expectancy'] - expected_expectancy) < 1.0
    
    def test_best_worst_trades(self, sample_equity_curve_profitable, sample_trades_profitable):
        """Test best and worst trade identification"""
        analytics = PerformanceAnalytics()
        
        metrics = analytics.calculate_metrics(
            sample_equity_curve_profitable,
            sample_trades_profitable,
            initial_capital=100000.0
        )
        
        # Verify best and worst trades
        assert metrics['best_trade'] > 0
        assert metrics['worst_trade'] < 0
        assert metrics['best_trade'] > abs(metrics['worst_trade'])
    
    def test_recovery_factor(self, sample_equity_curve_with_drawdown, sample_trades_profitable):
        """Test recovery factor calculation"""
        analytics = PerformanceAnalytics()
        
        metrics = analytics.calculate_metrics(
            sample_equity_curve_with_drawdown,
            sample_trades_profitable,
            initial_capital=100000.0
        )
        
        # Recovery factor = total_return / max_drawdown
        assert metrics['recovery_factor'] > 0
        
        expected_rf = metrics['total_return'] / metrics['max_drawdown']
        assert abs(metrics['recovery_factor'] - expected_rf) < 0.01
    
    def test_empty_trades(self):
        """Test handling of empty trades list"""
        start = datetime(2024, 1, 1)
        curve = [(start + timedelta(days=i), 100000.0) for i in range(10)]
        
        analytics = PerformanceAnalytics()
        
        metrics = analytics.calculate_metrics(
            curve,
            [],  # Empty trades
            initial_capital=100000.0
        )
        
        # Should handle gracefully
        assert metrics['total_trades'] == 0
        assert metrics['win_rate'] == 0.0
        assert metrics['profit_factor'] == 0.0
        assert metrics['expectancy'] == 0.0
    
    def test_single_trade(self, sample_equity_curve_profitable):
        """Test with single trade"""
        single_trade = [BacktestTrade(
            trade_id=1,
            symbol='AAPL',
            entry_time=datetime(2024, 1, 1),
            exit_time=datetime(2024, 1, 1, 6),
            entry_price=150.0,
            exit_price=155.0,
            quantity=100,
            direction='LONG',
            pnl=500.0,
            pnl_percent=0.005,
            commission=1.0
        )]
        
        analytics = PerformanceAnalytics()
        
        metrics = analytics.calculate_metrics(
            sample_equity_curve_profitable,
            single_trade,
            initial_capital=100000.0
        )
        
        assert metrics['total_trades'] == 1
        assert metrics['winning_trades'] == 1
        assert metrics['losing_trades'] == 0
        assert metrics['win_rate'] == 1.0
    
    def test_print_summary(self, sample_equity_curve_profitable, sample_trades_profitable, capsys):
        """Test summary printing"""
        analytics = PerformanceAnalytics()
        
        metrics = analytics.calculate_metrics(
            sample_equity_curve_profitable,
            sample_trades_profitable,
            initial_capital=100000.0
        )
        analytics.print_summary(metrics)
        
        captured = capsys.readouterr()
        
        # Verify output contains key sections
        assert "Performance Metrics" in captured.out
        assert "Returns Analysis" in captured.out
        assert "Risk-Adjusted Returns" in captured.out
        assert "Drawdown Analysis" in captured.out
        assert "Trade Statistics" in captured.out
        
        # Verify key values are printed
        assert "Total Return:" in captured.out
        assert "Sharpe Ratio:" in captured.out
        assert "Max Drawdown:" in captured.out
        assert "Win Rate:" in captured.out


class TestDrawdownPeriod:
    """Test suite for DrawdownPeriod dataclass"""
    
    def test_drawdown_period_creation(self):
        """Test DrawdownPeriod creation"""
        period = DrawdownPeriod(
            start_date=datetime(2024, 1, 1),
            end_date=datetime(2024, 2, 1),
            peak_date=datetime(2024, 1, 1),
            valley_date=datetime(2024, 1, 15),
            peak_value=100000.0,
            valley_value=90000.0,
            drawdown=10000.0,
            drawdown_pct=0.1,
            duration_days=31,
            recovery_days=16
        )
        
        assert period.peak_value == 100000.0
        assert period.valley_value == 90000.0
        assert period.drawdown == 10000.0
        assert period.drawdown_pct == 0.1
        assert period.duration_days == 31
        assert period.recovery_days == 16
    
    def test_drawdown_period_dict_conversion(self):
        """Test DrawdownPeriod to dict conversion"""
        period = DrawdownPeriod(
            start_date=datetime(2024, 1, 1),
            end_date=datetime(2024, 2, 1),
            peak_date=datetime(2024, 1, 1),
            valley_date=datetime(2024, 1, 15),
            peak_value=100000.0,
            valley_value=90000.0,
            drawdown=10000.0,
            drawdown_pct=0.1,
            duration_days=31,
            recovery_days=16
        )
        
        # Can be converted to dict
        period_dict = {
            'start_date': period.start_date,
            'end_date': period.end_date,
            'drawdown': period.drawdown,
            'drawdown_pct': period.drawdown_pct
        }
        
        assert period_dict['drawdown'] == 10000.0
        assert period_dict['drawdown_pct'] == 0.1


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
