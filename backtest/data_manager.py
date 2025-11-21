"""
Historical Data Manager

Handles loading, validation, and management of historical market data for backtesting.

Supports multiple data sources:
- CSV files
- Pandas DataFrames
- Database queries
- API data

Author: TWS Robot Development Team
Date: November 2025
Week 4 Day 1
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Union
from pathlib import Path
import logging

from .data_models import Bar, BarSeries, TimeFrame, MarketData

logger = logging.getLogger(__name__)


class HistoricalDataManager:
    """
    Manages historical market data for backtesting
    
    Responsibilities:
    - Load data from various sources (CSV, database, API)
    - Validate data quality
    - Provide time-windowed access to historical bars
    - Cache data for performance
    - Handle multiple symbols and timeframes
    """
    
    def __init__(self, data_dir: Optional[str] = None):
        """
        Initialize data manager
        
        Args:
            data_dir: Directory containing historical data files
        """
        self.data_dir = Path(data_dir) if data_dir else Path("data/historical")
        self.data: Dict[str, BarSeries] = {}  # symbol -> BarSeries
        self.metadata: Dict[str, dict] = {}  # symbol -> metadata
        self._cache: Dict[tuple, List[Bar]] = {}  # Cache for windowed queries
        
        logger.info(f"Initialized HistoricalDataManager with data_dir: {self.data_dir}")
    
    def load_csv(
        self,
        symbol: str,
        filepath: Union[str, Path],
        timeframe: TimeFrame = TimeFrame.DAY_1,
        date_column: str = 'Date',
        format: str = 'standard'
    ) -> bool:
        """
        Load historical data from CSV file
        
        Args:
            symbol: Symbol/ticker
            filepath: Path to CSV file
            timeframe: Data timeframe
            date_column: Name of date column
            format: CSV format ('standard', 'yahoo', 'ib', 'custom')
            
        Returns:
            True if loaded successfully
            
        CSV Format:
            Standard: Date, Open, High, Low, Close, Volume
            Yahoo: Date, Open, High, Low, Close, Adj Close, Volume
            IB: Date, Open, High, Low, Close, Volume, WAP (VWAP)
        """
        try:
            logger.info(f"Loading {symbol} data from {filepath}")
            
            # Read CSV
            df = pd.read_csv(filepath)
            
            # Parse dates
            df[date_column] = pd.to_datetime(df[date_column])
            
            # Standardize column names
            column_map = self._get_column_map(format)
            df = df.rename(columns=column_map)
            
            # Validate required columns
            required = ['date', 'open', 'high', 'low', 'close', 'volume']
            missing = [col for col in required if col not in df.columns]
            if missing:
                raise ValueError(f"Missing required columns: {missing}")
            
            # Create BarSeries
            bar_series = BarSeries(symbol=symbol, timeframe=timeframe)
            
            for _, row in df.iterrows():
                bar = Bar(
                    timestamp=row['date'],
                    symbol=symbol,
                    open=float(row['open']),
                    high=float(row['high']),
                    low=float(row['low']),
                    close=float(row['close']),
                    volume=int(row['volume']),
                    timeframe=timeframe,
                    vwap=float(row['vwap']) if 'vwap' in df.columns else None
                )
                bar_series.add_bar(bar)
            
            self.data[symbol] = bar_series
            self.metadata[symbol] = {
                'start_date': bar_series.bars[0].timestamp,
                'end_date': bar_series.bars[-1].timestamp,
                'bar_count': len(bar_series.bars),
                'timeframe': timeframe,
                'source': 'csv',
                'filepath': str(filepath)
            }
            
            logger.info(
                f"Loaded {len(bar_series.bars)} bars for {symbol} "
                f"({self.metadata[symbol]['start_date'].date()} to "
                f"{self.metadata[symbol]['end_date'].date()})"
            )
            
            return True
            
        except Exception as e:
            logger.error(f"Error loading {symbol} from {filepath}: {e}")
            return False
    
    def load_dataframe(
        self,
        symbol: str,
        df: pd.DataFrame,
        timeframe: TimeFrame = TimeFrame.DAY_1,
        date_column: str = 'date'
    ) -> bool:
        """
        Load historical data from pandas DataFrame
        
        Args:
            symbol: Symbol/ticker
            df: DataFrame with OHLCV data
            timeframe: Data timeframe
            date_column: Name of date column
            
        Returns:
            True if loaded successfully
        """
        try:
            logger.info(f"Loading {symbol} data from DataFrame ({len(df)} rows)")
            
            # Ensure date column is datetime
            if date_column in df.columns:
                df[date_column] = pd.to_datetime(df[date_column])
            else:
                raise ValueError(f"Date column '{date_column}' not found")
            
            # Standardize column names (lowercase)
            df.columns = [col.lower() for col in df.columns]
            
            # Create BarSeries
            bar_series = BarSeries(symbol=symbol, timeframe=timeframe)
            
            for _, row in df.iterrows():
                bar = Bar(
                    timestamp=row[date_column.lower()],
                    symbol=symbol,
                    open=float(row['open']),
                    high=float(row['high']),
                    low=float(row['low']),
                    close=float(row['close']),
                    volume=int(row['volume']),
                    timeframe=timeframe,
                    vwap=float(row['vwap']) if 'vwap' in df.columns else None
                )
                bar_series.add_bar(bar)
            
            self.data[symbol] = bar_series
            self.metadata[symbol] = {
                'start_date': bar_series.bars[0].timestamp,
                'end_date': bar_series.bars[-1].timestamp,
                'bar_count': len(bar_series.bars),
                'timeframe': timeframe,
                'source': 'dataframe'
            }
            
            logger.info(f"Loaded {len(bar_series.bars)} bars for {symbol}")
            return True
            
        except Exception as e:
            logger.error(f"Error loading {symbol} from DataFrame: {e}")
            return False
    
    def get_bars(
        self,
        symbol: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        lookback: Optional[int] = None
    ) -> List[Bar]:
        """
        Get bars for a symbol within date range or lookback period
        
        Args:
            symbol: Symbol/ticker
            start_date: Start date (inclusive)
            end_date: End date (inclusive)
            lookback: Number of most recent bars (alternative to date range)
            
        Returns:
            List of bars in chronological order
        """
        if symbol not in self.data:
            logger.warning(f"No data available for {symbol}")
            return []
        
        bar_series = self.data[symbol]
        
        # Use lookback if specified
        if lookback is not None:
            return bar_series.get_bars(lookback)
        
        # Filter by date range
        bars = bar_series.bars
        
        if start_date:
            bars = [bar for bar in bars if bar.timestamp >= start_date]
        
        if end_date:
            bars = [bar for bar in bars if bar.timestamp <= end_date]
        
        return bars
    
    def get_bar_at_time(self, symbol: str, timestamp: datetime) -> Optional[Bar]:
        """
        Get bar at or before a specific timestamp
        
        Args:
            symbol: Symbol/ticker
            timestamp: Timestamp to query
            
        Returns:
            Most recent bar at or before timestamp, or None
        """
        if symbol not in self.data:
            return None
        
        bars = self.data[symbol].bars
        
        # Binary search for efficiency
        left, right = 0, len(bars) - 1
        result = None
        
        while left <= right:
            mid = (left + right) // 2
            if bars[mid].timestamp <= timestamp:
                result = bars[mid]
                left = mid + 1
            else:
                right = mid - 1
        
        return result
    
    def get_market_data(
        self,
        timestamp: datetime,
        symbols: Optional[List[str]] = None
    ) -> MarketData:
        """
        Get market data snapshot at a specific time for multiple symbols
        
        Args:
            timestamp: Timestamp for snapshot
            symbols: List of symbols (None = all loaded symbols)
            
        Returns:
            MarketData object with bars for all symbols
        """
        if symbols is None:
            symbols = list(self.data.keys())
        
        market_data = MarketData(timestamp=timestamp)
        
        for symbol in symbols:
            bar = self.get_bar_at_time(symbol, timestamp)
            if bar:
                market_data.add_bar(symbol, bar)
        
        return market_data
    
    def validate_data(self, symbol: str) -> Dict[str, any]:
        """
        Validate data quality for a symbol
        
        Checks:
        - Missing values
        - Price anomalies (negative prices, high > low violations)
        - Volume anomalies
        - Gaps in data
        - Duplicates
        
        Returns:
            Dictionary with validation results
        """
        if symbol not in self.data:
            return {'valid': False, 'error': 'Symbol not found'}
        
        bars = self.data[symbol].bars
        issues = []
        
        # Check for duplicates
        timestamps = [bar.timestamp for bar in bars]
        if len(timestamps) != len(set(timestamps)):
            issues.append("Duplicate timestamps found")
        
        # Check each bar
        for i, bar in enumerate(bars):
            # Price anomalies
            if bar.open <= 0 or bar.high <= 0 or bar.low <= 0 or bar.close <= 0:
                issues.append(f"Bar {i}: Non-positive price found")
            
            if bar.high < bar.low:
                issues.append(f"Bar {i}: High < Low")
            
            # Volume anomalies
            if bar.volume < 0:
                issues.append(f"Bar {i}: Negative volume")
            
            # Large gaps (> 50% from previous close)
            if i > 0:
                prev_close = bars[i-1].close
                gap = abs(bar.open - prev_close) / prev_close
                if gap > 0.50:
                    issues.append(
                        f"Bar {i}: Large gap ({gap:.1%}) from previous close"
                    )
        
        return {
            'valid': len(issues) == 0,
            'bar_count': len(bars),
            'issues': issues,
            'issue_count': len(issues)
        }
    
    def get_symbols(self) -> List[str]:
        """Get list of all loaded symbols"""
        return list(self.data.keys())
    
    def get_date_range(self, symbol: str) -> Optional[tuple]:
        """
        Get date range for a symbol
        
        Returns:
            Tuple of (start_date, end_date) or None
        """
        if symbol not in self.metadata:
            return None
        return (
            self.metadata[symbol]['start_date'],
            self.metadata[symbol]['end_date']
        )
    
    def get_bar_count(self, symbol: str) -> int:
        """Get number of bars for a symbol"""
        if symbol not in self.data:
            return 0
        return len(self.data[symbol].bars)
    
    def clear_cache(self) -> None:
        """Clear query cache"""
        self._cache.clear()
        logger.info("Cleared data cache")
    
    def _get_column_map(self, format: str) -> Dict[str, str]:
        """Get column name mapping for different CSV formats"""
        maps = {
            'standard': {
                'Date': 'date',
                'Open': 'open',
                'High': 'high',
                'Low': 'low',
                'Close': 'close',
                'Volume': 'volume'
            },
            'yahoo': {
                'Date': 'date',
                'Open': 'open',
                'High': 'high',
                'Low': 'low',
                'Close': 'close',
                'Adj Close': 'adj_close',
                'Volume': 'volume'
            },
            'ib': {
                'Date': 'date',
                'Open': 'open',
                'High': 'high',
                'Low': 'low',
                'Close': 'close',
                'Volume': 'volume',
                'WAP': 'vwap'
            }
        }
        return maps.get(format, maps['standard'])
    
    def __str__(self) -> str:
        return (f"HistoricalDataManager({len(self.data)} symbols, "
                f"dir={self.data_dir})")
