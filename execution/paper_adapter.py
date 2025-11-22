"""
Paper Trading Adapter

Bridges the backtest Strategy interface with live TWS paper trading.

Converts backtest-style strategy orders (Strategy.buy/sell) into actual
TWS API orders while maintaining compatibility with the backtest framework.

Key Features:
- Implements Strategy order interface (buy, sell, close_position)
- Real-time position tracking from TWS
- Commission simulation matching backtest assumptions
- Order status monitoring and callbacks
- Connection resilience and error handling

Author: TWS Robot Development Team
Date: November 22, 2025
Sprint 1 Task 2
"""

import logging
from typing import Optional, Dict, Callable
from datetime import datetime
from dataclasses import dataclass

from ibapi.client import EClient
from ibapi.wrapper import EWrapper
from ibapi.contract import Contract
from ibapi.order import Order as IBOrder
import threading

from backtest.data_models import Position

logger = logging.getLogger(__name__)


@dataclass
class PendingOrder:
    """Track pending orders"""
    order_id: int
    symbol: str
    action: str  # BUY or SELL
    quantity: int
    order_type: str
    limit_price: Optional[float] = None
    stop_price: Optional[float] = None
    status: str = "PENDING"
    filled_qty: int = 0
    avg_fill_price: float = 0.0
    commission: float = 0.0


class PaperTradingAdapter(EWrapper, EClient):
    """
    Adapter for paper trading through TWS API.
    
    Wraps TWS client and provides Strategy-compatible interface.
    Tracks positions, manages orders, simulates commissions.
    """
    
    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 7497,  # Paper trading port
        client_id: int = 100,
        commission_per_share: float = 0.005  # $0.005 per share (match backtest)
    ):
        """
        Initialize paper trading adapter.
        
        Args:
            host: TWS host address
            port: TWS port (7497 for paper)
            client_id: Unique client ID
            commission_per_share: Commission rate per share
        """
        EWrapper.__init__(self)
        EClient.__init__(self, wrapper=self)
        
        self.host = host
        self.port = port
        self.client_id = client_id
        self.commission_per_share = commission_per_share
        
        # Connection state
        self.connected = False
        self.next_valid_order_id = None
        self.ready = False
        
        # Position tracking (symbol -> Position)
        self._positions: Dict[str, Position] = {}
        self._positions_lock = threading.Lock()
        
        # Order tracking (order_id -> PendingOrder)
        self._orders: Dict[int, PendingOrder] = {}
        self._orders_lock = threading.Lock()
        
        # Callbacks
        self._on_fill_callback: Optional[Callable] = None
        self._on_error_callback: Optional[Callable] = None
        
        logger.info(f"Initialized PaperTradingAdapter (port={port}, client_id={client_id})")
    
    # ==================== Connection Management ====================
    
    def connect_and_run(self) -> bool:
        """
        Connect to TWS and run message loop in background thread.
        
        Returns:
            True if connection successful
        """
        try:
            self.connect(self.host, self.port, self.client_id)
            
            # Start message processing thread
            thread = threading.Thread(target=self.run, daemon=True)
            thread.start()
            
            # Wait for connection
            timeout = 10  # seconds
            for i in range(timeout * 10):
                if self.ready:
                    logger.info("Connected to TWS and ready for trading")
                    return True
                threading.Event().wait(0.1)
            
            logger.error("Connection timeout")
            return False
            
        except Exception as e:
            logger.error(f"Connection failed: {e}")
            return False
    
    def disconnect_gracefully(self):
        """Disconnect from TWS"""
        if self.connected:
            self.disconnect()
            self.connected = False
            self.ready = False
            logger.info("Disconnected from TWS")
    
    # ==================== EWrapper Callbacks ====================
    
    def connectAck(self):
        """Called when connection established"""
        logger.info("TWS connection acknowledged")
        self.connected = True
    
    def nextValidId(self, orderId: int):
        """Called when TWS sends next valid order ID - ready to trade"""
        self.next_valid_order_id = orderId
        self.ready = True
        logger.info(f"Ready to trade - next valid order ID: {orderId}")
    
    def error(self, reqId: int, errorCode: int, errorString: str):
        """Handle errors from TWS"""
        # Informational codes (2100-2199) are not errors
        if 2100 <= errorCode < 2200:
            logger.info(f"TWS Info [{errorCode}]: {errorString}")
            return
        
        # Real errors
        logger.error(f"TWS Error [{errorCode}]: {errorString} (reqId={reqId})")
        
        if self._on_error_callback:
            self._on_error_callback(reqId, errorCode, errorString)
        
        # Mark order as rejected if it's an order error
        if reqId > 0 and reqId in self._orders:
            with self._orders_lock:
                if reqId in self._orders:
                    self._orders[reqId].status = "REJECTED"
    
    def orderStatus(
        self,
        orderId: int,
        status: str,
        filled: float,
        remaining: float,
        avgFillPrice: float,
        permId: int,
        parentId: int,
        lastFillPrice: float,
        clientId: int,
        whyHeld: str,
        mktCapPrice: float
    ):
        """Track order status updates"""
        logger.info(f"Order {orderId}: {status} (filled={filled}, remaining={remaining}, avgPrice={avgFillPrice})")
        
        with self._orders_lock:
            if orderId in self._orders:
                order = self._orders[orderId]
                order.status = status
                order.filled_qty = int(filled)
                order.avg_fill_price = avgFillPrice
                
                # Calculate commission
                if filled > 0:
                    order.commission = filled * self.commission_per_share
                
                # If filled, update positions
                if status == "Filled":
                    self._update_position_from_fill(order)
                    
                    if self._on_fill_callback:
                        self._on_fill_callback(order)
    
    def position(self, account: str, contract: Contract, position: float, avgCost: float):
        """Receive position updates"""
        symbol = contract.symbol
        
        with self._positions_lock:
            if position == 0:
                # Position closed
                if symbol in self._positions:
                    del self._positions[symbol]
            else:
                # Position open or updated
                self._positions[symbol] = Position(
                    symbol=symbol,
                    quantity=int(position),
                    average_cost=avgCost
                )
        
        logger.debug(f"Position update: {symbol} = {position} @ {avgCost}")
    
    def positionEnd(self):
        """Called when all positions have been delivered"""
        logger.debug("Position updates complete")
    
    # ==================== Position Management ====================
    
    def request_positions(self):
        """Request current positions from TWS"""
        self.reqPositions()
    
    def get_position(self, symbol: str) -> Optional[Position]:
        """
        Get current position for a symbol.
        
        Args:
            symbol: Stock symbol
        
        Returns:
            Position object or None
        """
        with self._positions_lock:
            return self._positions.get(symbol)
    
    def get_all_positions(self) -> Dict[str, Position]:
        """Get all current positions"""
        with self._positions_lock:
            return self._positions.copy()
    
    def _update_position_from_fill(self, order: PendingOrder):
        """Update position tracking from filled order"""
        symbol = order.symbol
        
        with self._positions_lock:
            current_pos = self._positions.get(symbol)
            
            if order.action == "BUY":
                qty_change = order.filled_qty
            else:  # SELL
                qty_change = -order.filled_qty
            
            if current_pos:
                # Update existing position
                new_qty = current_pos.quantity + qty_change
                if new_qty == 0:
                    # Position closed
                    del self._positions[symbol]
                else:
                    # Update position with weighted average price
                    if qty_change > 0:  # Adding to position
                        total_cost = (current_pos.quantity * current_pos.average_cost + 
                                    qty_change * order.avg_fill_price)
                        new_avg_price = total_cost / new_qty
                    else:  # Reducing position
                        new_avg_price = current_pos.average_cost  # Keep original cost basis
                    
                    self._positions[symbol] = Position(
                        symbol=symbol,
                        quantity=new_qty,
                        average_cost=new_avg_price
                    )
            else:
                # New position
                if qty_change != 0:
                    self._positions[symbol] = Position(
                        symbol=symbol,
                        quantity=qty_change,
                        average_cost=order.avg_fill_price
                    )
    
    # ==================== Order Execution (Strategy Interface) ====================
    
    def buy(
        self,
        symbol: str,
        quantity: int,
        order_type: str = 'MARKET',
        limit_price: Optional[float] = None,
        stop_price: Optional[float] = None
    ) -> int:
        """
        Place a BUY order (Strategy interface).
        
        Args:
            symbol: Stock symbol
            quantity: Number of shares
            order_type: 'MARKET', 'LIMIT', or 'STOP'
            limit_price: Limit price (for LIMIT orders)
            stop_price: Stop price (for STOP orders)
        
        Returns:
            Order ID
        """
        return self._place_order(symbol, 'BUY', quantity, order_type, limit_price, stop_price)
    
    def sell(
        self,
        symbol: str,
        quantity: int,
        order_type: str = 'MARKET',
        limit_price: Optional[float] = None,
        stop_price: Optional[float] = None
    ) -> int:
        """
        Place a SELL order (Strategy interface).
        
        Args:
            symbol: Stock symbol
            quantity: Number of shares
            order_type: 'MARKET', 'LIMIT', or 'STOP'
            limit_price: Limit price (for LIMIT orders)
            stop_price: Stop price (for STOP orders)
        
        Returns:
            Order ID
        """
        return self._place_order(symbol, 'SELL', quantity, order_type, limit_price, stop_price)
    
    def close_position(self, symbol: str, order_type: str = 'MARKET') -> Optional[int]:
        """
        Close entire position (Strategy interface).
        
        Args:
            symbol: Stock symbol
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
    
    def _place_order(
        self,
        symbol: str,
        action: str,
        quantity: int,
        order_type: str,
        limit_price: Optional[float],
        stop_price: Optional[float]
    ) -> int:
        """
        Internal method to place order with TWS.
        
        Returns:
            Order ID
        """
        if not self.ready:
            raise RuntimeError("Not connected to TWS or not ready")
        
        # Get order ID
        order_id = self.next_valid_order_id
        self.next_valid_order_id += 1
        
        # Create contract
        contract = Contract()
        contract.symbol = symbol
        contract.secType = "STK"
        contract.exchange = "SMART"
        contract.currency = "USD"
        
        # Create order
        order = IBOrder()
        order.action = action
        order.totalQuantity = quantity
        order.orderType = order_type
        
        if order_type == "LIMIT" and limit_price:
            order.lmtPrice = limit_price
        elif order_type == "STOP" and stop_price:
            order.auxPrice = stop_price
        elif order_type == "STOP_LIMIT" and limit_price and stop_price:
            order.lmtPrice = limit_price
            order.auxPrice = stop_price
        
        # Track order
        pending = PendingOrder(
            order_id=order_id,
            symbol=symbol,
            action=action,
            quantity=quantity,
            order_type=order_type,
            limit_price=limit_price,
            stop_price=stop_price
        )
        
        with self._orders_lock:
            self._orders[order_id] = pending
        
        # Submit to TWS
        self.placeOrder(order_id, contract, order)
        
        logger.info(f"Placed {action} order: {symbol} x{quantity} ({order_type}) - Order ID: {order_id}")
        
        return order_id
    
    def cancel_order(self, order_id: int) -> bool:
        """
        Cancel a pending order.
        
        Args:
            order_id: Order ID to cancel
        
        Returns:
            True if cancel request sent
        """
        try:
            self.cancelOrder(order_id)
            logger.info(f"Cancellation requested for order {order_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to cancel order {order_id}: {e}")
            return False
    
    def get_order_status(self, order_id: int) -> Optional[str]:
        """Get status of an order"""
        with self._orders_lock:
            if order_id in self._orders:
                return self._orders[order_id].status
        return None
    
    def get_order(self, order_id: int) -> Optional[PendingOrder]:
        """Get order details"""
        with self._orders_lock:
            return self._orders.get(order_id)
    
    # ==================== Callbacks ====================
    
    def set_on_fill_callback(self, callback: Callable):
        """Set callback for order fills"""
        self._on_fill_callback = callback
    
    def set_on_error_callback(self, callback: Callable):
        """Set callback for errors"""
        self._on_error_callback = callback
