"""
Strategy Templates Usage Examples

This module demonstrates how to use the pre-built strategy templates
for backtesting. Each template implements a proven trading approach
with sensible defaults that can be customized.

Templates Available:
- MovingAverageCrossStrategy: Dual MA crossover system
- MeanReversionStrategy: Bollinger Bands + RSI mean reversion
- MomentumStrategy: ROC + MACD trend following
"""


import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
del _os, _sys

from datetime import datetime

from backtest.strategy_templates import (
    MovingAverageCrossStrategy, MACrossConfig,
    MeanReversionStrategy, MeanReversionConfig,
    MomentumStrategy, MomentumConfig,
    get_template, list_templates
)
from backtest.strategy import StrategyConfig
from backtest.engine import BacktestEngine
from backtest.profiles import ProfileManager


def example_1_basic_ma_cross():
    """
    Example 1: Basic Moving Average Crossover Strategy
    
    The classic dual moving average system - buy when fast MA crosses
    above slow MA, sell when it crosses below.
    """
    print("=" * 80)
    print("EXAMPLE 1: Moving Average Crossover Strategy")
    print("=" * 80)
    
    # Create strategy configuration
    config = StrategyConfig(
        name="MA_Cross_20_50",
        symbols=['AAPL', 'MSFT'],
        initial_capital=100000.0
    )
    
    # Configure MA periods
    ma_config = MACrossConfig(
        fast_period=20,  # 20-day fast MA
        slow_period=50,  # 50-day slow MA
        min_bars=50      # Wait for 50 bars before trading
    )
    
    # Create strategy
    strategy = MovingAverageCrossStrategy(config, ma_config)
    
    print("\nStrategy Configuration:")
    print(f"  Fast Period: {ma_config.fast_period} days")
    print(f"  Slow Period: {ma_config.slow_period} days")
    print(f"  Min Bars: {ma_config.min_bars}")
    print(f"  Symbols: {', '.join(config.symbols)}")
    print(f"  Initial Capital: ${config.initial_capital:,.2f}")
    
    print("\nTrading Rules:")
    print("  • BUY: When fast MA crosses above slow MA (Golden Cross)")
    print("  • SELL: When fast MA crosses below slow MA (Death Cross)")
    print("  • Works best in trending markets")
    print("  • May generate false signals in choppy markets")
    
    print("\nTo run backtest:")
    print("  engine = BacktestEngine()")
    print("  result = engine.run_backtest(strategy, start_date, end_date)")
    print()


def example_2_custom_ma_cross():
    """
    Example 2: Custom MA Cross with Different Periods
    
    Demonstrates how to customize MA periods for different timeframes.
    """
    print("=" * 80)
    print("EXAMPLE 2: Custom MA Cross Configurations")
    print("=" * 80)
    
    configurations = [
        ("Short-term", 10, 20, "Day trading, quick signals"),
        ("Medium-term", 20, 50, "Swing trading, balanced"),
        ("Long-term", 50, 200, "Position trading, major trends")
    ]
    
    print("\nCommon MA Cross Configurations:\n")
    
    for name, fast, slow, description in configurations:
        print(f"{name} ({fast}/{slow}):")
        print(f"  Fast: {fast} days, Slow: {slow} days")
        print(f"  Use case: {description}")
        
        ma_config = MACrossConfig(fast_period=fast, slow_period=slow)
        print(f"  Min bars required: {ma_config.min_bars}")
        print()


def example_3_mean_reversion():
    """
    Example 3: Mean Reversion Strategy
    
    Uses Bollinger Bands and RSI to identify oversold/overbought conditions
    and trades the reversion to the mean.
    """
    print("=" * 80)
    print("EXAMPLE 3: Mean Reversion Strategy")
    print("=" * 80)
    
    # Create strategy configuration
    config = StrategyConfig(
        name="MeanReversion_BB_RSI",
        symbols=['SPY', 'QQQ'],
        initial_capital=100000.0
    )
    
    # Configure mean reversion parameters
    mr_config = MeanReversionConfig(
        bb_period=20,           # 20-day Bollinger Bands
        bb_std=2.0,            # 2 standard deviations
        rsi_period=14,         # 14-day RSI
        rsi_oversold=30.0,     # Buy when RSI < 30
        rsi_overbought=70.0    # Sell when RSI > 70
    )
    
    # Create strategy
    strategy = MeanReversionStrategy(config, mr_config)
    
    print("\nStrategy Configuration:")
    print(f"  BB Period: {mr_config.bb_period} days")
    print(f"  BB Std Dev: {mr_config.bb_std}")
    print(f"  RSI Period: {mr_config.rsi_period} days")
    print(f"  RSI Oversold: {mr_config.rsi_oversold}")
    print(f"  RSI Overbought: {mr_config.rsi_overbought}")
    
    print("\nTrading Rules:")
    print("  • BUY: Price at/below lower BB AND RSI < 30 (oversold)")
    print("  • SELL: Price at/above upper BB AND RSI > 70 (overbought)")
    print("  • Both conditions must be met for a signal")
    print("  • Works best in range-bound markets")
    print("  • May underperform in strong trends")
    print()


def example_4_momentum():
    """
    Example 4: Momentum Strategy
    
    Follows trends using Rate of Change (ROC) and MACD confirmation.
    """
    print("=" * 80)
    print("EXAMPLE 4: Momentum Strategy")
    print("=" * 80)
    
    # Create strategy configuration
    config = StrategyConfig(
        name="Momentum_ROC_MACD",
        symbols=['AAPL', 'GOOGL', 'MSFT'],
        initial_capital=100000.0
    )
    
    # Configure momentum parameters
    mom_config = MomentumConfig(
        lookback_period=20,      # 20-day momentum
        momentum_threshold=0.02,  # 2% minimum momentum
        macd_fast=12,            # 12-day fast EMA
        macd_slow=26,            # 26-day slow EMA
        macd_signal=9            # 9-day signal line
    )
    
    # Create strategy
    strategy = MomentumStrategy(config, mom_config)
    
    print("\nStrategy Configuration:")
    print(f"  Lookback Period: {mom_config.lookback_period} days")
    print(f"  Momentum Threshold: {mom_config.momentum_threshold * 100}%")
    print(f"  MACD Fast: {mom_config.macd_fast}")
    print(f"  MACD Slow: {mom_config.macd_slow}")
    print(f"  MACD Signal: {mom_config.macd_signal}")
    
    print("\nTrading Rules:")
    print("  • BUY: ROC > 2% AND MACD > signal line (strong uptrend)")
    print("  • SELL: ROC < -2% AND MACD < signal line (strong downtrend)")
    print("  • Both conditions must be met for a signal")
    print("  • Works best in trending markets")
    print("  • Filters out weak momentum moves")
    print()


def example_5_template_registry():
    """
    Example 5: Using the Template Registry
    
    Shows how to discover and use templates dynamically.
    """
    print("=" * 80)
    print("EXAMPLE 5: Template Registry")
    print("=" * 80)
    
    # List all available templates
    templates = list_templates()
    
    print("\nAvailable Strategy Templates:")
    for i, template_name in enumerate(templates, 1):
        template_class = get_template(template_name)
        print(f"\n{i}. {template_name}")
        print(f"   Class: {template_class.__name__}")
        print(f"   Description: {template_class.__doc__.split(chr(10))[1].strip()}")
    
    print("\n" + "=" * 80)
    print("\nDynamic Template Usage:")
    print("  # Get template by name")
    print("  template_class = get_template('ma_cross')")
    print("  strategy = template_class(config)")
    print()


def example_6_with_risk_profiles():
    """
    Example 6: Combining Templates with Risk Profiles
    
    Shows how to use strategy templates with different risk profiles
    for position sizing and risk management.
    """
    print("=" * 80)
    print("EXAMPLE 6: Templates + Risk Profiles")
    print("=" * 80)
    
    # Create profile manager
    profile_manager = ProfileManager()
    
    # Get risk profiles
    conservative = profile_manager.get_profile('conservative')
    moderate = profile_manager.get_profile('moderate')
    aggressive = profile_manager.get_profile('aggressive')
    
    print("\nRisk Profile Comparison:")
    print("\n" + "-" * 80)
    
    profiles = [
        ('Conservative', conservative),
        ('Moderate', moderate),
        ('Aggressive', aggressive)
    ]
    
    for name, profile in profiles:
        print(f"\n{name} Profile:")
        print(f"  Max Position Size: {profile['max_position_size_pct'] * 100}%")
        print(f"  Max Portfolio Risk: {profile['max_portfolio_risk_pct'] * 100}%")
        print(f"  Max Total Exposure: {profile['max_total_exposure_pct'] * 100}%")
        print(f"  Stop Loss: {profile['stop_loss_pct'] * 100}%")
        print(f"  Take Profit: {profile['take_profit_pct'] * 100}%")
    
    print("\n" + "-" * 80)
    print("\nUsing Templates with Profiles:")
    print("  # Create MA Cross strategy with conservative profile")
    print("  config = StrategyConfig(")
    print("      name='MA_Cross_Conservative',")
    print("      symbols=['SPY'],")
    print("      initial_capital=100000.0,")
    print("      max_position_size=conservative['max_position_size_pct']")
    print("  )")
    print("  strategy = MovingAverageCrossStrategy(config)")
    print()


def example_7_parameter_tuning():
    """
    Example 7: Parameter Tuning Guidelines
    
    Provides guidance on adjusting strategy parameters for different
    market conditions and trading styles.
    """
    print("=" * 80)
    print("EXAMPLE 7: Parameter Tuning Guidelines")
    print("=" * 80)
    
    print("\nMoving Average Cross:")
    print("  Faster signals (more trades):")
    print("    • Decrease MA periods (e.g., 10/20 instead of 20/50)")
    print("    • More whipsaws in choppy markets")
    print("  Slower signals (fewer trades):")
    print("    • Increase MA periods (e.g., 50/200 instead of 20/50)")
    print("    • Miss early entry/exit but avoid false signals")
    
    print("\nMean Reversion:")
    print("  More conservative (fewer trades):")
    print("    • Increase BB std (e.g., 2.5 instead of 2.0)")
    print("    • Lower RSI oversold (e.g., 20 instead of 30)")
    print("    • Higher RSI overbought (e.g., 80 instead of 70)")
    print("  More aggressive (more trades):")
    print("    • Decrease BB std (e.g., 1.5 instead of 2.0)")
    print("    • Higher RSI oversold (e.g., 35 instead of 30)")
    print("    • Lower RSI overbought (e.g., 65 instead of 70)")
    
    print("\nMomentum:")
    print("  Capture stronger trends only:")
    print("    • Increase momentum threshold (e.g., 0.05 instead of 0.02)")
    print("    • Increase lookback period (e.g., 30 instead of 20)")
    print("  Capture more trend opportunities:")
    print("    • Decrease momentum threshold (e.g., 0.01 instead of 0.02)")
    print("    • Decrease lookback period (e.g., 10 instead of 20)")
    
    print("\n" + "=" * 80)
    print("Remember: Always backtest parameter changes before live trading!")
    print("=" * 80)
    print()


def main():
    """Run all examples"""
    print("\n" + "=" * 80)
    print("STRATEGY TEMPLATES USAGE EXAMPLES")
    print("=" * 80)
    print("\nThese examples demonstrate how to use pre-built strategy templates")
    print("for backtesting and live trading.")
    print("=" * 80)
    
    examples = [
        ("Basic MA Cross", example_1_basic_ma_cross),
        ("Custom MA Cross", example_2_custom_ma_cross),
        ("Mean Reversion", example_3_mean_reversion),
        ("Momentum", example_4_momentum),
        ("Template Registry", example_5_template_registry),
        ("Risk Profiles", example_6_with_risk_profiles),
        ("Parameter Tuning", example_7_parameter_tuning)
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
    print("\nFor more information:")
    print("  • Strategy templates: backtest/strategy_templates.py")
    print("  • Risk profiles: backtest/profiles.py")
    print("  • Backtest engine: backtest/engine.py")
    print("=" * 80)


if __name__ == '__main__':
    main()
