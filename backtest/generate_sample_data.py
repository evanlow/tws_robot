"""
Sample Data Generator

Generates sample historical data for testing and demonstration.

Author: TWS Robot Development Team
Date: November 2025
Week 4 Day 1
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from pathlib import Path


def generate_sample_data(
    symbol: str,
    start_date: str = "2023-01-01",
    end_date: str = "2024-12-31",
    initial_price: float = 100.0,
    volatility: float = 0.02,
    trend: float = 0.0001,
    output_dir: str = "data/historical"
) -> str:
    """
    Generate synthetic OHLCV data for testing
    
    Args:
        symbol: Stock symbol
        start_date: Start date (YYYY-MM-DD)
        end_date: End date (YYYY-MM-DD)
        initial_price: Starting price
        volatility: Daily volatility (std dev)
        trend: Daily drift (mean return)
        output_dir: Output directory for CSV
        
    Returns:
        Path to generated CSV file
    """
    # Generate date range (business days only)
    dates = pd.bdate_range(start=start_date, end=end_date)
    
    # Generate returns (geometric Brownian motion)
    returns = np.random.normal(trend, volatility, len(dates))
    
    # Generate price series
    prices = initial_price * np.exp(np.cumsum(returns))
    
    # Generate OHLC from close prices
    data = []
    
    for i, date in enumerate(dates):
        close = prices[i]
        
        # Generate intraday high/low with some randomness
        intraday_range = close * np.random.uniform(0.005, 0.02)  # 0.5-2% range
        high = close + np.random.uniform(0, intraday_range)
        low = close - np.random.uniform(0, intraday_range)
        
        # Open is somewhere between previous close and today's close
        if i > 0:
            prev_close = prices[i-1]
            open_price = prev_close + (close - prev_close) * np.random.uniform(0.2, 0.8)
        else:
            open_price = close * np.random.uniform(0.99, 1.01)
        
        # Ensure OHLC consistency
        high = max(high, open_price, close)
        low = min(low, open_price, close)
        
        # Generate volume (log-normal distribution)
        volume = int(np.random.lognormal(15, 0.5))  # Mean around 3M shares
        
        data.append({
            'Date': date.strftime('%Y-%m-%d'),
            'Open': round(open_price, 2),
            'High': round(high, 2),
            'Low': round(low, 2),
            'Close': round(close, 2),
            'Volume': volume
        })
    
    # Create DataFrame
    df = pd.DataFrame(data)
    
    # Ensure output directory exists
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    
    # Save to CSV
    csv_path = output_path / f"{symbol}_daily.csv"
    df.to_csv(csv_path, index=False)
    
    print(f"Generated {len(df)} bars for {symbol}")
    print(f"Date range: {df['Date'].iloc[0]} to {df['Date'].iloc[-1]}")
    print(f"Price range: ${df['Close'].min():.2f} to ${df['Close'].max():.2f}")
    print(f"Saved to: {csv_path}")
    
    return str(csv_path)


def generate_multiple_symbols(
    symbols: list = ['AAPL', 'MSFT', 'GOOGL', 'TSLA', 'SPY'],
    start_date: str = "2023-01-01",
    end_date: str = "2024-12-31",
    output_dir: str = "data/historical"
) -> list:
    """
    Generate sample data for multiple symbols
    
    Returns:
        List of generated file paths
    """
    print(f"\nGenerating sample data for {len(symbols)} symbols...")
    print(f"Date range: {start_date} to {end_date}\n")
    
    # Different parameters for each symbol to create variety
    params = {
        'AAPL': {'initial_price': 150.0, 'volatility': 0.018, 'trend': 0.0005},
        'MSFT': {'initial_price': 300.0, 'volatility': 0.016, 'trend': 0.0006},
        'GOOGL': {'initial_price': 120.0, 'volatility': 0.020, 'trend': 0.0004},
        'TSLA': {'initial_price': 200.0, 'volatility': 0.035, 'trend': 0.0003},
        'SPY': {'initial_price': 400.0, 'volatility': 0.012, 'trend': 0.0004},
        'AMZN': {'initial_price': 140.0, 'volatility': 0.022, 'trend': 0.0005},
        'NVDA': {'initial_price': 400.0, 'volatility': 0.030, 'trend': 0.0008},
        'META': {'initial_price': 300.0, 'volatility': 0.025, 'trend': 0.0004},
    }
    
    files = []
    
    for symbol in symbols:
        symbol_params = params.get(symbol, {
            'initial_price': 100.0,
            'volatility': 0.02,
            'trend': 0.0004
        })
        
        file_path = generate_sample_data(
            symbol=symbol,
            start_date=start_date,
            end_date=end_date,
            output_dir=output_dir,
            **symbol_params
        )
        files.append(file_path)
        print()
    
    print(f"Generated {len(files)} files in {output_dir}/")
    return files


if __name__ == "__main__":
    # Generate sample data for common symbols
    symbols = ['AAPL', 'MSFT', 'GOOGL', 'TSLA', 'SPY']
    
    files = generate_multiple_symbols(
        symbols=symbols,
        start_date="2023-01-01",
        end_date="2024-12-31",
        output_dir="data/historical"
    )
    
    print("\n" + "="*60)
    print("Sample data generation complete!")
    print("="*60)
    print("\nYou can now use this data for backtesting:")
    print("\n  from backtest import HistoricalDataManager")
    print("  data_mgr = HistoricalDataManager('data/historical')")
    print("  data_mgr.load_csv('AAPL', 'data/historical/AAPL_daily.csv')")
