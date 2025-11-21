"""
Position sizing algorithms for optimal capital allocation.

Provides multiple position sizing strategies:
- Fixed Percent: Simple percentage-based sizing
- Kelly Criterion: Optimal growth-based sizing
- Risk Parity: Equal risk contribution across positions

Week 3 Day 2 Implementation.
"""

import logging
from abc import ABC, abstractmethod
from typing import Dict, Optional, List
from dataclasses import dataclass
import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class PositionSizeResult:
    """Result of position size calculation."""
    shares: int
    position_value: float
    position_pct: float
    rationale: str
    risk_amount: Optional[float] = None
    kelly_fraction: Optional[float] = None


class PositionSizer(ABC):
    """
    Abstract base class for position sizing strategies.
    
    All position sizers must implement the calculate() method
    to determine optimal position size.
    """
    
    @abstractmethod
    def calculate(
        self,
        symbol: str,
        price: float,
        equity: float,
        **kwargs
    ) -> PositionSizeResult:
        """
        Calculate position size for a trade.
        
        Args:
            symbol: Trading symbol
            price: Entry price
            equity: Current account equity
            **kwargs: Strategy-specific parameters
            
        Returns:
            PositionSizeResult with calculated size and metadata
        """
        pass
    
    def _validate_inputs(
        self,
        price: float,
        equity: float
    ) -> bool:
        """Validate common inputs."""
        if price <= 0:
            logger.error(f"Invalid price: {price}")
            return False
        if equity <= 0:
            logger.error(f"Invalid equity: {equity}")
            return False
        return True


class FixedPercentSizer(PositionSizer):
    """
    Fixed percentage position sizing.
    
    Simple and conservative approach - allocates a fixed percentage
    of equity to each position.
    
    Example:
        >>> sizer = FixedPercentSizer(position_pct=0.10)
        >>> result = sizer.calculate("AAPL", 150.0, 100000)
        >>> print(f"Shares: {result.shares}, Value: ${result.position_value:,.2f}")
    """
    
    def __init__(
        self,
        position_pct: float = 0.10,  # 10% default
        max_position_pct: float = 0.25,  # 25% max
        min_shares: int = 1
    ):
        """
        Initialize fixed percent sizer.
        
        Args:
            position_pct: Target position size as % of equity
            max_position_pct: Maximum allowed position size
            min_shares: Minimum shares to trade (0 = allow fractional)
        """
        self.position_pct = position_pct
        self.max_position_pct = max_position_pct
        self.min_shares = min_shares
        
        logger.info(f"FixedPercentSizer initialized: {position_pct:.1%} per position")
    
    def calculate(
        self,
        symbol: str,
        price: float,
        equity: float,
        position_pct: Optional[float] = None
    ) -> PositionSizeResult:
        """
        Calculate position size as fixed percentage of equity.
        
        Args:
            symbol: Trading symbol
            price: Entry price
            equity: Current equity
            position_pct: Override default position percent
            
        Returns:
            PositionSizeResult
        """
        if not self._validate_inputs(price, equity):
            return PositionSizeResult(0, 0.0, 0.0, "Invalid inputs")
        
        # Use provided or default percentage
        pct = position_pct if position_pct is not None else self.position_pct
        pct = min(pct, self.max_position_pct)  # Cap at max
        
        # Calculate shares
        position_value = equity * pct
        shares = int(position_value / price)
        
        # Enforce minimum
        if shares < self.min_shares:
            shares = 0
        
        # Actual values
        actual_value = shares * price
        actual_pct = actual_value / equity if equity > 0 else 0.0
        
        rationale = f"Fixed {pct:.1%} of equity"
        
        return PositionSizeResult(
            shares=shares,
            position_value=actual_value,
            position_pct=actual_pct,
            rationale=rationale
        )


class KellySizer(PositionSizer):
    """
    Kelly Criterion position sizing for optimal growth.
    
    Calculates optimal position size based on win rate and win/loss ratio.
    Uses fractional Kelly (half-Kelly default) for safety.
    
    Formula: f* = (p * b - q) / b
    Where:
        f* = Kelly fraction
        p = win probability
        q = loss probability (1 - p)
        b = win/loss ratio (avg_win / avg_loss)
    
    Example:
        >>> sizer = KellySizer(kelly_fraction=0.5)  # Half-Kelly
        >>> result = sizer.calculate(
        ...     "AAPL", 150.0, 100000,
        ...     win_rate=0.60, avg_win=0.03, avg_loss=0.02
        ... )
    """
    
    def __init__(
        self,
        kelly_fraction: float = 0.5,  # Half-Kelly for safety
        max_position_pct: float = 0.25,  # 25% max regardless of Kelly
        min_kelly: float = 0.01,  # Minimum 1% Kelly
        min_shares: int = 1
    ):
        """
        Initialize Kelly Criterion sizer.
        
        Args:
            kelly_fraction: Fraction of Kelly to use (0.5 = half-Kelly)
            max_position_pct: Maximum position size regardless of Kelly
            min_kelly: Minimum Kelly fraction to use
            min_shares: Minimum shares to trade
        """
        self.kelly_fraction = kelly_fraction
        self.max_position_pct = max_position_pct
        self.min_kelly = min_kelly
        self.min_shares = min_shares
        
        logger.info(f"KellySizer initialized: {kelly_fraction:.1%} Kelly fraction")
    
    def calculate(
        self,
        symbol: str,
        price: float,
        equity: float,
        win_rate: float,
        avg_win: float,
        avg_loss: float,
        **kwargs
    ) -> PositionSizeResult:
        """
        Calculate position size using Kelly Criterion.
        
        Args:
            symbol: Trading symbol
            price: Entry price
            equity: Current equity
            win_rate: Historical win rate (0-1)
            avg_win: Average winning trade return (as decimal)
            avg_loss: Average losing trade return (as decimal, positive)
            
        Returns:
            PositionSizeResult with Kelly fraction included
        """
        if not self._validate_inputs(price, equity):
            return PositionSizeResult(0, 0.0, 0.0, "Invalid inputs")
        
        # Validate Kelly inputs
        if not (0 < win_rate < 1):
            logger.warning(f"Invalid win_rate {win_rate}, using 0.5")
            win_rate = 0.5
        
        if avg_win <= 0 or avg_loss <= 0:
            logger.error(f"Invalid avg_win ({avg_win}) or avg_loss ({avg_loss})")
            return PositionSizeResult(0, 0.0, 0.0, "Invalid Kelly parameters")
        
        # Calculate Kelly fraction
        loss_rate = 1 - win_rate
        win_loss_ratio = avg_win / avg_loss
        
        # Kelly formula: f* = (p * b - q) / b
        kelly_raw = (win_rate * win_loss_ratio - loss_rate) / win_loss_ratio
        
        # Apply safety constraints
        kelly_raw = max(kelly_raw, 0)  # No negative Kelly
        kelly_raw = max(kelly_raw, self.min_kelly)  # Minimum threshold
        
        # Apply fractional Kelly (half-Kelly, quarter-Kelly, etc.)
        kelly_adjusted = kelly_raw * self.kelly_fraction
        
        # Cap at maximum position size
        final_pct = min(kelly_adjusted, self.max_position_pct)
        
        # Calculate shares
        position_value = equity * final_pct
        shares = int(position_value / price)
        
        # Enforce minimum
        if shares < self.min_shares:
            shares = 0
        
        # Actual values
        actual_value = shares * price
        actual_pct = actual_value / equity if equity > 0 else 0.0
        
        rationale = (
            f"Kelly: {kelly_raw:.2%} raw, {kelly_adjusted:.2%} adjusted "
            f"(WR:{win_rate:.1%}, W/L:{win_loss_ratio:.2f})"
        )
        
        return PositionSizeResult(
            shares=shares,
            position_value=actual_value,
            position_pct=actual_pct,
            rationale=rationale,
            kelly_fraction=kelly_adjusted
        )


class RiskBasedSizer(PositionSizer):
    """
    Risk-based position sizing.
    
    Sizes position based on how much capital to risk per trade
    and the distance to stop loss.
    
    Formula: shares = (equity * risk_pct) / (price * stop_loss_pct)
    
    Example:
        >>> sizer = RiskBasedSizer(risk_pct=0.02)  # Risk 2% per trade
        >>> result = sizer.calculate(
        ...     "AAPL", 150.0, 100000,
        ...     stop_loss_pct=0.05  # 5% stop loss
        ... )
    """
    
    def __init__(
        self,
        risk_pct: float = 0.02,  # Risk 2% per trade
        max_position_pct: float = 0.25,
        min_stop_loss_pct: float = 0.01,  # 1% minimum stop
        min_shares: int = 1
    ):
        """
        Initialize risk-based sizer.
        
        Args:
            risk_pct: Percentage of equity to risk per trade
            max_position_pct: Maximum position size
            min_stop_loss_pct: Minimum stop loss distance
            min_shares: Minimum shares to trade
        """
        self.risk_pct = risk_pct
        self.max_position_pct = max_position_pct
        self.min_stop_loss_pct = min_stop_loss_pct
        self.min_shares = min_shares
        
        logger.info(f"RiskBasedSizer initialized: {risk_pct:.1%} risk per trade")
    
    def calculate(
        self,
        symbol: str,
        price: float,
        equity: float,
        stop_loss_pct: float,
        risk_pct: Optional[float] = None
    ) -> PositionSizeResult:
        """
        Calculate position size based on risk and stop loss.
        
        Args:
            symbol: Trading symbol
            price: Entry price
            equity: Current equity
            stop_loss_pct: Stop loss distance as % of price
            risk_pct: Override default risk percentage
            
        Returns:
            PositionSizeResult with risk amount included
        """
        if not self._validate_inputs(price, equity):
            return PositionSizeResult(0, 0.0, 0.0, "Invalid inputs")
        
        # Validate stop loss
        if stop_loss_pct < self.min_stop_loss_pct:
            logger.warning(f"Stop loss {stop_loss_pct:.2%} too small, using {self.min_stop_loss_pct:.2%}")
            stop_loss_pct = self.min_stop_loss_pct
        
        # Use provided or default risk
        risk = risk_pct if risk_pct is not None else self.risk_pct
        
        # Calculate risk amount and shares
        risk_amount = equity * risk
        risk_per_share = price * stop_loss_pct
        shares = int(risk_amount / risk_per_share) if risk_per_share > 0 else 0
        
        # Check against max position size
        max_value = equity * self.max_position_pct
        max_shares = int(max_value / price)
        
        if shares > max_shares:
            shares = max_shares
            capped = True
        else:
            capped = False
        
        # Enforce minimum
        if shares < self.min_shares:
            shares = 0
        
        # Actual values
        actual_value = shares * price
        actual_pct = actual_value / equity if equity > 0 else 0.0
        actual_risk = shares * risk_per_share
        
        rationale = (
            f"Risk {risk:.1%} with {stop_loss_pct:.1%} stop"
            f"{' (capped at max)' if capped else ''}"
        )
        
        return PositionSizeResult(
            shares=shares,
            position_value=actual_value,
            position_pct=actual_pct,
            rationale=rationale,
            risk_amount=actual_risk
        )


class RiskParitySizer(PositionSizer):
    """
    Risk parity position sizing.
    
    Allocates capital so each position contributes equal risk to portfolio.
    Uses volatility-adjusted position sizes.
    
    Formula: position_i = target_risk / (price * volatility_i * num_positions)
    
    Example:
        >>> sizer = RiskParitySizer(target_risk_pct=0.10)
        >>> result = sizer.calculate(
        ...     "AAPL", 150.0, 100000,
        ...     volatility=0.25,  # 25% annual volatility
        ...     num_positions=5
        ... )
    """
    
    def __init__(
        self,
        target_risk_pct: float = 0.10,  # 10% target portfolio risk
        max_position_pct: float = 0.25,
        default_volatility: float = 0.20,  # 20% default volatility
        min_shares: int = 1
    ):
        """
        Initialize risk parity sizer.
        
        Args:
            target_risk_pct: Target portfolio risk percentage
            max_position_pct: Maximum position size
            default_volatility: Default volatility if not provided
            min_shares: Minimum shares to trade
        """
        self.target_risk_pct = target_risk_pct
        self.max_position_pct = max_position_pct
        self.default_volatility = default_volatility
        self.min_shares = min_shares
        
        logger.info(f"RiskParitySizer initialized: {target_risk_pct:.1%} target risk")
    
    def calculate(
        self,
        symbol: str,
        price: float,
        equity: float,
        volatility: Optional[float] = None,
        num_positions: int = 1,
        **kwargs
    ) -> PositionSizeResult:
        """
        Calculate position size for equal risk contribution.
        
        Args:
            symbol: Trading symbol
            price: Entry price
            equity: Current equity
            volatility: Asset volatility (annualized)
            num_positions: Total number of positions in portfolio
            
        Returns:
            PositionSizeResult
        """
        if not self._validate_inputs(price, equity):
            return PositionSizeResult(0, 0.0, 0.0, "Invalid inputs")
        
        # Use provided or default volatility
        vol = volatility if volatility is not None else self.default_volatility
        
        if vol <= 0:
            logger.warning(f"Invalid volatility {vol}, using default {self.default_volatility}")
            vol = self.default_volatility
        
        if num_positions < 1:
            num_positions = 1
        
        # Calculate equal risk contribution
        # Each position should contribute (target_risk / num_positions) to portfolio risk
        risk_per_position = self.target_risk_pct / num_positions
        
        # Position size = (risk_per_position * equity) / (price * volatility)
        position_value = (risk_per_position * equity) / vol
        
        # Cap at maximum
        max_value = equity * self.max_position_pct
        position_value = min(position_value, max_value)
        
        shares = int(position_value / price)
        
        # Enforce minimum
        if shares < self.min_shares:
            shares = 0
        
        # Actual values
        actual_value = shares * price
        actual_pct = actual_value / equity if equity > 0 else 0.0
        
        # Estimated risk contribution
        risk_contribution = actual_value * vol / equity if equity > 0 else 0.0
        
        rationale = (
            f"Risk parity: {risk_per_position:.1%} target "
            f"(vol:{vol:.1%}, {num_positions} positions)"
        )
        
        return PositionSizeResult(
            shares=shares,
            position_value=actual_value,
            position_pct=actual_pct,
            rationale=rationale,
            risk_amount=risk_contribution * equity
        )


class PositionSizerFactory:
    """
    Factory for creating position sizers.
    
    Provides easy access to different sizing strategies.
    
    Example:
        >>> sizer = PositionSizerFactory.create("kelly", kelly_fraction=0.5)
        >>> result = sizer.calculate("AAPL", 150.0, 100000, 0.60, 0.03, 0.02)
    """
    
    @staticmethod
    def create(strategy: str, **kwargs) -> PositionSizer:
        """
        Create position sizer by strategy name.
        
        Args:
            strategy: Strategy name ('fixed', 'kelly', 'risk_based', 'risk_parity')
            **kwargs: Strategy-specific parameters
            
        Returns:
            PositionSizer instance
            
        Raises:
            ValueError: If strategy name is unknown
        """
        strategy = strategy.lower().replace('_', '').replace('-', '')
        
        if strategy in ('fixed', 'fixedpercent'):
            return FixedPercentSizer(**kwargs)
        elif strategy == 'kelly':
            return KellySizer(**kwargs)
        elif strategy in ('riskbased', 'risk'):
            return RiskBasedSizer(**kwargs)
        elif strategy in ('riskparity', 'parity'):
            return RiskParitySizer(**kwargs)
        else:
            raise ValueError(
                f"Unknown strategy: {strategy}. "
                f"Valid options: fixed, kelly, risk_based, risk_parity"
            )
    
    @staticmethod
    def list_strategies() -> List[str]:
        """Get list of available strategies."""
        return ['fixed_percent', 'kelly', 'risk_based', 'risk_parity']
