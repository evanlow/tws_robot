"""
Backtesting engine for strategy evaluation.

Simulates trading strategies against historical data with realistic
order execution, slippage, and commission models.
"""

import logging
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum

from .historical_data import BarData, HistoricalDataManager
from strategies.base_strategy import BaseStrategy, StrategyState
from strategies.signal import Signal, SignalType


logger = logging.getLogger(__name__)


class OrderStatus(Enum):
    """Order execution status"""
    PENDING = "PENDING"
    FILLED = "FILLED"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"


@dataclass
class BacktestOrder:
    """
    Order in backtest simulation.
    
    Attributes:
        order_id: Unique order identifier
        symbol: Trading symbol
        order_type: BUY or SELL
        quantity: Number of shares
        price: Limit price (None for market orders)
        timestamp: When order was created
        status: Current order status
        fill_price: Actual execution price (if filled)
        fill_timestamp: When order was filled
    """
    order_id: int
    symbol: str
    order_type: SignalType
    quantity: int
    timestamp: datetime
    price: Optional[float] = None
    status: OrderStatus = OrderStatus.PENDING
    fill_price: Optional[float] = None
    fill_timestamp: Optional[datetime] = None


@dataclass
class BacktestPosition:
    """
    Position in backtest simulation.
    
    Attributes:
        symbol: Trading symbol
        quantity: Number of shares (positive=long, negative=short)
        avg_price: Average entry price
        current_price: Current market price
        unrealized_pnl: Unrealized profit/loss
        realized_pnl: Realized profit/loss from closed positions
    """
    symbol: str
    quantity: int = 0
    avg_price: float = 0.0
    current_price: float = 0.0
    unrealized_pnl: float = 0.0
    realized_pnl: float = 0.0
    
    def update_market_price(self, price: float):
        """Update current market price and unrealized P&L"""
        self.current_price = price
        if self.quantity != 0:
            self.unrealized_pnl = (price - self.avg_price) * self.quantity
    
    def add_shares(self, quantity: int, price: float) -> float:
        """
        Add shares to position and return realized P&L.
        
        Args:
            quantity: Number of shares (positive=buy, negative=sell)
            price: Execution price
            
        Returns:
            Realized P&L from this transaction
        """
        realized = 0.0
        
        if self.quantity == 0:
            # Opening new position
            self.quantity = quantity
            self.avg_price = price
        elif (self.quantity > 0 and quantity > 0) or (self.quantity < 0 and quantity < 0):
            # Adding to existing position
            total_cost = self.avg_price * abs(self.quantity) + price * abs(quantity)
            self.quantity += quantity
            self.avg_price = total_cost / abs(self.quantity)
        else:
            # Reducing or closing position
            if abs(quantity) < abs(self.quantity):
                # Partial close
                realized = (price - self.avg_price) * abs(quantity)
                self.quantity += quantity
            else:
                # Full close (and possibly reverse)
                realized = (price - self.avg_price) * abs(self.quantity)
                remaining_qty = abs(quantity) - abs(self.quantity)
                self.quantity = remaining_qty if quantity > 0 else -remaining_qty
                self.avg_price = price if remaining_qty > 0 else 0.0
        
        self.realized_pnl += realized
        self.update_market_price(price)
        return realized


@dataclass
class BacktestTrade:
    """
    Completed trade in backtest.
    
    Attributes:
        trade_id: Unique trade identifier
        symbol: Trading symbol
        entry_time: Entry timestamp
        exit_time: Exit timestamp
        entry_price: Entry price
        exit_price: Exit price
        quantity: Number of shares
        direction: LONG or SHORT
        pnl: Profit/loss
        pnl_percent: P&L as percentage
        commission: Total commission paid
    """
    trade_id: int
    symbol: str
    entry_time: datetime
    exit_time: datetime
    entry_price: float
    exit_price: float
    quantity: int
    direction: str
    pnl: float
    pnl_percent: float
    commission: float


class BacktestEngine:
    """
    Backtesting engine for strategy evaluation.
    
    Features:
    - Bar-by-bar simulation
    - Realistic order execution with slippage
    - Commission and fee modeling
    - Position tracking
    - Performance metrics calculation
    
    Example:
        >>> engine = BacktestEngine(
        ...     initial_capital=100000,
        ...     commission=0.001,
        ...     slippage=0.0005
        ... )
        >>> 
        >>> # Load historical data
        >>> data_manager = HistoricalDataManager()
        >>> bars = data_manager.get_historical_data("AAPL", start, end)
        >>> 
        >>> # Run backtest
        >>> results = engine.run_backtest(strategy, bars)
        >>> print(f"Total Return: {results.total_return:.2%}")
    """
    
    def __init__(
        self,
        initial_capital: float = 100000.0,
        commission: float = 0.001,  # 0.1% per trade
        slippage: float = 0.0005,   # 0.05% slippage
        position_sizing: str = "fixed"
    ):
        """
        Initialize backtesting engine.
        
        Args:
            initial_capital: Starting capital
            commission: Commission rate (as decimal)
            slippage: Slippage rate (as decimal)
            position_sizing: Position sizing method ('fixed', 'percent', 'risk_based')
        """
        self.initial_capital = initial_capital
        self.commission = commission
        self.slippage = slippage
        self.position_sizing = position_sizing
        
        # Current state
        self.cash = initial_capital
        self.equity = initial_capital
        
        # Tracking
        self.positions: Dict[str, BacktestPosition] = {}
        self.orders: List[BacktestOrder] = []
        self.trades: List[BacktestTrade] = []
        
        # Counters
        self._order_id = 0
        self._trade_id = 0
        
        # Equity curve
        self.equity_curve: List[Tuple[datetime, float]] = []
        
        logger.info(f"BacktestEngine initialized with ${initial_capital:,.2f}")
    
    def reset(self):
        """Reset engine state for new backtest"""
        self.cash = self.initial_capital
        self.equity = self.initial_capital
        self.positions.clear()
        self.orders.clear()
        self.trades.clear()
        self.equity_curve.clear()
        self._order_id = 0
        self._trade_id = 0
        logger.debug("BacktestEngine reset")
    
    def run_backtest(
        self,
        strategy: BaseStrategy,
        bars: List[BarData],
        symbol: str
    ) -> 'BacktestResults':
        """
        Run backtest simulation.
        
        Args:
            strategy: Strategy to test
            bars: Historical bar data
            symbol: Trading symbol
            
        Returns:
            BacktestResults object
        """
        self.reset()
        logger.info(f"Starting backtest for {symbol} with {len(bars)} bars")
        
        # Start strategy
        strategy.start()
        
        # Simulate bar by bar
        for i, bar in enumerate(bars):
            # Update positions with current prices
            self._update_positions(symbol, bar.close)
            
            # Calculate current equity
            self.equity = self.cash + sum(
                pos.quantity * pos.current_price 
                for pos in self.positions.values()
            )
            self.equity_curve.append((bar.timestamp, self.equity))
            
            # Process pending orders
            self._process_orders(bar)
            
            # Feed bar to strategy
            bar_data = {
                'symbol': symbol,
                'timestamp': bar.timestamp,
                'open': bar.open,
                'high': bar.high,
                'low': bar.low,
                'close': bar.close,
                'volume': bar.volume
            }
            
            # Call strategy's on_bar method
            try:
                strategy.on_bar(symbol, bar_data)
            except Exception as e:
                logger.error(f"Error in strategy on_bar: {e}")
                continue
            
            # Process any signals generated by strategy
            if hasattr(strategy, 'signals_to_emit'):
                for signal in strategy.signals_to_emit:
                    self.place_order(
                        symbol=signal.symbol,
                        signal_type=signal.signal_type,
                        quantity=100,  # Default quantity for backtest
                        timestamp=signal.timestamp
                    )
                strategy.signals_to_emit.clear()
            
            # Log progress periodically
            if (i + 1) % 100 == 0:
                logger.debug(f"Processed {i + 1}/{len(bars)} bars, Equity: ${self.equity:,.2f}")
        
        # Stop strategy
        strategy.stop()
        
        # Generate results
        results = self._calculate_results(bars[0].timestamp, bars[-1].timestamp)
        logger.info(f"Backtest complete. Final equity: ${self.equity:,.2f}")
        
        return results
    
    def place_order(
        self,
        symbol: str,
        signal_type: SignalType,
        quantity: int,
        price: Optional[float] = None,
        timestamp: Optional[datetime] = None
    ) -> int:
        """
        Place an order in backtest.
        
        Args:
            symbol: Trading symbol
            signal_type: BUY or SELL
            quantity: Number of shares
            price: Limit price (None for market order)
            timestamp: Order timestamp
            
        Returns:
            Order ID
        """
        self._order_id += 1
        
        order = BacktestOrder(
            order_id=self._order_id,
            symbol=symbol,
            order_type=signal_type,
            quantity=quantity,
            price=price,
            timestamp=timestamp or datetime.now()
        )
        
        self.orders.append(order)
        logger.debug(f"Order placed: {signal_type.value} {quantity} {symbol} @ "
                    f"{price if price else 'MARKET'}")
        
        return self._order_id
    
    def _process_orders(self, bar: BarData):
        """
        Process pending orders against current bar.
        
        Args:
            bar: Current bar data
        """
        for order in self.orders:
            if order.status != OrderStatus.PENDING:
                continue
            
            if order.symbol != bar.timestamp:  # Match symbol
                # Simple market order execution
                fill_price = self._calculate_fill_price(order, bar)
                
                if fill_price is None:
                    continue
                
                # Execute order
                success = self._execute_order(order, fill_price, bar.timestamp)
                
                if success:
                    order.status = OrderStatus.FILLED
                    order.fill_price = fill_price
                    order.fill_timestamp = bar.timestamp
    
    def _calculate_fill_price(
        self,
        order: BacktestOrder,
        bar: BarData
    ) -> Optional[float]:
        """
        Calculate order fill price with slippage.
        
        Args:
            order: Order to fill
            bar: Current bar
            
        Returns:
            Fill price or None if order can't be filled
        """
        if order.price is None:
            # Market order - use close with slippage
            if order.order_type == SignalType.BUY:
                fill_price = bar.close * (1 + self.slippage)
            else:
                fill_price = bar.close * (1 - self.slippage)
        else:
            # Limit order - check if price reached
            if order.order_type == SignalType.BUY:
                if bar.low <= order.price:
                    fill_price = order.price
                else:
                    return None
            else:
                if bar.high >= order.price:
                    fill_price = order.price
                else:
                    return None
        
        return round(fill_price, 2)
    
    def _execute_order(
        self,
        order: BacktestOrder,
        fill_price: float,
        timestamp: datetime
    ) -> bool:
        """
        Execute an order.
        
        Args:
            order: Order to execute
            fill_price: Execution price
            timestamp: Execution timestamp
            
        Returns:
            True if successful
        """
        # Calculate cost/proceeds
        value = fill_price * order.quantity
        commission_cost = value * self.commission
        
        # Check if we have enough cash for buys
        if order.order_type == SignalType.BUY:
            total_cost = value + commission_cost
            if total_cost > self.cash:
                logger.warning(f"Insufficient cash for order {order.order_id}")
                order.status = OrderStatus.REJECTED
                return False
            
            self.cash -= total_cost
        else:
            # Selling
            proceeds = value - commission_cost
            self.cash += proceeds
        
        # Update position
        symbol = order.symbol
        if symbol not in self.positions:
            self.positions[symbol] = BacktestPosition(symbol=symbol)
        
        quantity_change = order.quantity if order.order_type == SignalType.BUY else -order.quantity
        realized_pnl = self.positions[symbol].add_shares(quantity_change, fill_price)
        
        # Record trade if position closed
        if realized_pnl != 0:
            self._record_trade(order, fill_price, realized_pnl, commission_cost)
        
        logger.debug(f"Order {order.order_id} executed @ ${fill_price:.2f}")
        return True
    
    def _record_trade(
        self,
        order: BacktestOrder,
        exit_price: float,
        pnl: float,
        commission: float
    ):
        """
        Record a completed trade.
        
        Args:
            order: Exit order
            exit_price: Exit price
            pnl: Profit/loss
            commission: Commission paid
        """
        self._trade_id += 1
        
        # Note: This is simplified - in reality, we'd track entry/exit pairs
        trade = BacktestTrade(
            trade_id=self._trade_id,
            symbol=order.symbol,
            entry_time=order.timestamp,
            exit_time=order.fill_timestamp or order.timestamp,
            entry_price=order.price or exit_price,
            exit_price=exit_price,
            quantity=order.quantity,
            direction="LONG" if order.order_type == SignalType.SELL else "SHORT",
            pnl=pnl - commission,
            pnl_percent=(pnl / (order.quantity * order.price)) * 100 if order.price else 0,
            commission=commission
        )
        
        self.trades.append(trade)
    
    def _update_positions(self, symbol: str, price: float):
        """
        Update position values with current market price.
        
        Args:
            symbol: Trading symbol
            price: Current price
        """
        if symbol in self.positions:
            self.positions[symbol].update_market_price(price)
    
    def _calculate_results(
        self,
        start_date: datetime,
        end_date: datetime
    ) -> 'BacktestResults':
        """
        Calculate backtest results.
        
        Args:
            start_date: Backtest start date
            end_date: Backtest end date
            
        Returns:
            BacktestResults object
        """
        return BacktestResults(
            start_date=start_date,
            end_date=end_date,
            initial_capital=self.initial_capital,
            final_capital=self.equity,
            total_trades=len(self.trades),
            equity_curve=self.equity_curve.copy(),
            trades=self.trades.copy(),
            positions=dict(self.positions)
        )


@dataclass
class BacktestResults:
    """
    Results from backtest simulation.
    
    Contains performance metrics, trade history, and equity curve.
    """
    start_date: datetime
    end_date: datetime
    initial_capital: float
    final_capital: float
    total_trades: int
    equity_curve: List[Tuple[datetime, float]]
    trades: List[BacktestTrade]
    positions: Dict[str, BacktestPosition]
    
    @property
    def total_return(self) -> float:
        """Total return as decimal"""
        return (self.final_capital - self.initial_capital) / self.initial_capital
    
    @property
    def total_return_percent(self) -> float:
        """Total return as percentage"""
        return self.total_return * 100
    
    @property
    def winning_trades(self) -> int:
        """Number of winning trades"""
        return sum(1 for t in self.trades if t.pnl > 0)
    
    @property
    def losing_trades(self) -> int:
        """Number of losing trades"""
        return sum(1 for t in self.trades if t.pnl < 0)
    
    @property
    def win_rate(self) -> float:
        """Win rate as decimal"""
        if self.total_trades == 0:
            return 0.0
        return self.winning_trades / self.total_trades
    
    @property
    def average_win(self) -> float:
        """Average profit of winning trades"""
        wins = [t.pnl for t in self.trades if t.pnl > 0]
        return sum(wins) / len(wins) if wins else 0.0
    
    @property
    def average_loss(self) -> float:
        """Average loss of losing trades"""
        losses = [t.pnl for t in self.trades if t.pnl < 0]
        return sum(losses) / len(losses) if losses else 0.0
    
    @property
    def profit_factor(self) -> float:
        """Profit factor (gross profit / gross loss)"""
        gross_profit = sum(t.pnl for t in self.trades if t.pnl > 0)
        gross_loss = abs(sum(t.pnl for t in self.trades if t.pnl < 0))
        return gross_profit / gross_loss if gross_loss > 0 else 0.0
    
    def summary(self) -> dict:
        """Get summary statistics"""
        return {
            'start_date': self.start_date,
            'end_date': self.end_date,
            'duration_days': (self.end_date - self.start_date).days,
            'initial_capital': self.initial_capital,
            'final_capital': self.final_capital,
            'total_return': self.total_return,
            'total_return_percent': self.total_return_percent,
            'total_trades': self.total_trades,
            'winning_trades': self.winning_trades,
            'losing_trades': self.losing_trades,
            'win_rate': self.win_rate,
            'average_win': self.average_win,
            'average_loss': self.average_loss,
            'profit_factor': self.profit_factor
        }
