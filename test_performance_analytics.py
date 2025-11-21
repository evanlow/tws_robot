"""
Unit Tests for Performance Analytics

Tests for Week 4 Day 3 performance analytics components:
- Trade data structures
- DrawdownPeriod analysis
- PerformanceAnalyzer calculations
- ReportGenerator output

Author: Trading Bot Team
Week 4 Day 3
"""

import unittest
import sys
from pathlib import Path
from datetime import datetime, timedelta
from typing import List, Tuple

# Add parent directory for imports
sys.path.insert(0, str(Path(__file__).parent))

from backtest.performance import (
    Trade,
    TradeDirection,
    DrawdownPeriod,
    PerformanceMetrics,
    PerformanceAnalyzer,
    ReportGenerator
)


class TestTrade(unittest.TestCase):
    """Test Trade data structure"""
    
    def test_winning_trade(self):
        """Test winning trade identification"""
        trade = Trade(
            symbol="AAPL",
            entry_date=datetime(2024, 1, 1),
            exit_date=datetime(2024, 1, 10),
            direction=TradeDirection.LONG,
            entry_price=150.0,
            exit_price=160.0,
            quantity=100,
            pnl=990.0,  # After commission
            pnl_pct=6.67,
            commission=10.0,
            duration_bars=10
        )
        
        self.assertTrue(trade.is_winner)
        self.assertEqual(trade.duration_days, 9.0)
    
    def test_losing_trade(self):
        """Test losing trade identification"""
        trade = Trade(
            symbol="MSFT",
            entry_date=datetime(2024, 1, 1),
            exit_date=datetime(2024, 1, 5),
            direction=TradeDirection.LONG,
            entry_price=300.0,
            exit_price=290.0,
            quantity=50,
            pnl=-510.0,  # Loss + commission
            pnl_pct=-3.33,
            commission=10.0,
            duration_bars=5
        )
        
        self.assertFalse(trade.is_winner)
        self.assertEqual(trade.duration_days, 4.0)


class TestDrawdownPeriod(unittest.TestCase):
    """Test DrawdownPeriod data structure"""
    
    def test_recovered_drawdown(self):
        """Test recovered drawdown period"""
        dd = DrawdownPeriod(
            start_date=datetime(2024, 1, 1),
            trough_date=datetime(2024, 1, 15),
            end_date=datetime(2024, 2, 1),
            peak_equity=100000.0,
            trough_equity=90000.0,
            recovery_equity=100000.0,
            drawdown_pct=10.0,
            duration_days=14,
            recovery_days=17
        )
        
        self.assertTrue(dd.is_recovered)
        self.assertEqual(dd.total_duration_days, 31)
    
    def test_unrecovered_drawdown(self):
        """Test ongoing drawdown period"""
        dd = DrawdownPeriod(
            start_date=datetime(2024, 1, 1),
            trough_date=datetime(2024, 1, 15),
            end_date=None,
            peak_equity=100000.0,
            trough_equity=85000.0,
            recovery_equity=None,
            drawdown_pct=15.0,
            duration_days=14,
            recovery_days=None
        )
        
        self.assertFalse(dd.is_recovered)
        self.assertIsNone(dd.total_duration_days)


class TestPerformanceAnalyzer(unittest.TestCase):
    """Test PerformanceAnalyzer calculations"""
    
    def setUp(self):
        """Set up test data"""
        self.analyzer = PerformanceAnalyzer(risk_free_rate=0.02)
        
        # Create sample equity curve (50 days)
        self.equity_curve = self._create_sample_equity_curve()
        
        # Create sample trades
        self.trades = self._create_sample_trades()
    
    def _create_sample_equity_curve(self) -> List[Tuple[datetime, float]]:
        """Create sample equity curve with growth and drawdown"""
        start_date = datetime(2024, 1, 1)
        equity_curve = []
        equity = 100000.0
        
        # Phase 1: Growth (20 days)
        for i in range(20):
            equity += 500.0  # Steady growth
            date = start_date + timedelta(days=i)
            equity_curve.append((date, equity))
        
        # Phase 2: Drawdown (10 days)
        for i in range(20, 30):
            equity -= 300.0  # Pullback
            date = start_date + timedelta(days=i)
            equity_curve.append((date, equity))
        
        # Phase 3: Recovery (20 days)
        for i in range(30, 50):
            equity += 400.0  # Recovery
            date = start_date + timedelta(days=i)
            equity_curve.append((date, equity))
        
        return equity_curve
    
    def _create_sample_trades(self) -> List[Trade]:
        """Create sample trades"""
        trades = [
            # Winners
            Trade(
                symbol="AAPL",
                entry_date=datetime(2024, 1, 5),
                exit_date=datetime(2024, 1, 10),
                direction=TradeDirection.LONG,
                entry_price=150.0,
                exit_price=155.0,
                quantity=100,
                pnl=490.0,
                pnl_pct=3.33,
                commission=10.0,
                duration_bars=5
            ),
            Trade(
                symbol="MSFT",
                entry_date=datetime(2024, 1, 15),
                exit_date=datetime(2024, 1, 20),
                direction=TradeDirection.LONG,
                entry_price=300.0,
                exit_price=315.0,
                quantity=50,
                pnl=740.0,
                pnl_pct=5.0,
                commission=10.0,
                duration_bars=5
            ),
            # Losers
            Trade(
                symbol="GOOGL",
                entry_date=datetime(2024, 1, 22),
                exit_date=datetime(2024, 1, 25),
                direction=TradeDirection.LONG,
                entry_price=140.0,
                exit_price=135.0,
                quantity=80,
                pnl=-410.0,
                pnl_pct=-3.57,
                commission=10.0,
                duration_bars=3
            ),
            Trade(
                symbol="TSLA",
                entry_date=datetime(2024, 2, 1),
                exit_date=datetime(2024, 2, 5),
                direction=TradeDirection.LONG,
                entry_price=200.0,
                exit_price=195.0,
                quantity=60,
                pnl=-310.0,
                pnl_pct=-2.5,
                commission=10.0,
                duration_bars=4
            ),
        ]
        return trades
    
    def test_analyze_returns_basic_metrics(self):
        """Test basic return calculations"""
        metrics = self.analyzer.analyze(
            equity_curve=self.equity_curve,
            trades=self.trades,
            initial_capital=100000.0
        )
        
        # Check period info
        self.assertEqual(metrics.trading_days, 50)
        self.assertEqual(metrics.initial_capital, 100000.0)
        
        # Check final equity (should be higher than initial)
        self.assertGreater(metrics.final_equity, metrics.initial_capital)
        
        # Check return calculations
        self.assertGreater(metrics.total_return, 0)
        self.assertGreater(metrics.total_return_pct, 0)
        
        print(f"  ✓ Final equity: ${metrics.final_equity:,.2f}")
        print(f"  ✓ Total return: {metrics.total_return_pct:.2f}%")
    
    def test_analyze_trade_statistics(self):
        """Test trade statistics calculations"""
        metrics = self.analyzer.analyze(
            equity_curve=self.equity_curve,
            trades=self.trades,
            initial_capital=100000.0
        )
        
        # Check trade counts
        self.assertEqual(metrics.total_trades, 4)
        self.assertEqual(metrics.winning_trades, 2)
        self.assertEqual(metrics.losing_trades, 2)
        self.assertEqual(metrics.win_rate, 50.0)
        
        # Check P&L stats
        self.assertGreater(metrics.avg_win, 0)
        self.assertLess(metrics.avg_loss, 0)
        
        # Largest win should be MSFT trade ($740)
        self.assertEqual(metrics.largest_win, 740.0)
        
        # Largest loss should be GOOGL trade (-$410)
        self.assertEqual(metrics.largest_loss, -410.0)
        
        print(f"  ✓ Win rate: {metrics.win_rate:.1f}%")
        print(f"  ✓ Profit factor: {metrics.profit_factor:.3f}")
        print(f"  ✓ Expectancy: ${metrics.expectancy:.2f}")
    
    def test_analyze_risk_metrics(self):
        """Test risk metric calculations"""
        metrics = self.analyzer.analyze(
            equity_curve=self.equity_curve,
            trades=self.trades,
            initial_capital=100000.0
        )
        
        # Should have some drawdown
        self.assertGreater(metrics.max_drawdown_pct, 0)
        
        # Should have volatility
        self.assertGreater(metrics.volatility, 0)
        
        # Risk-adjusted returns
        # Note: May be 0 if insufficient data, but shouldn't be negative for positive return
        self.assertGreaterEqual(metrics.sharpe_ratio, 0)
        
        print(f"  ✓ Max drawdown: {metrics.max_drawdown_pct:.2f}%")
        print(f"  ✓ Volatility: {metrics.volatility:.2f}%")
        print(f"  ✓ Sharpe ratio: {metrics.sharpe_ratio:.3f}")
    
    def test_drawdown_period_calculation(self):
        """Test drawdown period identification"""
        drawdown_periods = self.analyzer._calculate_drawdown_periods(self.equity_curve)
        
        # Should find at least one drawdown period
        self.assertGreater(len(drawdown_periods), 0)
        
        # First period should have meaningful drawdown
        first_dd = drawdown_periods[0]
        self.assertGreater(first_dd.drawdown_pct, 0)
        self.assertIsNotNone(first_dd.trough_date)
        
        print(f"  ✓ Found {len(drawdown_periods)} drawdown period(s)")
        print(f"  ✓ Largest drawdown: {first_dd.drawdown_pct:.2f}%")
    
    def test_profit_factor(self):
        """Test profit factor calculation"""
        metrics = self.analyzer.analyze(
            equity_curve=self.equity_curve,
            trades=self.trades,
            initial_capital=100000.0
        )
        
        # Gross profit = 490 + 740 = 1230
        # Gross loss = 410 + 310 = 720
        # Profit factor = 1230 / 720 = 1.708
        expected_pf = (490.0 + 740.0) / (410.0 + 310.0)
        
        self.assertAlmostEqual(metrics.profit_factor, expected_pf, places=2)
        self.assertGreater(metrics.profit_factor, 1.0)  # Profitable overall


class TestReportGenerator(unittest.TestCase):
    """Test ReportGenerator output"""
    
    def test_generate_text_report(self):
        """Test text report generation"""
        # Create sample metrics
        metrics = PerformanceMetrics(
            start_date=datetime(2024, 1, 1),
            end_date=datetime(2024, 12, 31),
            total_days=365,
            trading_days=252,
            initial_capital=100000.0,
            final_equity=115000.0,
            peak_equity=118000.0,
            total_return=15000.0,
            total_return_pct=15.0,
            annualized_return=15.5,
            max_drawdown=5000.0,
            max_drawdown_pct=4.24,
            volatility=12.5,
            downside_deviation=8.3,
            sharpe_ratio=1.2,
            sortino_ratio=1.8,
            calmar_ratio=3.65,
            total_trades=50,
            winning_trades=30,
            losing_trades=20,
            win_rate=60.0,
            avg_win=800.0,
            avg_loss=-400.0,
            largest_win=2500.0,
            largest_loss=-1200.0,
            profit_factor=1.5,
            expectancy=300.0,
            avg_trade_duration_days=5.2,
            avg_winning_duration_days=6.1,
            avg_losing_duration_days=4.0,
            avg_drawdown_pct=2.1,
            avg_recovery_days=8.5,
            max_drawdown_duration_days=15,
            avg_exposure_pct=65.0,
            max_positions=3
        )
        
        report = ReportGenerator.generate_text_report(metrics, "Test Report")
        
        # Check report contains key elements
        self.assertIn("Test Report", report)
        self.assertIn("RETURNS", report)
        self.assertIn("RISK METRICS", report)
        self.assertIn("TRADE STATISTICS", report)
        self.assertIn("$115,000.00", report)  # Final equity
        self.assertIn("+15.00%", report)  # Total return
        self.assertIn("60.00%", report)  # Win rate
        
        print("  ✓ Text report generated successfully")
        print(f"  ✓ Report length: {len(report)} characters")
    
    def test_generate_html_report(self):
        """Test HTML report generation"""
        metrics = PerformanceMetrics(
            start_date=datetime(2024, 1, 1),
            end_date=datetime(2024, 12, 31),
            total_days=365,
            trading_days=252,
            initial_capital=100000.0,
            final_equity=115000.0,
            peak_equity=118000.0,
            total_return=15000.0,
            total_return_pct=15.0,
            annualized_return=15.5,
            max_drawdown=5000.0,
            max_drawdown_pct=4.24,
            volatility=12.5,
            downside_deviation=8.3,
            sharpe_ratio=1.2,
            sortino_ratio=1.8,
            calmar_ratio=3.65,
            total_trades=50,
            winning_trades=30,
            losing_trades=20,
            win_rate=60.0,
            avg_win=800.0,
            avg_loss=-400.0,
            largest_win=2500.0,
            largest_loss=-1200.0,
            profit_factor=1.5,
            expectancy=300.0,
            avg_trade_duration_days=5.2,
            avg_winning_duration_days=6.1,
            avg_losing_duration_days=4.0,
            avg_drawdown_pct=2.1,
            avg_recovery_days=8.5,
            max_drawdown_duration_days=15,
            avg_exposure_pct=65.0,
            max_positions=3
        )
        
        html = ReportGenerator.generate_html_report(metrics, "Test Report")
        
        # Check HTML structure
        self.assertIn("<!DOCTYPE html>", html)
        self.assertIn("<html>", html)
        self.assertIn("Test Report", html)
        self.assertIn("$115,000.00", html)
        
        print("  ✓ HTML report generated successfully")
        print(f"  ✓ HTML length: {len(html)} characters")
    
    def test_metrics_to_dict(self):
        """Test metrics dictionary conversion"""
        metrics = PerformanceMetrics(
            start_date=datetime(2024, 1, 1),
            end_date=datetime(2024, 12, 31),
            total_days=365,
            trading_days=252,
            initial_capital=100000.0,
            final_equity=115000.0,
            peak_equity=118000.0,
            total_return=15000.0,
            total_return_pct=15.0,
            annualized_return=15.5,
            max_drawdown=5000.0,
            max_drawdown_pct=4.24,
            volatility=12.5,
            downside_deviation=8.3,
            sharpe_ratio=1.2,
            sortino_ratio=1.8,
            calmar_ratio=3.65,
            total_trades=50,
            winning_trades=30,
            losing_trades=20,
            win_rate=60.0,
            avg_win=800.0,
            avg_loss=-400.0,
            largest_win=2500.0,
            largest_loss=-1200.0,
            profit_factor=1.5,
            expectancy=300.0,
            avg_trade_duration_days=5.2,
            avg_winning_duration_days=6.1,
            avg_losing_duration_days=4.0,
            avg_drawdown_pct=2.1,
            avg_recovery_days=8.5,
            max_drawdown_duration_days=15,
            avg_exposure_pct=65.0,
            max_positions=3
        )
        
        data = metrics.to_dict()
        
        # Check structure
        self.assertIn('period', data)
        self.assertIn('returns', data)
        self.assertIn('risk', data)
        self.assertIn('risk_adjusted', data)
        self.assertIn('trades', data)
        
        # Check values
        self.assertEqual(data['returns']['final_equity'], 115000.0)
        self.assertEqual(data['trades']['total_trades'], 50)
        self.assertEqual(data['risk_adjusted']['sharpe_ratio'], 1.2)
        
        print("  ✓ Metrics converted to dictionary")
        print(f"  ✓ Dictionary keys: {list(data.keys())}")


def main():
    """Run all tests"""
    print("\n" + "="*80)
    print("Testing Performance Analytics - Week 4 Day 3")
    print("="*80 + "\n")
    
    # Create test suite
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    
    # Add test cases
    suite.addTests(loader.loadTestsFromTestCase(TestTrade))
    suite.addTests(loader.loadTestsFromTestCase(TestDrawdownPeriod))
    suite.addTests(loader.loadTestsFromTestCase(TestPerformanceAnalyzer))
    suite.addTests(loader.loadTestsFromTestCase(TestReportGenerator))
    
    # Run tests with verbose output
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    # Summary
    print("\n" + "="*80)
    print("Test Summary")
    print("="*80)
    print(f"Tests run: {result.testsRun}")
    print(f"Failures: {len(result.failures)}")
    print(f"Errors: {len(result.errors)}")
    print(f"Success rate: {((result.testsRun - len(result.failures) - len(result.errors)) / result.testsRun * 100):.1f}%")
    print("="*80 + "\n")
    
    return result.wasSuccessful()


if __name__ == '__main__':
    success = main()
    sys.exit(0 if success else 1)
