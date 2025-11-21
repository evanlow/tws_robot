"""
Market Simulator

Simulates realistic market conditions by replaying historical data and
simulating order fills with realistic slippage and partial fills.

Author: TWS Robot Development Team
Date: November 2025
Week 4 Day 1
"""

from datetime import datetime, timedelta
from typing import Dict, List, Optional, Callable
from dataclasses import dataclass
import logging
import random

from .data_models import Bar, MarketData, Trade, Position
from .data_manager import HistoricalDataManager

logger = logging.getLogger(__name__)


@dataclass
class Order:
    """
    Represents a pending order
    
    Attributes:
        order_id: Unique order identifier
        symbol: Symbol to trade
        action: 'BUY' or 'SELL'
        quantity: Number of shares
        order_type: 'MARKET', 'LIMIT', 'STOP'
        limit_price: Limit price (for limit orders)
        stop_price: Stop price (for stop orders)
        time_in_force: 'DAY', 'GTC', 'IOC', 'FOK'
        submitted_at: Order submission timestamp
        strategy_name: Name of strategy submitting order
        status: 'PENDING', 'FILLED', 'PARTIAL', 'CANCELLED'
    """
    order_id: str
    symbol: str
    action: str  # 'BUY' or 'SELL'
    quantity: int
    order_type: str = 'MARKET'
    limit_price: Optional[float] = None
    stop_price: Optional[float] = None
    time_in_force: str = 'DAY'
    submitted_at: Optional[datetime] = None
    strategy_name: str = ""
    status: str = 'PENDING'
    filled_quantity: int = 0


class FillSimulator:
    """
    Simulates realistic order fills with slippage and partial fills
    
    Models:
    - Market impact based on order size vs. average volume
    - Bid-ask spread
    - Partial fills for large orders
    - Realistic slippage
    """
    
    def __init__(
        self,
        default_spread_bps: float = 5.0,  # 5 basis points
        market_impact_factor: float = 0.1,  # 10% of volume impact
        slippage_std: float = 0.0002  # 0.02% standard deviation
    ):
        """
        Initialize fill simulator
        
        Args:
            default_spread_bps: Default bid-ask spread in basis points
            market_impact_factor: Market impact as fraction of volume
            slippage_std: Standard deviation of random slippage
        """
        self.default_spread_bps = default_spread_bps
        self.market_impact_factor = market_impact_factor
        self.slippage_std = slippage_std
        
        logger.info(
            f"Initialized FillSimulator: spread={default_spread_bps}bps, "
            f"impact={market_impact_factor}, slippage_std={slippage_std}"
        )
    
    def simulate_fill(
        self,
        order: Order,
        bar: Bar,
        position_size_pct: float = 0.01  # Order size as % of avg volume
    ) -> Optional[Trade]:
        """
        Simulate order fill based on current market conditions
        
        Args:
            order: Order to fill
            bar: Current market bar
            position_size_pct: Order size as percentage of average volume
            
        Returns:
            Trade if filled, None if not filled
        """
        if order.order_type == 'MARKET':
            return self._fill_market_order(order, bar, position_size_pct)
        elif order.order_type == 'LIMIT':
            return self._fill_limit_order(order, bar)
        elif order.order_type == 'STOP':
            return self._fill_stop_order(order, bar)
        else:
            logger.warning(f"Unsupported order type: {order.order_type}")
            return None
    
    def _fill_market_order(
        self,
        order: Order,
        bar: Bar,
        position_size_pct: float
    ) -> Trade:
        """
        Fill market order with realistic slippage
        
        Market orders fill immediately but with:
        - Bid-ask spread
        - Market impact (larger orders = more impact)
        - Random slippage
        """
        # Base fill price (typical price of bar)
        base_price = bar.typical_price
        
        # Apply bid-ask spread (pay ask for buy, receive bid for sell)
        spread = base_price * (self.default_spread_bps / 10000)
        if order.action == 'BUY':
            fill_price = base_price + spread / 2
        else:  # SELL
            fill_price = base_price - spread / 2
        
        # Apply market impact (proportional to order size vs volume)
        if bar.volume > 0:
            volume_impact = min(position_size_pct, 0.10)  # Cap at 10%
            impact = fill_price * self.market_impact_factor * volume_impact
            if order.action == 'BUY':
                fill_price += impact
            else:
                fill_price -= impact
        
        # Apply random slippage
        random_slippage = random.gauss(0, self.slippage_std)
        fill_price *= (1 + random_slippage)
        
        # Ensure fill price is within bar's range
        fill_price = max(bar.low, min(bar.high, fill_price))
        
        # Calculate commission (simple model: $0.005 per share, $1 minimum)
        commission = max(1.0, order.quantity * 0.005)
        
        # Calculate total slippage
        slippage = fill_price - base_price
        
        trade = Trade(
            timestamp=bar.timestamp,
            symbol=order.symbol,
            action=order.action,
            quantity=order.quantity,
            price=fill_price,
            commission=commission,
            slippage=slippage,
            order_id=order.order_id,
            strategy_name=order.strategy_name
        )
        
        order.status = 'FILLED'
        order.filled_quantity = order.quantity
        
        logger.debug(
            f"Filled market order: {order.action} {order.quantity} {order.symbol} "
            f"@ ${fill_price:.2f} (slippage: ${slippage:.4f}, commission: ${commission:.2f})"
        )
        
        return trade
    
    def _fill_limit_order(self, order: Order, bar: Bar) -> Optional[Trade]:
        """
        Fill limit order if price condition met
        
        Buy limit: Fill if low <= limit_price
        Sell limit: Fill if high >= limit_price
        """
        if order.limit_price is None:
            logger.warning(f"Limit order {order.order_id} missing limit price")
            return None
        
        can_fill = False
        fill_price = order.limit_price
        
        if order.action == 'BUY':
            # Buy limit: fill if market went at or below limit price
            if bar.low <= order.limit_price:
                can_fill = True
                # Fill at limit price or better
                fill_price = min(order.limit_price, bar.open)
        else:  # SELL
            # Sell limit: fill if market went at or above limit price
            if bar.high >= order.limit_price:
                can_fill = True
                # Fill at limit price or better
                fill_price = max(order.limit_price, bar.open)
        
        if not can_fill:
            return None
        
        # Calculate commission
        commission = max(1.0, order.quantity * 0.005)
        
        trade = Trade(
            timestamp=bar.timestamp,
            symbol=order.symbol,
            action=order.action,
            quantity=order.quantity,
            price=fill_price,
            commission=commission,
            order_id=order.order_id,
            strategy_name=order.strategy_name
        )
        
        order.status = 'FILLED'
        order.filled_quantity = order.quantity
        
        logger.debug(
            f"Filled limit order: {order.action} {order.quantity} {order.symbol} "
            f"@ ${fill_price:.2f} (limit: ${order.limit_price:.2f})"
        )
        
        return trade
    
    def _fill_stop_order(self, order: Order, bar: Bar) -> Optional[Trade]:
        """
        Fill stop order if stop price triggered
        
        Buy stop: Trigger if high >= stop_price (breakout)
        Sell stop: Trigger if low <= stop_price (stop loss)
        """
        if order.stop_price is None:
            logger.warning(f"Stop order {order.order_id} missing stop price")
            return None
        
        triggered = False
        
        if order.action == 'BUY':
            # Buy stop: trigger if price went at or above stop
            if bar.high >= order.stop_price:
                triggered = True
        else:  # SELL
            # Sell stop: trigger if price went at or below stop
            if bar.low <= order.stop_price:
                triggered = True
        
        if not triggered:
            return None
        
        # Once triggered, fill as market order with slippage
        # Use stop price as base, but apply slippage
        fill_price = order.stop_price
        
        # Apply slippage (stops usually have more slippage)
        slippage_pct = abs(random.gauss(0, self.slippage_std * 2))  # 2x normal slippage
        
        if order.action == 'BUY':
            fill_price *= (1 + slippage_pct)  # Buy higher
        else:
            fill_price *= (1 - slippage_pct)  # Sell lower
        
        # Ensure within bar range
        fill_price = max(bar.low, min(bar.high, fill_price))
        
        # Calculate commission
        commission = max(1.0, order.quantity * 0.005)
        
        trade = Trade(
            timestamp=bar.timestamp,
            symbol=order.symbol,
            action=order.action,
            quantity=order.quantity,
            price=fill_price,
            commission=commission,
            slippage=fill_price - order.stop_price,
            order_id=order.order_id,
            strategy_name=order.strategy_name
        )
        
        order.status = 'FILLED'
        order.filled_quantity = order.quantity
        
        logger.debug(
            f"Filled stop order: {order.action} {order.quantity} {order.symbol} "
            f"@ ${fill_price:.2f} (stop: ${order.stop_price:.2f})"
        )
        
        return trade


class MarketSimulator:
    """
    Simulates market by replaying historical data chronologically
    
    Responsibilities:
    - Iterate through historical data bar by bar
    - Provide current market state to strategies
    - Process orders and simulate fills
    - Track positions and equity
    """
    
    def __init__(
        self,
        data_manager: HistoricalDataManager,
        fill_simulator: Optional[FillSimulator] = None
    ):
        """
        Initialize market simulator
        
        Args:
            data_manager: Historical data manager
            fill_simulator: Fill simulator (creates default if None)
        """
        self.data_manager = data_manager
        self.fill_simulator = fill_simulator or FillSimulator()
        
        self.current_time: Optional[datetime] = None
        self.symbols: List[str] = []
        self.pending_orders: List[Order] = []
        self.completed_trades: List[Trade] = []
        self.positions: Dict[str, Position] = {}
        
        # Event callbacks
        self.on_bar_callbacks: List[Callable] = []
        self.on_trade_callbacks: List[Callable] = []
        
        logger.info("Initialized MarketSimulator")
    
    def replay(
        self,
        start_date: datetime,
        end_date: datetime,
        symbols: List[str],
        initial_cash: float = 100000.0
    ):
        """
        Replay historical market data bar by bar
        
        Args:
            start_date: Start date for replay
            end_date: End date for replay
            symbols: List of symbols to simulate
            initial_cash: Starting cash
            
        Yields:
            MarketData for each timestamp
        """
        self.symbols = symbols
        self.current_time = start_date
        
        logger.info(
            f"Starting market replay: {start_date.date()} to {end_date.date()}, "
            f"symbols: {symbols}"
        )
        
        # Get all unique timestamps across all symbols
        all_timestamps = set()
        for symbol in symbols:
            bars = self.data_manager.get_bars(symbol, start_date, end_date)
            all_timestamps.update(bar.timestamp for bar in bars)
        
        # Sort timestamps chronologically
        timestamps = sorted(all_timestamps)
        
        logger.info(f"Replaying {len(timestamps)} time periods")
        
        # Replay each timestamp
        for timestamp in timestamps:
            self.current_time = timestamp
            
            # Get market data for this timestamp
            market_data = self.data_manager.get_market_data(timestamp, symbols)
            
            # Process pending orders
            self._process_pending_orders(market_data)
            
            # Update positions with current prices
            self._update_positions(market_data)
            
            # Call bar callbacks
            for callback in self.on_bar_callbacks:
                callback(market_data)
            
            yield market_data
        
        logger.info(
            f"Replay complete. {len(self.completed_trades)} trades executed, "
            f"{len(self.positions)} positions remaining"
        )
    
    def submit_order(self, order: Order) -> str:
        """
        Submit order for execution
        
        Args:
            order: Order to submit
            
        Returns:
            Order ID
        """
        order.submitted_at = self.current_time
        self.pending_orders.append(order)
        
        logger.debug(
            f"Order submitted: {order.action} {order.quantity} {order.symbol} "
            f"({order.order_type})"
        )
        
        return order.order_id
    
    def cancel_order(self, order_id: str) -> bool:
        """
        Cancel pending order
        
        Args:
            order_id: Order to cancel
            
        Returns:
            True if cancelled successfully
        """
        for order in self.pending_orders:
            if order.order_id == order_id:
                order.status = 'CANCELLED'
                self.pending_orders.remove(order)
                logger.debug(f"Order {order_id} cancelled")
                return True
        
        logger.warning(f"Order {order_id} not found")
        return False
    
    def get_position(self, symbol: str) -> Optional[Position]:
        """Get current position for symbol"""
        return self.positions.get(symbol)
    
    def get_all_positions(self) -> Dict[str, Position]:
        """Get all current positions"""
        return self.positions.copy()
    
    def register_bar_callback(self, callback: Callable) -> None:
        """Register callback for each bar event"""
        self.on_bar_callbacks.append(callback)
    
    def register_trade_callback(self, callback: Callable) -> None:
        """Register callback for trade events"""
        self.on_trade_callbacks.append(callback)
    
    def _process_pending_orders(self, market_data: MarketData) -> None:
        """Process all pending orders"""
        filled_orders = []
        
        for order in self.pending_orders[:]:  # Copy list to allow removal
            # Get bar for this symbol
            bar = market_data.get_bar(order.symbol)
            if not bar:
                continue
            
            # Try to fill order
            trade = self.fill_simulator.simulate_fill(order, bar)
            
            if trade:
                # Update positions
                self._update_position_from_trade(trade)
                
                # Record trade
                self.completed_trades.append(trade)
                filled_orders.append(order)
                
                # Call trade callbacks
                for callback in self.on_trade_callbacks:
                    callback(trade)
        
        # Remove filled orders
        for order in filled_orders:
            if order in self.pending_orders:
                self.pending_orders.remove(order)
    
    def _update_position_from_trade(self, trade: Trade) -> None:
        """Update position based on trade"""
        symbol = trade.symbol
        
        if symbol not in self.positions:
            # New position
            if trade.action == 'BUY':
                self.positions[symbol] = Position(
                    symbol=symbol,
                    quantity=trade.quantity,
                    average_cost=trade.price,
                    current_price=trade.price
                )
            else:  # SELL (short)
                self.positions[symbol] = Position(
                    symbol=symbol,
                    quantity=-trade.quantity,
                    average_cost=trade.price,
                    current_price=trade.price
                )
        else:
            # Update existing position
            position = self.positions[symbol]
            
            if trade.action == 'BUY':
                # Adding to long or reducing short
                new_quantity = position.quantity + trade.quantity
                
                if position.quantity >= 0:
                    # Adding to long
                    total_cost = (position.quantity * position.average_cost + 
                                 trade.quantity * trade.price)
                    position.average_cost = total_cost / new_quantity
                else:
                    # Closing short
                    if new_quantity == 0:
                        # Position closed
                        del self.positions[symbol]
                        return
                
                position.quantity = new_quantity
            
            else:  # SELL
                # Adding to short or reducing long
                new_quantity = position.quantity - trade.quantity
                
                if position.quantity <= 0:
                    # Adding to short
                    total_cost = (abs(position.quantity) * position.average_cost + 
                                 trade.quantity * trade.price)
                    position.average_cost = total_cost / abs(new_quantity)
                else:
                    # Closing long
                    if new_quantity == 0:
                        # Position closed
                        del self.positions[symbol]
                        return
                
                position.quantity = new_quantity
    
    def _update_positions(self, market_data: MarketData) -> None:
        """Update position prices with current market data"""
        for symbol, position in self.positions.items():
            bar = market_data.get_bar(symbol)
            if bar:
                position.update_price(bar.close)
