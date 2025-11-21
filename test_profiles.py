"""
Tests for Risk Profile Framework (Week 4 Day 4)

Tests cover:
- RiskProfile dataclass validation
- ProfileLibrary pre-defined profiles
- ProfileManager operations
- Custom profile creation
- Profile comparison
- Edge cases and error handling
"""

import pytest
from backtest.profiles import (
    RiskProfile, ProfileType, ProfileLibrary, ProfileManager
)


class TestRiskProfile:
    """Test RiskProfile dataclass"""
    
    def test_risk_profile_creation(self):
        """Test creating a basic risk profile"""
        profile = RiskProfile(
            name="Test Profile",
            profile_type=ProfileType.CUSTOM,
            description="Test profile",
            max_position_size=0.10
        )
        
        assert profile.name == "Test Profile"
        assert profile.profile_type == ProfileType.CUSTOM
        assert profile.max_position_size == 0.10
    
    def test_risk_profile_defaults(self):
        """Test default values are set correctly"""
        profile = RiskProfile(
            name="Defaults",
            profile_type=ProfileType.CUSTOM
        )
        
        assert profile.max_position_size == 0.10
        assert profile.min_position_size == 0.01
        assert profile.max_portfolio_risk == 0.02
        assert profile.max_daily_loss == 0.05
        assert profile.max_drawdown == 0.15
        assert profile.default_stop_loss == 0.02
        assert profile.default_profit_target == 0.06
        assert profile.max_leverage == 1.0
        assert profile.max_concurrent_positions == 5
        assert not profile.allow_shorting
    
    def test_profile_validation_success(self):
        """Test validation passes for valid profile"""
        profile = ProfileLibrary.moderate()
        errors = profile.validate()
        
        assert len(errors) == 0
        assert profile.is_valid()
    
    def test_profile_validation_invalid_position_size(self):
        """Test validation catches invalid position sizes"""
        # Max position size too large
        profile = RiskProfile(
            name="Invalid",
            profile_type=ProfileType.CUSTOM,
            max_position_size=1.5  # > 1.0
        )
        errors = profile.validate()
        assert any("max_position_size" in err for err in errors)
        assert not profile.is_valid()
        
        # Min position size larger than max
        profile2 = RiskProfile(
            name="Invalid2",
            profile_type=ProfileType.CUSTOM,
            max_position_size=0.05,
            min_position_size=0.10  # > max
        )
        errors2 = profile2.validate()
        assert any("min_position_size" in err for err in errors2)
    
    def test_profile_validation_invalid_risk_limits(self):
        """Test validation catches invalid risk limits"""
        # Portfolio risk too high
        profile = RiskProfile(
            name="Risky",
            profile_type=ProfileType.CUSTOM,
            max_portfolio_risk=0.30  # > 0.20
        )
        errors = profile.validate()
        assert any("max_portfolio_risk" in err for err in errors)
        
        # Daily loss too high
        profile2 = RiskProfile(
            name="Risky2",
            profile_type=ProfileType.CUSTOM,
            max_daily_loss=0.60  # > 0.50
        )
        errors2 = profile2.validate()
        assert any("max_daily_loss" in err for err in errors2)
    
    def test_profile_validation_risk_reward_ratio(self):
        """Test validation checks risk:reward ratio"""
        # Bad risk:reward (target < stop loss)
        profile = RiskProfile(
            name="BadRatio",
            profile_type=ProfileType.CUSTOM,
            default_stop_loss=0.05,
            default_profit_target=0.03  # < stop loss
        )
        errors = profile.validate()
        assert any("Risk:reward" in err for err in errors)
    
    def test_profile_validation_leverage(self):
        """Test validation checks leverage limits"""
        # Leverage too high
        profile = RiskProfile(
            name="HighLeverage",
            profile_type=ProfileType.CUSTOM,
            max_leverage=5.0  # > 4.0
        )
        errors = profile.validate()
        assert any("max_leverage" in err for err in errors)
    
    def test_profile_validation_exposure(self):
        """Test validation checks exposure limits"""
        # Single exposure > total exposure
        profile = RiskProfile(
            name="BadExposure",
            profile_type=ProfileType.CUSTOM,
            max_total_exposure=1.0,
            max_single_exposure=1.5  # > total
        )
        errors = profile.validate()
        assert any("max_single_exposure" in err for err in errors)
    
    def test_profile_validation_position_limits(self):
        """Test validation checks position limits"""
        # Too many concurrent positions
        profile = RiskProfile(
            name="TooMany",
            profile_type=ProfileType.CUSTOM,
            max_concurrent_positions=100  # > 50
        )
        errors = profile.validate()
        assert any("max_concurrent_positions" in err for err in errors)
        
        # Zero positions per symbol
        profile2 = RiskProfile(
            name="ZeroPos",
            profile_type=ProfileType.CUSTOM,
            max_positions_per_symbol=0
        )
        errors2 = profile2.validate()
        assert any("max_positions_per_symbol" in err for err in errors2)
    
    def test_profile_to_dict(self):
        """Test converting profile to dictionary"""
        profile = ProfileLibrary.conservative()
        data = profile.to_dict()
        
        assert data['name'] == "Conservative"
        assert data['profile_type'] == "conservative"
        assert data['max_position_size'] == 0.05
        assert data['max_leverage'] == 1.0
        assert not data['allow_shorting']
    
    def test_profile_copy(self):
        """Test deep copying a profile"""
        original = ProfileLibrary.moderate()
        copied = original.copy()
        
        # Verify it's a copy
        assert copied.name == original.name
        assert copied.max_position_size == original.max_position_size
        
        # Modify copy
        copied.max_position_size = 0.15
        
        # Original unchanged
        assert original.max_position_size == 0.10
        assert copied.max_position_size == 0.15


class TestProfileLibrary:
    """Test ProfileLibrary with pre-defined profiles"""
    
    def test_conservative_profile(self):
        """Test conservative profile characteristics"""
        profile = ProfileLibrary.conservative()
        
        assert profile.name == "Conservative"
        assert profile.profile_type == ProfileType.CONSERVATIVE
        assert profile.max_position_size == 0.05
        assert profile.max_portfolio_risk == 0.01
        assert profile.max_drawdown == 0.10
        assert profile.max_leverage == 1.0
        assert profile.max_concurrent_positions == 3
        assert not profile.allow_shorting
        assert profile.is_valid()
    
    def test_moderate_profile(self):
        """Test moderate profile characteristics"""
        profile = ProfileLibrary.moderate()
        
        assert profile.name == "Moderate"
        assert profile.profile_type == ProfileType.MODERATE
        assert profile.max_position_size == 0.10
        assert profile.max_portfolio_risk == 0.02
        assert profile.max_drawdown == 0.15
        assert profile.max_leverage == 1.5
        assert profile.max_concurrent_positions == 5
        assert not profile.allow_shorting
        assert profile.is_valid()
    
    def test_aggressive_profile(self):
        """Test aggressive profile characteristics"""
        profile = ProfileLibrary.aggressive()
        
        assert profile.name == "Aggressive"
        assert profile.profile_type == ProfileType.AGGRESSIVE
        assert profile.max_position_size == 0.20
        assert profile.max_portfolio_risk == 0.03
        assert profile.max_drawdown == 0.25
        assert profile.max_leverage == 2.0
        assert profile.max_concurrent_positions == 8
        assert profile.allow_shorting  # Aggressive allows shorting
        assert profile.is_valid()
    
    def test_risk_progression(self):
        """Test that risk increases from Conservative -> Moderate -> Aggressive"""
        conservative = ProfileLibrary.conservative()
        moderate = ProfileLibrary.moderate()
        aggressive = ProfileLibrary.aggressive()
        
        # Position sizes increase
        assert conservative.max_position_size < moderate.max_position_size < aggressive.max_position_size
        
        # Risk tolerances increase
        assert conservative.max_portfolio_risk < moderate.max_portfolio_risk < aggressive.max_portfolio_risk
        assert conservative.max_drawdown < moderate.max_drawdown < aggressive.max_drawdown
        
        # Leverage increases
        assert conservative.max_leverage < moderate.max_leverage < aggressive.max_leverage
        
        # Concurrent positions increase
        assert conservative.max_concurrent_positions < moderate.max_concurrent_positions < aggressive.max_concurrent_positions
    
    def test_get_all_profiles(self):
        """Test getting all pre-defined profiles"""
        profiles = ProfileLibrary.get_all_profiles()
        
        assert len(profiles) == 3
        assert 'conservative' in profiles
        assert 'moderate' in profiles
        assert 'aggressive' in profiles
        
        # All are valid
        for profile in profiles.values():
            assert profile.is_valid()
    
    def test_get_profile_by_name(self):
        """Test retrieving profile by name"""
        conservative = ProfileLibrary.get_profile('conservative')
        assert conservative is not None
        assert conservative.name == "Conservative"
        
        # Case insensitive
        moderate = ProfileLibrary.get_profile('MODERATE')
        assert moderate is not None
        assert moderate.name == "Moderate"
        
        # Non-existent
        invalid = ProfileLibrary.get_profile('nonexistent')
        assert invalid is None


class TestProfileManager:
    """Test ProfileManager operations"""
    
    def test_manager_initialization(self):
        """Test manager initializes with default profiles"""
        manager = ProfileManager()
        
        profiles = manager.list_profiles()
        assert len(profiles) == 3
        assert 'conservative' in profiles
        assert 'moderate' in profiles
        assert 'aggressive' in profiles
    
    def test_get_profile(self):
        """Test retrieving profiles from manager"""
        manager = ProfileManager()
        
        # Get existing profile
        moderate = manager.get_profile('moderate')
        assert moderate is not None
        assert moderate.name == "Moderate"
        
        # Case insensitive
        conservative = manager.get_profile('CONSERVATIVE')
        assert conservative is not None
        
        # Non-existent
        invalid = manager.get_profile('nonexistent')
        assert invalid is None
    
    def test_add_valid_custom_profile(self):
        """Test adding a valid custom profile"""
        manager = ProfileManager()
        
        custom = RiskProfile(
            name="Custom",
            profile_type=ProfileType.CUSTOM,
            max_position_size=0.08,
            max_portfolio_risk=0.015
        )
        
        result = manager.add_profile(custom)
        assert result is True
        
        # Verify it's added
        retrieved = manager.get_profile('custom')
        assert retrieved is not None
        assert retrieved.name == "Custom"
    
    def test_add_invalid_profile(self):
        """Test adding invalid profile fails"""
        manager = ProfileManager()
        
        invalid = RiskProfile(
            name="Invalid",
            profile_type=ProfileType.CUSTOM,
            max_position_size=2.0  # Invalid
        )
        
        result = manager.add_profile(invalid)
        assert result is False
        
        # Not added
        assert manager.get_profile('invalid') is None
    
    def test_add_duplicate_profile(self):
        """Test adding duplicate profile without overwrite fails"""
        manager = ProfileManager()
        
        custom = RiskProfile(
            name="Moderate",  # Already exists
            profile_type=ProfileType.CUSTOM
        )
        
        result = manager.add_profile(custom, overwrite=False)
        assert result is False
    
    def test_add_duplicate_with_overwrite(self):
        """Test overwriting existing profile"""
        manager = ProfileManager()
        
        # Get original
        original = manager.get_profile('moderate')
        assert original.max_position_size == 0.10
        
        # Create modified version
        modified = RiskProfile(
            name="Moderate",
            profile_type=ProfileType.CUSTOM,
            max_position_size=0.12  # Different
        )
        
        result = manager.add_profile(modified, overwrite=True)
        assert result is True
        
        # Verify it's updated
        updated = manager.get_profile('moderate')
        assert updated.max_position_size == 0.12
    
    def test_remove_profile(self):
        """Test removing a profile"""
        manager = ProfileManager()
        
        # Add custom profile
        custom = RiskProfile(
            name="ToRemove",
            profile_type=ProfileType.CUSTOM
        )
        manager.add_profile(custom)
        
        # Verify it exists
        assert manager.get_profile('toremove') is not None
        
        # Remove it
        result = manager.remove_profile('toremove')
        assert result is True
        
        # Verify it's gone
        assert manager.get_profile('toremove') is None
    
    def test_remove_nonexistent_profile(self):
        """Test removing non-existent profile returns False"""
        manager = ProfileManager()
        
        result = manager.remove_profile('nonexistent')
        assert result is False
    
    def test_list_profiles(self):
        """Test listing all profiles"""
        manager = ProfileManager()
        
        profiles = manager.list_profiles()
        assert len(profiles) == 3
        assert 'conservative' in profiles
        assert 'moderate' in profiles
        assert 'aggressive' in profiles
        
        # Add custom
        custom = RiskProfile(
            name="Custom",
            profile_type=ProfileType.CUSTOM
        )
        manager.add_profile(custom)
        
        profiles = manager.list_profiles()
        assert len(profiles) == 4
        assert 'custom' in profiles
    
    def test_compare_profiles(self):
        """Test comparing two profiles"""
        manager = ProfileManager()
        
        comparison = manager.compare_profiles('conservative', 'aggressive')
        
        assert 'profile1' in comparison
        assert 'profile2' in comparison
        assert 'differences' in comparison
        
        # Should have differences
        diffs = comparison['differences']
        assert len(diffs) > 0
        assert 'max_position_size' in diffs
        assert 'max_drawdown' in diffs
        assert 'allow_shorting' in diffs
    
    def test_compare_nonexistent_profiles(self):
        """Test comparing with non-existent profile"""
        manager = ProfileManager()
        
        comparison = manager.compare_profiles('conservative', 'nonexistent')
        assert 'error' in comparison
    
    def test_create_custom_profile_from_base(self):
        """Test creating custom profile based on existing one"""
        manager = ProfileManager()
        
        custom = manager.create_custom_profile(
            name="MyCustom",
            base_profile="moderate",
            max_position_size=0.12,
            max_concurrent_positions=7
        )
        
        assert custom is not None
        assert custom.name == "MyCustom"
        assert custom.profile_type == ProfileType.CUSTOM
        assert custom.max_position_size == 0.12  # Overridden
        assert custom.max_concurrent_positions == 7  # Overridden
        assert custom.max_portfolio_risk == 0.02  # From moderate base
    
    def test_create_custom_invalid_base(self):
        """Test creating custom profile with invalid base"""
        manager = ProfileManager()
        
        custom = manager.create_custom_profile(
            name="Invalid",
            base_profile="nonexistent"
        )
        
        assert custom is None
    
    def test_create_custom_invalid_overrides(self):
        """Test creating custom profile with invalid overrides"""
        manager = ProfileManager()
        
        custom = manager.create_custom_profile(
            name="Invalid",
            base_profile="moderate",
            max_position_size=2.0  # Invalid
        )
        
        assert custom is None
    
    def test_create_custom_unknown_parameter(self):
        """Test creating custom profile with unknown parameter"""
        manager = ProfileManager()
        
        # Should succeed but ignore unknown parameter
        custom = manager.create_custom_profile(
            name="WithUnknown",
            base_profile="moderate",
            unknown_param=123  # Unknown
        )
        
        assert custom is not None
        assert not hasattr(custom, 'unknown_param')


class TestProfileIntegration:
    """Test profile integration scenarios"""
    
    def test_profile_comparison_conservative_vs_aggressive(self):
        """Test detailed comparison of conservative vs aggressive"""
        manager = ProfileManager()
        
        comparison = manager.compare_profiles('conservative', 'aggressive')
        diffs = comparison['differences']
        
        # Verify key differences
        assert diffs['max_position_size']['Conservative'] < diffs['max_position_size']['Aggressive']
        assert diffs['max_drawdown']['Conservative'] < diffs['max_drawdown']['Aggressive']
        assert diffs['max_leverage']['Conservative'] < diffs['max_leverage']['Aggressive']
        assert diffs['allow_shorting']['Conservative'] is False
        assert diffs['allow_shorting']['Aggressive'] is True
    
    def test_progressive_custom_profiles(self):
        """Test creating a series of custom profiles"""
        manager = ProfileManager()
        
        # Create slightly more aggressive than conservative
        custom1 = manager.create_custom_profile(
            name="Conservative Plus",
            base_profile="conservative",
            max_position_size=0.07,
            max_concurrent_positions=4
        )
        assert custom1 is not None
        
        # Create slightly less aggressive than aggressive
        custom2 = manager.create_custom_profile(
            name="Moderate Plus",
            base_profile="moderate",
            max_position_size=0.15,
            max_leverage=1.8
        )
        assert custom2 is not None
        
        # Verify risk progression
        conservative = manager.get_profile('conservative')
        assert conservative.max_position_size < custom1.max_position_size
        assert custom1.max_position_size < custom2.max_position_size
    
    def test_profile_extensibility(self):
        """Test that profiles are extensible with custom parameters"""
        profile = RiskProfile(
            name="Extended",
            profile_type=ProfileType.CUSTOM,
            custom_params={
                'use_trailing_stop': True,
                'trailing_stop_pct': 0.05,
                'min_volume': 1000000,
                'sectors': ['Technology', 'Healthcare']
            }
        )
        
        assert profile.custom_params['use_trailing_stop'] is True
        assert profile.custom_params['trailing_stop_pct'] == 0.05
        assert len(profile.custom_params['sectors']) == 2
    
    def test_all_library_profiles_valid(self):
        """Test that all library profiles pass validation"""
        profiles = ProfileLibrary.get_all_profiles()
        
        for name, profile in profiles.items():
            errors = profile.validate()
            assert len(errors) == 0, f"Profile '{name}' has validation errors: {errors}"
            assert profile.is_valid()


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
