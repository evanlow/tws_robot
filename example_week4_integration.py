"""
Week 4 Integration Examples

This file demonstrates how to use the complete backtesting system with
real-world scenarios. Each example builds on the previous ones to show
progressively more sophisticated usage patterns.

Examples:
1. Basic MA Cross Backtest
2. Multi-Profile Comparison
3. Custom Strategy Creation
4. Parameter Optimization
5. Full Production Workflow
"""

from datetime import datetime
from backtest.data import HistoricalDataManager
from backtest.market_simulator import MarketSimulator, FillSimulator
from backtest.strategy import Strategy, StrategyConfig
from backtest.strategy_templates import (
    MovingAverageCrossStrategy, MACrossConfig,
    MeanReversionStrategy, MeanReversionConfig,
    MomentumStrategy, MomentumConfig
)
from backtest.performance import PerformanceAnalyzer
from backtest.profiles import ProfileLibrary, RiskProfile
from backtest.profile_comparison import ProfileComparator


# ============================================================================
# Example 1: Basic MA Cross Backtest
# ============================================================================

def example_1_basic_ma_cross():
    """
    Simple moving average crossover backtest on AAPL
    
    This example shows:
    - Loading historical data
    - Creating a strategy with default parameters
    - Running a backtest
    - Analyzing performance
    """
    print("="*70)
    print("Example 1: Basic MA Cross Backtest")
    print("="*70)
    
    # Setup data manager
    data_manager = HistoricalDataManager("data/historical")
    data_manager.load_symbol("AAPL")
    
    # Create strategy configuration
    config = StrategyConfig(
        name="MA Cross 20/50",
        symbols=["AAPL"],
        initial_capital=100000.0
    )
    
    # Create MA cross strategy with default parameters
    strategy = MovingAverageCrossStrategy(config)
    
    # Setup market simulator
    fill_sim = FillSimulator()
    simulator = MarketSimulator(data_manager, fill_sim)
    simulator.subscribe_bars(strategy._process_market_data)
    
    # Run backtest for 2024
    print("\nRunning backtest...")
    simulator.replay(
        start_date=datetime(2024, 1, 1),
        end_date=datetime(2024, 12, 31),
        symbols=["AAPL"]
    )
    
    # Analyze performance
    analyzer = PerformanceAnalyzer(strategy.state)
    results = analyzer.analyze()
    
    # Print key metrics
    print(f"\nPerformance Summary:")
    print(f"  Total Return:     {results['total_return_pct']:>8.2f}%")
    print(f"  Annual Return:    {results['annualized_return_pct']:>8.2f}%")
    print(f"  Sharpe Ratio:     {results['sharpe_ratio']:>8.2f}")
    print(f"  Max Drawdown:     {results['max_drawdown_pct']:>8.2f}%")
    print(f"  Win Rate:         {results['win_rate_pct']:>8.2f}%")
    print(f"  Total Trades:     {results['total_trades']:>8d}")
    print(f"  Profit Factor:    {results['profit_factor']:>8.2f}")
    
    return results


# ============================================================================
# Example 2: Multi-Profile Comparison
# ============================================================================

def example_2_multi_profile_comparison():
    """
    Compare strategy performance across different risk profiles
    
    This example shows:
    - Running backtests with multiple risk profiles
    - Comparing performance across profiles
    - Identifying optimal risk/return trade-offs
    """
    print("\n" + "="*70)
    print("Example 2: Multi-Profile Comparison")
    print("="*70)
    
    # Setup data
    data_manager = HistoricalDataManager("data/historical")
    data_manager.load_symbol("AAPL")
    
    # Base configuration
    config = StrategyConfig(
        name="MA Cross Multi-Profile",
        symbols=["AAPL"],
        initial_capital=100000.0
    )
    
    # Test with three risk profiles
    profile_names = ['conservative', 'moderate', 'aggressive']
    comparator = ProfileComparator()
    
    for profile_name in profile_names:
        print(f"\nTesting {profile_name.upper()} profile...")
        
        # Get profile
        profile = ProfileLibrary.get_profile_by_name(profile_name)
        
        # Create strategy
        strategy = MovingAverageCrossStrategy(config)
        
        # Setup simulator
        fill_sim = FillSimulator()
        simulator = MarketSimulator(data_manager, fill_sim)
        simulator.subscribe_bars(strategy._process_market_data)
        
        # Run backtest
        simulator.replay(
            start_date=datetime(2024, 1, 1),
            end_date=datetime(2024, 12, 31),
            symbols=["AAPL"]
        )
        
        # Analyze
        analyzer = PerformanceAnalyzer(strategy.state)
        results = analyzer.analyze()
        
        # Add to comparison
        comparator.add_profile_results(profile_name, results)
        
        print(f"  Return: {results['total_return_pct']:.2f}% | "
              f"Sharpe: {results['sharpe_ratio']:.2f} | "
              f"Drawdown: {results['max_drawdown_pct']:.2f}%")
    
    # Compare profiles
    print("\n" + "-"*70)
    print("Profile Comparison Results:")
    print("-"*70)
    
    comparison = comparator.compare()
    print(comparison.get_comparison_table())
    
    # Find best profile by Sharpe ratio
    best = comparison.get_best_profile('sharpe_ratio')
    print(f"\nBest Risk-Adjusted Profile: {best['name']}")
    print(f"  Sharpe Ratio: {best['value']:.2f}")
    
    return comparison


# ============================================================================
# Example 3: Custom Strategy Creation
# ============================================================================

class RSIStrategy(Strategy):
    """
    Custom RSI-based mean reversion strategy
    
    Demonstrates:
    - Creating a custom strategy from scratch
    - Implementing indicator calculations
    - Managing strategy state
    - Applying risk management
    """
    
    def __init__(self, config: StrategyConfig, rsi_period: int = 14,
                 oversold: float = 30, overbought: float = 70):
        super().__init__(config)
        self.rsi_period = rsi_period
        self.oversold = oversold
        self.overbought = overbought
        
        # Track RSI values per symbol
        self.rsi_values = {}
        self.rsi_gains = {}
        self.rsi_losses = {}
    
    def on_bar(self, symbol: str, bar):
        """Process new bar and check for RSI signals"""
        # Get price history
        bars = self.get_bar_history(symbol, lookback=self.rsi_period + 1)
        
        if len(bars) < self.rsi_period + 1:
            return
        
        # Calculate RSI
        rsi = self._calculate_rsi(symbol, bars)
        self.rsi_values[symbol] = rsi
        
        # Check signals
        current_price = bar.close
        
        # Buy on oversold
        if rsi <= self.oversold and not self.has_position(symbol):
            size = self.calculate_position_size(symbol, current_price)
            if size > 0:
                self.buy(symbol, size)
                print(f"{bar.timestamp}: BUY {symbol} @ ${current_price:.2f} (RSI: {rsi:.1f})")
        
        # Sell on overbought
        elif rsi >= self.overbought and self.has_position(symbol):
            position = self.get_position(symbol)
            self.sell(symbol, position.quantity)
            print(f"{bar.timestamp}: SELL {symbol} @ ${current_price:.2f} (RSI: {rsi:.1f})")
    
    def _calculate_rsi(self, symbol: str, bars):
        """Calculate RSI indicator"""
        prices = [b.close for b in bars]
        
        # Calculate price changes
        changes = [prices[i] - prices[i-1] for i in range(1, len(prices))]
        
        # Separate gains and losses
        gains = [max(0, c) for c in changes]
        losses = [abs(min(0, c)) for c in changes]
        
        # Calculate averages
        avg_gain = sum(gains[-self.rsi_period:]) / self.rsi_period
        avg_loss = sum(losses[-self.rsi_period:]) / self.rsi_period
        
        # Calculate RSI
        if avg_loss == 0:
            return 100.0
        
        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
        
        return rsi


def example_3_custom_strategy():
    """
    Backtest a custom RSI strategy
    
    Shows:
    - Using a custom strategy implementation
    - Applying risk profiles to custom strategies
    - Performance analysis of custom logic
    """
    print("\n" + "="*70)
    print("Example 3: Custom RSI Strategy")
    print("="*70)
    
    # Setup
    data_manager = HistoricalDataManager("data/historical")
    data_manager.load_symbol("AAPL")
    
    config = StrategyConfig(
        name="RSI Mean Reversion",
        symbols=["AAPL"],
        initial_capital=100000.0
    )
    
    # Create custom strategy
    strategy = RSIStrategy(config, rsi_period=14, oversold=30, overbought=70)
    
    # Apply moderate risk profile
    profile = ProfileLibrary.get_moderate()
    
    # Setup simulator
    fill_sim = FillSimulator()
    simulator = MarketSimulator(data_manager, fill_sim)
    simulator.subscribe_bars(strategy._process_market_data)
    
    # Run backtest
    print("\nRunning custom strategy backtest...")
    simulator.replay(
        start_date=datetime(2024, 1, 1),
        end_date=datetime(2024, 12, 31),
        symbols=["AAPL"]
    )
    
    # Analyze
    analyzer = PerformanceAnalyzer(strategy.state)
    results = analyzer.analyze()
    
    print(f"\nCustom Strategy Performance:")
    print(f"  Total Return:     {results['total_return_pct']:>8.2f}%")
    print(f"  Sharpe Ratio:     {results['sharpe_ratio']:>8.2f}")
    print(f"  Max Drawdown:     {results['max_drawdown_pct']:>8.2f}%")
    print(f"  Win Rate:         {results['win_rate_pct']:>8.2f}%")
    print(f"  Total Trades:     {results['total_trades']:>8d}")
    
    return results


# ============================================================================
# Example 4: Parameter Optimization
# ============================================================================

def example_4_parameter_optimization():
    """
    Optimize MA cross parameters using grid search
    
    Demonstrates:
    - Parameter optimization workflow
    - Testing multiple parameter combinations
    - Finding optimal parameters
    - Avoiding overfitting
    """
    print("\n" + "="*70)
    print("Example 4: Parameter Optimization")
    print("="*70)
    
    # Setup data
    data_manager = HistoricalDataManager("data/historical")
    data_manager.load_symbol("AAPL")
    
    # Parameter ranges to test
    fast_periods = [10, 15, 20, 25]
    slow_periods = [40, 50, 60, 70]
    
    # Store results
    optimization_results = []
    
    print("\nTesting parameter combinations...")
    print("-" * 70)
    
    for fast in fast_periods:
        for slow in slow_periods:
            if fast >= slow:
                continue
            
            # Create strategy with these parameters
            config = StrategyConfig(
                name=f"MA {fast}/{slow}",
                symbols=["AAPL"],
                initial_capital=100000.0
            )
            
            ma_config = MACrossConfig(fast_period=fast, slow_period=slow)
            strategy = MovingAverageCrossStrategy(config, ma_config)
            
            # Run backtest
            fill_sim = FillSimulator()
            simulator = MarketSimulator(data_manager, fill_sim)
            simulator.subscribe_bars(strategy._process_market_data)
            
            simulator.replay(
                start_date=datetime(2024, 1, 1),
                end_date=datetime(2024, 12, 31),
                symbols=["AAPL"]
            )
            
            # Analyze
            analyzer = PerformanceAnalyzer(strategy.state)
            results = analyzer.analyze()
            
            # Store results
            optimization_results.append({
                'fast': fast,
                'slow': slow,
                'return': results['total_return_pct'],
                'sharpe': results['sharpe_ratio'],
                'drawdown': results['max_drawdown_pct'],
                'trades': results['total_trades']
            })
            
            print(f"MA {fast:2d}/{slow:2d}: Return={results['total_return_pct']:6.2f}% | "
                  f"Sharpe={results['sharpe_ratio']:5.2f} | "
                  f"Trades={results['total_trades']:3d}")
    
    # Find best parameters by Sharpe ratio
    best = max(optimization_results, key=lambda x: x['sharpe'])
    
    print("\n" + "="*70)
    print("Optimization Results:")
    print("="*70)
    print(f"Best Parameters: MA {best['fast']}/{best['slow']}")
    print(f"  Return:       {best['return']:.2f}%")
    print(f"  Sharpe Ratio: {best['sharpe']:.2f}")
    print(f"  Max Drawdown: {best['drawdown']:.2f}%")
    print(f"  Total Trades: {best['trades']}")
    
    print("\nNote: Results may be overfit to 2024 data.")
    print("      Use walk-forward analysis for production.")
    
    return optimization_results


# ============================================================================
# Example 5: Full Production Workflow
# ============================================================================

def example_5_production_workflow():
    """
    Complete workflow for production strategy deployment
    
    Demonstrates:
    - Multi-symbol backtesting
    - Multiple strategy comparison
    - Risk profile optimization
    - Performance validation
    - Final strategy selection
    """
    print("\n" + "="*70)
    print("Example 5: Full Production Workflow")
    print("="*70)
    
    # 1. Setup multi-symbol universe
    symbols = ["AAPL", "MSFT", "SPY"]
    data_manager = HistoricalDataManager("data/historical")
    
    print("\n1. Loading data for symbol universe...")
    for symbol in symbols:
        data_manager.load_symbol(symbol)
        print(f"   Loaded {symbol}")
    
    # 2. Test multiple strategies
    print("\n2. Testing multiple strategies...")
    print("-" * 70)
    
    strategies_to_test = [
        ("MA Cross 20/50", MovingAverageCrossStrategy, 
         MACrossConfig(fast_period=20, slow_period=50)),
        ("Mean Reversion", MeanReversionStrategy, 
         MeanReversionConfig()),
        ("Momentum", MomentumStrategy,
         MomentumConfig())
    ]
    
    all_results = {}
    
    for strategy_name, StrategyClass, strategy_config in strategies_to_test:
        print(f"\n  Testing {strategy_name}...")
        
        # Test with each symbol
        for symbol in symbols:
            config = StrategyConfig(
                name=f"{strategy_name} - {symbol}",
                symbols=[symbol],
                initial_capital=100000.0
            )
            
            strategy = StrategyClass(config, strategy_config)
            
            # Apply moderate profile
            profile = ProfileLibrary.get_moderate()
            
            # Run backtest
            fill_sim = FillSimulator()
            simulator = MarketSimulator(data_manager, fill_sim)
            simulator.subscribe_bars(strategy._process_market_data)
            
            simulator.replay(
                start_date=datetime(2024, 1, 1),
                end_date=datetime(2024, 12, 31),
                symbols=[symbol]
            )
            
            # Analyze
            analyzer = PerformanceAnalyzer(strategy.state)
            results = analyzer.analyze()
            
            key = f"{strategy_name}_{symbol}"
            all_results[key] = results
            
            print(f"    {symbol}: Return={results['total_return_pct']:6.2f}% | "
                  f"Sharpe={results['sharpe_ratio']:5.2f}")
    
    # 3. Find best strategy/symbol combination
    print("\n3. Identifying best combinations...")
    print("-" * 70)
    
    # Sort by Sharpe ratio
    sorted_results = sorted(all_results.items(), 
                           key=lambda x: x[1]['sharpe_ratio'],
                           reverse=True)
    
    print("\nTop 5 Strategy/Symbol Combinations (by Sharpe):")
    for i, (name, results) in enumerate(sorted_results[:5], 1):
        print(f"{i}. {name}")
        print(f"   Return: {results['total_return_pct']:6.2f}% | "
              f"Sharpe: {results['sharpe_ratio']:5.2f} | "
              f"Drawdown: {results['max_drawdown_pct']:6.2f}%")
    
    # 4. Final recommendation
    best_name, best_results = sorted_results[0]
    
    print("\n" + "="*70)
    print("PRODUCTION RECOMMENDATION")
    print("="*70)
    print(f"\nStrategy: {best_name}")
    print(f"\nPerformance Metrics:")
    print(f"  Total Return:     {best_results['total_return_pct']:>8.2f}%")
    print(f"  Annualized:       {best_results['annualized_return_pct']:>8.2f}%")
    print(f"  Sharpe Ratio:     {best_results['sharpe_ratio']:>8.2f}")
    print(f"  Sortino Ratio:    {best_results['sortino_ratio']:>8.2f}")
    print(f"  Max Drawdown:     {best_results['max_drawdown_pct']:>8.2f}%")
    print(f"  Win Rate:         {best_results['win_rate_pct']:>8.2f}%")
    print(f"  Profit Factor:    {best_results['profit_factor']:>8.2f}")
    print(f"  Total Trades:     {best_results['total_trades']:>8d}")
    
    print("\nNext Steps:")
    print("  1. Validate with walk-forward analysis")
    print("  2. Test on out-of-sample data")
    print("  3. Run Monte Carlo simulations")
    print("  4. Implement paper trading")
    print("  5. Deploy with strict risk controls")
    
    return all_results


# ============================================================================
# Main Execution
# ============================================================================

if __name__ == "__main__":
    print("\n" + "="*70)
    print("WEEK 4 INTEGRATION EXAMPLES")
    print("="*70)
    print("\nThis script demonstrates the full capabilities of the")
    print("backtesting system through progressively complex examples.")
    print("\nNote: All examples use 2024 data and are for demonstration only.")
    print("="*70)
    
    # Run examples
    try:
        # Example 1: Simple backtest
        results_1 = example_1_basic_ma_cross()
        
        # Example 2: Multi-profile comparison
        comparison = example_2_multi_profile_comparison()
        
        # Example 3: Custom strategy
        results_3 = example_3_custom_strategy()
        
        # Example 4: Parameter optimization
        optimization = example_4_parameter_optimization()
        
        # Example 5: Full production workflow
        production_results = example_5_production_workflow()
        
        print("\n" + "="*70)
        print("ALL EXAMPLES COMPLETED SUCCESSFULLY")
        print("="*70)
        
    except Exception as e:
        print(f"\nError running examples: {e}")
        print("Make sure historical data is loaded in data/historical/")
        raise
