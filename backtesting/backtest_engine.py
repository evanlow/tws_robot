"""
Backtesting engine for strategy evaluation.

Simulates trading strategies against historical data with realistic
order execution, slippage, and commission models.
"""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum

from .historical_data import BarData, HistoricalDataManager
from .performance_analytics import PerformanceAnalytics
from .risk_manager import RiskManager
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
        stop_loss: Stop loss price (optional)
        take_profit: Take profit price (optional)
        trailing_stop_pct: Trailing stop percentage (optional)
        trailing_stop_price: Current trailing stop price
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
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    trailing_stop_pct: Optional[float] = None
    trailing_stop_price: Optional[float] = None


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
        position_sizing: str = "fixed",
        position_size_pct: float = 0.1,  # 10% of equity per position
        risk_per_trade: float = 0.02,  # 2% risk per trade for risk-based sizing
        max_position_size: float = 0.25,  # Max 25% of equity in single position
        risk_manager: Optional[RiskManager] = None  # Optional risk management
    ):
        """
        Initialize backtesting engine.
        
        Args:
            initial_capital: Starting capital
            commission: Commission rate (as decimal)
            slippage: Slippage rate (as decimal)
            position_sizing: Position sizing method ('fixed', 'percent', 'risk_based')
            position_size_pct: Percentage of equity per position (for 'percent' method)
            risk_per_trade: Risk percentage per trade (for 'risk_based' method)
            max_position_size: Maximum position size as percentage of equity
            risk_manager: Optional RiskManager instance for risk controls
        """
        self.initial_capital = initial_capital
        self.commission = commission
        self.slippage = slippage
        self.position_sizing = position_sizing
        self.position_size_pct = position_size_pct
        self.risk_per_trade = risk_per_trade
        self.max_position_size = max_position_size
        
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
        
        # Risk manager (optional)
        self.risk_manager = risk_manager
        
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
        
        # Reset risk manager
        if self.risk_manager:
            self.risk_manager.reset()
        
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
            
            # Check stop-loss and take-profit
            self._check_stop_loss_take_profit(bar)
            
            # Calculate current equity
            self.equity = self.cash + sum(
                pos.quantity * pos.current_price 
                for pos in self.positions.values()
            )
            self.equity_curve.append((bar.timestamp, self.equity))
            
            # Update risk manager
            if self.risk_manager:
                self.risk_manager.update(self.equity, bar.timestamp)
            
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
                    # Check with risk manager before placing order
                    if self.risk_manager:
                        can_open, reason = self.risk_manager.can_open_position(
                            signal.symbol,
                            self.equity,
                            self.positions
                        )
                        if not can_open:
                            logger.warning(f"Risk check failed for {signal.symbol}: {reason}")
                            continue
                    
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
        timestamp: Optional[datetime] = None,
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None,
        trailing_stop_pct: Optional[float] = None
    ) -> int:
        """
        Place an order in backtest.
        
        Args:
            symbol: Trading symbol
            signal_type: BUY or SELL
            quantity: Number of shares
            price: Limit price (None for market order)
            timestamp: Order timestamp
            stop_loss: Stop loss price
            take_profit: Take profit price
            trailing_stop_pct: Trailing stop percentage (e.g., 0.02 for 2%)
            
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
            timestamp=timestamp or datetime.now(),
            stop_loss=stop_loss,
            take_profit=take_profit,
            trailing_stop_pct=trailing_stop_pct
        )
        
        self.orders.append(order)
        logger.debug(f"Order placed: {signal_type.value} {quantity} {symbol} @ "
                    f"{price if price else 'MARKET'}"
                    f"{f' SL:{stop_loss}' if stop_loss else ''}"
                    f"{f' TP:{take_profit}' if take_profit else ''}"
                    f"{f' Trail:{trailing_stop_pct*100}%' if trailing_stop_pct else ''}")
        
        return self._order_id
    
    def calculate_position_size(
        self,
        price: float,
        stop_loss: Optional[float] = None
    ) -> int:
        """
        Calculate position size based on position sizing method.
        
        Args:
            price: Entry price
            stop_loss: Stop loss price (required for risk-based sizing)
            
        Returns:
            Number of shares to trade
        """
        if self.position_sizing == "fixed":
            # Fixed quantity (default 100 shares)
            return 100
        
        elif self.position_sizing == "percent":
            # Fixed percentage of equity
            position_value = self.equity * self.position_size_pct
            quantity = int(position_value / price)
            
            # Apply max position size limit
            max_value = self.equity * self.max_position_size
            max_quantity = int(max_value / price)
            
            return min(quantity, max_quantity)
        
        elif self.position_sizing == "risk_based":
            # Size based on risk per trade
            if stop_loss is None or stop_loss == price:
                # Fallback to percent-based if no stop loss
                return self.calculate_position_size(price, None)
            
            risk_amount = self.equity * self.risk_per_trade
            risk_per_share = abs(price - stop_loss)
            
            if risk_per_share == 0:
                return 0
            
            quantity = int(risk_amount / risk_per_share)
            
            # Apply max position size limit
            max_value = self.equity * self.max_position_size
            max_quantity = int(max_value / price)
            
            return min(quantity, max_quantity)
        
        return 100  # Default fallback
    
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
    
    def _check_stop_loss_take_profit(self, bar: BarData):
        """
        Check if any positions hit stop-loss or take-profit levels.
        
        Args:
            bar: Current bar data
        """
        for symbol, position in list(self.positions.items()):
            if position.quantity == 0:
                continue
            
            # Check filled orders for stop-loss/take-profit
            for order in self.orders:
                if (order.status == OrderStatus.FILLED and 
                    order.symbol == symbol and
                    (order.stop_loss or order.take_profit or order.trailing_stop_pct)):
                    
                    should_exit = False
                    exit_price = None
                    exit_reason = ""
                    
                    # Update trailing stop
                    if order.trailing_stop_pct and position.quantity != 0:
                        if position.quantity > 0:  # Long position
                            # Trail upward
                            new_stop = bar.high * (1 - order.trailing_stop_pct)
                            if order.trailing_stop_price is None or new_stop > order.trailing_stop_price:
                                order.trailing_stop_price = new_stop
                            # Check if price hit trailing stop
                            if bar.low <= order.trailing_stop_price:
                                should_exit = True
                                exit_price = order.trailing_stop_price
                                exit_reason = "Trailing Stop"
                        else:  # Short position
                            # Trail downward
                            new_stop = bar.low * (1 + order.trailing_stop_pct)
                            if order.trailing_stop_price is None or new_stop < order.trailing_stop_price:
                                order.trailing_stop_price = new_stop
                            # Check if price hit trailing stop
                            if bar.high >= order.trailing_stop_price:
                                should_exit = True
                                exit_price = order.trailing_stop_price
                                exit_reason = "Trailing Stop"
                    
                    # Check stop-loss
                    if not should_exit and order.stop_loss:
                        if position.quantity > 0 and bar.low <= order.stop_loss:
                            should_exit = True
                            exit_price = order.stop_loss
                            exit_reason = "Stop Loss"
                        elif position.quantity < 0 and bar.high >= order.stop_loss:
                            should_exit = True
                            exit_price = order.stop_loss
                            exit_reason = "Stop Loss"
                    
                    # Check take-profit
                    if not should_exit and order.take_profit:
                        if position.quantity > 0 and bar.high >= order.take_profit:
                            should_exit = True
                            exit_price = order.take_profit
                            exit_reason = "Take Profit"
                        elif position.quantity < 0 and bar.low <= order.take_profit:
                            should_exit = True
                            exit_price = order.take_profit
                            exit_reason = "Take Profit"
                    
                    # Execute exit if triggered
                    if should_exit and exit_price:
                        exit_quantity = abs(position.quantity)
                        exit_signal_type = SignalType.SELL if position.quantity > 0 else SignalType.BUY
                        
                        # Create exit order
                        exit_order_id = self.place_order(
                            symbol=symbol,
                            signal_type=exit_signal_type,
                            quantity=exit_quantity,
                            price=exit_price,
                            timestamp=bar.timestamp
                        )
                        
                        # Execute immediately
                        exit_order = self.orders[-1]
                        exit_order.status = OrderStatus.FILLED
                        exit_order.fill_price = exit_price
                        exit_order.fill_timestamp = bar.timestamp
                        
                        # Update position
                        qty_change = exit_quantity if exit_signal_type == SignalType.BUY else -exit_quantity
                        realized_pnl = position.add_shares(qty_change, exit_price)
                        
                        logger.info(f"{exit_reason} triggered for {symbol} @ ${exit_price:.2f}, P&L: ${realized_pnl:.2f}")
    
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
        results = BacktestResults(
            start_date=start_date,
            end_date=end_date,
            initial_capital=self.initial_capital,
            final_capital=self.equity,
            total_trades=len(self.trades),
            equity_curve=self.equity_curve.copy(),
            trades=self.trades.copy(),
            positions=dict(self.positions)
        )
        
        # Calculate advanced metrics
        analytics = PerformanceAnalytics()
        results.metrics = analytics.calculate_metrics(
            equity_curve=self.equity_curve,
            trades=self.trades,
            initial_capital=self.initial_capital,
            risk_free_rate=0.02
        )
        
        return results


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
    metrics: Dict[str, Any] = None  # Advanced performance metrics
    
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
        summary_dict = {
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
        
        # Add advanced metrics if available
        if self.metrics:
            summary_dict.update({
                'sharpe_ratio': self.metrics.get('sharpe_ratio', 0.0),
                'sortino_ratio': self.metrics.get('sortino_ratio', 0.0),
                'max_drawdown_pct': self.metrics.get('max_drawdown_pct', 0.0),
                'calmar_ratio': self.metrics.get('calmar_ratio', 0.0)
            })
        
        return summary_dict
    
    def print_summary(self):
        """Print formatted summary of results"""
        print("\n" + "="*60)
        print("BACKTEST RESULTS")
        print("="*60)
        
        print(f"\nPeriod: {self.start_date.date()} to {self.end_date.date()}")
        print(f"Duration: {(self.end_date - self.start_date).days} days")
        
        print("\nCapital:")
        print(f"  Initial: ${self.initial_capital:,.2f}")
        print(f"  Final:   ${self.final_capital:,.2f}")
        print(f"  Return:  {self.total_return_percent:.2f}%")
        
        print("\nTrades:")
        print(f"  Total:   {self.total_trades}")
        print(f"  Winners: {self.winning_trades} ({self.win_rate:.1%})")
        print(f"  Losers:  {self.losing_trades}")
        
        print("\nP&L:")
        print(f"  Avg Win:      ${self.average_win:,.2f}")
        print(f"  Avg Loss:     ${self.average_loss:,.2f}")
        print(f"  Profit Factor: {self.profit_factor:.2f}")
        
        if self.metrics:
            print("\nRisk Metrics:")
            print(f"  Sharpe Ratio:  {self.metrics.get('sharpe_ratio', 0):.2f}")
            print(f"  Sortino Ratio: {self.metrics.get('sortino_ratio', 0):.2f}")
            print(f"  Max Drawdown:  {self.metrics.get('max_drawdown_pct', 0):.2f}%")
            print(f"  Calmar Ratio:  {self.metrics.get('calmar_ratio', 0):.2f}")
        
        print("\n" + "="*60 + "\n")
