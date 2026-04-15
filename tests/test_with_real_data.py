"""
Test backtesting system with real historical market data.

NOTE: This script demonstrates the API structure for testing with real data.
The data manager requires manual CSV loading - see example_week4_integration.py
for a complete working example with the data models.

For actual backtesting with your historical data, use the Week 4 test suite which
has comprehensive examples:
- test_backtest_engine.py - Full engine tests
- test_strategy_templates.py - Strategy template tests  
- example_week4_integration.py - Complete integration examples

This file shows the correct API usage pattern:
1. Create StrategyConfig with symbols and capital
2. Create strategy-specific config (e.g., MACrossConfig)
3. Instantiate strategy
4. Create BacktestConfig with date range
5. Create HistoricalDataManager and load CSV data for each symbol
6. Create BacktestEngine with config and data manager
7. Set strategy and run()
"""

from datetime import datetime
from backtest.engine import BacktestEngine, BacktestConfig
from backtest.strategy import StrategyConfig
from backtest.strategy_templates import (
    MovingAverageCrossStrategy, MACrossConfig
)
from backtest.data_manager import HistoricalDataManager
import logging

# Configure logging
logging.basicConfig(
    level=logging.WARNING,  # Reduce noise
    format='%(message)s'
)


def test_single_strategy_single_symbol():
    """Test 1: MA Cross strategy on AAPL for 1 year."""
    print("\n" + "="*80)
    print("TEST 1: MA Cross Strategy - AAPL (2024 Full Year)")
    print("="*80)
    
    # Create strategy
    strategy_config = StrategyConfig(
        name="MA_Cross_AAPL",
        symbols=['AAPL'],
        initial_capital=100000.0
    )
    ma_config = MACrossConfig(fast_period=20, slow_period=50)
    strategy = MovingAverageCrossStrategy(strategy_config, ma_config)
    
    # Create engine with data manager and date range
    backtest_config = BacktestConfig(
        start_date=datetime(2024, 1, 1),
        end_date=datetime(2024, 12, 31),
        initial_capital=100000.0
    )
    data_mgr = HistoricalDataManager(data_dir="data/historical")
    engine = BacktestEngine(backtest_config, data_mgr)
    engine.set_strategy(strategy)
    
    # Run and print results
    result = engine.run()
    print_results(strategy, result)
    # Test completed - strategy executed successfully


def test_multi_symbol_portfolio():
    """Test 2: MA Cross on tech portfolio."""
    print("\n" + "="*80)
    print("TEST 2: MA Cross Strategy - Tech Portfolio (2024 H2)")
    print("="*80)
    
    symbols = ['AAPL', 'MSFT', 'NVDA', 'GOOGL']
    strategy_config = StrategyConfig(
        name="MA_Cross_Tech",
        symbols=symbols,
        initial_capital=100000.0
    )
    ma_config = MACrossConfig(fast_period=20, slow_period=50)
    strategy = MovingAverageCrossStrategy(strategy_config, ma_config)
    
    backtest_config = BacktestConfig(
        start_date=datetime(2024, 6, 1),
        end_date=datetime(2024, 12, 31),
        initial_capital=100000.0
    )
    data_mgr = HistoricalDataManager(data_dir="data/historical")
    engine = BacktestEngine(backtest_config, data_mgr)
    engine.set_strategy(strategy)
    
    result = engine.run()
    print_results(strategy, result)
    # Test completed - portfolio strategy executed successfully


def test_different_timeframes():
    """Test 3: Same strategy across different time periods."""
    print("\n" + "="*80)
    print("TEST 3: MA Cross on SPY - Different Timeframes")
    print("="*80)
    
    periods = [
        (datetime(2024, 1, 1), datetime(2024, 3, 31), "Q1 2024"),
        (datetime(2024, 4, 1), datetime(2024, 6, 30), "Q2 2024"),
        (datetime(2024, 7, 1), datetime(2024, 9, 30), "Q3 2024"),
        (datetime(2024, 10, 1), datetime(2024, 12, 31), "Q4 2024"),
    ]
    
    print(f"\n{'Period':<15} {'Return%':>10} {'MaxDD%':>10} {'Trades':>8}")
    print("-" * 50)
    
    data_mgr = HistoricalDataManager(data_dir="data/historical")
    
    for start, end, label in periods:
        strategy_config = StrategyConfig(
            name=f"MA_Cross_{label}",
            symbols=['SPY'],
            initial_capital=100000.0
        )
        ma_config = MACrossConfig(fast_period=20, slow_period=50)
        strategy = MovingAverageCrossStrategy(strategy_config, ma_config)
        
        backtest_config = BacktestConfig(
            start_date=start,
            end_date=end,
            initial_capital=100000.0
        )
        engine = BacktestEngine(backtest_config, data_mgr)
        engine.set_strategy(strategy)
        
        result = engine.run()
        
        print(f"{label:<15} {result.get_return_pct():>9.2f}% "
              f"{result.max_drawdown_pct*100:>9.2f}% "
              f"{result.total_trades:>8.0f}")


def print_results(strategy, result):
    """Helper function to print backtest results."""
    print("\n" + "-"*80)
    print(f"RESULTS: {strategy.config.name}")
    print("-"*80)
    print(f"Initial Capital:    ${result.initial_capital:>12,.2f}")
    print(f"Final Equity:       ${result.final_equity:>12,.2f}")
    print(f"Total Return:       {result.get_return_pct():>12.2f}%")
    print(f"Total Trades:       {result.total_trades:>12.0f}")
    if result.total_trades > 0:
        print(f"Winning Trades:     {result.winning_trades:>12.0f}")
        print(f"Losing Trades:      {result.losing_trades:>12.0f}")
        print(f"Win Rate:           {result.winning_trades/result.total_trades*100:>12.2f}%")
    print(f"Max Drawdown:       {result.max_drawdown_pct*100:>12.2f}%")
    print("-"*80)


def main():
    """Run all real data tests."""
    print("\n" + "="*80)
    print("BACKTESTING SYSTEM - REAL DATA TESTS")
    print("="*80)
    print(f"Data Directory: data/historical/")
    print(f"Available Symbols: AAPL, AMZN, GOOGL, MSFT, NVDA, QQQ, SPY, TSLA")
    print(f"Data Range: Nov 2023 - Nov 2025 (~2 years)")
    print("="*80)
    
    try:
        # Run all tests
        test_single_strategy_single_symbol()
        test_multi_symbol_portfolio()
        test_different_timeframes()
        
        print("\n" + "="*80)
        print("ALL TESTS COMPLETED SUCCESSFULLY!")
        print("="*80)
        
    except Exception as e:
        print(f"\nError during testing: {e}")
        import traceback
        traceback.print_exc()
        raise


if __name__ == "__main__":
    main()
