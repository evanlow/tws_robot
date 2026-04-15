"""
Tests for Backtesting Data Components

Tests for data models, data manager, and market simulator.

Author: TWS Robot Development Team
Date: November 2025
Week 4 Day 1
"""

import unittest
from datetime import datetime, timedelta
from pathlib import Path
import sys
import pytest

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from backtest.data_models import Bar, MarketData, BarSeries, TimeFrame, Position, Trade
from backtest.data_manager import HistoricalDataManager
from backtest.market_simulator import MarketSimulator, FillSimulator, Order

# Check for test data availability
PROJECT_ROOT = Path(__file__).parent.parent
TEST_DATA_DIR = PROJECT_ROOT / "data" / "historical"
HAS_TEST_DATA = TEST_DATA_DIR.exists() and any(TEST_DATA_DIR.glob("*.csv"))


class TestBar(unittest.TestCase):
    """Test Bar data model"""
    
    def test_bar_creation(self):
        """Test creating a valid bar"""
        bar = Bar(
            timestamp=datetime(2024, 1, 1, 9, 30),
            symbol='AAPL',
            open=150.0,
            high=152.0,
            low=149.0,
            close=151.0,
            volume=1000000
        )
        
        self.assertEqual(bar.symbol, 'AAPL')
        self.assertEqual(bar.close, 151.0)
        self.assertTrue(bar.is_bullish)
        self.assertFalse(bar.is_bearish)
    
    def test_bar_validation(self):
        """Test bar data validation"""
        # High < Low should fail
        with self.assertRaises(ValueError):
            Bar(
                timestamp=datetime(2024, 1, 1),
                symbol='AAPL',
                open=150.0,
                high=149.0,  # Invalid: high < low
                low=151.0,
                close=150.5,
                volume=1000
            )
    
    def test_bar_properties(self):
        """Test bar calculated properties"""
        bar = Bar(
            timestamp=datetime(2024, 1, 1),
            symbol='AAPL',
            open=100.0,
            high=105.0,
            low=98.0,
            close=103.0,
            volume=1000000
        )
        
        # Test typical price: (H + L + C) / 3
        expected_typical = (105.0 + 98.0 + 103.0) / 3
        self.assertAlmostEqual(bar.typical_price, expected_typical, places=2)
        
        # Test range
        self.assertEqual(bar.range, 7.0)  # 105 - 98
        
        # Test body
        self.assertEqual(bar.body, 3.0)  # |103 - 100|
        
        # Test bullish
        self.assertTrue(bar.is_bullish)


class TestMarketData(unittest.TestCase):
    """Test MarketData container"""
    
    def test_market_data_creation(self):
        """Test creating market data"""
        md = MarketData(timestamp=datetime(2024, 1, 1))
        
        bar = Bar(
            timestamp=datetime(2024, 1, 1),
            symbol='AAPL',
            open=150.0,
            high=152.0,
            low=149.0,
            close=151.0,
            volume=1000000
        )
        
        md.add_bar('AAPL', bar)
        
        self.assertTrue(md.has_symbol('AAPL'))
        self.assertEqual(md.get_close('AAPL'), 151.0)
        self.assertEqual(len(md.symbols), 1)
    
    def test_multiple_symbols(self):
        """Test market data with multiple symbols"""
        md = MarketData(timestamp=datetime(2024, 1, 1))
        
        for symbol in ['AAPL', 'MSFT', 'GOOGL']:
            bar = Bar(
                timestamp=datetime(2024, 1, 1),
                symbol=symbol,
                open=100.0,
                high=102.0,
                low=99.0,
                close=101.0,
                volume=1000000
            )
            md.add_bar(symbol, bar)
        
        self.assertEqual(len(md.symbols), 3)
        self.assertTrue(all(md.has_symbol(s) for s in ['AAPL', 'MSFT', 'GOOGL']))


class TestBarSeries(unittest.TestCase):
    """Test BarSeries container"""
    
    def setUp(self):
        """Create test bar series"""
        self.series = BarSeries(symbol='AAPL')
        
        # Add 10 bars
        for i in range(10):
            bar = Bar(
                timestamp=datetime(2024, 1, 1) + timedelta(days=i),
                symbol='AAPL',
                open=100.0 + i,
                high=102.0 + i,
                low=99.0 + i,
                close=101.0 + i,
                volume=1000000
            )
            self.series.add_bar(bar)
    
    def test_bar_series_basics(self):
        """Test basic bar series operations"""
        self.assertEqual(len(self.series), 10)
        self.assertEqual(self.series.count, 10)
        self.assertIsNotNone(self.series.latest)
        self.assertEqual(self.series.latest.close, 110.0)  # 101 + 9
    
    def test_lookback(self):
        """Test lookback functionality"""
        # Get last 5 bars
        recent = self.series.get_bars(lookback=5)
        self.assertEqual(len(recent), 5)
        
        # Get closes
        closes = self.series.get_closes(lookback=3)
        self.assertEqual(len(closes), 3)
        self.assertEqual(closes[-1], 110.0)  # Most recent


class TestHistoricalDataManager(unittest.TestCase):
    """Test Historical Data Manager"""
    
    def setUp(self):
        """Setup data manager with sample data"""
        self.data_mgr = HistoricalDataManager('data/historical')
    
    @pytest.mark.skipif(not HAS_TEST_DATA, reason="Test data files not found in data/historical/")
    def test_load_csv(self):
        """Test loading CSV data"""
        success = self.data_mgr.load_csv(
            symbol='AAPL',
            filepath='data/historical/AAPL_daily.csv',
            format='standard'
        )
        
        self.assertTrue(success)
        self.assertIn('AAPL', self.data_mgr.get_symbols())
        
        # Check metadata
        date_range = self.data_mgr.get_date_range('AAPL')
        self.assertIsNotNone(date_range)
        
        bar_count = self.data_mgr.get_bar_count('AAPL')
        self.assertGreater(bar_count, 0)
        
        print(f"✓ Loaded {bar_count} bars for AAPL")
        print(f"  Date range: {date_range[0].date()} to {date_range[1].date()}")
    
    @pytest.mark.skipif(not HAS_TEST_DATA, reason="Test data files not found in data/historical/")
    def test_get_bars(self):
        """Test retrieving bars"""
        self.data_mgr.load_csv('AAPL', 'data/historical/AAPL_daily.csv')
        
        # Get all bars
        all_bars = self.data_mgr.get_bars('AAPL')
        self.assertGreater(len(all_bars), 0)
        
        # Get with lookback
        recent = self.data_mgr.get_bars('AAPL', lookback=10)
        self.assertEqual(len(recent), 10)
        
        print(f"✓ Retrieved {len(all_bars)} total bars, {len(recent)} recent bars")
    
    @pytest.mark.skipif(not HAS_TEST_DATA, reason="Test data files not found in data/historical/")
    def test_get_bar_at_time(self):
        """Test getting bar at specific time"""
        self.data_mgr.load_csv('AAPL', 'data/historical/AAPL_daily.csv')
        
        # Get bar at a specific date
        test_date = datetime(2024, 6, 15)
        bar = self.data_mgr.get_bar_at_time('AAPL', test_date)
        
        if bar:
            print(f"✓ Found bar at {test_date.date()}: {bar}")
        else:
            print(f"✓ No bar at {test_date.date()} (likely weekend)")
    
    @pytest.mark.skipif(not HAS_TEST_DATA, reason="Test data files not found in data/historical/")
    def test_validate_data(self):
        """Test data validation"""
        self.data_mgr.load_csv('AAPL', 'data/historical/AAPL_daily.csv')
        
        validation = self.data_mgr.validate_data('AAPL')
        
        self.assertIn('valid', validation)
        self.assertIn('bar_count', validation)
        
        if validation['valid']:
            print(f"✓ Data validation passed for AAPL ({validation['bar_count']} bars)")
        else:
            print(f"✗ Data validation failed: {validation['issue_count']} issues")
            for issue in validation['issues'][:5]:  # Show first 5
                print(f"  - {issue}")
    
    @pytest.mark.skipif(not HAS_TEST_DATA, reason="Test data files not found in data/historical/")
    def test_multiple_symbols(self):
        """Test loading multiple symbols"""
        symbols = ['AAPL', 'MSFT', 'SPY']
        
        for symbol in symbols:
            self.data_mgr.load_csv(
                symbol=symbol,
                filepath=f'data/historical/{symbol}_daily.csv'
            )
        
        loaded = self.data_mgr.get_symbols()
        self.assertEqual(len(loaded), 3)
        
        print(f"✓ Loaded {len(loaded)} symbols: {loaded}")


class TestFillSimulator(unittest.TestCase):
    """Test order fill simulation"""
    
    def setUp(self):
        """Setup fill simulator"""
        self.fill_sim = FillSimulator(
            default_spread_bps=5.0,
            market_impact_factor=0.1,
            slippage_std=0.0002
        )
        
        # Create sample bar
        self.bar = Bar(
            timestamp=datetime(2024, 1, 1, 10, 0),
            symbol='AAPL',
            open=150.0,
            high=152.0,
            low=149.0,
            close=151.0,
            volume=1000000
        )
    
    def test_market_order_fill(self):
        """Test market order fill"""
        order = Order(
            order_id='TEST001',
            symbol='AAPL',
            action='BUY',
            quantity=100,
            order_type='MARKET'
        )
        
        trade = self.fill_sim.simulate_fill(order, self.bar)
        
        self.assertIsNotNone(trade)
        self.assertEqual(trade.symbol, 'AAPL')
        self.assertEqual(trade.quantity, 100)
        self.assertGreater(trade.price, 0)
        self.assertGreater(trade.commission, 0)
        
        print(f"✓ Market order filled: {trade}")
    
    def test_limit_order_fill(self):
        """Test limit order fill"""
        # Buy limit below market
        order = Order(
            order_id='TEST002',
            symbol='AAPL',
            action='BUY',
            quantity=100,
            order_type='LIMIT',
            limit_price=149.5
        )
        
        trade = self.fill_sim.simulate_fill(order, self.bar)
        
        # Should fill since bar.low (149.0) <= limit_price (149.5)
        self.assertIsNotNone(trade)
        self.assertLessEqual(trade.price, order.limit_price)
        
        print(f"✓ Limit order filled: {trade}")
    
    def test_limit_order_no_fill(self):
        """Test limit order that doesn't fill"""
        # Buy limit way below market
        order = Order(
            order_id='TEST003',
            symbol='AAPL',
            action='BUY',
            quantity=100,
            order_type='LIMIT',
            limit_price=140.0  # Way below bar.low (149.0)
        )
        
        trade = self.fill_sim.simulate_fill(order, self.bar)
        
        # Should NOT fill
        self.assertIsNone(trade)
        print(f"✓ Limit order correctly not filled (price too low)")
    
    def test_stop_order_fill(self):
        """Test stop order fill"""
        # Sell stop at 149.5 (stop loss)
        order = Order(
            order_id='TEST004',
            symbol='AAPL',
            action='SELL',
            quantity=100,
            order_type='STOP',
            stop_price=149.5
        )
        
        trade = self.fill_sim.simulate_fill(order, self.bar)
        
        # Should fill since bar.low (149.0) <= stop_price (149.5)
        self.assertIsNotNone(trade)
        
        print(f"✓ Stop order filled: {trade}")


class TestMarketSimulator(unittest.TestCase):
    """Test market simulator"""
    
    def setUp(self):
        """Setup market simulator"""
        self.data_mgr = HistoricalDataManager('data/historical')
        self.data_mgr.load_csv('AAPL', 'data/historical/AAPL_daily.csv')
        self.data_mgr.load_csv('MSFT', 'data/historical/MSFT_daily.csv')
        
        self.market_sim = MarketSimulator(self.data_mgr)
    
    @pytest.mark.skipif(not HAS_TEST_DATA, reason="Test data files not found in data/historical/")

    def test_market_replay(self):
        """Test replaying market data"""
        start_date = datetime(2024, 1, 2)
        end_date = datetime(2024, 1, 31)
        symbols = ['AAPL', 'MSFT']
        
        bar_count = 0
        
        for market_data in self.market_sim.replay(start_date, end_date, symbols):
            bar_count += 1
            self.assertIsNotNone(market_data.timestamp)
            
            if bar_count <= 3:  # Print first 3
                print(f"  Bar {bar_count}: {market_data}")
        
        self.assertGreater(bar_count, 0)
        print(f"✓ Replayed {bar_count} bars")
    
    @pytest.mark.skipif(not HAS_TEST_DATA, reason="Test data files not found in data/historical/")
    def test_order_submission_and_fill(self):
        """Test submitting and filling orders"""
        start_date = datetime(2024, 1, 2)
        end_date = datetime(2024, 1, 5)
        symbols = ['AAPL']
        
        order_submitted = False
        trade_count = 0
        
        # Register trade callback
        def on_trade(trade):
            nonlocal trade_count
            trade_count += 1
            print(f"  Trade executed: {trade}")
        
        self.market_sim.register_trade_callback(on_trade)
        
        # Replay and submit order on first bar
        for i, market_data in enumerate(self.market_sim.replay(start_date, end_date, symbols)):
            if i == 0 and not order_submitted:
                # Submit market order
                order = Order(
                    order_id='TEST_ORDER_001',
                    symbol='AAPL',
                    action='BUY',
                    quantity=100,
                    order_type='MARKET'
                )
                self.market_sim.submit_order(order)
                order_submitted = True
                print("  ✓ Order submitted")
        
        self.assertTrue(order_submitted)
        self.assertGreater(trade_count, 0)
        print(f"✓ Order submission and fill test complete ({trade_count} trades)")


def run_tests():
    """Run all tests"""
    print("\n" + "="*70)
    print("Testing Backtesting Data Components - Week 4 Day 1")
    print("="*70 + "\n")
    
    # Create test suite
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    
    # Add all test classes
    suite.addTests(loader.loadTestsFromTestCase(TestBar))
    suite.addTests(loader.loadTestsFromTestCase(TestMarketData))
    suite.addTests(loader.loadTestsFromTestCase(TestBarSeries))
    suite.addTests(loader.loadTestsFromTestCase(TestHistoricalDataManager))
    suite.addTests(loader.loadTestsFromTestCase(TestFillSimulator))
    suite.addTests(loader.loadTestsFromTestCase(TestMarketSimulator))
    
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
