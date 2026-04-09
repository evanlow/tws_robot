"""
Tests for Backtesting Engine Core Components

Tests for Strategy base class and BacktestEngine.

Author: TWS Robot Development Team
Date: November 2025
Week 4 Day 2
"""

import unittest
from datetime import datetime, timedelta
from pathlib import Path
import sys

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from backtest import (
    Strategy,
    StrategyConfig,
    StrategyState,
    BacktestEngine,
    BacktestConfig,
    BacktestResult,
    HistoricalDataManager,
    MarketData,
    Bar
)


class SimpleTestStrategy(Strategy):
    """Simple strategy for testing"""
    
    def __init__(self, config: StrategyConfig):
        super().__init__(config)
        self.bar_count = 0
        self.trade_count = 0
        self.started = False
        self.stopped = False
    
    def on_start(self):
        self.started = True
    
    def on_bar(self, market_data: MarketData):
        self.bar_count += 1
        
        # Buy on first bar
        if self.bar_count == 1:
            for symbol in self.config.symbols:
                price = market_data.get_close(symbol)
                if price:
                    shares = self.calculate_position_size(symbol, price, 0.10)
                    if shares > 0:
                        self.buy(symbol, shares, 'MARKET')
    
    def on_stop(self):
        self.stopped = True
        # Close all positions
        for symbol in self.config.symbols:
            if self.has_position(symbol):
                self.close_position(symbol)
    
    def on_trade(self, trade):
        super().on_trade(trade)
        self.trade_count += 1


class TestStrategyConfig(unittest.TestCase):
    """Test StrategyConfig"""
    
    def test_valid_config(self):
        """Test creating valid config"""
        config = StrategyConfig(
            name="TestStrategy",
            symbols=['AAPL', 'MSFT'],
            initial_capital=100000.0,
            max_position_size=0.10
        )
        
        self.assertEqual(config.name, "TestStrategy")
        self.assertEqual(len(config.symbols), 2)
        self.assertEqual(config.initial_capital, 100000.0)
        self.assertEqual(config.max_position_size, 0.10)
    
    def test_invalid_capital(self):
        """Test that negative capital raises error"""
        with self.assertRaises(ValueError):
            StrategyConfig(
                name="Test",
                symbols=['AAPL'],
                initial_capital=-1000.0
            )
    
    def test_invalid_position_size(self):
        """Test that invalid position size raises error"""
        with self.assertRaises(ValueError):
            StrategyConfig(
                name="Test",
                symbols=['AAPL'],
                max_position_size=1.5  # Over 100%
            )


class TestStrategyState(unittest.TestCase):
    """Test StrategyState"""
    
    def test_state_initialization(self):
        """Test state initialization"""
        state = StrategyState(
            equity=100000.0,
            cash=100000.0
        )
        
        self.assertEqual(state.equity, 100000.0)
        self.assertEqual(state.cash, 100000.0)
        self.assertEqual(state.total_trades, 0)
        self.assertEqual(state.peak_equity, 100000.0)
    
    def test_drawdown_tracking(self):
        """Test drawdown calculation"""
        state = StrategyState(
            equity=100000.0,
            cash=100000.0
        )
        
        # Equity increases - peak updates
        state.update_equity(110000.0)
        self.assertEqual(state.peak_equity, 110000.0)
        self.assertEqual(state.max_drawdown, 0.0)
        
        # Equity drops - drawdown calculated
        state.update_equity(99000.0)  # 10% drop from peak
        self.assertEqual(state.peak_equity, 110000.0)
        self.assertAlmostEqual(state.max_drawdown, 0.10, places=2)


class TestStrategy(unittest.TestCase):
    """Test Strategy base class"""
    
    def setUp(self):
        """Create test strategy"""
        config = StrategyConfig(
            name="SimpleTest",
            symbols=['AAPL'],
            initial_capital=100000.0,
            parameters={'test_param': 42}
        )
        self.strategy = SimpleTestStrategy(config)
    
    def test_strategy_initialization(self):
        """Test strategy initializes correctly"""
        self.assertEqual(self.strategy.config.name, "SimpleTest")
        self.assertEqual(self.strategy.state.equity, 100000.0)
        self.assertEqual(self.strategy.state.cash, 100000.0)
        self.assertFalse(self.strategy.started)
        self.assertFalse(self.strategy.stopped)
    
    def test_lifecycle_callbacks(self):
        """Test on_start and on_stop called"""
        self.strategy.on_start()
        self.assertTrue(self.strategy.started)
        
        self.strategy.on_stop()
        self.assertTrue(self.strategy.stopped)
    
    def test_position_queries(self):
        """Test position query methods"""
        # Initially flat
        self.assertTrue(self.strategy.is_flat('AAPL'))
        self.assertFalse(self.strategy.has_position('AAPL'))
        self.assertFalse(self.strategy.is_long('AAPL'))
        self.assertFalse(self.strategy.is_short('AAPL'))
    
    def test_position_size_calculation(self):
        """Test position size calculation"""
        # 10% of $100k at $150/share
        shares = self.strategy.calculate_position_size('AAPL', 150.0, 0.10)
        expected = int((100000.0 * 0.10) / 150.0)
        self.assertEqual(shares, expected)
    
    def test_bar_history_tracking(self):
        """Test bar history is tracked"""
        # Create test bar
        bar = Bar(
            timestamp=datetime(2024, 1, 1),
            symbol='AAPL',
            open=150.0,
            high=152.0,
            low=149.0,
            close=151.0,
            volume=1000000
        )
        
        # Create market data
        md = MarketData(timestamp=datetime(2024, 1, 1))
        md.add_bar('AAPL', bar)
        
        # Update strategy
        self.strategy._update_bar(md)
        
        # Check history
        history = self.strategy.get_bar_history('AAPL')
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0].close, 151.0)
        
        # Check price
        self.assertEqual(self.strategy.get_current_price('AAPL'), 151.0)


class TestBacktestConfig(unittest.TestCase):
    """Test BacktestConfig"""
    
    def test_valid_config(self):
        """Test creating valid backtest config"""
        config = BacktestConfig(
            start_date=datetime(2024, 1, 1),
            end_date=datetime(2024, 12, 31),
            initial_capital=100000.0
        )
        
        self.assertEqual(config.initial_capital, 100000.0)
        self.assertTrue(config.track_equity_curve)
        self.assertFalse(config.use_risk_management)


class TestBacktestEngine(unittest.TestCase):
    """Test BacktestEngine"""
    
    def setUp(self):
        """Setup test environment"""
        # Load real data
        self.data_mgr = HistoricalDataManager('data/historical')
        
        # Load one symbol for testing
        success = self.data_mgr.load_csv(
            'AAPL',
            'data/historical/AAPL_daily.csv'
        )
        
        if not success:
            self.skipTest("Test data not available")
        
        # Create strategy config
        self.strategy_config = StrategyConfig(
            name="TestStrategy",
            symbols=['AAPL'],
            initial_capital=100000.0
        )
        
        # Create backtest config
        self.backtest_config = BacktestConfig(
            start_date=datetime(2024, 1, 1),
            end_date=datetime(2024, 3, 31),  # Just Q1 for faster tests
            initial_capital=100000.0,
            track_equity_curve=True
        )
    
    def test_engine_initialization(self):
        """Test engine initializes correctly"""
        engine = BacktestEngine(self.backtest_config, self.data_mgr)
        
        self.assertEqual(engine.cash, 100000.0)
        self.assertEqual(len(engine.positions), 0)
        self.assertIsNotNone(engine.market_sim)
    
    def test_strategy_attachment(self):
        """Test attaching strategy to engine"""
        engine = BacktestEngine(self.backtest_config, self.data_mgr)
        strategy = SimpleTestStrategy(self.strategy_config)
        
        engine.set_strategy(strategy)
        
        self.assertEqual(engine.strategy, strategy)
        self.assertIsNotNone(strategy._submit_order_callback)
        self.assertIsNotNone(strategy._get_position_callback)
    
    def test_backtest_execution(self):
        """Test running a backtest"""
        engine = BacktestEngine(self.backtest_config, self.data_mgr)
        strategy = SimpleTestStrategy(self.strategy_config)
        engine.set_strategy(strategy)
        
        # Run backtest
        result = engine.run()
        
        # Verify result structure
        self.assertIsInstance(result, BacktestResult)
        self.assertEqual(result.strategy_name, "TestStrategy")
        self.assertGreater(result.total_trades, 0)  # Should have executed trades
        
        # Verify strategy callbacks were called
        self.assertTrue(strategy.started)
        self.assertTrue(strategy.stopped)
        self.assertGreater(strategy.bar_count, 0)
        
        print(f"\n  ✓ Backtest executed: {result.total_trades} trades, "
              f"{result.get_return_pct():.2f}% return")
    
    def test_equity_curve_tracking(self):
        """Test equity curve is tracked"""
        engine = BacktestEngine(self.backtest_config, self.data_mgr)
        strategy = SimpleTestStrategy(self.strategy_config)
        engine.set_strategy(strategy)
        
        result = engine.run()
        
        # Should have equity curve points
        self.assertGreater(len(result.equity_curve), 0)
        
        # First point should be initial capital
        first_point = result.equity_curve[0]
        self.assertEqual(first_point.equity, 100000.0)
        
        print(f"  ✓ Equity curve: {len(result.equity_curve)} points tracked")
    
    def test_portfolio_tracking(self):
        """Test portfolio state tracking"""
        engine = BacktestEngine(self.backtest_config, self.data_mgr)
        strategy = SimpleTestStrategy(self.strategy_config)
        engine.set_strategy(strategy)
        
        result = engine.run()
        
        # Should have final equity
        self.assertGreater(result.final_equity, 0)
        self.assertNotEqual(result.final_equity, result.initial_capital)
        
        # Should track return
        expected_return = (result.final_equity - result.initial_capital) / result.initial_capital
        self.assertAlmostEqual(result.total_return, expected_return, places=4)
        
        print(f"  ✓ Final equity: ${result.final_equity:,.2f} "
              f"({result.get_return_pct():.2f}%)")
    
    def test_drawdown_tracking(self):
        """Test drawdown is tracked"""
        engine = BacktestEngine(self.backtest_config, self.data_mgr)
        strategy = SimpleTestStrategy(self.strategy_config)
        engine.set_strategy(strategy)
        
        result = engine.run()
        
        # Should have tracked max drawdown
        self.assertGreaterEqual(result.max_drawdown_pct, 0.0)
        
        print(f"  ✓ Max drawdown: {result.max_drawdown_pct * 100:.2f}%")
    
    def test_trade_statistics(self):
        """Test trade statistics calculation"""
        engine = BacktestEngine(self.backtest_config, self.data_mgr)
        strategy = SimpleTestStrategy(self.strategy_config)
        engine.set_strategy(strategy)
        
        result = engine.run()
        
        # Should have trade stats
        self.assertEqual(result.total_trades, result.winning_trades + result.losing_trades)
        
        if result.total_trades > 0:
            self.assertGreaterEqual(result.win_rate, 0.0)
            self.assertLessEqual(result.win_rate, 1.0)
        
        print(f"  ✓ Trades: {result.total_trades} "
              f"(W:{result.winning_trades} L:{result.losing_trades}, "
              f"WR:{result.get_win_rate_pct():.1f}%)")


def run_tests():
    """Run all tests"""
    print("\n" + "="*70)
    print("Testing Backtesting Engine Core - Week 4 Day 2")
    print("="*70 + "\n")
    
    # Create test suite
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    
    # Add all test classes
    suite.addTests(loader.loadTestsFromTestCase(TestStrategyConfig))
    suite.addTests(loader.loadTestsFromTestCase(TestStrategyState))
    suite.addTests(loader.loadTestsFromTestCase(TestStrategy))
    suite.addTests(loader.loadTestsFromTestCase(TestBacktestConfig))
    suite.addTests(loader.loadTestsFromTestCase(TestBacktestEngine))
    
    # Run tests
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    # Print summary
    print("\n" + "="*70)
    print("Test Summary")
    print("="*70)
    print(f"Tests run: {result.testsRun}")
    print(f"Failures: {len(result.failures)}")
    print(f"Errors: {len(result.errors)}")
    print(f"Success rate: {(result.testsRun - len(result.failures) - len(result.errors)) / result.testsRun * 100:.1f}%")
    print("="*70 + "\n")
    
    return result.wasSuccessful()


if __name__ == '__main__':
    success = run_tests()
    sys.exit(0 if success else 1)
