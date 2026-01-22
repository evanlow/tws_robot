"""
Quick Start Script - Your First Backtest

This script runs a simple backtest to show you how TWS Robot works.
It tests a Moving Average Crossover strategy on Apple stock.

What you'll learn:
- How to run a backtest
- How to interpret results
- Whether the strategy would have made money

Run this: python quick_start.py
"""

import sys
from datetime import datetime, timedelta
from backtest.strategy_templates import MovingAverageCrossStrategy, MACrossConfig
from backtest.strategy import StrategyConfig
from backtest.engine import BacktestEngine
from backtest.data_manager import HistoricalDataManager
from backtest.profiles import create_balanced_profile


def print_welcome():
    """Print welcome message"""
    print("=" * 70)
    print("🚀 TWS ROBOT - QUICK START")
    print("=" * 70)
    print()
    print("This will test a Moving Average Crossover strategy on historical data.")
    print("You'll see if this strategy would have made money.")
    print()
    print("-" * 70)


def print_strategy_explanation():
    """Explain the strategy in simple terms"""
    print("\n📚 STRATEGY EXPLANATION")
    print("-" * 70)
    print()
    print("Moving Average Crossover Strategy:")
    print("  • Calculates two moving averages: 20-day (fast) and 50-day (slow)")
    print("  • BUY when fast MA crosses ABOVE slow MA (golden cross)")
    print("  • SELL when fast MA crosses BELOW slow MA (death cross)")
    print()
    print("Why this works:")
    print("  • Captures major trends in stock prices")
    print("  • Filters out daily noise and volatility")
    print("  • Classic strategy used for decades")
    print()
    print("-" * 70)


def print_results_interpretation(results):
    """Explain what the results mean in plain English"""
    total_return = results['total_return'] * 100
    sharpe = results['sharpe_ratio']
    max_dd = results['max_drawdown'] * 100
    win_rate = results['win_rate'] * 100
    num_trades = results['num_trades']
    
    print("\n" + "=" * 70)
    print("📊 BACKTEST RESULTS - WHAT THEY MEAN")
    print("=" * 70)
    print()
    
    # Total Return
    print(f"💰 Total Return: {total_return:+.1f}%")
    if total_return > 15:
        print("   ✅ EXCELLENT: This strategy beat the market!")
    elif total_return > 5:
        print("   ✅ GOOD: This strategy made money")
    elif total_return > 0:
        print("   ⚠️  MARGINAL: Barely profitable")
    else:
        print("   ❌ LOSS: This strategy lost money")
    print()
    
    # Sharpe Ratio
    print(f"📈 Sharpe Ratio: {sharpe:.2f}")
    print("   (Measures return vs. risk)")
    if sharpe > 2:
        print("   ✅ EXCELLENT: Great risk-adjusted returns")
    elif sharpe > 1:
        print("   ✅ GOOD: Solid risk-adjusted returns")
    elif sharpe > 0.5:
        print("   ⚠️  FAIR: Barely acceptable")
    else:
        print("   ❌ POOR: Too much risk for the return")
    print()
    
    # Max Drawdown
    print(f"📉 Max Drawdown: {max_dd:.1f}%")
    print("   (Worst peak-to-trough loss)")
    if max_dd < 10:
        print("   ✅ LOW RISK: Small worst-case loss")
    elif max_dd < 20:
        print("   ⚠️  MODERATE RISK: Manageable worst-case")
    else:
        print("   ❌ HIGH RISK: Large potential losses")
    print()
    
    # Win Rate
    print(f"🎯 Win Rate: {win_rate:.1f}%")
    print("   (Percentage of profitable trades)")
    if win_rate > 60:
        print("   ✅ HIGH: Most trades are winners")
    elif win_rate > 50:
        print("   ✅ GOOD: More wins than losses")
    elif win_rate > 40:
        print("   ⚠️  FAIR: Close to break-even")
    else:
        print("   ❌ LOW: More losses than wins")
    print()
    
    # Number of Trades
    print(f"🔄 Number of Trades: {num_trades}")
    if num_trades < 5:
        print("   ⚠️  Few trades: Results may not be statistically significant")
    elif num_trades < 20:
        print("   ✅ Reasonable: Good sample size")
    else:
        print("   ✅ Many trades: Statistically significant results")
    print()
    
    # Overall Assessment
    print("=" * 70)
    print("🎯 OVERALL ASSESSMENT")
    print("=" * 70)
    print()
    
    if total_return > 10 and sharpe > 1 and max_dd < 20:
        print("✅ This strategy looks PROMISING!")
        print()
        print("Next Steps:")
        print("  1. Test on other stocks to see if it's consistent")
        print("  2. Try different parameter settings (fast/slow periods)")
        print("  3. Run paper trading for 30 days")
        print("  4. If paper trading is successful, consider going live")
    elif total_return > 0 and sharpe > 0.5:
        print("⚠️  This strategy is MARGINAL")
        print()
        print("Next Steps:")
        print("  1. Try adjusting parameters to improve performance")
        print("  2. Test on different stocks")
        print("  3. Consider a different strategy")
        print("  4. More optimization needed before paper trading")
    else:
        print("❌ This strategy DIDN'T WORK on this stock")
        print()
        print("Next Steps:")
        print("  1. Try a different stock (maybe one with clearer trends)")
        print("  2. Adjust parameters (try 10/30 instead of 20/50)")
        print("  3. Try a different strategy (Mean Reversion, Momentum)")
        print("  4. Don't use this strategy as-is!")
    
    print()
    print("=" * 70)


def run_backtest():
    """Run a simple backtest and show results"""
    
    print("\n⏳ Running backtest...")
    print("   (This may take a few seconds)")
    print()
    
    # Configuration
    symbol = "AAPL"
    initial_capital = 10000
    
    try:
        # Set up strategy
        strategy_config = StrategyConfig(
            initial_capital=initial_capital,
            position_size=0.05,  # 5% per trade
            max_positions=1
        )
        
        ma_config = MACrossConfig(
            fast_period=20,
            slow_period=50
        )
        
        strategy = MovingAverageCrossStrategy(strategy_config, ma_config)
        
        # Create backtest engine
        data_manager = HistoricalDataManager()
        
        # Generate sample data (1 year of daily bars)
        print(f"   Loading {symbol} data...")
        # Note: In real use, you'd load actual historical data here
        # For now, we'll create a simple framework
        
        print("   Testing strategy...")
        
        # Run backtest
        engine = BacktestEngine(strategy, data_manager)
        
        end_date = datetime.now()
        start_date = end_date - timedelta(days=365)
        
        results = engine.run(
            symbols=[symbol],
            start_date=start_date,
            end_date=end_date
        )
        
        # Show results
        print("\n✅ Backtest complete!")
        
        # Print results interpretation
        print_results_interpretation(results)
        
    except Exception as e:
        print(f"\n❌ Error running backtest: {e}")
        print("\nPossible issues:")
        print("  • Historical data not available")
        print("  • Check that 'data/historical' folder exists")
        print("  • Run 'python download_real_data.py' to get data")
        return False
    
    return True


def show_next_steps():
    """Show what to do next"""
    print("\n" + "=" * 70)
    print("🎓 WHAT TO DO NEXT")
    print("=" * 70)
    print()
    print("Explore More:")
    print()
    print("1. Compare Risk Profiles:")
    print("   python example_profile_comparison.py")
    print("   See how Conservative vs. Aggressive trading affects results")
    print()
    print("2. Try Different Strategies:")
    print("   python example_strategy_templates.py")
    print("   Test Mean Reversion and Momentum strategies")
    print()
    print("3. Test on Multiple Stocks:")
    print("   python example_week4_integration.py")
    print("   See which stocks work best with which strategies")
    print()
    print("4. Paper Trade:")
    print("   python tws_client.py --env paper")
    print("   Test with real-time data (fake money)")
    print()
    print("5. Read the User Guide:")
    print("   Open USER_GUIDE.md")
    print("   Learn strategy details, risk management, and best practices")
    print()
    print("=" * 70)


def main():
    """Main entry point"""
    print_welcome()
    print_strategy_explanation()
    
    # Run the backtest
    success = run_backtest()
    
    if success:
        show_next_steps()
    
    print("\n" + "=" * 70)
    print("Happy Trading! 🚀")
    print("=" * 70)


if __name__ == "__main__":
    main()
