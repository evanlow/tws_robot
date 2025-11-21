"""
Strategy Base Class

Abstract base class for trading strategies in backtesting.

Provides consistent interface for strategy implementation with:
- Bar data callbacks
- Order management
- Position tracking
- Risk management integration
- Performance metrics

Author: TWS Robot Development Team
Date: November 2025
Week 4 Day 2
"""

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field

from .data_models import Bar, MarketData, Position, Trade


@dataclass
class StrategyConfig:
    """Configuration for a strategy"""
    name: str
    symbols: List[str]
    initial_capital: float = 100000.0
    
    # Risk parameters
    max_position_size: float = 0.1  # 10% of capital per position
    max_total_exposure: float = 1.0  # 100% total exposure
    use_risk_management: bool = True
    
    # Strategy-specific parameters
    parameters: Dict[str, Any] = field(default_factory=dict)
    
    def __post_init__(self):
        """Validate configuration"""
        if self.initial_capital <= 0:
            raise ValueError("Initial capital must be positive")
        if self.max_position_size <= 0 or self.max_position_size > 1.0:
            raise ValueError("Max position size must be between 0 and 1")
        if self.max_total_exposure <= 0:
            raise ValueError("Max total exposure must be positive")


@dataclass
class StrategyState:
    """Current state of a strategy"""
    equity: float
    cash: float
    positions: Dict[str, Position] = field(default_factory=dict)
    pending_orders: List[Any] = field(default_factory=list)
    
    # Performance tracking
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    total_pnl: float = 0.0
    
    # Exposure tracking
    long_exposure: float = 0.0
    short_exposure: float = 0.0
    total_exposure: float = 0.0
    
    # Peak tracking for drawdown
    peak_equity: float = 0.0
    max_drawdown: float = 0.0
    
    def __post_init__(self):
        """Initialize state"""
        if self.peak_equity == 0.0:
            self.peak_equity = self.equity
    
    def update_equity(self, new_equity: float):
        """Update equity and track drawdown"""
        self.equity = new_equity
        
        # Update peak
        if new_equity > self.peak_equity:
            self.peak_equity = new_equity
        
        # Calculate drawdown
        if self.peak_equity > 0:
            drawdown = (self.peak_equity - new_equity) / self.peak_equity
            if drawdown > self.max_drawdown:
                self.max_drawdown = drawdown


class Strategy(ABC):
    """
    Abstract base class for trading strategies
    
    Subclasses must implement:
    - on_bar(): Process new market data
    - on_start(): Initialize strategy
    - on_stop(): Cleanup
    """
    
    def __init__(self, config: StrategyConfig):
        """
        Initialize strategy
        
        Args:
            config: Strategy configuration
        """
        self.config = config
        self.state = StrategyState(
            equity=config.initial_capital,
            cash=config.initial_capital
        )
        
        # Market data tracking
        self.current_time: Optional[datetime] = None
        self.current_prices: Dict[str, float] = {}
        self.bar_history: Dict[str, List[Bar]] = {symbol: [] for symbol in config.symbols}
        
        # Order tracking
        self._next_order_id = 1
        
        # Callbacks (set by backtest engine)
        self._submit_order_callback = None
        self._cancel_order_callback = None
        self._get_position_callback = None
    
    # ==================== Abstract Methods ====================
    
    @abstractmethod
    def on_bar(self, market_data: MarketData):
        """
        Called for each new bar of market data
        
        Args:
            market_data: Current market data for all symbols
        """
        pass
    
    def on_start(self):
        """Called when backtest starts (before first bar)"""
        pass
    
    def on_stop(self):
        """Called when backtest ends (after last bar)"""
        pass
    
    def on_trade(self, trade: Trade):
        """
        Called when an order is filled
        
        Args:
            trade: Executed trade
        """
        # Update trade statistics
        self.state.total_trades += 1
        
        # Track P&L for completed round trips
        if trade.action == 'SELL':
            position = self.state.positions.get(trade.symbol)
            if position:
                # Calculate realized P&L
                pnl = (trade.price - position.average_cost) * trade.quantity
                self.state.total_pnl += pnl
                
                if pnl > 0:
                    self.state.winning_trades += 1
                else:
                    self.state.losing_trades += 1
    
    # ==================== Order Management ====================
    
    def buy(self, symbol: str, quantity: int, order_type: str = 'MARKET',
            limit_price: Optional[float] = None, stop_price: Optional[float] = None) -> str:
        """
        Submit a buy order
        
        Args:
            symbol: Symbol to buy
            quantity: Number of shares
            order_type: 'MARKET', 'LIMIT', or 'STOP'
            limit_price: Limit price for LIMIT orders
            stop_price: Stop price for STOP orders
        
        Returns:
            Order ID
        """
        return self._create_order(symbol, 'BUY', quantity, order_type, limit_price, stop_price)
    
    def sell(self, symbol: str, quantity: int, order_type: str = 'MARKET',
             limit_price: Optional[float] = None, stop_price: Optional[float] = None) -> str:
        """
        Submit a sell order
        
        Args:
            symbol: Symbol to sell
            quantity: Number of shares
            order_type: 'MARKET', 'LIMIT', or 'STOP'
            limit_price: Limit price for LIMIT orders
            stop_price: Stop price for STOP orders
        
        Returns:
            Order ID
        """
        return self._create_order(symbol, 'SELL', quantity, order_type, limit_price, stop_price)
    
    def close_position(self, symbol: str, order_type: str = 'MARKET') -> Optional[str]:
        """
        Close entire position for a symbol
        
        Args:
            symbol: Symbol to close
            order_type: Order type to use
        
        Returns:
            Order ID or None if no position
        """
        position = self.get_position(symbol)
        if not position or position.quantity == 0:
            return None
        
        if position.quantity > 0:
            return self.sell(symbol, position.quantity, order_type)
        else:
            return self.buy(symbol, abs(position.quantity), order_type)
    
    def cancel_order(self, order_id: str) -> bool:
        """
        Cancel a pending order
        
        Args:
            order_id: ID of order to cancel
        
        Returns:
            True if cancelled, False otherwise
        """
        if self._cancel_order_callback:
            return self._cancel_order_callback(order_id)
        return False
    
    def _create_order(self, symbol: str, action: str, quantity: int,
                     order_type: str, limit_price: Optional[float],
                     stop_price: Optional[float]) -> str:
        """Internal method to create and submit order"""
        from .market_simulator import Order
        
        order_id = f"{self.config.name}_{self._next_order_id}"
        self._next_order_id += 1
        
        order = Order(
            order_id=order_id,
            symbol=symbol,
            action=action,
            quantity=quantity,
            order_type=order_type,
            limit_price=limit_price,
            stop_price=stop_price
        )
        
        if self._submit_order_callback:
            self._submit_order_callback(order)
        
        return order_id
    
    # ==================== Position Queries ====================
    
    def get_position(self, symbol: str) -> Optional[Position]:
        """
        Get current position for a symbol
        
        Args:
            symbol: Symbol to query
        
        Returns:
            Position or None if no position
        """
        if self._get_position_callback:
            return self._get_position_callback(symbol)
        return self.state.positions.get(symbol)
    
    def has_position(self, symbol: str) -> bool:
        """Check if we have a position in symbol"""
        position = self.get_position(symbol)
        return position is not None and position.quantity != 0
    
    def is_long(self, symbol: str) -> bool:
        """Check if we are long the symbol"""
        position = self.get_position(symbol)
        return position is not None and position.quantity > 0
    
    def is_short(self, symbol: str) -> bool:
        """Check if we are short the symbol"""
        position = self.get_position(symbol)
        return position is not None and position.quantity < 0
    
    def is_flat(self, symbol: str) -> bool:
        """Check if we have no position in symbol"""
        return not self.has_position(symbol)
    
    # ==================== Market Data Access ====================
    
    def get_bar_history(self, symbol: str, lookback: Optional[int] = None) -> List[Bar]:
        """
        Get historical bars for a symbol
        
        Args:
            symbol: Symbol to query
            lookback: Number of bars to return (None for all)
        
        Returns:
            List of bars
        """
        bars = self.bar_history.get(symbol, [])
        if lookback is None:
            return bars
        return bars[-lookback:]
    
    def get_price_history(self, symbol: str, lookback: Optional[int] = None) -> List[float]:
        """
        Get historical close prices for a symbol
        
        Args:
            symbol: Symbol to query
            lookback: Number of prices to return (None for all)
        
        Returns:
            List of close prices
        """
        bars = self.get_bar_history(symbol, lookback)
        return [bar.close for bar in bars]
    
    def get_current_price(self, symbol: str) -> Optional[float]:
        """Get current price for a symbol"""
        return self.current_prices.get(symbol)
    
    # ==================== Internal Methods ====================
    
    def _update_bar(self, market_data: MarketData):
        """Internal method to update bar history"""
        self.current_time = market_data.timestamp
        
        # Update prices and history
        for symbol in market_data.symbols:
            bar = market_data.get_bar(symbol)
            if bar:
                self.current_prices[symbol] = bar.close
                
                # Add to history
                if symbol not in self.bar_history:
                    self.bar_history[symbol] = []
                self.bar_history[symbol].append(bar)
    
    def _update_state(self, positions: Dict[str, Position], cash: float):
        """Internal method to update strategy state"""
        self.state.positions = positions
        self.state.cash = cash
        
        # Calculate exposure
        self.state.long_exposure = 0.0
        self.state.short_exposure = 0.0
        
        for position in positions.values():
            if position.quantity > 0:
                self.state.long_exposure += position.market_value
            else:
                self.state.short_exposure += abs(position.market_value)
        
        self.state.total_exposure = self.state.long_exposure + self.state.short_exposure
        
        # Calculate equity
        unrealized_pnl = sum(p.unrealized_pnl for p in positions.values())
        equity = cash + sum(p.market_value for p in positions.values())
        self.state.update_equity(equity)
    
    # ==================== Helper Methods ====================
    
    def calculate_position_size(self, symbol: str, price: float,
                               fraction_of_capital: Optional[float] = None) -> int:
        """
        Calculate position size based on capital and risk
        
        Args:
            symbol: Symbol to size
            price: Current price
            fraction_of_capital: Fraction of capital to use (default: config max_position_size)
        
        Returns:
            Number of shares
        """
        if fraction_of_capital is None:
            fraction_of_capital = self.config.max_position_size
        
        position_value = self.state.equity * fraction_of_capital
        shares = int(position_value / price)
        return shares
    
    def get_win_rate(self) -> float:
        """Get win rate percentage"""
        total = self.state.winning_trades + self.state.losing_trades
        if total == 0:
            return 0.0
        return (self.state.winning_trades / total) * 100
    
    def get_max_drawdown_pct(self) -> float:
        """Get maximum drawdown percentage"""
        return self.state.max_drawdown * 100
    
    def __repr__(self) -> str:
        return (f"Strategy(name={self.config.name}, "
                f"equity=${self.state.equity:,.2f}, "
                f"trades={self.state.total_trades})")
