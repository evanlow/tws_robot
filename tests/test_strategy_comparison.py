"""
Sprint 3 Task 3: Strategy Comparison Dashboard Tests
Tests for side-by-side strategy comparison, ranking, and visualization.
"""

import pytest
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Dict, List
import logging

from strategies.comparison_dashboard import (
    StrategyComparator,
    ComparisonMetrics,
    ComparisonDashboard,
    MetricType,
    RankingCriteria
)


# ============================================================================
# Test Fixtures
# ============================================================================


@pytest.fixture
def sample_metrics():
    """Create sample performance metrics for testing."""
    return {
        "Conservative": {
            "total_return": 15.5,
            "annualized_return": 18.2,
            "sharpe_ratio": 1.45,
            "sortino_ratio": 2.10,
            "max_drawdown": 8.3,
            "win_rate": 0.62,
            "profit_factor": 2.15,
            "total_trades": 85,
            "avg_trade": 0.18,
            "expectancy": 182.35,
            "calmar_ratio": 2.19,
            "recovery_factor": 1.87,
            "volatility": 12.5
        },
        "Aggressive": {
            "total_return": 32.8,
            "annualized_return": 42.5,
            "sharpe_ratio": 1.12,
            "sortino_ratio": 1.65,
            "max_drawdown": 22.1,
            "win_rate": 0.48,
            "profit_factor": 1.68,
            "total_trades": 142,
            "avg_trade": 0.23,
            "expectancy": 231.03,
            "calmar_ratio": 1.92,
            "recovery_factor": 1.48,
            "volatility": 28.3
        },
        "Balanced": {
            "total_return": 22.4,
            "annualized_return": 27.8,
            "sharpe_ratio": 1.28,
            "sortino_ratio": 1.88,
            "max_drawdown": 13.7,
            "win_rate": 0.54,
            "profit_factor": 1.92,
            "total_trades": 108,
            "avg_trade": 0.21,
            "expectancy": 207.41,
            "calmar_ratio": 2.03,
            "recovery_factor": 1.63,
            "volatility": 18.9
        }
    }


# ============================================================================
# ComparisonMetrics Tests
# ============================================================================

class TestComparisonMetrics:
    """Test the ComparisonMetrics data class."""
    
    def test_comparison_metrics_creation(self, sample_metrics):
        """Test creating ComparisonMetrics from dict."""
        metrics = ComparisonMetrics.from_dict("Conservative", sample_metrics["Conservative"])
        
        assert metrics.strategy_name == "Conservative"
        assert metrics.total_return == 15.5
        assert metrics.sharpe_ratio == 1.45
        assert metrics.max_drawdown == 8.3
        assert metrics.win_rate == 0.62
        assert metrics.total_trades == 85
    
    def test_comparison_metrics_ranking_score(self, sample_metrics):
        """Test calculating ranking score."""
        metrics = ComparisonMetrics.from_dict("Conservative", sample_metrics["Conservative"])
        
        # Default ranking (sharpe ratio)
        score = metrics.get_ranking_score(RankingCriteria.SHARPE_RATIO)
        assert score == 1.45
        
        # Total return ranking
        score = metrics.get_ranking_score(RankingCriteria.TOTAL_RETURN)
        assert score == 15.5
        
        # Risk-adjusted (sharpe/drawdown)
        score = metrics.get_ranking_score(RankingCriteria.RISK_ADJUSTED)
        assert abs(score - (1.45 / 8.3)) < 0.001
    
    def test_comparison_metrics_to_dict(self, sample_metrics):
        """Test converting ComparisonMetrics to dict."""
        metrics = ComparisonMetrics.from_dict("Aggressive", sample_metrics["Aggressive"])
        data = metrics.to_dict()
        
        assert data["strategy_name"] == "Aggressive"
        assert data["total_return"] == 32.8
        assert data["sharpe_ratio"] == 1.12
        assert "max_drawdown" in data
        assert "win_rate" in data


# ============================================================================
# StrategyComparator Tests
# ============================================================================

class TestStrategyComparator:
    """Test the StrategyComparator class."""
    
    def test_comparator_initialization(self):
        """Test basic comparator initialization."""
        comparator = StrategyComparator()
        
        assert comparator is not None
        assert len(comparator.get_all_strategies()) == 0
    
    def test_add_strategy_results(self, sample_metrics):
        """Test adding strategy results."""
        comparator = StrategyComparator()
        
        comparator.add_strategy("Conservative", sample_metrics["Conservative"])
        comparator.add_strategy("Aggressive", sample_metrics["Aggressive"])
        
        strategies = comparator.get_all_strategies()
        assert len(strategies) == 2
        assert "Conservative" in strategies
        assert "Aggressive" in strategies
    
    def test_add_duplicate_strategy(self, sample_metrics):
        """Test that duplicate strategy names are handled."""
        comparator = StrategyComparator()
        
        comparator.add_strategy("Conservative", sample_metrics["Conservative"])
        
        # Adding same strategy should update, not duplicate
        updated_metrics = sample_metrics["Conservative"].copy()
        updated_metrics["total_return"] = 20.0
        comparator.add_strategy("Conservative", updated_metrics)
        
        strategies = comparator.get_all_strategies()
        assert len(strategies) == 1
        
        # Verify it was updated
        metrics = comparator.get_strategy_metrics("Conservative")
        assert metrics.total_return == 20.0
    
    def test_get_strategy_metrics(self, sample_metrics):
        """Test retrieving metrics for a specific strategy."""
        comparator = StrategyComparator()
        comparator.add_strategy("Balanced", sample_metrics["Balanced"])
        
        metrics = comparator.get_strategy_metrics("Balanced")
        assert metrics is not None
        assert metrics.strategy_name == "Balanced"
        assert metrics.sharpe_ratio == 1.28
    
    def test_get_nonexistent_strategy(self):
        """Test retrieving metrics for strategy that doesn't exist."""
        comparator = StrategyComparator()
        
        metrics = comparator.get_strategy_metrics("NonExistent")
        assert metrics is None
    
    def test_remove_strategy(self, sample_metrics):
        """Test removing a strategy."""
        comparator = StrategyComparator()
        comparator.add_strategy("Conservative", sample_metrics["Conservative"])
        comparator.add_strategy("Aggressive", sample_metrics["Aggressive"])
        
        assert len(comparator.get_all_strategies()) == 2
        
        comparator.remove_strategy("Conservative")
        assert len(comparator.get_all_strategies()) == 1
        assert "Aggressive" in comparator.get_all_strategies()
    
    def test_rank_strategies_by_sharpe(self, sample_metrics):
        """Test ranking strategies by Sharpe ratio."""
        comparator = StrategyComparator()
        
        for name, metrics in sample_metrics.items():
            comparator.add_strategy(name, metrics)
        
        ranked = comparator.rank_strategies(RankingCriteria.SHARPE_RATIO)
        
        # Should be Conservative (1.45), Balanced (1.28), Aggressive (1.12)
        assert len(ranked) == 3
        assert ranked[0][0] == "Conservative"
        assert ranked[1][0] == "Balanced"
        assert ranked[2][0] == "Aggressive"
    
    def test_rank_strategies_by_return(self, sample_metrics):
        """Test ranking strategies by total return."""
        comparator = StrategyComparator()
        
        for name, metrics in sample_metrics.items():
            comparator.add_strategy(name, metrics)
        
        ranked = comparator.rank_strategies(RankingCriteria.TOTAL_RETURN)
        
        # Should be Aggressive (32.8), Balanced (22.4), Conservative (15.5)
        assert len(ranked) == 3
        assert ranked[0][0] == "Aggressive"
        assert ranked[1][0] == "Balanced"
        assert ranked[2][0] == "Conservative"
    
    def test_rank_strategies_by_drawdown(self, sample_metrics):
        """Test ranking strategies by max drawdown (lower is better)."""
        comparator = StrategyComparator()
        
        for name, metrics in sample_metrics.items():
            comparator.add_strategy(name, metrics)
        
        ranked = comparator.rank_strategies(RankingCriteria.MAX_DRAWDOWN)
        
        # Should be Conservative (8.3), Balanced (13.7), Aggressive (22.1)
        # Lower drawdown = better rank
        assert len(ranked) == 3
        assert ranked[0][0] == "Conservative"
        assert ranked[1][0] == "Balanced"
        assert ranked[2][0] == "Aggressive"
    
    def test_compare_two_strategies(self, sample_metrics):
        """Test head-to-head comparison of two strategies."""
        comparator = StrategyComparator()
        
        comparator.add_strategy("Conservative", sample_metrics["Conservative"])
        comparator.add_strategy("Aggressive", sample_metrics["Aggressive"])
        
        comparison = comparator.compare_strategies("Conservative", "Aggressive")
        
        assert comparison is not None
        assert "Conservative" in comparison
        assert "Aggressive" in comparison
        assert "differences" in comparison
        
        # Check differences
        diffs = comparison["differences"]
        assert "total_return" in diffs
        assert "sharpe_ratio" in diffs
        # Conservative has higher Sharpe, Aggressive has higher return
        assert diffs["sharpe_ratio"] > 0  # Conservative wins
        assert diffs["total_return"] < 0  # Conservative loses
    
    def test_compare_nonexistent_strategies(self, sample_metrics):
        """Test comparison with nonexistent strategy."""
        comparator = StrategyComparator()
        comparator.add_strategy("Conservative", sample_metrics["Conservative"])
        
        comparison = comparator.compare_strategies("Conservative", "NonExistent")
        assert comparison is None
    
    def test_get_best_strategy(self, sample_metrics):
        """Test finding the best strategy by criteria."""
        comparator = StrategyComparator()
        
        for name, metrics in sample_metrics.items():
            comparator.add_strategy(name, metrics)
        
        # Best by Sharpe
        best = comparator.get_best_strategy(RankingCriteria.SHARPE_RATIO)
        assert best == "Conservative"
        
        # Best by return
        best = comparator.get_best_strategy(RankingCriteria.TOTAL_RETURN)
        assert best == "Aggressive"
        
        # Best by drawdown (lowest)
        best = comparator.get_best_strategy(RankingCriteria.MAX_DRAWDOWN)
        assert best == "Conservative"
    
    def test_get_worst_strategy(self, sample_metrics):
        """Test finding the worst strategy by criteria."""
        comparator = StrategyComparator()
        
        for name, metrics in sample_metrics.items():
            comparator.add_strategy(name, metrics)
        
        # Worst by Sharpe
        worst = comparator.get_worst_strategy(RankingCriteria.SHARPE_RATIO)
        assert worst == "Aggressive"
        
        # Worst by return
        worst = comparator.get_worst_strategy(RankingCriteria.TOTAL_RETURN)
        assert worst == "Conservative"


# ============================================================================
# ComparisonDashboard Tests
# ============================================================================

class TestComparisonDashboard:
    """Test the ComparisonDashboard visualization class."""
    
    def test_dashboard_initialization(self):
        """Test dashboard creation."""
        dashboard = ComparisonDashboard()
        
        assert dashboard is not None
        assert dashboard.comparator is not None
    
    def test_dashboard_with_comparator(self, sample_metrics):
        """Test dashboard with existing comparator."""
        comparator = StrategyComparator()
        for name, metrics in sample_metrics.items():
            comparator.add_strategy(name, metrics)
        
        dashboard = ComparisonDashboard(comparator=comparator)
        
        assert dashboard.comparator == comparator
        assert len(dashboard.comparator.get_all_strategies()) == 3
    
    def test_generate_summary_table(self, sample_metrics):
        """Test generating comparison summary table."""
        comparator = StrategyComparator()
        for name, metrics in sample_metrics.items():
            comparator.add_strategy(name, metrics)
        
        dashboard = ComparisonDashboard(comparator=comparator)
        table = dashboard.generate_summary_table()
        
        assert table is not None
        assert "Conservative" in table
        assert "Aggressive" in table
        assert "Balanced" in table
    
    def test_generate_ranking_table(self, sample_metrics):
        """Test generating ranking table."""
        comparator = StrategyComparator()
        for name, metrics in sample_metrics.items():
            comparator.add_strategy(name, metrics)
        
        dashboard = ComparisonDashboard(comparator=comparator)
        table = dashboard.generate_ranking_table(RankingCriteria.SHARPE_RATIO)
        
        assert table is not None
        # Should contain rank information
        assert "1" in table or "#1" in table or "Conservative" in table
    
    def test_generate_metric_comparison(self, sample_metrics):
        """Test comparing specific metric across strategies."""
        comparator = StrategyComparator()
        for name, metrics in sample_metrics.items():
            comparator.add_strategy(name, metrics)
        
        dashboard = ComparisonDashboard(comparator=comparator)
        comparison = dashboard.generate_metric_comparison("sharpe_ratio")
        
        assert comparison is not None
        assert len(comparison) == 3
        assert all(name in comparison for name in sample_metrics.keys())
    
    def test_generate_sparkline(self):
        """Test generating sparkline visualization."""
        dashboard = ComparisonDashboard()
        
        # Test with simple data
        data = [1.0, 1.5, 1.2, 1.8, 2.0, 1.7]
        sparkline = dashboard.generate_sparkline(data, width=10)
        
        assert sparkline is not None
        assert len(sparkline) <= 10
        # Should contain sparkline characters
        assert any(c in sparkline for c in "▁▂▃▄▅▆▇█")
    
    def test_generate_sparkline_empty(self):
        """Test sparkline with empty data."""
        dashboard = ComparisonDashboard()
        
        sparkline = dashboard.generate_sparkline([])
        assert sparkline == ""
    
    def test_generate_sparkline_single_value(self):
        """Test sparkline with single value."""
        dashboard = ComparisonDashboard()
        
        sparkline = dashboard.generate_sparkline([1.5])
        assert sparkline is not None
        assert len(sparkline) == 1
    
    def test_generate_performance_chart(self, sample_metrics):
        """Test generating performance comparison chart."""
        comparator = StrategyComparator()
        for name, metrics in sample_metrics.items():
            comparator.add_strategy(name, metrics)
        
        dashboard = ComparisonDashboard(comparator=comparator)
        chart = dashboard.generate_performance_chart()
        
        assert chart is not None
        # Should contain strategy names
        assert "Conservative" in chart
        assert "Aggressive" in chart
    
    def test_generate_risk_return_scatter(self, sample_metrics):
        """Test generating risk-return scatter plot."""
        comparator = StrategyComparator()
        for name, metrics in sample_metrics.items():
            comparator.add_strategy(name, metrics)
        
        dashboard = ComparisonDashboard(comparator=comparator)
        scatter = dashboard.generate_risk_return_scatter()
        
        assert scatter is not None
        # Should reference volatility and return
        assert any(word in scatter.lower() for word in ["risk", "return", "volatility"])
    
    def test_generate_full_dashboard(self, sample_metrics):
        """Test generating complete dashboard."""
        comparator = StrategyComparator()
        for name, metrics in sample_metrics.items():
            comparator.add_strategy(name, metrics)
        
        dashboard = ComparisonDashboard(comparator=comparator)
        full_output = dashboard.generate_dashboard()
        
        assert full_output is not None
        # Should contain multiple sections
        assert "Strategy Comparison" in full_output or "Comparison" in full_output
        assert "Conservative" in full_output
        assert "Aggressive" in full_output


# ============================================================================
# MetricType Tests
# ============================================================================

class TestMetricType:
    """Test the MetricType enum."""
    
    def test_metric_types_exist(self):
        """Test that metric type enum has expected values."""
        assert hasattr(MetricType, "RETURN")
        assert hasattr(MetricType, "RISK")
        assert hasattr(MetricType, "RATIO")
        assert hasattr(MetricType, "TRADE")
    
    def test_metric_type_classification(self):
        """Test classifying metrics by type."""
        # Return metrics
        assert MetricType.classify("total_return") == MetricType.RETURN
        assert MetricType.classify("annualized_return") == MetricType.RETURN
        
        # Risk metrics
        assert MetricType.classify("max_drawdown") == MetricType.RISK
        assert MetricType.classify("volatility") == MetricType.RISK
        
        # Ratio metrics
        assert MetricType.classify("sharpe_ratio") == MetricType.RATIO
        assert MetricType.classify("sortino_ratio") == MetricType.RATIO
        
        # Trade metrics
        assert MetricType.classify("total_trades") == MetricType.TRADE
        assert MetricType.classify("win_rate") == MetricType.TRADE


# ============================================================================
# RankingCriteria Tests
# ============================================================================

class TestRankingCriteria:
    """Test the RankingCriteria enum."""
    
    def test_ranking_criteria_exist(self):
        """Test that ranking criteria enum has expected values."""
        assert hasattr(RankingCriteria, "SHARPE_RATIO")
        assert hasattr(RankingCriteria, "TOTAL_RETURN")
        assert hasattr(RankingCriteria, "MAX_DRAWDOWN")
        assert hasattr(RankingCriteria, "WIN_RATE")
        assert hasattr(RankingCriteria, "PROFIT_FACTOR")
        assert hasattr(RankingCriteria, "RISK_ADJUSTED")
    
    def test_ranking_direction(self):
        """Test that ranking criteria specify correct direction."""
        # Higher is better
        assert RankingCriteria.SHARPE_RATIO.higher_is_better() is True
        assert RankingCriteria.TOTAL_RETURN.higher_is_better() is True
        assert RankingCriteria.WIN_RATE.higher_is_better() is True
        
        # Lower is better
        assert RankingCriteria.MAX_DRAWDOWN.higher_is_better() is False


# ============================================================================
# Integration Tests
# ============================================================================

class TestComparisonIntegration:
    """Test complete comparison workflow."""
    
    def test_full_comparison_workflow(self, sample_metrics):
        """Test complete strategy comparison workflow."""
        # Create comparator and add strategies
        comparator = StrategyComparator()
        
        for name, metrics in sample_metrics.items():
            comparator.add_strategy(name, metrics)
        
        # Verify all strategies added
        assert len(comparator.get_all_strategies()) == 3
        
        # Rank by different criteria
        by_sharpe = comparator.rank_strategies(RankingCriteria.SHARPE_RATIO)
        by_return = comparator.rank_strategies(RankingCriteria.TOTAL_RETURN)
        
        assert by_sharpe[0][0] == "Conservative"  # Best Sharpe
        assert by_return[0][0] == "Aggressive"     # Best return
        
        # Create dashboard and generate output
        dashboard = ComparisonDashboard(comparator=comparator)
        output = dashboard.generate_dashboard()
        
        assert output is not None
        assert len(output) > 0
    
    def test_comparison_differences(self, sample_metrics):
        """Test comparison differences calculation."""
        comparator = StrategyComparator()
        
        # Add strategies
        for name, metrics in sample_metrics.items():
            comparator.add_strategy(name, metrics)
        
        # Compare Conservative vs Aggressive
        comparison = comparator.compare_strategies("Conservative", "Aggressive")
        
        assert comparison is not None
        
        # Conservative should have:
        # - Lower return but higher Sharpe
        # - Lower drawdown
        # - Higher win rate
        diffs = comparison["differences"]
        assert diffs["sharpe_ratio"] > 0
        assert diffs["total_return"] < 0
        assert diffs["max_drawdown"] < 0
        assert diffs["win_rate"] > 0
    
    def test_empty_dashboard(self):
        """Test dashboard with no strategies."""
        comparator = StrategyComparator()
        dashboard = ComparisonDashboard(comparator=comparator)
        
        # Should handle empty state gracefully
        output = dashboard.generate_dashboard()
        assert output is not None
        assert "No strategies" in output or "Empty" in output or len(output) == 0
