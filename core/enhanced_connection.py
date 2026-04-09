"""
Enhanced TWS Connection Management
Implements best practices from IB documentation for reliable connections
"""

import time
import threading
from typing import Optional, Callable
from ibapi.client import EClient
from ibapi.wrapper import EWrapper
import logging

class EnhancedTWSConnection:
    """
    Enhanced connection manager following TWS API best practices:
    - Proper connection state management
    - Automatic reconnection logic
    - Connection health monitoring
    - Graceful shutdown procedures
    """
    
    def __init__(self, wrapper_class, host: str = "127.0.0.1", 
                 port: int = 7497, client_id: int = 0):
        self.host = host
        self.port = port
        self.client_id = client_id
        
        self.app = wrapper_class()
        self.app.connection_manager = self
        
        # Connection state
        self.connection_established = False
        self.next_valid_id_received = False
        self.connection_attempts = 0
        self.max_connection_attempts = 3
        
        # Threading
        self.api_thread = None
        self.should_reconnect = True
        
        # Callbacks
        self.on_connection_established: Optional[Callable] = None
        self.on_connection_lost: Optional[Callable] = None
        
        self.logger = logging.getLogger(__name__)
    
    def connect(self, timeout: int = 10) -> bool:
        """
        Establish connection to TWS/IB Gateway with proper error handling
        Returns True if connection successful
        """
        try:
            self.logger.info(f"Connecting to TWS at {self.host}:{self.port} (Client ID: {self.client_id})")
            
            # Reset connection state
            self.connection_established = False
            self.next_valid_id_received = False
            
            # Attempt connection
            self.app.connect(self.host, self.port, self.client_id)
            
            # Start API message processing thread
            self.api_thread = threading.Thread(target=self.app.run, daemon=True)
            self.api_thread.start()
            
            # Wait for connection establishment with timeout
            start_time = time.time()
            while (not self.connection_established or not self.next_valid_id_received) and \
                  (time.time() - start_time) < timeout:
                time.sleep(0.1)
            
            if self.connection_established and self.next_valid_id_received:
                self.logger.info("TWS connection established successfully")
                self.connection_attempts = 0
                if self.on_connection_established:
                    self.on_connection_established()
                return True
            else:
                self.logger.error(f"Connection timeout after {timeout} seconds")
                self.disconnect()
                return False
                
        except Exception as e:
            self.logger.error(f"Connection failed: {e}")
            self.connection_attempts += 1
            return False
    
    def disconnect(self):
        """Gracefully disconnect from TWS"""
        try:
            self.logger.info("Disconnecting from TWS...")
            self.should_reconnect = False
            
            if self.app.isConnected():
                self.app.disconnect()
            
            # Wait for clean disconnection
            max_wait = 5
            wait_time = 0
            while self.app.isConnected() and wait_time < max_wait:
                time.sleep(0.1)
                wait_time += 0.1
            
            self.connection_established = False
            self.next_valid_id_received = False
            
            self.logger.info("Disconnected from TWS")
            
        except Exception as e:
            self.logger.error(f"Error during disconnect: {e}")
    
    def attempt_reconnection(self) -> bool:
        """
        Attempt to reconnect with exponential backoff
        Called automatically when connection is lost
        """
        if not self.should_reconnect:
            return False
        
        if self.connection_attempts >= self.max_connection_attempts:
            self.logger.error(f"Max reconnection attempts ({self.max_connection_attempts}) exceeded")
            return False
        
        self.connection_attempts += 1
        wait_time = min(2 ** self.connection_attempts, 30)  # Exponential backoff, max 30s
        
        self.logger.info(f"Reconnection attempt {self.connection_attempts} in {wait_time} seconds...")
        time.sleep(wait_time)
        
        return self.connect()
    
    def on_connection_established_event(self):
        """Called when connection is established"""
        self.connection_established = True
        self.logger.info("Connection established event received")
    
    def on_next_valid_id_event(self, order_id: int):
        """Called when next valid ID is received - indicates full connection"""
        self.next_valid_id_received = True
        self.logger.info(f"Next valid order ID received: {order_id}")
    
    def on_connection_lost_event(self, error_code: int):
        """Called when connection is lost"""
        self.connection_established = False
        self.next_valid_id_received = False
        
        self.logger.warning(f"Connection lost (Error: {error_code})")
        
        if self.on_connection_lost:
            self.on_connection_lost(error_code)
        
        # Attempt automatic reconnection for recoverable errors
        if error_code in [1100, 1101, 1102, 502, 503, 504] and self.should_reconnect:
            threading.Thread(target=self.attempt_reconnection, daemon=True).start()
    
    def is_connected(self) -> bool:
        """Check if fully connected and ready for requests"""
        return self.connection_established and self.next_valid_id_received and self.app.isConnected()
    
    def wait_for_connection(self, timeout: int = 30) -> bool:
        """Wait for connection to be fully established"""
        start_time = time.time()
        while not self.is_connected() and (time.time() - start_time) < timeout:
            time.sleep(0.1)
        return self.is_connected()

class EnhancedTradeApp(EWrapper, EClient):
    """
    Enhanced Trade App with proper connection management
    """
    
    def __init__(self):
        EClient.__init__(self, self)
        
        # Connection management
        self.connection_manager: Optional[EnhancedTWSConnection] = None
        
        # Enhanced error tracking
        self.error_counts = {}
        self.last_errors = {}
        
        self.logger = logging.getLogger(__name__)
    
    def connectAck(self):
        """Connection acknowledgment"""
        self.logger.info("TWS connection acknowledgment received")
        if self.connection_manager:
            self.connection_manager.on_connection_established_event()
    
    def nextValidId(self, orderId: int):
        """Next valid order ID received"""
        self.logger.info(f"Next valid order ID: {orderId}")
        if self.connection_manager:
            self.connection_manager.on_next_valid_id_event(orderId)
    
    def connectionClosed(self):
        """Connection closed"""
        self.logger.warning("TWS connection closed")
        if self.connection_manager:
            self.connection_manager.on_connection_lost_event(0)
    
    def error(self, reqId, errorTime, errorCode: int, errorString: str, advancedOrderRejectJson=""):
        """Enhanced error handling with categorization"""
        # Track error frequency
        self.error_counts[errorCode] = self.error_counts.get(errorCode, 0) + 1
        self.last_errors[errorCode] = (time.time(), errorString)
        
        # Categorize errors
        if errorCode in [502, 503, 504]:
            # Connection errors
            self.logger.error(f"Connection Error {errorCode}: {errorString}")
            if self.connection_manager:
                self.connection_manager.on_connection_lost_event(errorCode)
                
        elif errorCode in [1100, 1101, 1102, 1300]:
            # System messages about connectivity
            self.logger.warning(f"System Message {errorCode}: {errorString}")
            if errorCode in [1100, 1300] and self.connection_manager:
                self.connection_manager.on_connection_lost_event(errorCode)
                
        elif errorCode == 100:
            # Rate limiting
            self.logger.error(f"Rate Limit Exceeded: {errorString}")
            
        elif errorCode in [200, 162, 354, 10167]:
            # Market data issues
            self.logger.warning(f"Market Data Issue (ReqId {reqId}): {errorString}")
            
        elif errorCode in [2104, 2106, 2158]:
            # Informational messages
            self.logger.info(f"Market Data Farm: {errorString}")
            
        else:
            # General errors
            self.logger.error(f"Error {errorCode} (ReqId {reqId}): {errorString}")
    
    def get_error_summary(self) -> dict:
        """Get summary of recent errors for monitoring"""
        current_time = time.time()
        recent_errors = {}
        
        for error_code, (timestamp, message) in self.last_errors.items():
            if current_time - timestamp < 3600:  # Last hour
                recent_errors[error_code] = {
                    'message': message,
                    'count': self.error_counts[error_code],
                    'last_seen': timestamp
                }
        
        return recent_errors

# Example usage
def create_enhanced_connection(config: dict) -> EnhancedTWSConnection:
    """Create and configure enhanced connection"""
    
    def wrapper_factory():
        return EnhancedTradeApp()
    
    connection = EnhancedTWSConnection(
        wrapper_class=wrapper_factory,
        host=config['host'],
        port=config['port'],
        client_id=config['client_id']
    )
    
    # Set up connection callbacks
    def on_connected():
        logging.info("Successfully connected to TWS")
    
    def on_disconnected(error_code):
        logging.warning(f"Lost connection to TWS (Error: {error_code})")
    
    connection.on_connection_established = on_connected
    connection.on_connection_lost = on_disconnected
    
    return connection