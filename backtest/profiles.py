"""
Risk Profile Framework for Backtesting

This module provides risk profile management for backtesting strategies.
Profiles define risk tolerance levels (Conservative, Moderate, Aggressive)
with corresponding parameter constraints.

Features:
- Pre-defined risk profiles (Conservative, Moderate, Aggressive)
- Custom profile creation with validation
- Profile-based strategy configuration
- Integration with BacktestEngine
- Extensible for additional profiles

Author: Trading Bot Team
Week 4 Day 4
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from enum import Enum
import copy


class ProfileType(Enum):
    """Pre-defined risk profile types"""
    CONSERVATIVE = "conservative"
    MODERATE = "moderate"
    AGGRESSIVE = "aggressive"
    CUSTOM = "custom"


@dataclass
class RiskProfile:
    """
    Risk profile configuration for backtesting strategies
    
    Defines risk parameters that control strategy behavior:
    - Position sizing
    - Stop losses and profit targets
    - Maximum drawdown limits
    - Leverage constraints
    - Exposure limits
    """
    
    # Profile identification
    name: str
    profile_type: ProfileType
    description: str = ""
    
    # Position sizing (% of capital per position)
    max_position_size: float = 0.10  # 10% default
    min_position_size: float = 0.01  # 1% minimum
    
    # Risk limits (% of capital)
    max_portfolio_risk: float = 0.02  # 2% of portfolio per trade
    max_daily_loss: float = 0.05  # 5% max daily loss
    max_drawdown: float = 0.15  # 15% max drawdown before stopping
    
    # Stop loss and profit targets (% from entry)
    default_stop_loss: float = 0.02  # 2% stop loss
    default_profit_target: float = 0.06  # 6% profit target (3:1 reward:risk)
    
    # Leverage and exposure
    max_leverage: float = 1.0  # No leverage by default
    max_total_exposure: float = 1.0  # 100% of capital
    max_single_exposure: float = 0.20  # 20% per symbol
    
    # Position limits
    max_concurrent_positions: int = 5
    max_positions_per_symbol: int = 1
    
    # Trading constraints
    allow_shorting: bool = False
    allow_options: bool = False
    allow_futures: bool = False
    
    # Custom parameters (extensible)
    custom_params: Dict[str, Any] = field(default_factory=dict)
    
    def validate(self) -> List[str]:
        """
        Validate profile parameters
        
        Returns:
            List of validation errors (empty if valid)
        """
        errors = []
        
        # Position size validation
        if self.max_position_size <= 0 or self.max_position_size > 1.0:
            errors.append(f"max_position_size must be between 0 and 1.0, got {self.max_position_size}")
        
        if self.min_position_size <= 0 or self.min_position_size > self.max_position_size:
            errors.append(f"min_position_size must be > 0 and <= max_position_size")
        
        # Risk limits validation
        if self.max_portfolio_risk <= 0 or self.max_portfolio_risk > 0.20:
            errors.append(f"max_portfolio_risk should be between 0 and 0.20 (20%)")
        
        if self.max_daily_loss <= 0 or self.max_daily_loss > 0.50:
            errors.append(f"max_daily_loss should be between 0 and 0.50 (50%)")
        
        if self.max_drawdown <= 0 or self.max_drawdown > 0.50:
            errors.append(f"max_drawdown should be between 0 and 0.50 (50%)")
        
        # Stop loss and profit target validation
        if self.default_stop_loss <= 0 or self.default_stop_loss > 0.50:
            errors.append(f"default_stop_loss should be between 0 and 0.50 (50%)")
        
        if self.default_profit_target <= 0:
            errors.append(f"default_profit_target must be positive")
        
        # Risk:reward ratio check
        risk_reward = self.default_profit_target / self.default_stop_loss
        if risk_reward < 1.0:
            errors.append(f"Risk:reward ratio should be >= 1:1, got {risk_reward:.2f}:1")
        
        # Leverage validation
        if self.max_leverage < 1.0 or self.max_leverage > 4.0:
            errors.append(f"max_leverage should be between 1.0 and 4.0")
        
        # Exposure validation
        if self.max_total_exposure <= 0 or self.max_total_exposure > 2.0:
            errors.append(f"max_total_exposure should be between 0 and 2.0 (200%)")
        
        if self.max_single_exposure <= 0 or self.max_single_exposure > self.max_total_exposure:
            errors.append(f"max_single_exposure must be <= max_total_exposure")
        
        # Position limits
        if self.max_concurrent_positions <= 0 or self.max_concurrent_positions > 50:
            errors.append(f"max_concurrent_positions should be between 1 and 50")
        
        if self.max_positions_per_symbol <= 0:
            errors.append(f"max_positions_per_symbol must be positive")
        
        return errors
    
    def is_valid(self) -> bool:
        """Check if profile is valid"""
        return len(self.validate()) == 0
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert profile to dictionary"""
        return {
            'name': self.name,
            'profile_type': self.profile_type.value,
            'description': self.description,
            'max_position_size': self.max_position_size,
            'min_position_size': self.min_position_size,
            'max_portfolio_risk': self.max_portfolio_risk,
            'max_daily_loss': self.max_daily_loss,
            'max_drawdown': self.max_drawdown,
            'default_stop_loss': self.default_stop_loss,
            'default_profit_target': self.default_profit_target,
            'max_leverage': self.max_leverage,
            'max_total_exposure': self.max_total_exposure,
            'max_single_exposure': self.max_single_exposure,
            'max_concurrent_positions': self.max_concurrent_positions,
            'max_positions_per_symbol': self.max_positions_per_symbol,
            'allow_shorting': self.allow_shorting,
            'allow_options': self.allow_options,
            'allow_futures': self.allow_futures,
            'custom_params': self.custom_params
        }
    
    def copy(self) -> 'RiskProfile':
        """Create a deep copy of the profile"""
        return copy.deepcopy(self)


class ProfileLibrary:
    """Library of pre-defined risk profiles"""
    
    @staticmethod
    def conservative() -> RiskProfile:
        """
        Conservative risk profile
        
        Characteristics:
        - Small position sizes (5% max)
        - Tight risk controls
        - Low drawdown tolerance
        - No leverage
        - No shorting/derivatives
        - Focus on capital preservation
        """
        return RiskProfile(
            name="Conservative",
            profile_type=ProfileType.CONSERVATIVE,
            description="Low-risk profile focused on capital preservation",
            max_position_size=0.05,  # 5% max position
            min_position_size=0.01,  # 1% min position
            max_portfolio_risk=0.01,  # 1% risk per trade
            max_daily_loss=0.02,  # 2% max daily loss
            max_drawdown=0.10,  # 10% max drawdown
            default_stop_loss=0.015,  # 1.5% stop loss
            default_profit_target=0.045,  # 4.5% target (3:1 ratio)
            max_leverage=1.0,  # No leverage
            max_total_exposure=0.50,  # 50% total exposure
            max_single_exposure=0.10,  # 10% per symbol
            max_concurrent_positions=3,
            max_positions_per_symbol=1,
            allow_shorting=False,
            allow_options=False,
            allow_futures=False
        )
    
    @staticmethod
    def moderate() -> RiskProfile:
        """
        Moderate risk profile
        
        Characteristics:
        - Medium position sizes (10% max)
        - Balanced risk/reward
        - Moderate drawdown tolerance
        - Limited leverage (up to 1.5x)
        - No shorting by default
        - Growth with risk management
        """
        return RiskProfile(
            name="Moderate",
            profile_type=ProfileType.MODERATE,
            description="Balanced risk/reward profile for steady growth",
            max_position_size=0.10,  # 10% max position
            min_position_size=0.02,  # 2% min position
            max_portfolio_risk=0.02,  # 2% risk per trade
            max_daily_loss=0.05,  # 5% max daily loss
            max_drawdown=0.15,  # 15% max drawdown
            default_stop_loss=0.02,  # 2% stop loss
            default_profit_target=0.06,  # 6% target (3:1 ratio)
            max_leverage=1.5,  # Up to 1.5x leverage
            max_total_exposure=1.0,  # 100% total exposure
            max_single_exposure=0.20,  # 20% per symbol
            max_concurrent_positions=5,
            max_positions_per_symbol=1,
            allow_shorting=False,
            allow_options=False,
            allow_futures=False
        )
    
    @staticmethod
    def aggressive() -> RiskProfile:
        """
        Aggressive risk profile
        
        Characteristics:
        - Large position sizes (20% max)
        - Higher risk tolerance
        - Higher drawdown tolerance
        - Moderate leverage (up to 2x)
        - Shorting allowed
        - Growth maximization
        """
        return RiskProfile(
            name="Aggressive",
            profile_type=ProfileType.AGGRESSIVE,
            description="High-risk profile focused on maximizing growth",
            max_position_size=0.20,  # 20% max position
            min_position_size=0.05,  # 5% min position
            max_portfolio_risk=0.03,  # 3% risk per trade
            max_daily_loss=0.10,  # 10% max daily loss
            max_drawdown=0.25,  # 25% max drawdown
            default_stop_loss=0.03,  # 3% stop loss
            default_profit_target=0.09,  # 9% target (3:1 ratio)
            max_leverage=2.0,  # Up to 2x leverage
            max_total_exposure=1.5,  # 150% total exposure
            max_single_exposure=0.30,  # 30% per symbol
            max_concurrent_positions=8,
            max_positions_per_symbol=2,
            allow_shorting=True,
            allow_options=False,
            allow_futures=False
        )
    
    @staticmethod
    def get_all_profiles() -> Dict[str, RiskProfile]:
        """Get dictionary of all pre-defined profiles"""
        return {
            'conservative': ProfileLibrary.conservative(),
            'moderate': ProfileLibrary.moderate(),
            'aggressive': ProfileLibrary.aggressive()
        }
    
    @staticmethod
    def get_profile(name: str) -> Optional[RiskProfile]:
        """
        Get profile by name
        
        Args:
            name: Profile name (case-insensitive)
            
        Returns:
            RiskProfile if found, None otherwise
        """
        profiles = ProfileLibrary.get_all_profiles()
        return profiles.get(name.lower())


class ProfileManager:
    """
    Manages risk profiles for backtesting
    
    Responsibilities:
    - Store and retrieve profiles
    - Validate profiles
    - Apply profiles to strategies
    - Compare profiles
    """
    
    def __init__(self):
        """Initialize profile manager with default profiles"""
        self.profiles: Dict[str, RiskProfile] = ProfileLibrary.get_all_profiles()
    
    def add_profile(self, profile: RiskProfile, overwrite: bool = False) -> bool:
        """
        Add a custom profile
        
        Args:
            profile: RiskProfile to add
            overwrite: Allow overwriting existing profile
            
        Returns:
            True if added successfully, False otherwise
        """
        # Validate profile
        errors = profile.validate()
        if errors:
            print(f"Profile validation failed:")
            for error in errors:
                print(f"  - {error}")
            return False
        
        # Check if exists
        key = profile.name.lower()
        if key in self.profiles and not overwrite:
            print(f"Profile '{profile.name}' already exists. Use overwrite=True to replace.")
            return False
        
        # Add profile
        self.profiles[key] = profile
        return True
    
    def get_profile(self, name: str) -> Optional[RiskProfile]:
        """
        Get profile by name
        
        Args:
            name: Profile name (case-insensitive)
            
        Returns:
            RiskProfile if found, None otherwise
        """
        return self.profiles.get(name.lower())
    
    def remove_profile(self, name: str) -> bool:
        """
        Remove a profile
        
        Args:
            name: Profile name to remove
            
        Returns:
            True if removed, False if not found
        """
        key = name.lower()
        if key in self.profiles:
            del self.profiles[key]
            return True
        return False
    
    def list_profiles(self) -> List[str]:
        """Get list of all profile names"""
        return list(self.profiles.keys())
    
    def compare_profiles(self, profile1_name: str, profile2_name: str) -> Dict[str, Any]:
        """
        Compare two profiles
        
        Args:
            profile1_name: First profile name
            profile2_name: Second profile name
            
        Returns:
            Dictionary with comparison results
        """
        p1 = self.get_profile(profile1_name)
        p2 = self.get_profile(profile2_name)
        
        if not p1 or not p2:
            return {'error': 'One or both profiles not found'}
        
        comparison = {
            'profile1': p1.name,
            'profile2': p2.name,
            'differences': {}
        }
        
        # Compare key parameters
        params_to_compare = [
            'max_position_size', 'max_portfolio_risk', 'max_daily_loss',
            'max_drawdown', 'default_stop_loss', 'default_profit_target',
            'max_leverage', 'max_total_exposure', 'max_concurrent_positions',
            'allow_shorting'
        ]
        
        for param in params_to_compare:
            val1 = getattr(p1, param)
            val2 = getattr(p2, param)
            if val1 != val2:
                comparison['differences'][param] = {
                    p1.name: val1,
                    p2.name: val2
                }
        
        return comparison
    
    def create_custom_profile(
        self,
        name: str,
        base_profile: str = "moderate",
        **overrides
    ) -> Optional[RiskProfile]:
        """
        Create a custom profile based on an existing one
        
        Args:
            name: Name for the new profile
            base_profile: Base profile to start from
            **overrides: Parameters to override
            
        Returns:
            New RiskProfile if successful, None otherwise
        """
        base = self.get_profile(base_profile)
        if not base:
            print(f"Base profile '{base_profile}' not found")
            return None
        
        # Copy base profile
        new_profile = base.copy()
        new_profile.name = name
        new_profile.profile_type = ProfileType.CUSTOM
        new_profile.description = f"Custom profile based on {base_profile}"
        
        # Apply overrides
        for key, value in overrides.items():
            if hasattr(new_profile, key):
                setattr(new_profile, key, value)
            else:
                print(f"Warning: Unknown parameter '{key}' ignored")
        
        # Validate
        errors = new_profile.validate()
        if errors:
            print(f"Custom profile validation failed:")
            for error in errors:
                print(f"  - {error}")
            return None
        
        return new_profile
