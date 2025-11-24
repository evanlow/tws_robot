"""
Sprint 3 Task 4: Performance Attribution System Tests
Tests for analyzing P&L sources, trade attribution, and performance breakdown.
"""

import pytest
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Dict, List
import logging

from strategies.performance_attribution import (
    PerformanceAttribution,
    AttributionBreakdown,
    TradeAttribution,
    AttributionMetric,
    AttributionPeriod
)


# ============================================================================
# Test Fixtures
# ============================================================================

@pytest.fixture
def sample_trades():
    """Create sample trade data for attribution analysis."""
    base_time = datetime(2025, 1, 1, 9, 30)
    
    trades = [
        {
            "symbol": "AAPL",
            "entry_time": base_time,
            "exit_time": base_time + timedelta(hours=2),
            "entry_price": 150.00,
            "exit_price": 153.00,
            "quantity": 100,
            "pnl": 300.00,
            "strategy": "MA_Cross",
            "commission": 2.00
        },
        {
            "symbol": "AAPL",
            "entry_time": base_time + timedelta(days=1),
            "exit_time": base_time + timedelta(days=1, hours=3),
            "entry_price": 152.00,
            "exit_price": 151.00,
            "quantity": 100,
            "pnl": -100.00,
            "strategy": "MA_Cross",
            "commission": 2.00
        },
        {
            "symbol": "MSFT",
            "entry_time": base_time + timedelta(days=2),
            "exit_time": base_time + timedelta(days=2, hours=4),
            "entry_price": 380.00,
            "exit_price": 385.00,
            "quantity": 50,
            "pnl": 250.00,
            "strategy": "Mean_Reversion",
            "commission": 2.00
        },
        {
            "symbol": "GOOGL",
            "entry_time": base_time + timedelta(days=3),
            "exit_time": base_time + timedelta(days=3, hours=1),
            "entry_price": 140.00,
            "exit_price": 142.50,
            "quantity": 80,
            "pnl": 200.00,
            "strategy": "Momentum",
            "commission": 2.00
        },
        {
            "symbol": "TSLA",
            "entry_time": base_time + timedelta(days=4),
            "exit_time": base_time + timedelta(days=4, hours=5),
            "entry_price": 250.00,
            "exit_price": 245.00,
            "quantity": 40,
            "pnl": -200.00,
            "strategy": "Momentum",
            "commission": 2.00
        },
    ]
    
    return trades


@pytest.fixture
def sample_attribution():
    """Create sample attribution data."""
    return {
        "total_pnl": 450.00,
        "by_strategy": {
            "MA_Cross": 200.00,
            "Mean_Reversion": 250.00,
            "Momentum": 0.00
        },
        "by_symbol": {
            "AAPL": 200.00,
            "MSFT": 250.00,
            "GOOGL": 200.00,
            "TSLA": -200.00
        },
        "by_period": {
            "2025-01-01": 300.00,
            "2025-01-02": -100.00,
            "2025-01-03": 250.00,
            "2025-01-04": 200.00,
            "2025-01-05": -200.00
        }
    }


# ============================================================================
# TradeAttribution Tests
# ============================================================================

class TestTradeAttribution:
    """Test the TradeAttribution data class."""
    
    def test_trade_attribution_creation(self, sample_trades):
        """Test creating TradeAttribution from trade dict."""
        trade = sample_trades[0]
        attribution = TradeAttribution.from_dict(trade)
        
        assert attribution.symbol == "AAPL"
        assert attribution.pnl == 300.00
        assert attribution.strategy == "MA_Cross"
        assert attribution.quantity == 100
        assert attribution.commission == 2.00
    
    def test_trade_attribution_net_pnl(self, sample_trades):
        """Test net P&L calculation (after commissions)."""
        trade = sample_trades[0]
        attribution = TradeAttribution.from_dict(trade)
        
        net_pnl = attribution.get_net_pnl()
        assert net_pnl == 298.00  # 300 - 2
    
    def test_trade_attribution_return_pct(self, sample_trades):
        """Test return percentage calculation."""
        trade = sample_trades[0]
        attribution = TradeAttribution.from_dict(trade)
        
        return_pct = attribution.get_return_pct()
        # (153 - 150) / 150 = 2%
        assert abs(return_pct - 2.0) < 0.01
    
    def test_trade_attribution_hold_time(self, sample_trades):
        """Test hold time calculation."""
        trade = sample_trades[0]
        attribution = TradeAttribution.from_dict(trade)
        
        hold_hours = attribution.get_hold_time_hours()
        assert hold_hours == 2.0
    
    def test_trade_attribution_to_dict(self, sample_trades):
        """Test converting to dictionary."""
        trade = sample_trades[0]
        attribution = TradeAttribution.from_dict(trade)
        data = attribution.to_dict()
        
        assert data["symbol"] == "AAPL"
        assert data["pnl"] == 300.00
        assert data["strategy"] == "MA_Cross"


# ============================================================================
# AttributionBreakdown Tests
# ============================================================================

class TestAttributionBreakdown:
    """Test the AttributionBreakdown class."""
    
    def test_breakdown_creation(self):
        """Test creating an attribution breakdown."""
        breakdown = AttributionBreakdown(metric=AttributionMetric.STRATEGY)
        
        assert breakdown.metric == AttributionMetric.STRATEGY
        assert len(breakdown.get_all_keys()) == 0
    
    def test_add_attribution(self):
        """Test adding attribution to breakdown."""
        breakdown = AttributionBreakdown(metric=AttributionMetric.STRATEGY)
        
        breakdown.add_attribution("MA_Cross", 100.00)
        breakdown.add_attribution("Mean_Reversion", 50.00)
        
        assert breakdown.get_attribution("MA_Cross") == 100.00
        assert breakdown.get_attribution("Mean_Reversion") == 50.00
    
    def test_add_attribution_accumulates(self):
        """Test that multiple additions accumulate."""
        breakdown = AttributionBreakdown(metric=AttributionMetric.STRATEGY)
        
        breakdown.add_attribution("MA_Cross", 100.00)
        breakdown.add_attribution("MA_Cross", 50.00)
        
        assert breakdown.get_attribution("MA_Cross") == 150.00
    
    def test_get_total(self):
        """Test getting total attribution."""
        breakdown = AttributionBreakdown(metric=AttributionMetric.STRATEGY)
        
        breakdown.add_attribution("MA_Cross", 100.00)
        breakdown.add_attribution("Mean_Reversion", 50.00)
        breakdown.add_attribution("Momentum", -30.00)
        
        assert breakdown.get_total() == 120.00
    
    def test_get_all_keys(self):
        """Test getting all attribution keys."""
        breakdown = AttributionBreakdown(metric=AttributionMetric.SYMBOL)
        
        breakdown.add_attribution("AAPL", 100.00)
        breakdown.add_attribution("MSFT", 50.00)
        
        keys = breakdown.get_all_keys()
        assert len(keys) == 2
        assert "AAPL" in keys
        assert "MSFT" in keys
    
    def test_get_sorted_by_contribution(self):
        """Test sorting by contribution (descending)."""
        breakdown = AttributionBreakdown(metric=AttributionMetric.STRATEGY)
        
        breakdown.add_attribution("MA_Cross", 50.00)
        breakdown.add_attribution("Mean_Reversion", 150.00)
        breakdown.add_attribution("Momentum", 100.00)
        
        sorted_items = breakdown.get_sorted_by_contribution()
        
        assert len(sorted_items) == 3
        assert sorted_items[0][0] == "Mean_Reversion"
        assert sorted_items[1][0] == "Momentum"
        assert sorted_items[2][0] == "MA_Cross"
    
    def test_get_percentage_contribution(self):
        """Test calculating percentage contribution."""
        breakdown = AttributionBreakdown(metric=AttributionMetric.STRATEGY)
        
        breakdown.add_attribution("MA_Cross", 100.00)
        breakdown.add_attribution("Mean_Reversion", 200.00)
        breakdown.add_attribution("Momentum", 100.00)
        
        # Total = 400, MA_Cross = 100
        pct = breakdown.get_percentage_contribution("MA_Cross")
        assert abs(pct - 25.0) < 0.01
    
    def test_get_percentage_contribution_zero_total(self):
        """Test percentage contribution when total is zero."""
        breakdown = AttributionBreakdown(metric=AttributionMetric.STRATEGY)
        
        pct = breakdown.get_percentage_contribution("MA_Cross")
        assert pct == 0.0


# ============================================================================
# PerformanceAttribution Tests
# ============================================================================

class TestPerformanceAttribution:
    """Test the PerformanceAttribution analyzer."""
    
    def test_attribution_initialization(self):
        """Test basic initialization."""
        attribution = PerformanceAttribution()
        
        assert attribution is not None
        assert attribution.get_total_pnl() == 0.0
    
    def test_add_trade(self, sample_trades):
        """Test adding a single trade."""
        attribution = PerformanceAttribution()
        
        trade = sample_trades[0]
        attribution.add_trade(trade)
        
        assert attribution.get_total_pnl() == 300.00
    
    def test_add_multiple_trades(self, sample_trades):
        """Test adding multiple trades."""
        attribution = PerformanceAttribution()
        
        for trade in sample_trades:
            attribution.add_trade(trade)
        
        # Total: 300 - 100 + 250 + 200 - 200 = 450
        assert attribution.get_total_pnl() == 450.00
    
    def test_get_attribution_by_strategy(self, sample_trades):
        """Test attribution breakdown by strategy."""
        attribution = PerformanceAttribution()
        
        for trade in sample_trades:
            attribution.add_trade(trade)
        
        by_strategy = attribution.get_attribution_by(AttributionMetric.STRATEGY)
        
        # MA_Cross: 300 - 100 = 200
        assert by_strategy.get_attribution("MA_Cross") == 200.00
        # Mean_Reversion: 250
        assert by_strategy.get_attribution("Mean_Reversion") == 250.00
        # Momentum: 200 - 200 = 0
        assert by_strategy.get_attribution("Momentum") == 0.00
    
    def test_get_attribution_by_symbol(self, sample_trades):
        """Test attribution breakdown by symbol."""
        attribution = PerformanceAttribution()
        
        for trade in sample_trades:
            attribution.add_trade(trade)
        
        by_symbol = attribution.get_attribution_by(AttributionMetric.SYMBOL)
        
        # AAPL: 300 - 100 = 200
        assert by_symbol.get_attribution("AAPL") == 200.00
        # MSFT: 250
        assert by_symbol.get_attribution("MSFT") == 250.00
        # GOOGL: 200
        assert by_symbol.get_attribution("GOOGL") == 200.00
        # TSLA: -200
        assert by_symbol.get_attribution("TSLA") == -200.00
    
    def test_get_attribution_by_date(self, sample_trades):
        """Test attribution breakdown by date."""
        attribution = PerformanceAttribution()
        
        for trade in sample_trades:
            attribution.add_trade(trade)
        
        by_date = attribution.get_attribution_by(AttributionMetric.DATE)
        
        # Check that we have entries for each trading day
        dates = by_date.get_all_keys()
        assert len(dates) == 5
    
    def test_get_winning_trades(self, sample_trades):
        """Test filtering winning trades."""
        attribution = PerformanceAttribution()
        
        for trade in sample_trades:
            attribution.add_trade(trade)
        
        winners = attribution.get_winning_trades()
        
        # 3 winning trades: AAPL(300), MSFT(250), GOOGL(200)
        assert len(winners) == 3
        assert all(t.pnl > 0 for t in winners)
    
    def test_get_losing_trades(self, sample_trades):
        """Test filtering losing trades."""
        attribution = PerformanceAttribution()
        
        for trade in sample_trades:
            attribution.add_trade(trade)
        
        losers = attribution.get_losing_trades()
        
        # 2 losing trades: AAPL(-100), TSLA(-200)
        assert len(losers) == 2
        assert all(t.pnl < 0 for t in losers)
    
    def test_get_average_winner(self, sample_trades):
        """Test calculating average winning trade."""
        attribution = PerformanceAttribution()
        
        for trade in sample_trades:
            attribution.add_trade(trade)
        
        avg_winner = attribution.get_average_winner()
        
        # (300 + 250 + 200) / 3 = 250
        assert abs(avg_winner - 250.0) < 0.01
    
    def test_get_average_loser(self, sample_trades):
        """Test calculating average losing trade."""
        attribution = PerformanceAttribution()
        
        for trade in sample_trades:
            attribution.add_trade(trade)
        
        avg_loser = attribution.get_average_loser()
        
        # (-100 + -200) / 2 = -150
        assert abs(avg_loser - (-150.0)) < 0.01
    
    def test_get_largest_winner(self, sample_trades):
        """Test finding largest winning trade."""
        attribution = PerformanceAttribution()
        
        for trade in sample_trades:
            attribution.add_trade(trade)
        
        largest = attribution.get_largest_winner()
        
        assert largest is not None
        assert largest.symbol == "AAPL"
        assert largest.pnl == 300.00
    
    def test_get_largest_loser(self, sample_trades):
        """Test finding largest losing trade."""
        attribution = PerformanceAttribution()
        
        for trade in sample_trades:
            attribution.add_trade(trade)
        
        largest = attribution.get_largest_loser()
        
        assert largest is not None
        assert largest.symbol == "TSLA"
        assert largest.pnl == -200.00
    
    def test_get_win_rate(self, sample_trades):
        """Test calculating win rate."""
        attribution = PerformanceAttribution()
        
        for trade in sample_trades:
            attribution.add_trade(trade)
        
        win_rate = attribution.get_win_rate()
        
        # 3 winners out of 5 trades = 60%
        assert abs(win_rate - 0.60) < 0.01
    
    def test_generate_summary(self, sample_trades):
        """Test generating attribution summary."""
        attribution = PerformanceAttribution()
        
        for trade in sample_trades:
            attribution.add_trade(trade)
        
        summary = attribution.generate_summary()
        
        assert summary is not None
        assert "Total P&L" in summary or "total" in summary.lower()
        assert "450" in summary  # Total PnL
    
    def test_generate_breakdown_report(self, sample_trades):
        """Test generating detailed breakdown report."""
        attribution = PerformanceAttribution()
        
        for trade in sample_trades:
            attribution.add_trade(trade)
        
        report = attribution.generate_breakdown_report(AttributionMetric.STRATEGY)
        
        assert report is not None
        assert "MA_Cross" in report
        assert "Mean_Reversion" in report
        assert "Momentum" in report
    
    def test_empty_attribution(self):
        """Test attribution with no trades."""
        attribution = PerformanceAttribution()
        
        assert attribution.get_total_pnl() == 0.0
        assert len(attribution.get_winning_trades()) == 0
        assert len(attribution.get_losing_trades()) == 0
        assert attribution.get_win_rate() == 0.0


# ============================================================================
# AttributionMetric Tests
# ============================================================================

class TestAttributionMetric:
    """Test the AttributionMetric enum."""
    
    def test_metric_types_exist(self):
        """Test that all expected metric types exist."""
        assert hasattr(AttributionMetric, "STRATEGY")
        assert hasattr(AttributionMetric, "SYMBOL")
        assert hasattr(AttributionMetric, "DATE")
        assert hasattr(AttributionMetric, "HOUR")
        assert hasattr(AttributionMetric, "DAY_OF_WEEK")


# ============================================================================
# AttributionPeriod Tests
# ============================================================================

class TestAttributionPeriod:
    """Test the AttributionPeriod enum."""
    
    def test_period_types_exist(self):
        """Test that all expected period types exist."""
        assert hasattr(AttributionPeriod, "DAILY")
        assert hasattr(AttributionPeriod, "WEEKLY")
        assert hasattr(AttributionPeriod, "MONTHLY")
        assert hasattr(AttributionPeriod, "YEARLY")


# ============================================================================
# Integration Tests
# ============================================================================

class TestAttributionIntegration:
    """Test complete attribution workflows."""
    
    def test_full_attribution_workflow(self, sample_trades):
        """Test complete attribution analysis workflow."""
        attribution = PerformanceAttribution()
        
        # Add all trades
        for trade in sample_trades:
            attribution.add_trade(trade)
        
        # Verify total
        assert attribution.get_total_pnl() == 450.00
        
        # Get strategy breakdown
        by_strategy = attribution.get_attribution_by(AttributionMetric.STRATEGY)
        assert by_strategy.get_total() == 450.00
        
        # Get symbol breakdown
        by_symbol = attribution.get_attribution_by(AttributionMetric.SYMBOL)
        assert by_symbol.get_total() == 450.00
        
        # Verify win/loss stats
        assert len(attribution.get_winning_trades()) == 3
        assert len(attribution.get_losing_trades()) == 2
        assert attribution.get_win_rate() == 0.60
        
        # Generate reports
        summary = attribution.generate_summary()
        assert summary is not None
        
        strategy_report = attribution.generate_breakdown_report(AttributionMetric.STRATEGY)
        assert strategy_report is not None
    
    def test_strategy_performance_comparison(self, sample_trades):
        """Test comparing performance across strategies."""
        attribution = PerformanceAttribution()
        
        for trade in sample_trades:
            attribution.add_trade(trade)
        
        by_strategy = attribution.get_attribution_by(AttributionMetric.STRATEGY)
        sorted_strategies = by_strategy.get_sorted_by_contribution()
        
        # Mean_Reversion should be top (250)
        assert sorted_strategies[0][0] == "Mean_Reversion"
        assert sorted_strategies[0][1] == 250.00
        
        # MA_Cross should be second (200)
        assert sorted_strategies[1][0] == "MA_Cross"
        assert sorted_strategies[1][1] == 200.00
        
        # Momentum should be last (0)
        assert sorted_strategies[2][0] == "Momentum"
        assert sorted_strategies[2][1] == 0.00
    
    def test_symbol_performance_comparison(self, sample_trades):
        """Test comparing performance across symbols."""
        attribution = PerformanceAttribution()
        
        for trade in sample_trades:
            attribution.add_trade(trade)
        
        by_symbol = attribution.get_attribution_by(AttributionMetric.SYMBOL)
        sorted_symbols = by_symbol.get_sorted_by_contribution()
        
        # MSFT should be top (250)
        assert sorted_symbols[0][0] == "MSFT"
        assert sorted_symbols[0][1] == 250.00
        
        # TSLA should be last (-200)
        assert sorted_symbols[-1][0] == "TSLA"
        assert sorted_symbols[-1][1] == -200.00
    
    def test_percentage_contributions(self, sample_trades):
        """Test percentage contribution calculations."""
        attribution = PerformanceAttribution()
        
        for trade in sample_trades:
            attribution.add_trade(trade)
        
        by_strategy = attribution.get_attribution_by(AttributionMetric.STRATEGY)
        
        # Mean_Reversion: 250 / 450 = 55.56%
        pct = by_strategy.get_percentage_contribution("Mean_Reversion")
        assert abs(pct - 55.56) < 0.1
        
        # MA_Cross: 200 / 450 = 44.44%
        pct = by_strategy.get_percentage_contribution("MA_Cross")
        assert abs(pct - 44.44) < 0.1
        
        # Momentum: 0 / 450 = 0%
        pct = by_strategy.get_percentage_contribution("Momentum")
        assert abs(pct - 0.0) < 0.1
