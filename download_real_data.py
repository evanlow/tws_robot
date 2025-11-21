"""
Real Historical Data Downloader

Downloads real historical market data from Yahoo Finance using yfinance.

Features:
- Download OHLCV data for any stock symbol
- Multiple timeframes (1d, 1h, 1m, etc.)
- Automatic date range handling
- CSV export in standard format
- Batch downloading for multiple symbols

Author: TWS Robot Development Team
Date: November 2025
Week 4 Day 2
"""

import pandas as pd
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Optional, Dict
import sys

try:
    import yfinance as yf
except ImportError:
    print("ERROR: yfinance not installed")
    print("Install with: pip install yfinance")
    sys.exit(1)


def download_historical_data(
    symbol: str,
    start_date: str,
    end_date: str,
    interval: str = "1d",
    output_dir: str = "data/historical"
) -> Optional[str]:
    """
    Download historical data from Yahoo Finance
    
    Args:
        symbol: Stock ticker symbol (e.g., 'AAPL', 'MSFT')
        start_date: Start date (YYYY-MM-DD)
        end_date: End date (YYYY-MM-DD)
        interval: Data interval ('1d', '1h', '1m', etc.)
        output_dir: Directory to save CSV file
        
    Returns:
        Path to saved CSV file, or None if failed
    """
    try:
        print(f"\nDownloading {symbol}...")
        print(f"  Period: {start_date} to {end_date}")
        print(f"  Interval: {interval}")
        
        # Download data
        ticker = yf.Ticker(symbol)
        df = ticker.history(
            start=start_date,
            end=end_date,
            interval=interval
        )
        
        if df.empty:
            print(f"  ✗ No data returned for {symbol}")
            return None
        
        # Clean up the dataframe
        df = df.reset_index()
        
        # Rename columns to match our standard format
        column_mapping = {
            'Date': 'Date',
            'Datetime': 'Date',  # For intraday data
            'Open': 'Open',
            'High': 'High',
            'Low': 'Low',
            'Close': 'Close',
            'Volume': 'Volume'
        }
        
        # Select only OHLCV columns
        available_cols = [col for col in column_mapping.keys() if col in df.columns]
        df = df[available_cols]
        df.columns = [column_mapping.get(col, col) for col in df.columns]
        
        # Format date column
        if 'Date' in df.columns:
            df['Date'] = pd.to_datetime(df['Date']).dt.strftime('%Y-%m-%d')
        
        # Create output directory
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        
        # Save to CSV
        interval_suffix = f"_{interval}" if interval != "1d" else "_daily"
        filename = f"{symbol}{interval_suffix}.csv"
        filepath = output_path / filename
        
        df.to_csv(filepath, index=False)
        
        print(f"  ✓ Downloaded {len(df)} bars")
        print(f"  Date range: {df['Date'].iloc[0]} to {df['Date'].iloc[-1]}")
        print(f"  Price range: ${df['Close'].min():.2f} to ${df['Close'].max():.2f}")
        print(f"  Saved to: {filepath}")
        
        return str(filepath)
        
    except Exception as e:
        print(f"  ✗ Error downloading {symbol}: {e}")
        return None


def download_multiple_symbols(
    symbols: List[str],
    start_date: str,
    end_date: str,
    interval: str = "1d",
    output_dir: str = "data/historical"
) -> Dict[str, Optional[str]]:
    """
    Download data for multiple symbols
    
    Args:
        symbols: List of ticker symbols
        start_date: Start date (YYYY-MM-DD)
        end_date: End date (YYYY-MM-DD)
        interval: Data interval
        output_dir: Output directory
        
    Returns:
        Dictionary mapping symbols to file paths (None if failed)
    """
    print("="*70)
    print("Downloading Real Historical Data from Yahoo Finance")
    print("="*70)
    
    results = {}
    
    for symbol in symbols:
        filepath = download_historical_data(
            symbol=symbol,
            start_date=start_date,
            end_date=end_date,
            interval=interval,
            output_dir=output_dir
        )
        results[symbol] = filepath
    
    # Summary
    print("\n" + "="*70)
    print("Download Summary")
    print("="*70)
    
    successful = [s for s, p in results.items() if p is not None]
    failed = [s for s, p in results.items() if p is None]
    
    print(f"\nSuccessful: {len(successful)}/{len(symbols)}")
    if successful:
        for symbol in successful:
            print(f"  ✓ {symbol}")
    
    if failed:
        print(f"\nFailed: {len(failed)}")
        for symbol in failed:
            print(f"  ✗ {symbol}")
    
    print("="*70 + "\n")
    
    return results


def download_recent_data(
    symbols: List[str],
    period: str = "2y",
    interval: str = "1d",
    output_dir: str = "data/historical"
) -> Dict[str, Optional[str]]:
    """
    Download recent historical data (easier API)
    
    Args:
        symbols: List of ticker symbols
        period: Time period ('1mo', '3mo', '6mo', '1y', '2y', '5y', 'max')
        interval: Data interval
        output_dir: Output directory
        
    Returns:
        Dictionary mapping symbols to file paths
    """
    print("="*70)
    print(f"Downloading Recent Data ({period}) from Yahoo Finance")
    print("="*70)
    
    results = {}
    
    for symbol in symbols:
        try:
            print(f"\nDownloading {symbol} ({period})...")
            
            ticker = yf.Ticker(symbol)
            df = ticker.history(period=period, interval=interval)
            
            if df.empty:
                print(f"  ✗ No data returned for {symbol}")
                results[symbol] = None
                continue
            
            # Clean and format
            df = df.reset_index()
            df = df[['Date', 'Open', 'High', 'Low', 'Close', 'Volume']]
            df['Date'] = pd.to_datetime(df['Date']).dt.strftime('%Y-%m-%d')
            
            # Save
            output_path = Path(output_dir)
            output_path.mkdir(parents=True, exist_ok=True)
            
            interval_suffix = f"_{interval}" if interval != "1d" else "_daily"
            filename = f"{symbol}{interval_suffix}.csv"
            filepath = output_path / filename
            
            df.to_csv(filepath, index=False)
            
            print(f"  ✓ Downloaded {len(df)} bars")
            print(f"  Date range: {df['Date'].iloc[0]} to {df['Date'].iloc[-1]}")
            print(f"  Price range: ${df['Close'].min():.2f} to ${df['Close'].max():.2f}")
            print(f"  Saved to: {filepath}")
            
            results[symbol] = str(filepath)
            
        except Exception as e:
            print(f"  ✗ Error downloading {symbol}: {e}")
            results[symbol] = None
    
    # Summary
    print("\n" + "="*70)
    print("Download Summary")
    print("="*70)
    
    successful = [s for s, p in results.items() if p is not None]
    failed = [s for s, p in results.items() if p is None]
    
    print(f"\nSuccessful: {len(successful)}/{len(symbols)}")
    if successful:
        for symbol in successful:
            print(f"  ✓ {symbol}")
    
    if failed:
        print(f"\nFailed: {len(failed)}")
        for symbol in failed:
            print(f"  ✗ {symbol}")
    
    print("="*70 + "\n")
    
    return results


def get_stock_info(symbol: str) -> Dict:
    """
    Get stock information
    
    Args:
        symbol: Stock ticker symbol
        
    Returns:
        Dictionary with stock info
    """
    try:
        ticker = yf.Ticker(symbol)
        info = ticker.info
        
        return {
            'symbol': symbol,
            'name': info.get('longName', 'N/A'),
            'sector': info.get('sector', 'N/A'),
            'industry': info.get('industry', 'N/A'),
            'market_cap': info.get('marketCap', 0),
            'currency': info.get('currency', 'USD')
        }
    except Exception as e:
        print(f"Error getting info for {symbol}: {e}")
        return {'symbol': symbol, 'error': str(e)}


if __name__ == "__main__":
    # Default symbols to download
    symbols = ['AAPL', 'MSFT', 'GOOGL', 'TSLA', 'SPY', 'QQQ', 'AMZN', 'NVDA']
    
    print("\n" + "="*70)
    print("Real Historical Data Downloader")
    print("="*70)
    print("\nThis will download REAL market data from Yahoo Finance")
    print(f"Symbols: {', '.join(symbols)}")
    print("Period: Last 2 years")
    print("\n" + "="*70 + "\n")
    
    # Download recent 2 years of data
    results = download_recent_data(
        symbols=symbols,
        period="2y",
        interval="1d",
        output_dir="data/historical"
    )
    
    # Show what can be done next
    successful = [s for s, p in results.items() if p is not None]
    
    if successful:
        print("\n✓ Real historical data ready!")
        print("\nYou can now backtest with real data:")
        print("\n  from backtest import HistoricalDataManager")
        print("  data_mgr = HistoricalDataManager('data/historical')")
        print(f"  data_mgr.load_csv('{successful[0]}', 'data/historical/{successful[0]}_daily.csv')")
        print("\nOr run the existing backtest example:")
        print("  python example_backtest_complete.py")
