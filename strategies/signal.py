"""
Trading signal data structures.

Standardized signal format for communication between strategies
and execution systems.
"""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Optional, Dict, Any


class SignalType(Enum):
    """Types of trading signals"""
    BUY = "BUY"
    SELL = "SELL"
    CLOSE = "CLOSE"  # Close existing position
    HOLD = "HOLD"    # No action


class SignalStrength(Enum):
    """Signal confidence levels"""
    WEAK = 1
    MODERATE = 2
    STRONG = 3
    VERY_STRONG = 4


@dataclass
class Signal:
    """
    Trading signal from strategy to execution system.
    
    Contains all information needed to execute a trade.
    
    Attributes:
        symbol: Trading symbol (e.g., "AAPL")
        signal_type: Type of signal (BUY, SELL, CLOSE, HOLD)
        strength: Signal confidence level
        timestamp: When signal was generated
        target_price: Desired execution price (None for market orders)
        stop_loss: Stop loss price level
        take_profit: Take profit price level
        quantity: Number of shares/contracts (None = auto-calculate)
        reason: Human-readable explanation of signal
        indicators: Dict of indicator values that triggered signal
        strategy_name: Name of strategy that generated signal
        confidence: Numeric confidence score (0.0 to 1.0)
    
    Example:
        >>> signal = Signal(
        ...     symbol="AAPL",
        ...     signal_type=SignalType.BUY,
        ...     strength=SignalStrength.STRONG,
        ...     timestamp=datetime.now(),
        ...     target_price=150.0,
        ...     stop_loss=145.0,
        ...     take_profit=160.0,
        ...     reason="Bollinger Band lower band touch",
        ...     confidence=0.85
        ... )
    """
    symbol: str
    signal_type: SignalType
    strength: SignalStrength
    timestamp: datetime
    
    # Price and sizing
    target_price: Optional[float] = None
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    quantity: Optional[int] = None
    
    # Context and metadata
    reason: Optional[str] = None
    indicators: Optional[Dict[str, float]] = None
    strategy_name: Optional[str] = None
    confidence: float = 0.0  # 0.0 to 1.0
    
    def to_dict(self) -> Dict[str, Any]:
        """
        Convert signal to dictionary for serialization.
        
        Returns:
            Dictionary representation suitable for JSON serialization
        """
        return {
            'symbol': self.symbol,
            'signal_type': self.signal_type.value,
            'strength': self.strength.value,
            'timestamp': self.timestamp.isoformat(),
            'target_price': self.target_price,
            'stop_loss': self.stop_loss,
            'take_profit': self.take_profit,
            'quantity': self.quantity,
            'reason': self.reason,
            'indicators': self.indicators,
            'strategy_name': self.strategy_name,
            'confidence': self.confidence
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Signal':
        """
        Create signal from dictionary.
        
        Args:
            data: Dictionary containing signal data
            
        Returns:
            Signal instance
        """
        return cls(
            symbol=data['symbol'],
            signal_type=SignalType(data['signal_type']),
            strength=SignalStrength(data['strength']),
            timestamp=datetime.fromisoformat(data['timestamp']),
            target_price=data.get('target_price'),
            stop_loss=data.get('stop_loss'),
            take_profit=data.get('take_profit'),
            quantity=data.get('quantity'),
            reason=data.get('reason'),
            indicators=data.get('indicators'),
            strategy_name=data.get('strategy_name'),
            confidence=data.get('confidence', 0.0)
        )
    
    def is_entry_signal(self) -> bool:
        """
        Check if this is an entry signal (BUY or SELL).
        
        Returns:
            True if signal is BUY or SELL
        """
        return self.signal_type in [SignalType.BUY, SignalType.SELL]
    
    def is_exit_signal(self) -> bool:
        """
        Check if this is an exit signal (CLOSE).
        
        Returns:
            True if signal is CLOSE
        """
        return self.signal_type == SignalType.CLOSE
    
    def validate(self) -> bool:
        """
        Validate signal data integrity.
        
        Returns:
            True if signal is valid, False otherwise
        """
        # Check required fields
        if not self.symbol:
            return False
        
        if self.confidence < 0.0 or self.confidence > 1.0:
            return False
        
        # Validate price logic
        if self.target_price is not None:
            if self.target_price <= 0:
                return False
            
            # For BUY signals, stop loss should be below target
            if self.signal_type == SignalType.BUY:
                if self.stop_loss is not None and self.stop_loss >= self.target_price:
                    return False
                if self.take_profit is not None and self.take_profit <= self.target_price:
                    return False
            
            # For SELL signals, stop loss should be above target
            elif self.signal_type == SignalType.SELL:
                if self.stop_loss is not None and self.stop_loss <= self.target_price:
                    return False
                if self.take_profit is not None and self.take_profit >= self.target_price:
                    return False
        
        return True
    
    def __str__(self) -> str:
        """String representation of signal"""
        price_str = f"@ ${self.target_price:.2f}" if self.target_price else "@ MARKET"
        return (f"Signal({self.signal_type.value} {self.symbol} "
                f"{price_str} - {self.reason or 'No reason'})")
    
    def __repr__(self) -> str:
        """Detailed representation of signal"""
        return (f"Signal(symbol='{self.symbol}', "
                f"type={self.signal_type.value}, "
                f"strength={self.strength.name}, "
                f"confidence={self.confidence:.2f})")
