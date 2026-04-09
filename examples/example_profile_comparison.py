"""
Profile Comparison Examples

This module demonstrates how to use the ProfileComparator to analyze and compare
different risk profiles in backtesting scenarios.
"""


import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
del _os, _sys

from datetime import datetime
from backtest.profiles import ProfileManager
from backtest.profile_comparison import ProfileComparator
from backtest.strategy_templates import MomentumStrategy


def example_1_basic_comparison():
    """
    Example 1: Basic comparison of Conservative vs Moderate vs Aggressive profiles
    
    This demonstrates the most common use case: comparing all three standard
    risk profiles to see which performs best for a given strategy and time period.
    """
    print("=" * 80)
    print("EXAMPLE 1: Basic Profile Comparison")
    print("=" * 80)
    
    # Initialize the comparator
    comparator = ProfileComparator()
    
    # Define backtest parameters
    strategy_class = MomentumStrategy
    profile_names = ['conservative', 'moderate', 'aggressive']
    start_date = datetime(2023, 1, 1)
    end_date = datetime(2023, 12, 31)
    symbols = ['AAPL', 'MSFT', 'GOOGL']
    initial_capital = 100000.0
    
    # Run comparison
    print(f"\nComparing {len(profile_names)} profiles...")
    print(f"Strategy: {strategy_class.__name__}")
    print(f"Period: {start_date.date()} to {end_date.date()}")
    print(f"Symbols: {', '.join(symbols)}")
    print(f"Initial Capital: ${initial_capital:,.2f}")
    
    try:
        result = comparator.compare_profiles(
            strategy_class=strategy_class,
            profile_names=profile_names,
            start_date=start_date,
            end_date=end_date,
            symbols=symbols,
            initial_capital=initial_capital
        )
        
        # Display results
        comparator.print_comparison(result)
        
        # Get best profile
        best_profile = result.get_best_profile()
        print(f"\n[SUCCESS] Best Overall Profile: {best_profile}")
        
    except Exception as e:
        print(f"\n[ERROR] Error: {e}")
        print("Note: This example requires real market data to run.")
    
    print()


def example_2_two_profile_comparison():
    """
    Example 2: Detailed comparison of two specific profiles
    
    When you want to understand the differences between two profiles in detail,
    use the compare_two_profiles method for a more focused analysis.
    """
    print("=" * 80)
    print("EXAMPLE 2: Two-Profile Detailed Comparison")
    print("=" * 80)
    
    comparator = ProfileComparator()
    
    # Define parameters
    strategy_class = MomentumStrategy
    profile_names = ['conservative', 'aggressive']
    start_date = datetime(2023, 1, 1)
    end_date = datetime(2023, 12, 31)
    symbols = ['SPY', 'QQQ']
    
    print(f"\nDetailed comparison: Conservative vs Aggressive")
    print(f"Strategy: {strategy_class.__name__}")
    print(f"Period: {start_date.date()} to {end_date.date()}")
    
    try:
        # Run comparison
        result = comparator.compare_profiles(
            strategy_class=strategy_class,
            profile_names=profile_names,
            start_date=start_date,
            end_date=end_date,
            symbols=symbols
        )
        
        # Get detailed comparison
        comparison = comparator.compare_two_profiles(result, 'conservative', 'aggressive')
        
        print("\n" + "=" * 60)
        print("CONSERVATIVE vs AGGRESSIVE")
        print("=" * 60)
        
        for metric, details in comparison.items():
            print(f"\n{metric.replace('_', ' ').title()}:")
            print(f"  Conservative: {details['conservative']:.4f}")
            print(f"  Aggressive:   {details['aggressive']:.4f}")
            print(f"  Difference:   {details['difference']:.4f}")
            print(f"  Winner: {details['winner']}")
            
    except Exception as e:
        print(f"\n[ERROR] Error: {e}")
        print("Note: This example requires real market data to run.")
    
    print()


def example_3_optimization_insights():
    """
    Example 3: Getting optimization insights from comparison results
    
    The comparator can provide actionable insights based on the comparison results,
    helping you understand which profile might be best for your needs.
    """
    print("=" * 80)
    print("EXAMPLE 3: Optimization Insights")
    print("=" * 80)
    
    comparator = ProfileComparator()
    
    profile_names = ['conservative', 'moderate', 'aggressive']
    strategy_class = MomentumStrategy
    start_date = datetime(2023, 1, 1)
    end_date = datetime(2023, 12, 31)
    symbols = ['AAPL', 'MSFT', 'GOOGL', 'AMZN']
    
    print(f"\nAnalyzing profiles for optimization opportunities...")
    
    try:
        result = comparator.compare_profiles(
            strategy_class=strategy_class,
            profile_names=profile_names,
            start_date=start_date,
            end_date=end_date,
            symbols=symbols
        )
        
        # Get insights
        insights = comparator.get_optimization_insights(result)
        
        print("\n" + "=" * 60)
        print("OPTIMIZATION INSIGHTS")
        print("=" * 60)
        
        for i, insight in enumerate(insights, 1):
            print(f"\n{i}. {insight}")
        
        print("\n" + "=" * 60)
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        print("Note: This example requires real market data to run.")
    
    print()


def example_4_custom_profile_comparison():
    """
    Example 4: Comparing custom profiles
    
    You can also create and compare custom risk profiles to find the optimal
    configuration for your specific strategy and market conditions.
    """
    print("=" * 80)
    print("EXAMPLE 4: Custom Profile Comparison")
    print("=" * 80)
    
    # Initialize profile manager
    manager = ProfileManager()
    
    # Create custom profiles
    print("\nCreating custom profiles...")
    
    # Ultra-conservative profile
    ultra_conservative = {
        'max_position_size_pct': 0.05,
        'max_portfolio_risk_pct': 0.005,
        'max_total_exposure_pct': 0.40,
        'stop_loss_pct': 0.01,
        'take_profit_pct': 0.02
    }
    manager.add_profile('ultra_conservative', ultra_conservative)
    print("[OK] Ultra-conservative profile created")
    
    # High-growth profile
    high_growth = {
        'max_position_size_pct': 0.30,
        'max_portfolio_risk_pct': 0.04,
        'max_total_exposure_pct': 0.95,
        'stop_loss_pct': 0.06,
        'take_profit_pct': 0.15
    }
    manager.add_profile('high_growth', high_growth)
    print("[OK] High-growth profile created")
    
    # Compare custom profiles
    comparator = ProfileComparator(profile_manager=manager)
    
    profile_names = ['ultra_conservative', 'conservative', 'moderate', 
                    'aggressive', 'high_growth']
    strategy_class = MomentumStrategy
    start_date = datetime(2023, 1, 1)
    end_date = datetime(2023, 12, 31)
    symbols = ['AAPL', 'MSFT', 'GOOGL']
    
    print(f"\nComparing {len(profile_names)} profiles (including custom)...")
    
    try:
        result = comparator.compare_profiles(
            strategy_class=strategy_class,
            profile_names=profile_names,
            start_date=start_date,
            end_date=end_date,
            symbols=symbols
        )
        
        comparator.print_comparison(result)
        
        # Show which custom profile performed best
        best = result.get_best_profile()
        if best in ['ultra_conservative', 'high_growth']:
            print(f"\n[SUCCESS] Custom profile '{best}' performed best!")
        
    except Exception as e:
        print(f"\n[ERROR] Error: {e}")
        print("Note: This example requires real market data to run.")
    
    print()


def example_5_interpreting_rankings():
    """
    Example 5: Understanding and interpreting rankings
    
    Rankings help you understand relative performance across different metrics.
    This example shows how to interpret ranking results.
    """
    print("=" * 80)
    print("EXAMPLE 5: Interpreting Rankings")
    print("=" * 80)
    
    print("\nRanking System Explanation:")
    print("-" * 60)
    print("• Rankings are assigned from 1 (best) to N (worst)")
    print("• Four key metrics are ranked:")
    print("  - Sharpe Ratio (risk-adjusted returns)")
    print("  - Total Return (absolute performance)")
    print("  - Max Drawdown (downside risk)")
    print("  - Win Rate (consistency)")
    print()
    print("Interpretation:")
    print("  Rank 1 = Best performer in that metric")
    print("  Rank 2 = Second best")
    print("  Rank N = Worst performer")
    print()
    
    comparator = ProfileComparator()
    
    try:
        result = comparator.compare_profiles(
            strategy_class=MomentumStrategy,
            profile_names=['conservative', 'moderate', 'aggressive'],
            start_date=datetime(2023, 1, 1),
            end_date=datetime(2023, 12, 31),
            symbols=['SPY']
        )
        
        print("\nRanking Results:")
        print("-" * 60)
        
        for profile_name in result.profile_results.keys():
            print(f"\n{profile_name.upper()}:")
            print(f"  Sharpe Rank:    {result.sharpe_ranking[profile_name]}")
            print(f"  Return Rank:    {result.return_ranking[profile_name]}")
            print(f"  Drawdown Rank:  {result.drawdown_ranking[profile_name]}")
            print(f"  Win Rate Rank:  {result.winrate_ranking[profile_name]}")
            
            # Calculate average rank
            avg_rank = (
                result.sharpe_ranking[profile_name] +
                result.return_ranking[profile_name] +
                result.drawdown_ranking[profile_name] +
                result.winrate_ranking[profile_name]
            ) / 4
            print(f"  Average Rank:   {avg_rank:.2f}")
        
        print("\n" + "=" * 60)
        print("Best profile has the lowest average rank")
        print("=" * 60)
        
    except Exception as e:
        print(f"\n[ERROR] Error: {e}")
        print("Note: This example requires real market data to run.")
    
    print()


def example_6_summary_statistics():
    """
    Example 6: Using summary statistics for decision making
    
    Summary statistics help you understand the overall distribution of performance
    across all profiles.
    """
    print("=" * 80)
    print("EXAMPLE 6: Summary Statistics")
    print("=" * 80)
    
    print("\nSummary Statistics Explanation:")
    print("-" * 60)
    print("• Mean: Average value across all profiles")
    print("• Std Dev: Variability/spread of values")
    print("• High Std Dev = Large differences between profiles")
    print("• Low Std Dev = Similar performance across profiles")
    print()
    
    comparator = ProfileComparator()
    
    try:
        result = comparator.compare_profiles(
            strategy_class=MomentumStrategy,
            profile_names=['conservative', 'moderate', 'aggressive'],
            start_date=datetime(2023, 1, 1),
            end_date=datetime(2023, 12, 31),
            symbols=['SPY', 'QQQ']
        )
        
        print("\nSummary Statistics:")
        print("-" * 60)
        
        if result.summary_stats:
            for stat_name, value in result.summary_stats.items():
                print(f"{stat_name.replace('_', ' ').title()}: {value:.4f}")
        
        print("\nInterpretation:")
        print("-" * 60)
        
        if result.summary_stats:
            sharpe_std = result.summary_stats.get('sharpe_std', 0)
            return_std = result.summary_stats.get('return_std', 0)
            
            if sharpe_std > 0.5:
                print("• High Sharpe variability - Profile choice matters significantly")
            else:
                print("• Low Sharpe variability - Similar risk-adjusted performance")
            
            if return_std > 0.1:
                print("• High return variability - Aggressive profiles may outperform")
            else:
                print("• Low return variability - Conservative approach may be sufficient")
        
    except Exception as e:
        print(f"\n[ERROR] Error: {e}")
        print("Note: This example requires real market data to run.")
    
    print()


def main():
    """Run all examples"""
    print("\n" + "=" * 80)
    print("PROFILE COMPARISON EXAMPLES")
    print("=" * 80)
    print("\nThese examples demonstrate how to use the ProfileComparator")
    print("for analyzing and comparing different risk profiles.")
    print("\nNote: Examples require market data connection to run successfully.")
    print("=" * 80)
    
    examples = [
        ("Basic Comparison", example_1_basic_comparison),
        ("Two-Profile Comparison", example_2_two_profile_comparison),
        ("Optimization Insights", example_3_optimization_insights),
        ("Custom Profiles", example_4_custom_profile_comparison),
        ("Interpreting Rankings", example_5_interpreting_rankings),
        ("Summary Statistics", example_6_summary_statistics)
    ]
    
    for i, (name, func) in enumerate(examples, 1):
        print(f"\n\nRunning Example {i}: {name}")
        print("-" * 80)
        func()
        
        if i < len(examples):
            input("\nPress Enter to continue to next example...")
    
    print("\n" + "=" * 80)
    print("EXAMPLES COMPLETED")
    print("=" * 80)


if __name__ == '__main__':
    main()
