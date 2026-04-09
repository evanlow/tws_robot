"""
Risk Profile Framework - Usage Examples

This example demonstrates how to use the risk profile framework
for backtesting strategies with different risk tolerances.

Week 4 Day 4
"""


import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
del _os, _sys

from backtest.profiles import (
    RiskProfile, ProfileType, ProfileLibrary, ProfileManager
)


def example_1_using_predefined_profiles():
    """Example 1: Using pre-defined profiles"""
    print("="*60)
    print("Example 1: Using Pre-defined Profiles")
    print("="*60)
    
    # Get profiles from library
    conservative = ProfileLibrary.conservative()
    moderate = ProfileLibrary.moderate()
    aggressive = ProfileLibrary.aggressive()
    
    print(f"\n{conservative.name} Profile:")
    print(f"  Max Position Size: {conservative.max_position_size*100}%")
    print(f"  Max Portfolio Risk: {conservative.max_portfolio_risk*100}%")
    print(f"  Max Drawdown: {conservative.max_drawdown*100}%")
    print(f"  Max Leverage: {conservative.max_leverage}x")
    print(f"  Stop Loss: {conservative.default_stop_loss*100}%")
    print(f"  Profit Target: {conservative.default_profit_target*100}%")
    print(f"  Allow Shorting: {conservative.allow_shorting}")
    
    print(f"\n{moderate.name} Profile:")
    print(f"  Max Position Size: {moderate.max_position_size*100}%")
    print(f"  Max Portfolio Risk: {moderate.max_portfolio_risk*100}%")
    print(f"  Max Drawdown: {moderate.max_drawdown*100}%")
    print(f"  Max Leverage: {moderate.max_leverage}x")
    print(f"  Stop Loss: {moderate.default_stop_loss*100}%")
    print(f"  Profit Target: {moderate.default_profit_target*100}%")
    print(f"  Allow Shorting: {moderate.allow_shorting}")
    
    print(f"\n{aggressive.name} Profile:")
    print(f"  Max Position Size: {aggressive.max_position_size*100}%")
    print(f"  Max Portfolio Risk: {aggressive.max_portfolio_risk*100}%")
    print(f"  Max Drawdown: {aggressive.max_drawdown*100}%")
    print(f"  Max Leverage: {aggressive.max_leverage}x")
    print(f"  Stop Loss: {aggressive.default_stop_loss*100}%")
    print(f"  Profit Target: {aggressive.default_profit_target*100}%")
    print(f"  Allow Shorting: {aggressive.allow_shorting}")


def example_2_profile_manager():
    """Example 2: Using ProfileManager"""
    print("\n" + "="*60)
    print("Example 2: Using ProfileManager")
    print("="*60)
    
    # Create manager
    manager = ProfileManager()
    
    # List available profiles
    print("\nAvailable profiles:")
    for name in manager.list_profiles():
        profile = manager.get_profile(name)
        print(f"  - {profile.name}: {profile.description}")
    
    # Get a specific profile
    moderate = manager.get_profile('moderate')
    print(f"\nRetrieved '{moderate.name}' profile")
    print(f"  Valid: {moderate.is_valid()}")


def example_3_custom_profile():
    """Example 3: Creating custom profiles"""
    print("\n" + "="*60)
    print("Example 3: Creating Custom Profiles")
    print("="*60)
    
    manager = ProfileManager()
    
    # Method 1: Create from scratch
    print("\nMethod 1: Create from scratch")
    custom1 = RiskProfile(
        name="Day Trader",
        profile_type=ProfileType.CUSTOM,
        description="Profile for active day trading",
        max_position_size=0.15,
        max_portfolio_risk=0.025,
        max_drawdown=0.20,
        default_stop_loss=0.01,  # Tight 1% stops
        default_profit_target=0.02,  # Quick 2% targets
        max_leverage=1.5,
        max_concurrent_positions=10,
        allow_shorting=True
    )
    
    # Validate
    errors = custom1.validate()
    if errors:
        print(f"  Validation errors: {errors}")
    else:
        print(f"  Created '{custom1.name}' profile")
        print(f"  Valid: {custom1.is_valid()}")
        manager.add_profile(custom1)
    
    # Method 2: Create from existing profile
    print("\nMethod 2: Create from existing profile")
    custom2 = manager.create_custom_profile(
        name="Conservative Plus",
        base_profile="conservative",
        max_position_size=0.07,  # Slightly larger than conservative
        max_concurrent_positions=4  # One more position
    )
    
    if custom2:
        print(f"  Created '{custom2.name}' based on Conservative")
        print(f"  Max Position: {custom2.max_position_size*100}% (Conservative: 5%)")
        print(f"  Max Positions: {custom2.max_concurrent_positions} (Conservative: 3)")
        manager.add_profile(custom2)
    
    # List all profiles
    print(f"\nTotal profiles: {len(manager.list_profiles())}")
    for name in manager.list_profiles():
        print(f"  - {name}")


def example_4_profile_comparison():
    """Example 4: Comparing profiles"""
    print("\n" + "="*60)
    print("Example 4: Comparing Profiles")
    print("="*60)
    
    manager = ProfileManager()
    
    # Compare conservative vs aggressive
    comparison = manager.compare_profiles('conservative', 'aggressive')
    
    print(f"\nComparing: {comparison['profile1']} vs {comparison['profile2']}")
    print("\nKey Differences:")
    
    for param, values in comparison['differences'].items():
        p1_val = values[comparison['profile1']]
        p2_val = values[comparison['profile2']]
        print(f"  {param}:")
        print(f"    {comparison['profile1']}: {p1_val}")
        print(f"    {comparison['profile2']}: {p2_val}")


def example_5_backtest_integration():
    """Example 5: Using profiles with backtesting (conceptual)"""
    print("\n" + "="*60)
    print("Example 5: Backtest Integration (Conceptual)")
    print("="*60)
    
    manager = ProfileManager()
    
    # Get profile for strategy
    profile = manager.get_profile('moderate')
    
    print(f"\nUsing '{profile.name}' profile for backtest")
    print("\nProfile Configuration:")
    print(f"  Position Sizing: {profile.min_position_size*100}% - {profile.max_position_size*100}%")
    print(f"  Risk per Trade: {profile.max_portfolio_risk*100}%")
    print(f"  Stop Loss: {profile.default_stop_loss*100}%")
    print(f"  Profit Target: {profile.default_profit_target*100}%")
    print(f"  Max Concurrent: {profile.max_concurrent_positions} positions")
    
    # Conceptual backtest setup
    print("\nBacktest Setup:")
    print(f"""
    from backtest.engine import BacktestEngine, BacktestConfig
    from backtest.strategy import Strategy
    
    # Create strategy with profile constraints
    class MyStrategy(Strategy):
        def __init__(self, profile: RiskProfile):
            self.profile = profile
            # Configure strategy based on profile
            config = StrategyConfig(
                initial_capital=100000,
                max_position_size=profile.max_position_size,
                max_positions=profile.max_concurrent_positions
            )
            super().__init__(config)
        
        def calculate_position_size(self, price: float) -> int:
            # Use profile risk limits
            risk_per_trade = self.equity * self.profile.max_portfolio_risk
            stop_distance = price * self.profile.default_stop_loss
            shares = int(risk_per_trade / stop_distance)
            
            # Cap at max position size
            max_shares = int(self.equity * self.profile.max_position_size / price)
            return min(shares, max_shares)
    
    # Run backtest with profile
    profile = manager.get_profile('moderate')
    strategy = MyStrategy(profile)
    
    config = BacktestConfig(
        strategy=strategy,
        start_date='2023-01-01',
        end_date='2023-12-31',
        symbols=['AAPL', 'MSFT', 'GOOGL']
    )
    
    engine = BacktestEngine(config)
    results = engine.run()
    """)


def example_6_extensible_profiles():
    """Example 6: Extensible profiles with custom parameters"""
    print("\n" + "="*60)
    print("Example 6: Extensible Profiles (Custom Parameters)")
    print("="*60)
    
    # Create profile with custom parameters
    profile = RiskProfile(
        name="ML-Enhanced",
        profile_type=ProfileType.CUSTOM,
        description="Profile with ML-based adjustments",
        max_position_size=0.12,
        max_portfolio_risk=0.02,
        custom_params={
            # ML-specific parameters
            'use_ml_signal': True,
            'min_confidence': 0.75,
            'model_name': 'RandomForest_v2',
            
            # Advanced risk management
            'use_trailing_stop': True,
            'trailing_stop_pct': 0.05,
            'scale_out_levels': [0.03, 0.06, 0.09],
            
            # Market filters
            'min_volume': 1000000,
            'min_market_cap': 1e9,
            'allowed_sectors': ['Technology', 'Healthcare', 'Finance'],
            
            # Time filters
            'trading_hours_only': True,
            'avoid_earnings': True,
            'avoid_fomc': True
        }
    )
    
    print(f"\nCreated '{profile.name}' profile")
    print(f"Description: {profile.description}")
    print("\nStandard Parameters:")
    print(f"  Max Position Size: {profile.max_position_size*100}%")
    print(f"  Max Portfolio Risk: {profile.max_portfolio_risk*100}%")
    
    print("\nCustom Parameters:")
    for key, value in profile.custom_params.items():
        print(f"  {key}: {value}")
    
    # Custom parameters can be accessed
    if profile.custom_params.get('use_ml_signal'):
        print(f"\nML Signal enabled with min confidence: {profile.custom_params['min_confidence']}")
    
    if profile.custom_params.get('use_trailing_stop'):
        print(f"Trailing stop enabled: {profile.custom_params['trailing_stop_pct']*100}%")


def example_7_profile_validation():
    """Example 7: Profile validation"""
    print("\n" + "="*60)
    print("Example 7: Profile Validation")
    print("="*60)
    
    # Create invalid profile
    print("\nCreating invalid profile (for demonstration):")
    invalid = RiskProfile(
        name="Invalid",
        profile_type=ProfileType.CUSTOM,
        max_position_size=1.5,  # Too large
        max_portfolio_risk=0.30,  # Too high
        default_stop_loss=0.05,
        default_profit_target=0.03  # Lower than stop (bad risk:reward)
    )
    
    errors = invalid.validate()
    print(f"\nValidation errors found: {len(errors)}")
    for i, error in enumerate(errors, 1):
        print(f"  {i}. {error}")
    
    print(f"\nIs valid: {invalid.is_valid()}")
    
    # Fix the errors
    print("\nFixing errors...")
    invalid.max_position_size = 0.15
    invalid.max_portfolio_risk = 0.025
    invalid.default_profit_target = 0.15  # 3:1 risk:reward
    
    errors = invalid.validate()
    print(f"Validation errors: {len(errors)}")
    print(f"Is valid: {invalid.is_valid()}")


def main():
    """Run all examples"""
    print("\n" + "="*60)
    print("RISK PROFILE FRAMEWORK - USAGE EXAMPLES")
    print("="*60)
    
    example_1_using_predefined_profiles()
    example_2_profile_manager()
    example_3_custom_profile()
    example_4_profile_comparison()
    example_5_backtest_integration()
    example_6_extensible_profiles()
    example_7_profile_validation()
    
    print("\n" + "="*60)
    print("All examples completed!")
    print("="*60)


if __name__ == '__main__':
    main()
