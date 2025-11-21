"""
Example: Complete Backtest with Strategy and Risk Management

Demonstrates the full backtesting workflow using:
- Strategy base class
- BacktestEngine
- Week 3 risk management integration
- Performance tracking

Author: TWS Robot Development Team
Date: November 2025
Week 4 Day 2
"""

from datetime import datetime
from pathlib import Path
import sys

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from backtest import (
    Strategy,
    StrategyConfig,
    BacktestEngine,
    BacktestConfig,
    HistoricalDataManager,
    MarketData
)


class MovingAverageCrossover(Strategy):
    """
    Simple Moving Average Crossover Strategy
    
    Buy when short MA crosses above long MA
    Sell when short MA crosses below long MA
    """
    
    def __init__(self, config: StrategyConfig):
        super().__init__(config)
        
        # Get parameters
        self.short_period = config.parameters.get('short_period', 10)
        self.long_period = config.parameters.get('long_period', 20)
        
        # Track signals
        self.previous_signal = {}
    
    def on_start(self):
        """Initialize strategy"""
        print(f"\nStarting {self.config.name}")
        print(f"  Short MA: {self.short_period}")
        print(f"  Long MA: {self.long_period}")
        print(f"  Symbols: {self.config.symbols}")
        print(f"  Initial Capital: ${self.config.initial_capital:,.2f}")
    
    def on_bar(self, market_data: MarketData):
        """Process each bar"""
        for symbol in market_data.symbols:
            # Calculate moving averages
            short_ma = self._calculate_ma(symbol, self.short_period)
            long_ma = self._calculate_ma(symbol, self.long_period)
            
            if short_ma is None or long_ma is None:
                continue  # Not enough data yet
            
            # Determine signal
            current_signal = 'BULLISH' if short_ma > long_ma else 'BEARISH'
            previous_signal = self.previous_signal.get(symbol, 'NEUTRAL')
            
            # Detect crossovers
            if previous_signal == 'BEARISH' and current_signal == 'BULLISH':
                # Bullish crossover - buy
                self._enter_long(symbol, market_data.get_close(symbol))
            
            elif previous_signal == 'BULLISH' and current_signal == 'BEARISH':
                # Bearish crossover - sell
                self._exit_long(symbol)
            
            # Update previous signal
            self.previous_signal[symbol] = current_signal
    
    def on_stop(self):
        """Cleanup"""
        # Close any remaining positions
        for symbol in self.config.symbols:
            if self.has_position(symbol):
                self.close_position(symbol)
        
        print(f"\n{self.config.name} Complete")
        print(f"  Total Trades: {self.state.total_trades}")
        print(f"  Win Rate: {self.get_win_rate():.1f}%")
        print(f"  Final Equity: ${self.state.equity:,.2f}")
    
    def _calculate_ma(self, symbol: str, period: int) -> float:
        """Calculate simple moving average"""
        prices = self.get_price_history(symbol, lookback=period)
        if len(prices) < period:
            return None
        return sum(prices) / period
    
    def _enter_long(self, symbol: str, price: float):
        """Enter long position"""
        # Only enter if flat
        if not self.is_flat(symbol):
            return
        
        # Calculate position size (use 10% of equity per position)
        shares = self.calculate_position_size(symbol, price, 0.10)
        
        if shares > 0:
            self.buy(symbol, shares, 'MARKET')
    
    def _exit_long(self, symbol: str):
        """Exit long position"""
        if self.is_long(symbol):
            self.close_position(symbol, 'MARKET')


def main():
    """Run complete backtest example"""
    print("\n" + "="*70)
    print("Complete Backtest Example with Risk Management")
    print("="*70)
    
    # 1. Load historical data
    print("\n1. Loading historical data...")
    data_mgr = HistoricalDataManager('data/historical')
    
    symbols = ['AAPL', 'MSFT', 'SPY']
    for symbol in symbols:
        success = data_mgr.load_csv(
            symbol=symbol,
            filepath=f'data/historical/{symbol}_daily.csv'
        )
        if success:
            bar_count = data_mgr.get_bar_count(symbol)
            print(f"  ✓ Loaded {symbol}: {bar_count} bars")
    
    # 2. Configure strategy
    print("\n2. Configuring strategy...")
    strategy_config = StrategyConfig(
        name="MA_Crossover_10_20",
        symbols=symbols,
        initial_capital=100000.0,
        max_position_size=0.10,  # 10% per position
        use_risk_management=True,
        parameters={
            'short_period': 10,
            'long_period': 20
        }
    )
    
    strategy = MovingAverageCrossover(strategy_config)
    print(f"  ✓ Strategy: {strategy_config.name}")
    
    # 3. Configure backtest
    print("\n3. Configuring backtest engine...")
    backtest_config = BacktestConfig(
        start_date=datetime(2024, 1, 2),
        end_date=datetime(2024, 12, 31),
        initial_capital=100000.0,
        use_risk_management=True,  # Enable Week 3 risk management
        track_equity_curve=True
    )
    print("  ✓ Backtest period: Jan 2024 - Dec 2024")
    print("  ✓ Risk management: ENABLED")
    
    # 4. Create backtest engine
    print("\n4. Creating backtest engine...")
    engine = BacktestEngine(backtest_config, data_mgr)
    engine.set_strategy(strategy)
    engine.enable_risk_management()  # Enable Week 3 components
    print("  ✓ Engine ready with risk management")
    
    # 5. Run backtest
    print("\n5. Running backtest...")
    print("-" * 70)
    
    result = engine.run()
    
    print("-" * 70)
    
    # 6. Display results
    print("\n" + "="*70)
    print("Backtest Results")
    print("="*70)
    
    print(f"\nStrategy: {result.strategy_name}")
    print(f"Period: {result.start_date.date()} to {result.end_date.date()}")
    
    print(f"\nPerformance:")
    print(f"  Initial Capital: ${result.initial_capital:,.2f}")
    print(f"  Final Equity: ${result.final_equity:,.2f}")
    print(f"  Total Return: {result.get_return_pct():.2f}%")
    print(f"  Total P&L: ${result.total_pnl:,.2f}")
    
    print(f"\nTrading Statistics:")
    print(f"  Total Trades: {result.total_trades}")
    print(f"  Winning Trades: {result.winning_trades}")
    print(f"  Losing Trades: {result.losing_trades}")
    print(f"  Win Rate: {result.get_win_rate_pct():.1f}%")
    
    print(f"\nRisk Metrics:")
    print(f"  Max Drawdown: ${result.max_drawdown:,.2f}")
    print(f"  Max Drawdown %: {result.max_drawdown_pct * 100:.2f}%")
    
    if result.trades:
        print(f"\nFirst 5 Trades:")
        for i, trade in enumerate(result.trades[:5], 1):
            print(f"  {i}. {trade}")
        
        if len(result.trades) > 5:
            print(f"\n  ... and {len(result.trades) - 5} more trades")
    
    if result.equity_curve:
        print(f"\nEquity Curve:")
        print(f"  Data Points: {len(result.equity_curve)}")
        
        # Show first and last few points
        print(f"\n  First 3 points:")
        for point in result.equity_curve[:3]:
            print(f"    {point.timestamp.date()}: ${point.equity:,.2f} (DD: {point.drawdown*100:.2f}%)")
        
        print(f"\n  Last 3 points:")
        for point in result.equity_curve[-3:]:
            print(f"    {point.timestamp.date()}: ${point.equity:,.2f} (DD: {point.drawdown*100:.2f}%)")
    
    print("\n" + "="*70)
    print("✓ Complete backtest with risk management finished!")
    print("="*70 + "\n")


if __name__ == '__main__':
    main()
