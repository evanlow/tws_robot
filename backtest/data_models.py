"""
Data Models for Backtesting

Defines core data structures used throughout the backtesting system.

Author: TWS Robot Development Team
Date: November 2025
Week 4 Day 1
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional
from enum import Enum


class TimeFrame(Enum):
    """Supported timeframes for historical data"""
    TICK = "tick"
    SECOND_1 = "1s"
    SECOND_5 = "5s"
    SECOND_15 = "15s"
    SECOND_30 = "30s"
    MINUTE_1 = "1min"
    MINUTE_5 = "5min"
    MINUTE_15 = "15min"
    MINUTE_30 = "30min"
    HOUR_1 = "1h"
    HOUR_4 = "4h"
    DAY_1 = "1d"
    WEEK_1 = "1w"
    MONTH_1 = "1mo"


@dataclass
class Bar:
    """
    Represents a single OHLCV bar (candlestick) of market data
    
    Attributes:
        timestamp: Bar timestamp (open time)
        open: Opening price
        high: Highest price
        low: Lowest price
        close: Closing price
        volume: Trading volume
        symbol: Symbol/ticker
        timeframe: Bar timeframe
        typical_price: (high + low + close) / 3
        vwap: Volume-weighted average price (if available)
    """
    timestamp: datetime
    symbol: str
    open: float
    high: float
    low: float
    close: float
    volume: int
    timeframe: TimeFrame = TimeFrame.MINUTE_1
    vwap: Optional[float] = None
    
    def __post_init__(self):
        """Validate bar data"""
        if self.high < self.low:
            raise ValueError(f"High ({self.high}) cannot be less than low ({self.low})")
        if self.high < self.close or self.high < self.open:
            raise ValueError(f"High ({self.high}) must be >= open and close")
        if self.low > self.close or self.low > self.open:
            raise ValueError(f"Low ({self.low}) must be <= open and close")
        if self.volume < 0:
            raise ValueError(f"Volume cannot be negative: {self.volume}")
    
    @property
    def typical_price(self) -> float:
        """Calculate typical price: (high + low + close) / 3"""
        return (self.high + self.low + self.close) / 3.0
    
    @property
    def range(self) -> float:
        """Calculate bar range (high - low)"""
        return self.high - self.low
    
    @property
    def body(self) -> float:
        """Calculate bar body (abs(close - open))"""
        return abs(self.close - self.open)
    
    @property
    def is_bullish(self) -> bool:
        """Check if bar is bullish (close > open)"""
        return self.close > self.open
    
    @property
    def is_bearish(self) -> bool:
        """Check if bar is bearish (close < open)"""
        return self.close < self.open
    
    def __str__(self) -> str:
        return (f"Bar({self.symbol} {self.timestamp.strftime('%Y-%m-%d %H:%M:%S')} "
                f"O:{self.open:.2f} H:{self.high:.2f} L:{self.low:.2f} "
                f"C:{self.close:.2f} V:{self.volume})")


@dataclass
class MarketData:
    """
    Container for market data across multiple symbols
    
    Attributes:
        timestamp: Current timestamp in the replay
        bars: Dictionary of symbol -> Bar
        symbols: List of all symbols in the data
    """
    timestamp: datetime
    bars: Dict[str, Bar] = field(default_factory=dict)
    
    @property
    def symbols(self) -> List[str]:
        """Get list of all symbols with data"""
        return list(self.bars.keys())
    
    def get_bar(self, symbol: str) -> Optional[Bar]:
        """Get bar for a specific symbol"""
        return self.bars.get(symbol)
    
    def add_bar(self, symbol: str, bar: Bar) -> None:
        """Add or update bar for a symbol"""
        self.bars[symbol] = bar
    
    def has_symbol(self, symbol: str) -> bool:
        """Check if symbol has data"""
        return symbol in self.bars
    
    def get_close(self, symbol: str) -> Optional[float]:
        """Get closing price for a symbol"""
        bar = self.get_bar(symbol)
        return bar.close if bar else None
    
    def get_volume(self, symbol: str) -> Optional[int]:
        """Get volume for a symbol"""
        bar = self.get_bar(symbol)
        return bar.volume if bar else None
    
    def __str__(self) -> str:
        return (f"MarketData({self.timestamp.strftime('%Y-%m-%d %H:%M:%S')}, "
                f"{len(self.bars)} symbols)")


@dataclass
class BarSeries:
    """
    Time series of bars for a single symbol
    
    Useful for calculating indicators and looking back in history
    
    Attributes:
        symbol: Symbol/ticker
        bars: List of bars in chronological order
        timeframe: Timeframe of the bars
    """
    symbol: str
    bars: List[Bar] = field(default_factory=list)
    timeframe: TimeFrame = TimeFrame.MINUTE_1
    
    def add_bar(self, bar: Bar) -> None:
        """Add a bar to the series (must be chronological)"""
        if self.bars and bar.timestamp <= self.bars[-1].timestamp:
            raise ValueError(
                f"Bar timestamp {bar.timestamp} is not after last bar "
                f"{self.bars[-1].timestamp}"
            )
        self.bars.append(bar)
    
    def get_bars(self, lookback: int = None) -> List[Bar]:
        """
        Get bars with optional lookback
        
        Args:
            lookback: Number of most recent bars to return (None = all)
            
        Returns:
            List of bars (most recent last)
        """
        if lookback is None:
            return self.bars
        return self.bars[-lookback:] if lookback > 0 else []
    
    def get_closes(self, lookback: int = None) -> List[float]:
        """Get closing prices"""
        bars = self.get_bars(lookback)
        return [bar.close for bar in bars]
    
    def get_highs(self, lookback: int = None) -> List[float]:
        """Get high prices"""
        bars = self.get_bars(lookback)
        return [bar.high for bar in bars]
    
    def get_lows(self, lookback: int = None) -> List[float]:
        """Get low prices"""
        bars = self.get_bars(lookback)
        return [bar.low for bar in bars]
    
    def get_volumes(self, lookback: int = None) -> List[int]:
        """Get volumes"""
        bars = self.get_bars(lookback)
        return [bar.volume for bar in bars]
    
    @property
    def latest(self) -> Optional[Bar]:
        """Get the most recent bar"""
        return self.bars[-1] if self.bars else None
    
    @property
    def count(self) -> int:
        """Get number of bars in series"""
        return len(self.bars)
    
    def __len__(self) -> int:
        return len(self.bars)
    
    def __getitem__(self, index: int) -> Bar:
        return self.bars[index]
    
    def __str__(self) -> str:
        return f"BarSeries({self.symbol}, {len(self.bars)} bars, {self.timeframe.value})"


@dataclass
class Trade:
    """
    Represents a completed trade (filled order)
    
    Attributes:
        timestamp: Execution timestamp
        symbol: Symbol traded
        action: 'BUY' or 'SELL'
        quantity: Number of shares
        price: Execution price
        commission: Commission paid
        slippage: Slippage incurred
        order_id: Order identifier
        strategy_name: Name of strategy that generated the trade
        pnl: Profit/loss (for closing trades)
    """
    timestamp: datetime
    symbol: str
    action: str  # 'BUY' or 'SELL'
    quantity: int
    price: float
    commission: float = 0.0
    slippage: float = 0.0
    order_id: str = ""
    strategy_name: str = ""
    pnl: float = 0.0
    
    @property
    def value(self) -> float:
        """Calculate trade value (quantity * price)"""
        return self.quantity * self.price
    
    @property
    def total_cost(self) -> float:
        """Calculate total cost including commission and slippage"""
        return self.value + self.commission + abs(self.slippage * self.quantity)
    
    def __str__(self) -> str:
        return (f"Trade({self.action} {self.quantity} {self.symbol} @ ${self.price:.2f} "
                f"[{self.timestamp.strftime('%Y-%m-%d %H:%M:%S')}])")


@dataclass
class Position:
    """
    Represents an open position
    
    Attributes:
        symbol: Symbol held
        quantity: Number of shares (positive for long, negative for short)
        average_cost: Average cost basis
        current_price: Current market price
        market_value: Current market value
        unrealized_pnl: Unrealized P&L
        realized_pnl: Realized P&L from closed portion
    """
    symbol: str
    quantity: int
    average_cost: float
    current_price: float = 0.0
    realized_pnl: float = 0.0
    
    @property
    def market_value(self) -> float:
        """Calculate current market value"""
        return self.quantity * self.current_price
    
    @property
    def cost_basis(self) -> float:
        """Calculate total cost basis"""
        return self.quantity * self.average_cost
    
    @property
    def unrealized_pnl(self) -> float:
        """Calculate unrealized P&L"""
        return self.market_value - self.cost_basis
    
    @property
    def total_pnl(self) -> float:
        """Calculate total P&L (realized + unrealized)"""
        return self.realized_pnl + self.unrealized_pnl
    
    @property
    def is_long(self) -> bool:
        """Check if position is long"""
        return self.quantity > 0
    
    @property
    def is_short(self) -> bool:
        """Check if position is short"""
        return self.quantity < 0
    
    def update_price(self, price: float) -> None:
        """Update current price"""
        self.current_price = price
    
    def __str__(self) -> str:
        return (f"Position({self.symbol}: {self.quantity} @ ${self.average_cost:.2f}, "
                f"Current: ${self.current_price:.2f}, P&L: ${self.unrealized_pnl:.2f})")
