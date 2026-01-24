"""
Market Data Feed - Real-time Data Pipeline

Bridges TWS real-time market data to strategy interface.
Subscribes to tick data, constructs OHLCV bars, feeds to strategies.

Features:
- Real-time bar construction (5-second TWS bars)
- Bar aggregation (5-sec → 5-min → 15-min, etc.)
- Historical buffer management
- Multiple symbol support
- Thread-safe data handling

Usage:
    feed = MarketDataFeed(tws_adapter, symbols=['AAPL', 'MSFT'], bar_size_minutes=5)
    feed.subscribe(my_strategy.on_bar)
    feed.start()

Author: TWS Robot Development Team
Date: January 24, 2026
Phase 1: MVP Live Trading
"""

# ==============================================================================
# API VERIFICATION CHECKLIST ✓
# ==============================================================================
# Date: 2026-01-24
# Task: Create real-time market data feed for live trading
#
# TWS API Methods (from ibapi library):
# 1. reqRealTimeBars - Request 5-second bars
#    Tool: read_file of ibapi documentation
#    Signature: reqRealTimeBars(reqId, contract, barSize, whatToShow, useRTH, realTimeBarsOptions)
#    Verified: ✓ (Standard IBAPI method)
#
# 2. PaperTradingAdapter (our wrapper)
#    Tool: read_file execution/paper_adapter.py:53-150
#    Found: class PaperTradingAdapter(EWrapper, EClient)
#    Verified: ✓
#
# VERIFICATION COMPLETE: ✓ APIs confirmed
# ==============================================================================

import logging
import threading
from typing import Dict, List, Callable, Optional
from datetime import datetime, timedelta
from collections import deque
from dataclasses import dataclass
import time

from ibapi.contract import Contract

logger = logging.getLogger(__name__)


@dataclass
class TickData:
    """Single tick of market data"""
    timestamp: datetime
    price: float
    volume: int
    
@dataclass
class BarData:
    """OHLCV bar data"""
    symbol: str
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: int


class BarAggregator:
    """
    Aggregates 5-second TWS bars into larger timeframes.
    
    Example: 5-second bars → 5-minute bars (60 bars aggregated)
    """
    
    def __init__(self, symbol: str, bar_size_minutes: int = 5):
        """
        Initialize bar aggregator.
        
        Args:
            symbol: Stock symbol
            bar_size_minutes: Target bar size in minutes (default: 5)
        """
        self.symbol = symbol
        self.bar_size_minutes = bar_size_minutes
        self.bars_per_period = bar_size_minutes * 12  # 12 five-second bars per minute
        
        self.current_bars: List[BarData] = []
        self.last_complete_bar: Optional[BarData] = None
        
        logger.info(f"BarAggregator created: {symbol}, {bar_size_minutes}min bars")
    
    def add_bar(self, bar: BarData) -> Optional[BarData]:
        """
        Add 5-second bar, return aggregated bar if period complete.
        
        Args:
            bar: 5-second bar from TWS
        
        Returns:
            Aggregated bar if period complete, None otherwise
        """
        self.current_bars.append(bar)
        
        # Check if we have enough bars for one period
        if len(self.current_bars) >= self.bars_per_period:
            aggregated = self._aggregate_bars()
            self.current_bars = []  # Reset for next period
            self.last_complete_bar = aggregated
            return aggregated
        
        return None
    
    def _aggregate_bars(self) -> BarData:
        """Aggregate current bars into single OHLCV bar"""
        if not self.current_bars:
            raise ValueError("No bars to aggregate")
        
        return BarData(
            symbol=self.symbol,
            timestamp=self.current_bars[-1].timestamp,  # Use last bar's timestamp
            open=self.current_bars[0].open,
            high=max(bar.high for bar in self.current_bars),
            low=min(bar.low for bar in self.current_bars),
            close=self.current_bars[-1].close,
            volume=sum(bar.volume for bar in self.current_bars)
        )


class MarketDataFeed:
    """
    Real-time market data feed for live trading.
    
    Subscribes to TWS real-time bars, aggregates to strategy timeframe,
    maintains historical buffer, and notifies subscribers.
    """
    
    def __init__(
        self,
        tws_adapter,
        symbols: List[str],
        bar_size_minutes: int = 5,
        buffer_size: int = 100
    ):
        """
        Initialize market data feed.
        
        Args:
            tws_adapter: PaperTradingAdapter instance
            symbols: List of symbols to subscribe
            bar_size_minutes: Bar size in minutes (default: 5)
            buffer_size: Number of historical bars to keep
        """
        self.tws_adapter = tws_adapter
        self.symbols = symbols
        self.bar_size_minutes = bar_size_minutes
        self.buffer_size = buffer_size
        
        # Bar aggregators (one per symbol)
        self.aggregators: Dict[str, BarAggregator] = {}
        for symbol in symbols:
            self.aggregators[symbol] = BarAggregator(symbol, bar_size_minutes)
        
        # Historical buffers (symbol -> deque of BarData)
        self.buffers: Dict[str, deque] = {}
        for symbol in symbols:
            self.buffers[symbol] = deque(maxlen=buffer_size)
        
        # Subscribers (callbacks to notify)
        self.subscribers: List[Callable[[str, BarData], None]] = []
        
        # Request ID tracking
        self.next_req_id = 5000
        self.req_id_to_symbol: Dict[int, str] = {}
        
        # Thread safety
        self._lock = threading.Lock()
        
        # State
        self.running = False
        
        logger.info(f"MarketDataFeed initialized: {symbols}, {bar_size_minutes}min bars")
    
    def subscribe(self, callback: Callable[[str, BarData], None]):
        """
        Subscribe to receive bar data.
        
        Args:
            callback: Function(symbol: str, bar: BarData) to call on new bars
        """
        with self._lock:
            self.subscribers.append(callback)
        logger.info(f"Subscriber added (total: {len(self.subscribers)})")
    
    def start(self):
        """Start receiving market data from TWS"""
        if self.running:
            logger.warning("MarketDataFeed already running")
            return
        
        logger.info("Starting market data feed...")
        
        # Register callback with TWS adapter to receive bars
        self.tws_adapter.realtimeBar = self._on_realtime_bar
        
        # Request real-time bars for each symbol
        for symbol in self.symbols:
            self._request_realtime_bars(symbol)
        
        self.running = True
        logger.info("✅ Market data feed started")
    
    def stop(self):
        """Stop receiving market data"""
        if not self.running:
            return
        
        logger.info("Stopping market data feed...")
        
        # Cancel all real-time bar subscriptions
        for req_id, symbol in self.req_id_to_symbol.items():
            try:
                self.tws_adapter.cancelRealTimeBars(req_id)
                logger.info(f"Cancelled real-time bars for {symbol}")
            except Exception as e:
                logger.error(f"Error cancelling bars for {symbol}: {e}")
        
        self.running = False
        logger.info("✅ Market data feed stopped")
    
    def _request_realtime_bars(self, symbol: str):
        """
        Request 5-second real-time bars from TWS.
        
        Args:
            symbol: Stock symbol
        """
        req_id = self.next_req_id
        self.next_req_id += 1
        
        with self._lock:
            self.req_id_to_symbol[req_id] = symbol
        
        # Create contract
        contract = Contract()
        contract.symbol = symbol
        contract.secType = "STK"
        contract.exchange = "SMART"
        contract.currency = "USD"
        
        # Request 5-second bars
        # whatToShow: "TRADES" for last price, "MIDPOINT" for bid/ask midpoint
        self.tws_adapter.reqRealTimeBars(
            reqId=req_id,
            contract=contract,
            barSize=5,  # 5 seconds (only option)
            whatToShow="TRADES",
            useRTH=False,  # False = include pre/post market
            realTimeBarsOptions=[]
        )
        
        logger.info(f"Requested real-time bars for {symbol} (req_id={req_id})")
    
    def _on_realtime_bar(
        self,
        reqId: int,
        time: int,
        open_: float,
        high: float,
        low: float,
        close: float,
        volume: int,
        wap: float,
        count: int
    ):
        """
        Callback when 5-second bar arrives from TWS.
        
        This is called by TWS adapter thread.
        """
        # Get symbol for this request ID
        with self._lock:
            symbol = self.req_id_to_symbol.get(reqId)
        
        if not symbol:
            logger.warning(f"Received bar for unknown reqId: {reqId}")
            return
        
        # Create bar data
        bar = BarData(
            symbol=symbol,
            timestamp=datetime.fromtimestamp(time),
            open=open_,
            high=high,
            low=low,
            close=close,
            volume=volume
        )
        
        # Add to aggregator
        aggregator = self.aggregators[symbol]
        aggregated_bar = aggregator.add_bar(bar)
        
        # If aggregation complete, notify subscribers
        if aggregated_bar:
            logger.debug(f"Bar complete: {symbol} @ {aggregated_bar.timestamp} "
                        f"O:{aggregated_bar.open} H:{aggregated_bar.high} "
                        f"L:{aggregated_bar.low} C:{aggregated_bar.close} V:{aggregated_bar.volume}")
            
            # Add to buffer
            self.buffers[symbol].append(aggregated_bar)
            
            # Notify all subscribers
            for subscriber in self.subscribers:
                try:
                    subscriber(symbol, aggregated_bar)
                except Exception as e:
                    logger.error(f"Error in subscriber callback: {e}", exc_info=True)
    
    def get_historical_bars(self, symbol: str, count: int = 20) -> List[BarData]:
        """
        Get historical bars from buffer.
        
        Args:
            symbol: Stock symbol
            count: Number of bars to return (default: 20)
        
        Returns:
            List of recent bars (oldest first)
        """
        with self._lock:
            buffer = self.buffers.get(symbol, deque())
            return list(buffer)[-count:] if buffer else []
    
    def get_latest_bar(self, symbol: str) -> Optional[BarData]:
        """
        Get most recent bar.
        
        Args:
            symbol: Stock symbol
        
        Returns:
            Latest bar or None
        """
        with self._lock:
            buffer = self.buffers.get(symbol, deque())
            return buffer[-1] if buffer else None


# Example usage (for testing)
if __name__ == '__main__':
    print("MarketDataFeed - Manual testing")
    print("This module requires running TWS and PaperTradingAdapter")
    print("Use run_live.py to test in full integration")
