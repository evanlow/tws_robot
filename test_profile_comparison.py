"""
Tests for Profile Comparison Framework (Week 4 Day 5)

Tests cover:
- ProfileComparisonResult dataclass
- ProfileComparator comparison logic
- Rankings calculation
- Statistical analysis
- Optimization insights
- Two-profile detailed comparison
"""

import pytest
from datetime import datetime

from backtest.profile_comparison import (
    ProfileComparisonResult, ProfileComparator
)
from backtest.profiles import ProfileManager, ProfileLibrary, RiskProfile, ProfileType
from backtest.engine import BacktestResult
from backtest.performance import PerformanceMetrics
from backtest.strategy import Strategy, StrategyConfig


# Helper function to create test metrics
def create_test_metrics(
    total_return=0.15,
    sharpe_ratio=1.5,
    sortino_ratio=2.0,
    calmar_ratio=1.2,
    max_drawdown=0.10,
    win_rate=0.55,
    profit_factor=1.8,
    total_trades=50
):
    """Create a PerformanceMetrics instance with all required fields"""
    return PerformanceMetrics(
        start_date=datetime(2024, 1, 1),
        end_date=datetime(2024, 12, 31),
        total_days=365,
        trading_days=252,
        initial_capital=100000.0,
        final_equity=100000.0 * (1 + total_return),
        peak_equity=100000.0 * (1 + total_return + 0.05),
        total_return=total_return,
        total_return_pct=total_return * 100,
        annualized_return=total_return,
        max_drawdown=max_drawdown,
        max_drawdown_pct=max_drawdown * 100,
        volatility=0.15,
        downside_deviation=0.10,
        sharpe_ratio=sharpe_ratio,
        sortino_ratio=sortino_ratio,
        calmar_ratio=calmar_ratio,
        total_trades=total_trades,
        winning_trades=int(total_trades * win_rate),
        losing_trades=int(total_trades * (1 - win_rate)),
        win_rate=win_rate,
        avg_win=500.0,
        avg_loss=-300.0,
        largest_win=2000.0,
        largest_loss=-1200.0,
        profit_factor=profit_factor,
        expectancy=150.0,
        avg_trade_duration_days=5.0,
        avg_winning_duration_days=4.5,
        avg_losing_duration_days=5.5,
        avg_drawdown_pct=max_drawdown / 2,
        avg_recovery_days=10.0,
        max_drawdown_duration_days=30,
        avg_exposure_pct=0.75,
        max_positions=5
    )


# Helper function to create test backtest result
def create_test_backtest_result(metrics=None):
    """Create a BacktestResult instance with all required fields"""
    if metrics is None:
        metrics = create_test_metrics()
    
    return BacktestResult(
        strategy_name="TestStrategy",
        start_date=datetime(2024, 1, 1),
        end_date=datetime(2024, 12, 31),
        initial_capital=100000.0,
        final_equity=metrics.final_equity,
        total_return=metrics.total_return,
        total_pnl=metrics.final_equity - 100000.0,
        total_trades=metrics.total_trades,
        winning_trades=metrics.winning_trades,
        losing_trades=metrics.losing_trades,
        win_rate=metrics.win_rate,
        max_drawdown=metrics.max_drawdown,
        max_drawdown_pct=metrics.max_drawdown_pct,
        metrics=metrics
    )


# Mock strategy for testing
class MockStrategy(Strategy):
    """Simple mock strategy for testing"""
    
    def __init__(self, profile: RiskProfile = None, **kwargs):
        config = StrategyConfig(
            initial_capital=100000,
            max_position_size=0.10
        )
        super().__init__(config)
        self.profile = profile
    
    def on_start(self):
        """Called when backtest starts"""
        pass
    
    def on_bar(self, market_data):
        """Called for each bar"""
        pass
    
    def on_stop(self):
        """Called when backtest ends"""
        pass


class TestProfileComparisonResult:
    """Test ProfileComparisonResult dataclass"""
    
    def test_comparison_result_creation(self):
        """Test creating comparison result"""
        result = ProfileComparisonResult(
            start_date='2024-01-01',
            end_date='2024-12-31',
            symbols=['AAPL', 'MSFT'],
            initial_capital=100000.0
        )
        
        assert result.start_date == '2024-01-01'
        assert result.end_date == '2024-12-31'
        assert result.symbols == ['AAPL', 'MSFT']
        assert result.initial_capital == 100000.0
        assert len(result.profile_results) == 0
    
    def test_get_best_profile(self):
        """Test getting best profile by metric"""
        result = ProfileComparisonResult()
        
        # Need to add profile_results for get_best_profile to work
        result.profile_results['conservative'] = create_test_backtest_result()
        result.profile_results['aggressive'] = create_test_backtest_result()
        result.profile_results['moderate'] = create_test_backtest_result()
        
        result.sharpe_ranking = {'conservative': 2, 'aggressive': 1, 'moderate': 3}
        result.return_ranking = {'conservative': 3, 'aggressive': 1, 'moderate': 2}
        
        assert result.get_best_profile('sharpe') == 'aggressive'
        assert result.get_best_profile('return') == 'aggressive'
        assert result.get_best_profile('nonexistent') is None
    
    def test_get_best_profile_empty(self):
        """Test getting best profile with no results"""
        result = ProfileComparisonResult()
        assert result.get_best_profile('sharpe') is None
    
    def test_get_profile_metrics(self):
        """Test retrieving metrics for specific profile"""
        result = ProfileComparisonResult()
        
        # Create mock backtest result
        metrics = create_test_metrics(
            total_return=0.15,
            sharpe_ratio=1.5,
            max_drawdown=0.10
        )
        backtest_result = create_test_backtest_result(metrics)
        result.profile_results['conservative'] = backtest_result
        
        retrieved_metrics = result.get_profile_metrics('conservative')
        assert retrieved_metrics is not None
        assert retrieved_metrics.total_return == 0.15
        assert retrieved_metrics.sharpe_ratio == 1.5
        
        # Non-existent profile
        assert result.get_profile_metrics('nonexistent') is None
    
    def test_get_comparison_table(self):
        """Test generating comparison table"""
        result = ProfileComparisonResult()
        
        # Add mock results
        metrics1 = create_test_metrics(
            total_return=0.15,
            sharpe_ratio=1.5,
            sortino_ratio=2.0,
            max_drawdown=0.10,
            win_rate=0.55,
            profit_factor=1.8,
            total_trades=50
        )
        result.profile_results['conservative'] = create_test_backtest_result(metrics1)
        
        metrics2 = create_test_metrics(
            total_return=0.25,
            sharpe_ratio=1.8,
            sortino_ratio=2.3,
            max_drawdown=0.15,
            win_rate=0.60,
            profit_factor=2.0,
            total_trades=75
        )
        result.profile_results['aggressive'] = create_test_backtest_result(metrics2)
        
        result.sharpe_ranking = {'conservative': 2, 'aggressive': 1}
        result.return_ranking = {'conservative': 2, 'aggressive': 1}
        
        table = result.get_comparison_table()
        
        assert len(table) == 2
        assert 'conservative' in table
        assert 'aggressive' in table
        
        assert table['conservative']['total_return'] == 0.15
        assert table['conservative']['sharpe_ratio'] == 1.5
        assert table['aggressive']['total_return'] == 0.25
        assert table['aggressive']['sharpe_ratio'] == 1.8


class TestProfileComparator:
    """Test ProfileComparator functionality"""
    
    def test_comparator_initialization(self):
        """Test comparator initialization"""
        comparator = ProfileComparator()
        
        assert comparator.profile_manager is not None
        assert len(comparator.comparison_results) == 0
        
        # With custom manager
        manager = ProfileManager()
        comparator2 = ProfileComparator(profile_manager=manager)
        assert comparator2.profile_manager is manager
    
    def test_rank_values_higher_is_better(self):
        """Test ranking values where higher is better"""
        comparator = ProfileComparator()
        
        values = {
            'profile1': 1.5,
            'profile2': 2.0,
            'profile3': 1.0
        }
        
        rankings = comparator._rank_values(values, higher_is_better=True)
        
        assert rankings['profile2'] == 1  # Highest value
        assert rankings['profile1'] == 2
        assert rankings['profile3'] == 3  # Lowest value
    
    def test_rank_values_lower_is_better(self):
        """Test ranking values where lower is better"""
        comparator = ProfileComparator()
        
        values = {
            'profile1': 0.15,
            'profile2': 0.10,
            'profile3': 0.20
        }
        
        rankings = comparator._rank_values(values, higher_is_better=False)
        
        assert rankings['profile2'] == 1  # Lowest value
        assert rankings['profile1'] == 2
        assert rankings['profile3'] == 3  # Highest value
    
    def test_rank_values_empty(self):
        """Test ranking with empty values"""
        comparator = ProfileComparator()
        
        rankings = comparator._rank_values({}, higher_is_better=True)
        assert rankings == {}
    
    def test_calculate_rankings(self):
        """Test calculating rankings from results"""
        comparator = ProfileComparator()
        result = ProfileComparisonResult()
        
        # Add mock results
        metrics1 = create_test_metrics(total_return=0.15, sharpe_ratio=1.5, max_drawdown=0.10, win_rate=0.55
       )
        result.profile_results['conservative'] = create_test_backtest_result(metrics1)
        
        metrics2 = create_test_metrics(total_return=0.25, sharpe_ratio=1.8, max_drawdown=0.08, win_rate=0.60
       )
        result.profile_results['aggressive'] = create_test_backtest_result(metrics2)
        
        metrics3 = create_test_metrics(total_return=0.20, sharpe_ratio=1.6, max_drawdown=0.12, win_rate=0.58
       )
        result.profile_results['moderate'] = create_test_backtest_result(metrics3)
        
        # Calculate rankings
        comparator._calculate_rankings(result)
        
        # Verify rankings
        assert result.sharpe_ranking['aggressive'] == 1  # Highest Sharpe
        assert result.return_ranking['aggressive'] == 1  # Highest return
        assert result.drawdown_ranking['aggressive'] == 1  # Lowest drawdown
        assert result.winrate_ranking['aggressive'] == 1  # Highest win rate
        
        assert result.sharpe_ranking['conservative'] == 3  # Lowest Sharpe
        assert result.return_ranking['conservative'] == 3  # Lowest return
    
    def test_calculate_summary_stats(self):
        """Test calculating summary statistics"""
        comparator = ProfileComparator()
        result = ProfileComparisonResult()
        
        # Add mock results
        metrics1 = create_test_metrics(total_return=0.15, sharpe_ratio=1.5, max_drawdown=0.10, win_rate=0.55
       )
        result.profile_results['profile1'] = create_test_backtest_result(metrics1)
        
        metrics2 = create_test_metrics(total_return=0.25, sharpe_ratio=1.7, max_drawdown=0.15, win_rate=0.60
       )
        result.profile_results['profile2'] = create_test_backtest_result(metrics2)
        
        # Calculate stats
        comparator._calculate_summary_stats(result)
        
        stats = result.summary_stats
        assert stats['num_profiles'] == 2
        assert stats['sharpe_mean'] == 1.6  # (1.5 + 1.7) / 2
        assert stats['return_mean'] == 0.20  # (0.15 + 0.25) / 2
        assert stats['sharpe_std'] > 0  # Should have standard deviation
    
    def test_calculate_summary_stats_single_profile(self):
        """Test summary stats with single profile"""
        comparator = ProfileComparator()
        result = ProfileComparisonResult()
        
        metrics = create_test_metrics(total_return=0.15, sharpe_ratio=1.5, max_drawdown=0.10, win_rate=0.55
       )
        result.profile_results['profile1'] = create_test_backtest_result(metrics)
        
        comparator._calculate_summary_stats(result)
        
        stats = result.summary_stats
        assert stats['num_profiles'] == 1
        assert stats['sharpe_mean'] == 1.5
        assert stats['sharpe_std'] == 0.0  # No std with single value
    
    def test_get_optimization_insights(self):
        """Test generating optimization insights"""
        comparator = ProfileComparator()
        result = ProfileComparisonResult()
        
        # Add mock results
        metrics1 = create_test_metrics(total_return=0.15, sharpe_ratio=1.5, max_drawdown=0.10, win_rate=0.55,
            total_trades=50
       )
        result.profile_results['conservative'] = create_test_backtest_result(metrics1)
        
        metrics2 = create_test_metrics(total_return=0.25, sharpe_ratio=1.8, max_drawdown=0.08, win_rate=0.60,
            total_trades=75
       )
        result.profile_results['aggressive'] = create_test_backtest_result(metrics2)
        
        # Set rankings
        result.sharpe_ranking = {'conservative': 2, 'aggressive': 1}
        result.return_ranking = {'conservative': 2, 'aggressive': 1}
        result.drawdown_ranking = {'conservative': 2, 'aggressive': 1}
        result.winrate_ranking = {'conservative': 2, 'aggressive': 1}
        
        result.summary_stats = {
            'sharpe_std': 0.3,
            'sharpe_mean': 1.65
        }
        
        # Get insights
        insights = comparator.get_optimization_insights(result)
        
        assert len(insights) > 0
        assert any('aggressive' in insight.lower() for insight in insights)
    
    def test_get_optimization_insights_empty(self):
        """Test insights with no results"""
        comparator = ProfileComparator()
        result = ProfileComparisonResult()
        
        insights = comparator.get_optimization_insights(result)
        
        assert len(insights) == 1
        assert 'No results' in insights[0]
    
    def test_compare_two_profiles(self):
        """Test detailed two-profile comparison"""
        comparator = ProfileComparator()
        result = ProfileComparisonResult()
        
        # Add mock results
        metrics1 = create_test_metrics(total_return=0.15, sharpe_ratio=1.5, max_drawdown=0.10, win_rate=0.55
       )
        result.profile_results['conservative'] = create_test_backtest_result(metrics1)
        
        metrics2 = create_test_metrics(total_return=0.25, sharpe_ratio=1.8, max_drawdown=0.15, win_rate=0.60
       )
        result.profile_results['aggressive'] = create_test_backtest_result(metrics2)
        
        # Compare
        comparison = comparator.compare_two_profiles(
            'conservative',
            'aggressive',
            result
        )
        
        assert 'profile1' in comparison
        assert 'profile2' in comparison
        assert 'metrics' in comparison
        
        # Check metrics
        assert comparison['metrics']['total_return']['conservative'] == 0.15
        assert comparison['metrics']['total_return']['aggressive'] == 0.25
        assert comparison['metrics']['total_return']['winner'] == 'aggressive'
        
        assert comparison['metrics']['max_drawdown']['winner'] == 'conservative'  # Lower is better
    
    def test_compare_two_profiles_not_found(self):
        """Test comparing profiles that don't exist"""
        comparator = ProfileComparator()
        result = ProfileComparisonResult()
        
        comparison = comparator.compare_two_profiles(
            'nonexistent1',
            'nonexistent2',
            result
        )
        
        assert 'error' in comparison


class TestProfileComparisonIntegration:
    """Test integration scenarios"""
    
    def test_dominance_detection(self):
        """Test detecting when one profile dominates"""
        comparator = ProfileComparator()
        result = ProfileComparisonResult()
        
        # Aggressive dominates
        metrics_aggressive = create_test_metrics(
            total_return=0.25,
            sharpe_ratio=1.8,
            max_drawdown=0.08,
            win_rate=0.60,
            total_trades=50
        )
        result.profile_results['aggressive'] = create_test_backtest_result(metrics_aggressive)
        
        # Conservative underperforms
        metrics_conservative = create_test_metrics(
            total_return=0.15,
            sharpe_ratio=1.2,
            max_drawdown=0.12,
            win_rate=0.50,
            total_trades=30
        )
        result.profile_results['conservative'] = create_test_backtest_result(metrics_conservative)
        
        # Calculate rankings
        comparator._calculate_rankings(result)
        result.summary_stats = {'sharpe_std': 0.3}
        
        # Check insights
        insights = comparator.get_optimization_insights(result)
        
        # Should detect dominance
        assert any('aggressive' in insight.lower() for insight in insights)
    
    def test_mixed_performance(self):
        """Test when different profiles excel in different metrics"""
        comparator = ProfileComparator()
        result = ProfileComparisonResult()
        
        # High return, high drawdown
        metrics1 = create_test_metrics(total_return=0.30, sharpe_ratio=1.5, max_drawdown=0.20, win_rate=0.55,
            total_trades=50
       )
        result.profile_results['high_return'] = create_test_backtest_result(metrics1)
        
        # Low return, low drawdown
        metrics2 = create_test_metrics(total_return=0.15, sharpe_ratio=1.8, max_drawdown=0.08, win_rate=0.60,
            total_trades=40
       )
        result.profile_results['low_risk'] = create_test_backtest_result(metrics2)
        
        comparator._calculate_rankings(result)
        result.summary_stats = {'sharpe_std': 0.15}
        
        # Different profiles should win different metrics
        assert result.get_best_profile('return') == 'high_return'
        assert result.get_best_profile('drawdown') == 'low_risk'
        
        insights = comparator.get_optimization_insights(result)
        assert any('different' in insight.lower() for insight in insights)
    
    def test_consistency_analysis(self):
        """Test detecting consistent vs inconsistent performance"""
        comparator = ProfileComparator()
        result = ProfileComparisonResult()
        
        # Similar performance profiles
        for i in range(3):
            metrics = create_test_metrics(total_return=0.15 + i * 0.01, sharpe_ratio=1.5 + i * 0.1, max_drawdown=0.10, win_rate=0.55,
                total_trades=50
           )
            result.profile_results[f'profile{i}'] = create_test_backtest_result(metrics)
        
        comparator._calculate_summary_stats(result)
        
        # Low variance should indicate consistency
        assert result.summary_stats['sharpe_std'] < 0.5
    
    def test_comparison_table_formatting(self):
        """Test comparison table contains all required fields"""
        result = ProfileComparisonResult()
        
        metrics = create_test_metrics(
            total_return=0.15,
            sharpe_ratio=1.5,
            sortino_ratio=2.0,
            max_drawdown=0.10,
            win_rate=0.55,
            profit_factor=1.8,
            total_trades=50
        )
        result.profile_results['test'] = create_test_backtest_result(metrics)
        
        result.sharpe_ranking = {'test': 1}
        result.return_ranking = {'test': 1}
        result.drawdown_ranking = {'test': 1}
        result.winrate_ranking = {'test': 1}
        
        table = result.get_comparison_table()
        
        # Verify all required fields (cagr field doesn't exist, using annualized_return)
        required_fields = [
            'total_return', 'sharpe_ratio', 'sortino_ratio',
            'max_drawdown', 'win_rate', 'profit_factor', 'total_trades',
            'sharpe_rank', 'return_rank', 'drawdown_rank', 'winrate_rank'
        ]
        
        for field in required_fields:
            assert field in table['test']


if __name__ == '__main__':
    pytest.main([__file__, '-v'])


