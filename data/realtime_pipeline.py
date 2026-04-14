"""
Real-time Market Data Pipeline

Streams market data from TWS and converts to backtest-compatible format.
Distributes data to multiple strategies efficiently.

Author: TWS Robot Development Team
Date: November 22, 2025
Sprint 1 Task 3
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Callable, Set
from threading import Lock
from decimal import Decimal

from ibapi.client import EClient
from ibapi.wrapper import EWrapper
from ibapi.contract import Contract

from backtest.data_models import Bar, MarketData, TimeFrame


logger = logging.getLogger(__name__)


@dataclass
class DataSubscription:
    """
    Represents a strategy's subscription to market data.
    
    Attributes:
        strategy_id: Unique identifier for the strategy
        symbols: List of symbols to subscribe to
        callback: Function to call when new data arrives (receives MarketData)
        timeframe: Bar timeframe (MINUTE_1, MINUTE_5, etc.)
        active: Whether subscription is active
        include_sentiment: When True, each MarketData delivered to the callback
            will include a ``sentiment`` key in its ``extra`` dict containing
            a float score in [-1.0, 1.0].  Scores are fetched via
            ``data.sentiment_feed.fetch_sentiment`` and cached per symbol.
    """
    strategy_id: str
    symbols: List[str]
    callback: Callable[[MarketData], None]
    timeframe: TimeFrame = TimeFrame.MINUTE_1
    active: bool = True
    include_sentiment: bool = False


@dataclass
class BarBuffer:
    """
    Buffers tick data to form complete bars.
    
    Tracks OHLCV for each symbol and emits Bar when complete.
    """
    symbol: str
    open: Optional[float] = None
    high: Optional[float] = None
    low: Optional[float] = None
    close: Optional[float] = None
    volume: int = 0
    bar_start: Optional[datetime] = None
    last_update: Optional[datetime] = None
    
    def update_price(self, price: float, size: int, timestamp: datetime):
        """Update buffer with new tick"""
        if self.open is None:
            self.open = price
            self.bar_start = timestamp
        
        if self.high is None or price > self.high:
            self.high = price
        
        if self.low is None or price < self.low:
            self.low = price
        
        self.close = price
        self.volume += size
        self.last_update = timestamp
    
    def is_complete(self) -> bool:
        """Check if buffer has all OHLCV components"""
        return all([
            self.open is not None,
            self.high is not None,
            self.low is not None,
            self.close is not None,
            self.volume > 0
        ])
    
    def to_bar(self, timeframe: TimeFrame) -> Bar:
        """Convert buffer to Bar object"""
        if not self.is_complete():
            raise ValueError(f"Cannot create Bar - buffer incomplete for {self.symbol}")
        
        return Bar(
            timestamp=self.bar_start or self.last_update,
            symbol=self.symbol,
            open=self.open,
            high=self.high,
            low=self.low,
            close=self.close,
            volume=self.volume,
            timeframe=timeframe
        )
    
    def reset(self):
        """Reset buffer for next bar"""
        self.open = None
        self.high = None
        self.low = None
        self.close = None
        self.volume = 0
        self.bar_start = None
        self.last_update = None


class RealtimeDataManager(EWrapper, EClient):
    """
    Manages real-time market data streaming from TWS.
    
    Features:
    - Subscribe/unsubscribe to symbols
    - Convert TWS ticks to backtest Bar format
    - Distribute data to multiple strategies
    - Handle reconnection and error recovery
    - Data quality monitoring
    
    Usage:
        manager = RealtimeDataManager(host="127.0.0.1", port=7497)
        manager.connect_and_run()
        
        subscription = DataSubscription(
            strategy_id="ma_cross_1",
            symbols=["AAPL", "MSFT"],
            callback=strategy.on_bar
        )
        manager.subscribe(subscription)
    """
    
    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 7497,
        client_id: int = 200
    ):
        """
        Initialize real-time data manager.
        
        Args:
            host: TWS hostname
            port: TWS port (7497 for paper, 7496 for live)
            client_id: TWS client ID (unique per connection)
        """
        EClient.__init__(self, self)
        
        self.host = host
        self.port = port
        self.client_id = client_id
        
        # Connection state
        self.connected = False
        self.ready = False
        self.next_valid_order_id = None
        
        # Subscriptions: strategy_id -> DataSubscription
        self._subscriptions: Dict[str, DataSubscription] = {}
        self._subscriptions_lock = Lock()
        
        # Symbol tracking: symbol -> req_id
        self._symbol_to_req_id: Dict[str, int] = {}
        self._req_id_to_symbol: Dict[int, str] = {}
        self._next_req_id = 1
        
        # Bar buffers: symbol -> BarBuffer
        self._bar_buffers: Dict[str, BarBuffer] = {}
        self._bar_buffers_lock = Lock()
        
        # Last prices for tick data: symbol -> price
        self._last_prices: Dict[str, float] = {}
        self._last_sizes: Dict[str, int] = {}
        
        # Connection thread
        self._conn_thread = None
        
        logger.info(f"Initialized RealtimeDataManager (port={port}, client_id={client_id})")
    
    # ==================== Connection Management ====================
    
    def connectAck(self):
        """EWrapper callback: Connection acknowledged"""
        self.connected = True
        logger.info("TWS connection acknowledged")
    
    def nextValidId(self, orderId: int):
        """EWrapper callback: Receive next valid order ID (ready signal)"""
        self.next_valid_order_id = orderId
        self.ready = True
        logger.info(f"Ready to stream data - next valid ID: {orderId}")
    
    def connect_and_run(self, timeout: int = 10) -> bool:
        """
        Connect to TWS and start message loop in background thread.
        
        Args:
            timeout: Connection timeout in seconds
        
        Returns:
            True if connected successfully
        """
        try:
            self.connect(self.host, self.port, self.client_id)
            
            # Start message loop in background thread
            import threading
            self._conn_thread = threading.Thread(target=self.run, daemon=True)
            self._conn_thread.start()
            
            # Wait for ready signal
            import time
            elapsed = 0
            while not self.ready and elapsed < timeout:
                time.sleep(0.1)
                elapsed += 0.1
            
            if not self.ready:
                logger.error(f"Connection timeout after {timeout}s")
                return False
            
            logger.info("Connection established and ready")
            return True
            
        except Exception as e:
            logger.error(f"Connection error: {e}")
            return False
    
    def disconnect_gracefully(self):
        """Disconnect from TWS gracefully"""
        logger.info("Disconnecting from TWS")
        
        # Cancel all market data subscriptions
        with self._subscriptions_lock:
            for req_id in list(self._req_id_to_symbol.keys()):
                self.cancelMktData(req_id)
        
        self.disconnect()
        self.connected = False
        self.ready = False
    
    # ==================== EWrapper Callbacks ====================
    
    def error(self, reqId: int, errorCode: int, errorString: str):
        """Handle TWS errors"""
        # Filter informational messages (2100-2199 range)
        if 2100 <= errorCode <= 2199:
            logger.info(f"TWS Info [{errorCode}]: {errorString}")
            return
        
        logger.error(f"TWS Error [{errorCode}]: {errorString} (reqId={reqId})")
        
        # Handle specific errors
        if errorCode == 354:  # Requested market data is not subscribed
            symbol = self._req_id_to_symbol.get(reqId)
            if symbol:
                logger.warning(f"Market data subscription failed for {symbol}")
    
    def tickPrice(self, reqId: int, tickType: int, price: float, attrib):
        """
        EWrapper callback: Receive price tick.
        
        TickTypes:
        1 = BID, 2 = ASK, 4 = LAST, 6 = HIGH, 7 = LOW, 9 = CLOSE
        """
        symbol = self._req_id_to_symbol.get(reqId)
        if not symbol:
            return
        
        # Track last price for LAST ticks
        if tickType == 4:  # LAST
            self._last_prices[symbol] = price
            
            # Update bar buffer with last trade
            timestamp = datetime.now()
            size = self._last_sizes.get(symbol, 100)  # Default 100 if size not yet received
            
            with self._bar_buffers_lock:
                if symbol not in self._bar_buffers:
                    self._bar_buffers[symbol] = BarBuffer(symbol=symbol)
                
                self._bar_buffers[symbol].update_price(price, size, timestamp)
                
                # Check if bar is complete and emit
                if self._bar_buffers[symbol].is_complete():
                    self._emit_bar(symbol)
    
    def tickSize(self, reqId: int, tickType: int, size: Decimal):
        """
        EWrapper callback: Receive size tick.
        
        TickTypes:
        0 = BID_SIZE, 3 = ASK_SIZE, 5 = LAST_SIZE, 8 = VOLUME
        """
        symbol = self._req_id_to_symbol.get(reqId)
        if not symbol:
            return
        
        # Track last size for LAST_SIZE ticks
        if tickType == 5:  # LAST_SIZE
            self._last_sizes[symbol] = int(size)
    
    def tickString(self, reqId: int, tickType: int, value: str):
        """EWrapper callback: Receive string tick (timestamp, etc.)"""
        pass
    
    def tickGeneric(self, reqId: int, tickType: int, value: float):
        """EWrapper callback: Receive generic tick"""
        pass
    
    # ==================== Subscription Management ====================
    
    def subscribe(self, subscription: DataSubscription) -> bool:
        """
        Subscribe a strategy to market data.
        
        Args:
            subscription: DataSubscription object
        
        Returns:
            True if subscription successful
        """
        if not self.ready:
            logger.error("Cannot subscribe - not connected to TWS")
            return False
        
        with self._subscriptions_lock:
            # Store subscription
            self._subscriptions[subscription.strategy_id] = subscription
            
            # Request market data for each symbol
            for symbol in subscription.symbols:
                if symbol not in self._symbol_to_req_id:
                    # New symbol - request market data
                    req_id = self._next_req_id
                    self._next_req_id += 1
                    
                    # Create contract
                    contract = Contract()
                    contract.symbol = symbol
                    contract.secType = "STK"
                    contract.exchange = "SMART"
                    contract.currency = "USD"
                    
                    # Request market data (live tick-by-tick)
                    self.reqMktData(req_id, contract, "", False, False, [])
                    
                    # Track mapping
                    self._symbol_to_req_id[symbol] = req_id
                    self._req_id_to_symbol[req_id] = symbol
                    
                    logger.info(f"Subscribed to {symbol} market data (req_id={req_id})")
        
        logger.info(f"Strategy '{subscription.strategy_id}' subscribed to {len(subscription.symbols)} symbols")
        return True
    
    def unsubscribe(self, strategy_id: str) -> bool:
        """
        Unsubscribe a strategy from market data.
        
        Args:
            strategy_id: Strategy identifier
        
        Returns:
            True if unsubscribed successfully
        """
        with self._subscriptions_lock:
            if strategy_id not in self._subscriptions:
                logger.warning(f"Strategy '{strategy_id}' not found in subscriptions")
                return False
            
            subscription = self._subscriptions[strategy_id]
            subscription.active = False
            
            # Check if any other strategies are using these symbols
            symbols_in_use = set()
            for sub in self._subscriptions.values():
                if sub.active and sub.strategy_id != strategy_id:
                    symbols_in_use.update(sub.symbols)
            
            # Cancel subscriptions for symbols no longer needed
            for symbol in subscription.symbols:
                if symbol not in symbols_in_use and symbol in self._symbol_to_req_id:
                    req_id = self._symbol_to_req_id[symbol]
                    self.cancelMktData(req_id)
                    
                    del self._symbol_to_req_id[symbol]
                    del self._req_id_to_symbol[req_id]
                    
                    logger.info(f"Cancelled {symbol} market data subscription")
            
            del self._subscriptions[strategy_id]
        
        logger.info(f"Strategy '{strategy_id}' unsubscribed")
        return True
    
    def get_subscriptions(self) -> List[DataSubscription]:
        """Get list of all active subscriptions"""
        with self._subscriptions_lock:
            return [sub for sub in self._subscriptions.values() if sub.active]
    
    def get_symbols(self) -> Set[str]:
        """Get set of all subscribed symbols"""
        return set(self._symbol_to_req_id.keys())
    
    # ==================== Data Distribution ====================
    
    def _emit_bar(self, symbol: str):
        """
        Emit completed bar to all subscribed strategies.
        
        Args:
            symbol: Symbol for which bar is complete
        """
        with self._bar_buffers_lock:
            if symbol not in self._bar_buffers:
                return
            
            buffer = self._bar_buffers[symbol]
            if not buffer.is_complete():
                return
            
            # Create Bar object
            try:
                bar = buffer.to_bar(TimeFrame.MINUTE_1)
            except ValueError as e:
                logger.error(f"Failed to create bar for {symbol}: {e}")
                return
            
            # Reset buffer for next bar
            buffer.reset()
        
        # Create MarketData container
        market_data = MarketData(
            timestamp=bar.timestamp,
            bars={symbol: bar}
        )
        
        # Distribute to subscribed strategies
        with self._subscriptions_lock:
            for subscription in self._subscriptions.values():
                if subscription.active and symbol in subscription.symbols:
                    try:
                        # Attach sentiment score when the subscription requests it
                        if subscription.include_sentiment:
                            try:
                                from data.sentiment_feed import fetch_sentiment
                                market_data.sentiment = fetch_sentiment(symbol)
                            except Exception as sent_exc:
                                logger.warning(
                                    "Sentiment fetch failed for %s: %s", symbol, sent_exc
                                )
                                market_data.sentiment = 0.0
                        subscription.callback(market_data)
                        logger.debug(f"Delivered {symbol} bar to strategy '{subscription.strategy_id}'")
                    except Exception as e:
                        logger.error(f"Error delivering data to '{subscription.strategy_id}': {e}")
    
    def get_last_price(self, symbol: str) -> Optional[float]:
        """Get last traded price for a symbol"""
        return self._last_prices.get(symbol)
    
    def get_last_prices(self) -> Dict[str, float]:
        """Get last traded prices for all symbols"""
        return self._last_prices.copy()
    
    # ==================== Data Quality ====================
    
    def get_data_quality_stats(self) -> Dict[str, dict]:
        """
        Get data quality statistics for each symbol.
        
        Returns:
            Dict of symbol -> stats (last_update, buffer_status, etc.)
        """
        stats = {}
        
        with self._bar_buffers_lock:
            for symbol, buffer in self._bar_buffers.items():
                stats[symbol] = {
                    'last_update': buffer.last_update,
                    'complete': buffer.is_complete(),
                    'volume': buffer.volume,
                    'last_price': self._last_prices.get(symbol)
                }
        
        return stats
