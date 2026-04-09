"""
Backtesting Integration Example

Demonstrates the complete backtesting workflow using the data infrastructure.

This example shows:
1. Loading historical data
2. Replaying market conditions
3. Simulating orders and fills
4. Tracking positions and performance

Author: TWS Robot Development Team
Date: November 2025
Week 4 Day 1
"""


import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
del _os, _sys

from datetime import datetime
from pathlib import Path
import sys

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from backtest import (
    HistoricalDataManager, 
    MarketSimulator, 
    Bar,
    MarketData
)
from backtest.market_simulator import Order


class SimpleStrategy:
    """Simple moving average crossover strategy for demonstration"""
    
    def __init__(self, market_sim: MarketSimulator, short_period=10, long_period=20):
        self.market_sim = market_sim
        self.short_period = short_period
        self.long_period = long_period
        
        # Track price history
        self.price_history = {}
        
        # Track positions
        self.positions = {}
        
        # Track performance
        self.trades = []
        self.equity = 100000.0  # Starting capital
        
        # Register callbacks
        self.market_sim.register_bar_callback(self.on_bar)
        self.market_sim.register_trade_callback(self.on_trade)
    
    def calculate_sma(self, symbol: str, period: int) -> float:
        """Calculate simple moving average"""
        if symbol not in self.price_history:
            return None
        
        prices = self.price_history[symbol]
        if len(prices) < period:
            return None
        
        return sum(prices[-period:]) / period
    
    def on_bar(self, market_data: MarketData):
        """Called for each bar during replay"""
        # Update price history
        for symbol in market_data.symbols:
            if symbol not in self.price_history:
                self.price_history[symbol] = []
            
            close = market_data.get_close(symbol)
            self.price_history[symbol].append(close)
            
            # Keep only what we need
            max_period = max(self.short_period, self.long_period)
            if len(self.price_history[symbol]) > max_period + 10:
                self.price_history[symbol] = self.price_history[symbol][-max_period:]
        
        # Check signals for each symbol
        for symbol in market_data.symbols:
            self.check_signal(symbol, market_data.timestamp)
    
    def check_signal(self, symbol: str, timestamp: datetime):
        """Check for trading signals"""
        # Calculate moving averages
        short_ma = self.calculate_sma(symbol, self.short_period)
        long_ma = self.calculate_sma(symbol, self.long_period)
        
        if short_ma is None or long_ma is None:
            return  # Not enough data yet
        
        # Get current position
        position = self.positions.get(symbol, 0)
        
        # Generate signals
        if short_ma > long_ma and position <= 0:
            # Bullish crossover - buy signal
            if position < 0:
                # Close short
                order = Order(
                    order_id=f"CLOSE_{symbol}_{timestamp}",
                    symbol=symbol,
                    action='BUY',
                    quantity=abs(position),
                    order_type='MARKET'
                )
                self.market_sim.submit_order(order)
            
            # Go long
            quantity = 100  # Fixed position size
            order = Order(
                order_id=f"BUY_{symbol}_{timestamp}",
                symbol=symbol,
                action='BUY',
                quantity=quantity,
                order_type='MARKET'
            )
            self.market_sim.submit_order(order)
        
        elif short_ma < long_ma and position >= 0:
            # Bearish crossover - sell signal
            if position > 0:
                # Close long
                order = Order(
                    order_id=f"CLOSE_{symbol}_{timestamp}",
                    symbol=symbol,
                    action='SELL',
                    quantity=position,
                    order_type='MARKET'
                )
                self.market_sim.submit_order(order)
    
    def on_trade(self, trade):
        """Called when an order is filled"""
        self.trades.append(trade)
        
        # Update position
        symbol = trade.symbol
        if symbol not in self.positions:
            self.positions[symbol] = 0
        
        if trade.action == 'BUY':
            self.positions[symbol] += trade.quantity
        else:
            self.positions[symbol] -= trade.quantity
        
        # Update equity (simplified - doesn't account for unrealized P&L)
        cost = trade.value + trade.commission
        if trade.action == 'BUY':
            self.equity -= cost
        else:
            self.equity += cost
    
    def print_summary(self):
        """Print backtest summary"""
        print("\n" + "="*70)
        print("Backtest Summary")
        print("="*70)
        print(f"Total Trades: {len(self.trades)}")
        print(f"Final Equity: ${self.equity:,.2f}")
        print(f"Net P&L: ${self.equity - 100000:,.2f}")
        print(f"Return: {((self.equity / 100000) - 1) * 100:.2f}%")
        
        if self.trades:
            print(f"\nFirst 5 Trades:")
            for i, trade in enumerate(self.trades[:5], 1):
                print(f"  {i}. {trade}")
            
            if len(self.trades) > 5:
                print(f"\n... and {len(self.trades) - 5} more trades")
        
        print("\nFinal Positions:")
        for symbol, qty in self.positions.items():
            if qty != 0:
                print(f"  {symbol}: {qty} shares")
        
        print("="*70 + "\n")


def main():
    """Run backtesting integration example"""
    print("\n" + "="*70)
    print("Backtesting Integration Example - Week 4 Day 1")
    print("="*70 + "\n")
    
    # 1. Initialize data manager
    print("1. Loading historical data...")
    data_mgr = HistoricalDataManager('data/historical')
    
    symbols = ['AAPL', 'MSFT', 'SPY']
    for symbol in symbols:
        success = data_mgr.load_csv(
            symbol=symbol,
            filepath=f'data/historical/{symbol}_daily.csv'
        )
        if success:
            bar_count = data_mgr.get_bar_count(symbol)
            date_range = data_mgr.get_date_range(symbol)
            print(f"  ✓ Loaded {symbol}: {bar_count} bars ({date_range[0].date()} to {date_range[1].date()})")
    
    # 2. Create market simulator
    print("\n2. Initializing market simulator...")
    market_sim = MarketSimulator(data_mgr)
    print("  ✓ Market simulator ready")
    
    # 3. Create and attach strategy
    print("\n3. Attaching trading strategy...")
    strategy = SimpleStrategy(market_sim, short_period=10, long_period=20)
    print("  ✓ Simple MA crossover strategy (10/20)")
    
    # 4. Run backtest
    print("\n4. Running backtest...")
    start_date = datetime(2024, 1, 2)
    end_date = datetime(2024, 12, 31)
    
    bar_count = 0
    for market_data in market_sim.replay(start_date, end_date, symbols):
        bar_count += 1
        
        # Print progress every 50 bars
        if bar_count % 50 == 0:
            print(f"  Processed {bar_count} bars...")
    
    print(f"  ✓ Backtest complete: {bar_count} bars processed")
    
    # 5. Print results
    strategy.print_summary()
    
    print("\n✓ Integration example complete!")


if __name__ == '__main__':
    main()
