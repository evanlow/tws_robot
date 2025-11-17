"""
Enhanced Order Management for TWS API
Implements best practices for order handling and lifecycle management
"""

from ibapi.order import Order
from ibapi.contract import Contract
from typing import Dict, Optional, List, Callable
from enum import Enum
from dataclasses import dataclass
from datetime import datetime
import threading
import logging

class OrderStatus(Enum):
    """Order status enumeration"""
    PENDING = "PendingSubmit"
    SUBMITTED = "Submitted" 
    FILLED = "Filled"
    CANCELLED = "Cancelled"
    REJECTED = "Rejected"
    PARTIALLY_FILLED = "PartiallyFilled"
    PENDING_CANCEL = "PendingCancel"

@dataclass
class OrderRecord:
    """Track order lifecycle"""
    order_id: int
    contract: Contract
    order: Order
    status: OrderStatus
    filled: float = 0.0
    remaining: float = 0.0
    avg_fill_price: float = 0.0
    last_fill_price: float = 0.0
    parent_id: Optional[int] = None
    oca_group: Optional[str] = None
    created_at: datetime = datetime.now()
    updated_at: datetime = datetime.now()
    error_message: Optional[str] = None

class OrderManager:
    """
    Comprehensive order management following TWS API best practices:
    - Order ID management
    - Order status tracking  
    - Error handling and recovery
    - Bracket order management
    - Position tracking
    """
    
    def __init__(self, app):
        self.app = app
        self.next_order_id = 1
        self.orders: Dict[int, OrderRecord] = {}
        self.pending_orders: Dict[int, OrderRecord] = {}
        self.filled_orders: List[OrderRecord] = []
        
        # Callbacks
        self.on_order_filled: Optional[Callable] = None
        self.on_order_rejected: Optional[Callable] = None
        
        # Thread safety
        self.lock = threading.Lock()
        
        self.logger = logging.getLogger(__name__)
    
    def set_next_valid_id(self, order_id: int):
        """Set the next valid order ID from TWS"""
        with self.lock:
            self.next_order_id = order_id
            self.logger.info(f"Next valid order ID set to: {order_id}")
    
    def get_next_order_id(self) -> int:
        """Get the next available order ID"""
        with self.lock:
            order_id = self.next_order_id
            self.next_order_id += 1
            return order_id
    
    def create_market_order(self, contract: Contract, action: str, 
                          quantity: int) -> Order:
        """Create a market order"""
        order = Order()
        order.action = action.upper()
        order.totalQuantity = quantity
        order.orderType = "MKT"
        order.transmit = True
        
        return order
    
    def create_limit_order(self, contract: Contract, action: str, 
                          quantity: int, limit_price: float) -> Order:
        """Create a limit order"""
        order = Order()
        order.action = action.upper()
        order.totalQuantity = quantity
        order.orderType = "LMT"
        order.lmtPrice = limit_price
        order.transmit = True
        
        return order
    
    def create_stop_order(self, contract: Contract, action: str,
                         quantity: int, stop_price: float) -> Order:
        """Create a stop loss order"""
        order = Order()
        order.action = action.upper()
        order.totalQuantity = quantity
        order.orderType = "STP"
        order.auxPrice = stop_price
        order.transmit = True
        
        return order
    
    def create_bracket_order(self, contract: Contract, action: str, quantity: int,
                           limit_price: float, stop_price: float, 
                           target_price: float) -> List[Order]:
        """
        Create bracket order (parent + stop loss + profit target)
        Returns list of [parent_order, stop_loss_order, profit_target_order]
        """
        
        parent_order_id = self.get_next_order_id()
        stop_order_id = self.get_next_order_id()
        target_order_id = self.get_next_order_id()
        
        # Parent order
        parent = Order()
        parent.orderId = parent_order_id
        parent.action = action.upper()
        parent.totalQuantity = quantity
        parent.orderType = "LMT"
        parent.lmtPrice = limit_price
        parent.transmit = False  # Don't transmit until all orders are placed
        
        # Stop loss order (opposite action)
        stop_action = "SELL" if action.upper() == "BUY" else "BUY"
        stop_loss = Order()
        stop_loss.orderId = stop_order_id
        stop_loss.action = stop_action
        stop_loss.totalQuantity = quantity
        stop_loss.orderType = "STP"
        stop_loss.auxPrice = stop_price
        stop_loss.parentId = parent_order_id
        stop_loss.transmit = False
        
        # Profit target order (opposite action)
        profit_target = Order()
        profit_target.orderId = target_order_id
        profit_target.action = stop_action
        profit_target.totalQuantity = quantity
        profit_target.orderType = "LMT"
        profit_target.lmtPrice = target_price
        profit_target.parentId = parent_order_id
        profit_target.transmit = True  # This transmits the whole bracket
        
        return [parent, stop_loss, profit_target]
    
    def place_order(self, contract: Contract, order: Order) -> int:
        """
        Place an order with proper tracking
        Returns the order ID
        """
        
        # Get order ID if not set
        if not hasattr(order, 'orderId') or order.orderId == 0:
            order.orderId = self.get_next_order_id()
        
        # Create order record
        order_record = OrderRecord(
            order_id=order.orderId,
            contract=contract,
            order=order,
            status=OrderStatus.PENDING
        )
        
        # Store order
        with self.lock:
            self.orders[order.orderId] = order_record
            self.pending_orders[order.orderId] = order_record
        
        # Place order
        try:
            self.app.placeOrder(order.orderId, contract, order)
            self.logger.info(f"Order placed: {order.orderId} - {order.action} {order.totalQuantity} {contract.symbol}")
            
        except Exception as e:
            self.logger.error(f"Failed to place order {order.orderId}: {e}")
            # Mark as rejected
            order_record.status = OrderStatus.REJECTED
            order_record.error_message = str(e)
            
            with self.lock:
                if order.orderId in self.pending_orders:
                    del self.pending_orders[order.orderId]
        
        return order.orderId
    
    def place_bracket_order(self, contract: Contract, action: str, quantity: int,
                           limit_price: float, stop_price: float, 
                           target_price: float) -> List[int]:
        """Place bracket order and return list of order IDs"""
        
        orders = self.create_bracket_order(
            contract, action, quantity, limit_price, stop_price, target_price
        )
        
        order_ids = []
        
        # Place all orders in sequence
        for order in orders:
            order_id = self.place_order(contract, order)
            order_ids.append(order_id)
        
        self.logger.info(f"Bracket order placed: Parent {order_ids[0]}, Stop {order_ids[1]}, Target {order_ids[2]}")
        
        return order_ids
    
    def cancel_order(self, order_id: int):
        """Cancel an order"""
        with self.lock:
            if order_id in self.orders:
                order_record = self.orders[order_id]
                if order_record.status in [OrderStatus.PENDING, OrderStatus.SUBMITTED]:
                    self.app.cancelOrder(order_id)
                    order_record.status = OrderStatus.PENDING_CANCEL
                    order_record.updated_at = datetime.now()
                    
                    self.logger.info(f"Cancel request sent for order {order_id}")
                else:
                    self.logger.warning(f"Cannot cancel order {order_id} - status: {order_record.status}")
            else:
                self.logger.warning(f"Order {order_id} not found for cancellation")
    
    def on_order_status(self, order_id: int, status: str, filled: float,
                       remaining: float, avg_fill_price: float,
                       perm_id: int, parent_id: int, last_fill_price: float,
                       client_id: int, why_held: str, mkt_cap_price: float):
        """Handle order status updates from TWS"""
        
        with self.lock:
            if order_id not in self.orders:
                # This might be a manually placed order - create a record
                self.logger.warning(f"Received status for unknown order {order_id}")
                return
            
            order_record = self.orders[order_id]
            
            # Update order record
            old_status = order_record.status
            order_record.status = OrderStatus(status) if status in [s.value for s in OrderStatus] else OrderStatus.PENDING
            order_record.filled = filled
            order_record.remaining = remaining
            order_record.avg_fill_price = avg_fill_price
            order_record.last_fill_price = last_fill_price
            order_record.updated_at = datetime.now()
            
            self.logger.info(f"Order {order_id} status: {status} (Filled: {filled}, Remaining: {remaining})")
            
            # Handle status transitions
            if order_record.status == OrderStatus.FILLED:
                # Move to filled orders
                if order_id in self.pending_orders:
                    del self.pending_orders[order_id]
                self.filled_orders.append(order_record)
                
                # Callback
                if self.on_order_filled:
                    self.on_order_filled(order_record)
                    
            elif order_record.status in [OrderStatus.CANCELLED, OrderStatus.REJECTED]:
                # Remove from pending
                if order_id in self.pending_orders:
                    del self.pending_orders[order_id]
                
                if order_record.status == OrderStatus.REJECTED and self.on_order_rejected:
                    self.on_order_rejected(order_record)
    
    def on_open_order(self, order_id: int, contract: Contract, order: Order,
                     order_state):
        """Handle open order updates"""
        with self.lock:
            if order_id not in self.orders:
                # This is an existing order we didn't place
                order_record = OrderRecord(
                    order_id=order_id,
                    contract=contract,
                    order=order,
                    status=OrderStatus.SUBMITTED
                )
                self.orders[order_id] = order_record
                self.pending_orders[order_id] = order_record
                
                self.logger.info(f"Discovered existing order: {order_id}")
    
    def get_open_orders(self) -> List[OrderRecord]:
        """Get all open orders"""
        with self.lock:
            return list(self.pending_orders.values())
    
    def get_filled_orders(self) -> List[OrderRecord]:
        """Get all filled orders"""
        with self.lock:
            return self.filled_orders.copy()
    
    def get_order_by_id(self, order_id: int) -> Optional[OrderRecord]:
        """Get order record by ID"""
        with self.lock:
            return self.orders.get(order_id)
    
    def get_position_summary(self) -> Dict:
        """Get summary of positions from filled orders"""
        positions = {}
        
        with self.lock:
            for order_record in self.filled_orders:
                symbol = order_record.contract.symbol
                
                if symbol not in positions:
                    positions[symbol] = {
                        'long': 0,
                        'short': 0,
                        'net': 0,
                        'avg_price': 0,
                        'total_cost': 0
                    }
                
                filled = order_record.filled
                avg_price = order_record.avg_fill_price
                
                if order_record.order.action == 'BUY':
                    positions[symbol]['long'] += filled
                    positions[symbol]['total_cost'] += filled * avg_price
                else:
                    positions[symbol]['short'] += filled
                    positions[symbol]['total_cost'] -= filled * avg_price
                
                positions[symbol]['net'] = positions[symbol]['long'] - positions[symbol]['short']
                
                if positions[symbol]['net'] != 0:
                    positions[symbol]['avg_price'] = positions[symbol]['total_cost'] / positions[symbol]['net']
        
        return positions