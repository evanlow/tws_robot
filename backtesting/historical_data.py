"""
Historical data management for backtesting.

Fetches, caches, and provides historical market data for strategy backtesting.
"""

import logging
import pandas as pd
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from pathlib import Path
import pickle
import hashlib
from dataclasses import dataclass

from ibapi.contract import Contract


logger = logging.getLogger(__name__)


@dataclass
class BarData:
    """
    Single bar of market data.
    
    Attributes:
        timestamp: Bar timestamp
        open: Opening price
        high: High price
        low: Low price
        close: Closing price
        volume: Trading volume
        bar_count: Number of trades (if available)
        wap: Weighted average price (if available)
    """
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: int
    bar_count: int = 0
    wap: float = 0.0
    
    def to_dict(self) -> dict:
        """Convert to dictionary"""
        return {
            'timestamp': self.timestamp,
            'open': self.open,
            'high': self.high,
            'low': self.low,
            'close': self.close,
            'volume': self.volume,
            'bar_count': self.bar_count,
            'wap': self.wap
        }


class HistoricalDataManager:
    """
    Manages historical market data for backtesting.
    
    Features:
    - Fetch historical data from IBKR API
    - Cache data locally to avoid repeated API calls
    - Support multiple timeframes (1min, 5min, 1hour, 1day)
    - Data validation and cleaning
    - DataFrame conversion for analysis
    
    Example:
        >>> manager = HistoricalDataManager(ib_client, cache_dir="data/cache")
        >>> 
        >>> # Fetch historical data
        >>> bars = manager.get_historical_data(
        ...     symbol="AAPL",
        ...     start_date=datetime(2024, 1, 1),
        ...     end_date=datetime(2024, 12, 31),
        ...     bar_size="1 day"
        ... )
        >>> 
        >>> # Convert to DataFrame for analysis
        >>> df = manager.bars_to_dataframe(bars)
    """
    
    def __init__(self, ib_client=None, cache_dir: str = "data/historical_cache"):
        """
        Initialize historical data manager.
        
        Args:
            ib_client: Interactive Brokers client (optional for cached data)
            cache_dir: Directory for caching historical data
        """
        self.ib_client = ib_client
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        
        # Data cache (in-memory)
        self._data_cache: Dict[str, List[BarData]] = {}
        
        logger.info(f"HistoricalDataManager initialized with cache: {self.cache_dir}")
    
    def get_historical_data(
        self,
        symbol: str,
        start_date: datetime,
        end_date: datetime,
        bar_size: str = "1 day",
        use_cache: bool = True
    ) -> List[BarData]:
        """
        Get historical data for a symbol.
        
        Args:
            symbol: Trading symbol (e.g., "AAPL")
            start_date: Start date for historical data
            end_date: End date for historical data
            bar_size: Bar size (e.g., "1 min", "5 mins", "1 hour", "1 day")
            use_cache: Whether to use cached data if available
            
        Returns:
            List of BarData objects
            
        Raises:
            ValueError: If dates are invalid or bar_size unsupported
        """
        # Validate dates
        if end_date <= start_date:
            raise ValueError("end_date must be after start_date")
        
        # Generate cache key
        cache_key = self._generate_cache_key(symbol, start_date, end_date, bar_size)
        
        # Check in-memory cache
        if use_cache and cache_key in self._data_cache:
            logger.debug(f"Using in-memory cache for {symbol}")
            return self._data_cache[cache_key]
        
        # Check file cache
        if use_cache:
            cached_data = self._load_from_cache(cache_key)
            if cached_data is not None:
                logger.info(f"Loaded {len(cached_data)} bars from cache for {symbol}")
                self._data_cache[cache_key] = cached_data
                return cached_data
        
        # Fetch from IBKR API
        logger.info(f"Fetching historical data for {symbol} from {start_date} to {end_date}")
        bars = self._fetch_from_api(symbol, start_date, end_date, bar_size)
        
        # Cache the data
        if bars:
            self._save_to_cache(cache_key, bars)
            self._data_cache[cache_key] = bars
            logger.info(f"Cached {len(bars)} bars for {symbol}")
        
        return bars
    
    def _fetch_from_api(
        self,
        symbol: str,
        start_date: datetime,
        end_date: datetime,
        bar_size: str
    ) -> List[BarData]:
        """
        Fetch historical data from IBKR API.
        
        Args:
            symbol: Trading symbol
            start_date: Start date
            end_date: End date
            bar_size: Bar size
            
        Returns:
            List of BarData objects
        """
        if self.ib_client is None:
            logger.warning("No IB client available, returning empty data")
            return []
        
        # Create contract
        contract = Contract()
        contract.symbol = symbol
        contract.secType = "STK"
        contract.exchange = "SMART"
        contract.currency = "USD"
        
        # Calculate duration
        duration_days = (end_date - start_date).days
        
        # Format duration string for IBKR
        if duration_days <= 1:
            duration_str = f"{duration_days} D"
        elif duration_days <= 7:
            duration_str = f"{duration_days} D"
        elif duration_days <= 30:
            duration_str = f"{duration_days} D"
        elif duration_days <= 365:
            duration_str = f"{int(duration_days / 30)} M"
        else:
            duration_str = f"{int(duration_days / 365)} Y"
        
        try:
            # Request historical data from IBKR
            # Note: This is a placeholder - actual implementation would use
            # the IBKR API's reqHistoricalData method with proper callbacks
            logger.info(f"API call: reqHistoricalData({symbol}, end={end_date}, "
                       f"duration={duration_str}, barSize={bar_size})")
            
            # TODO: Implement actual IBKR API call
            # For now, return empty list
            bars = []
            
            return bars
        
        except Exception as e:
            logger.error(f"Failed to fetch historical data: {e}")
            return []
    
    def _generate_cache_key(
        self,
        symbol: str,
        start_date: datetime,
        end_date: datetime,
        bar_size: str
    ) -> str:
        """
        Generate cache key for historical data request.
        
        Args:
            symbol: Trading symbol
            start_date: Start date
            end_date: End date
            bar_size: Bar size
            
        Returns:
            Cache key string
        """
        # Create unique identifier
        identifier = f"{symbol}_{start_date.date()}_{end_date.date()}_{bar_size}"
        
        # Hash it for consistent filename
        hash_obj = hashlib.md5(identifier.encode())
        return hash_obj.hexdigest()
    
    def _save_to_cache(self, cache_key: str, bars: List[BarData]):
        """
        Save historical data to cache file.
        
        Args:
            cache_key: Cache key
            bars: List of BarData to cache
        """
        cache_file = self.cache_dir / f"{cache_key}.pkl"
        
        try:
            with open(cache_file, 'wb') as f:
                pickle.dump(bars, f)
            logger.debug(f"Saved {len(bars)} bars to cache: {cache_file.name}")
        except Exception as e:
            logger.error(f"Failed to save cache: {e}")
    
    def _load_from_cache(self, cache_key: str) -> Optional[List[BarData]]:
        """
        Load historical data from cache file.
        
        Args:
            cache_key: Cache key
            
        Returns:
            List of BarData if found, None otherwise
        """
        cache_file = self.cache_dir / f"{cache_key}.pkl"
        
        if not cache_file.exists():
            return None
        
        try:
            with open(cache_file, 'rb') as f:
                bars = pickle.load(f)
            logger.debug(f"Loaded {len(bars)} bars from cache: {cache_file.name}")
            return bars
        except Exception as e:
            logger.error(f"Failed to load cache: {e}")
            return None
    
    def bars_to_dataframe(self, bars: List[BarData]) -> pd.DataFrame:
        """
        Convert list of BarData to pandas DataFrame.
        
        Args:
            bars: List of BarData objects
            
        Returns:
            DataFrame with OHLCV data
        """
        if not bars:
            return pd.DataFrame()
        
        data = [bar.to_dict() for bar in bars]
        df = pd.DataFrame(data)
        df.set_index('timestamp', inplace=True)
        df.sort_index(inplace=True)
        
        return df
    
    def create_sample_data(
        self,
        symbol: str,
        start_date: datetime,
        end_date: datetime,
        bar_size: str = "1 day",
        base_price: float = 100.0,
        volatility: float = 0.02
    ) -> List[BarData]:
        """
        Create sample historical data for testing.
        
        Generates realistic-looking OHLCV data with random walk price movement.
        
        Args:
            symbol: Trading symbol
            start_date: Start date
            end_date: End date
            bar_size: Bar size (determines frequency)
            base_price: Starting price
            volatility: Price volatility (std dev as fraction of price)
            
        Returns:
            List of BarData objects
        """
        import numpy as np
        
        # Determine time delta based on bar size
        if "min" in bar_size:
            minutes = int(bar_size.split()[0])
            delta = timedelta(minutes=minutes)
        elif "hour" in bar_size:
            hours = int(bar_size.split()[0])
            delta = timedelta(hours=hours)
        elif "day" in bar_size:
            days = int(bar_size.split()[0])
            delta = timedelta(days=days)
        else:
            delta = timedelta(days=1)
        
        # Generate timestamps
        timestamps = []
        current = start_date
        while current <= end_date:
            timestamps.append(current)
            current += delta
        
        # Generate prices using random walk
        np.random.seed(42)  # For reproducibility
        n_bars = len(timestamps)
        
        # Generate returns
        returns = np.random.normal(0, volatility, n_bars)
        
        # Calculate prices
        prices = base_price * np.exp(np.cumsum(returns))
        
        # Create bars
        bars = []
        for i, (timestamp, close) in enumerate(zip(timestamps, prices)):
            # Generate realistic OHLC from close price
            daily_range = close * volatility * 2
            
            open_price = close + np.random.uniform(-daily_range/2, daily_range/2)
            high_price = max(open_price, close) + np.random.uniform(0, daily_range/2)
            low_price = min(open_price, close) - np.random.uniform(0, daily_range/2)
            
            # Generate volume
            volume = int(np.random.uniform(1_000_000, 10_000_000))
            
            bar = BarData(
                timestamp=timestamp,
                open=round(open_price, 2),
                high=round(high_price, 2),
                low=round(low_price, 2),
                close=round(close, 2),
                volume=volume,
                bar_count=int(volume / 1000),
                wap=round((high_price + low_price + close) / 3, 2)
            )
            bars.append(bar)
        
        logger.info(f"Created {len(bars)} sample bars for {symbol}")
        return bars
    
    def validate_data(self, bars: List[BarData]) -> Tuple[bool, List[str]]:
        """
        Validate historical data for consistency.
        
        Args:
            bars: List of BarData to validate
            
        Returns:
            Tuple of (is_valid, list_of_errors)
        """
        errors = []
        
        if not bars:
            errors.append("No data to validate")
            return False, errors
        
        for i, bar in enumerate(bars):
            # Check price relationships
            if bar.high < bar.low:
                errors.append(f"Bar {i}: High < Low")
            
            if bar.close > bar.high or bar.close < bar.low:
                errors.append(f"Bar {i}: Close outside High/Low range")
            
            if bar.open > bar.high or bar.open < bar.low:
                errors.append(f"Bar {i}: Open outside High/Low range")
            
            # Check for negative values
            if any(v < 0 for v in [bar.open, bar.high, bar.low, bar.close]):
                errors.append(f"Bar {i}: Negative prices detected")
            
            if bar.volume < 0:
                errors.append(f"Bar {i}: Negative volume")
        
        # Check chronological order
        for i in range(1, len(bars)):
            if bars[i].timestamp <= bars[i-1].timestamp:
                errors.append(f"Bar {i}: Not in chronological order")
        
        is_valid = len(errors) == 0
        return is_valid, errors
    
    def clear_cache(self, symbol: Optional[str] = None):
        """
        Clear cached data.
        
        Args:
            symbol: If provided, clear only cache for this symbol
                   If None, clear all cache
        """
        if symbol:
            # Clear specific symbol from memory cache
            keys_to_remove = [k for k in self._data_cache.keys() if symbol in k]
            for key in keys_to_remove:
                del self._data_cache[key]
            logger.info(f"Cleared cache for {symbol}")
        else:
            # Clear all memory cache
            self._data_cache.clear()
            logger.info("Cleared all in-memory cache")
    
    def get_cache_size(self) -> int:
        """
        Get total size of cached data files.
        
        Returns:
            Total cache size in bytes
        """
        total_size = 0
        for cache_file in self.cache_dir.glob("*.pkl"):
            total_size += cache_file.stat().st_size
        return total_size
    
    def list_cached_symbols(self) -> List[str]:
        """
        List all symbols with cached data.
        
        Returns:
            List of symbol identifiers
        """
        return list(self._data_cache.keys())
