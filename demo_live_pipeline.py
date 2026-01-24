"""
Demo: Live Trading Pipeline with Real Historical Data

Demonstrates the complete pipeline using real Yahoo Finance data:
- Downloads recent historical data from Yahoo Finance
- Feeds to BollingerBandsStrategy
- OrderExecutor processes signals
- Shows all safety checks in action

Usage:
    python demo_live_pipeline.py

Author: TWS Robot Development Team
Date: January 24, 2026
"""

# ==============================================================================
# API VERIFICATION CHECKLIST ✓
# ==============================================================================
# Date: 2026-01-24
# Task: Create demo with Yahoo Finance data
#
# Verified APIs:
# 1. yfinance.Ticker (from yfinance library)
#    Tool: read_file download_real_data.py:62-68
#    Found: ticker = yf.Ticker(symbol)
#           df = ticker.history(start=..., end=..., interval=...)
#    Verified: ✓
#
# 2. BollingerBandsStrategy.on_bar (from strategies/bollinger_bands.py:137)
#    Tool: read_file strategies/bollinger_bands.py:137-160
#    Signature: on_bar(self, symbol: str, bar: Dict) -> Signal
#    Verified: ✓
#
# 3. OrderExecutor.execute_signal (from execution/order_executor.py)
#    Tool: read_file execution/order_executor.py:194-217
#    Signature: execute_signal(strategy_name, signal, current_equity, positions)
#    Verified: ✓
#
# VERIFICATION COMPLETE: ✓ All APIs confirmed
# ==============================================================================

import sys
import logging
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import Mock
import pandas as pd

# Yahoo Finance import
try:
    import yfinance as yf
except ImportError:
    print("ERROR: yfinance not installed")
    print("Install with: pip install yfinance")
    sys.exit(1)

# Core imports
from strategies.bollinger_bands import BollingerBandsStrategy
from execution.order_executor import OrderExecutor, OrderStatus
from risk.risk_manager import RiskManager, Position

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def download_yahoo_data(symbol: str, days: int = 30) -> pd.DataFrame:
    """
    Download recent historical data from Yahoo Finance.
    
    Args:
        symbol: Stock ticker (e.g., 'AAPL')
        days: Number of days of history
    
    Returns:
        DataFrame with OHLCV data
    """
    end_date = datetime.now()
    start_date = end_date - timedelta(days=days)
    
    print(f"📊 Downloading {symbol} data from Yahoo Finance...")
    print(f"   Period: {start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}")
    
    try:
        # Download using yfinance (API verified from download_real_data.py:62-68)
        ticker = yf.Ticker(symbol)
        df = ticker.history(
            start=start_date.strftime('%Y-%m-%d'),
            end=end_date.strftime('%Y-%m-%d'),
            interval='1h'  # Hourly data for more bars
        )
        
        if df.empty:
            raise ValueError(f"No data returned for {symbol}")
        
        # Standardize column names to lowercase
        df.columns = [col.lower() for col in df.columns]
        
        # Reset index to make datetime a column
        df = df.reset_index()
        
        # Ensure we have required columns
        required = ['open', 'high', 'low', 'close', 'volume']
        for col in required:
            if col not in df.columns:
                raise ValueError(f"Missing required column: {col}")
        
        print(f"✅ Downloaded {len(df)} hourly bars")
        print(f"   Date range: {df.index[0]} to {df.index[-1]}")
        print(f"   Price range: ${df['close'].min():.2f} - ${df['close'].max():.2f}")
        
        return df
        
    except Exception as e:
        print(f"❌ Error downloading data: {e}")
        raise


def create_mock_tws():
    """Create mock TWS adapter for testing"""
    adapter = Mock()
    adapter.connected = True
    adapter.buy = Mock(side_effect=lambda **kwargs: 10000 + len(adapter.buy.call_args_list))
    adapter.sell = Mock(side_effect=lambda **kwargs: 20000 + len(adapter.sell.call_args_list))
    adapter.close_position = Mock(side_effect=lambda **kwargs: 30000 + len(adapter.close_position.call_args_list))
    adapter.get_all_positions = Mock(return_value={})
    return adapter


def main():
    """Run demo with Yahoo Finance data"""
    
    print("=" * 80)
    print("LIVE TRADING PIPELINE DEMO - Real Yahoo Finance Data")
    print("=" * 80)
    print()
    
    # 1. Download real data from Yahoo Finance
    try:
        df = download_yahoo_data('AAPL', days=30)
    except Exception as e:
        logger.exception(f"Failed to download data: {e}")
        return
    
    print()
    
    # 2. Initialize components
    print("🔧 Initializing components...")
    
    # Mock TWS adapter
    tws_adapter = create_mock_tws()
    print("✅ Mock TWS adapter created")
    
    # Risk manager
    risk_manager = RiskManager(
        initial_capital=100000.0,
        max_positions=2,
        max_position_pct=0.20,  # 20% per position
        max_drawdown_pct=0.15,
        daily_loss_limit_pct=0.05
    )
    print("✅ Risk manager initialized")
    
    # Order executor (paper mode)
    order_executor = OrderExecutor(
        tws_adapter=tws_adapter,
        risk_manager=risk_manager,
        is_live_mode=False,  # Paper mode
        require_confirmation=False
    )
    print("✅ Order executor initialized")
    
    # Strategy
    strategy = BollingerBandsStrategy(
        name='BollingerBands_Demo',
        symbols=['AAPL'],
        period=20,
        std_dev=2.0,
        position_size=0.15  # 15% position size
    )
    strategy.start()
    print("✅ Bollinger Bands strategy created")
    print()
    
    # 3. Process bars through pipeline
    print("=" * 80)
    print("🚀 PIPELINE ACTIVE - Processing Historical Bars")
    print("=" * 80)
    print()
    
    current_equity = 100000.0
    current_positions = {}
    signals_generated = 0
    orders_submitted = 0
    orders_blocked = 0
    orders_rejected = 0
    
    
    bar_count = 0
    for i, row in df.iterrows():
        bar_count += 1
        
        # Get timestamp (handle both index and column)
        if isinstance(i, datetime):
            timestamp = i
        elif 'date' in row:
            timestamp = pd.to_datetime(row['date'])
        else:
            timestamp = datetime.now()
        
        # Convert row to bar dict (API verified from bollinger_bands.py:137)
        bar = {
            'timestamp': timestamp,
            'open': float(row['open']),
            'high': float(row['high']),
            'low': float(row['low']),
            'close': float(row['close']),
            'volume': int(row['volume'])
        }
        
        # Feed to strategy
        signal = strategy.on_bar('AAPL', bar)
        
        # If signal generated, execute it
        if signal and signal.signal_type.value != 'HOLD':
            signals_generated += 1
            
            print(f"\n📊 Bar {bar_count}/{len(df)} - {timestamp.strftime('%Y-%m-%d %H:%M')}")
            print(f"   Price: ${row['close']:.2f} | Volume: {row['volume']:,}")
            print(f"   🎯 SIGNAL: {signal.signal_type.value} {signal.symbol}")
            print(f"      Quantity: {signal.quantity} shares")
            print(f"      Confidence: {signal.confidence:.2%}")
            print(f"      Reason: {signal.reason}")
            
            # Execute through order executor (API verified from order_executor.py:194-217)
            result = order_executor.execute_signal(
                strategy_name=strategy.name,
                signal=signal,
                current_equity=current_equity,
                positions=current_positions
            )
            
            # Display result
            if result.status == OrderStatus.SUBMITTED:
                orders_submitted += 1
                print(f"   ✅ ORDER SUBMITTED: #{result.order_id}")
                
                # Update mock positions (simplified)
                if signal.signal_type.value == 'BUY':
                    current_positions['AAPL'] = Position(
                        symbol='AAPL',
                        quantity=signal.quantity,
                        entry_price=row['close'],
                        current_price=row['close'],
                        side='LONG'
                    )
                elif signal.signal_type.value == 'CLOSE':
                    if 'AAPL' in current_positions:
                        del current_positions['AAPL']
                
            elif result.status == OrderStatus.BLOCKED:
                orders_blocked += 1
                print(f"   🚫 ORDER BLOCKED: {result.reason}")
                
            elif result.status == OrderStatus.REJECTED:
                orders_rejected += 1
                print(f"   ❌ ORDER REJECTED: {result.reason}")
        
        # Show progress every 20 bars
        elif bar_count % 20 == 0:
            print(f"Bar {bar_count}/{len(df)} - {timestamp.strftime('%Y-%m-%d')} - ${row['close']:.2f} - No signal")
    
    # 4. Display final statistics
    print()
    print("=" * 80)
    print("📈 FINAL STATISTICS")
    print("=" * 80)
    print(f"Bars Processed: {len(df)}")
    print(f"Signals Generated: {signals_generated}")
    print(f"Orders Submitted: {orders_submitted}")
    print(f"Orders Blocked: {orders_blocked}")
    print(f"Orders Rejected: {orders_rejected}")
    print()
    
    stats = order_executor.get_statistics()
    print("Order Executor Statistics:")
    print(f"  Total Orders: {stats['total_orders']}")
    print(f"  Submitted: {stats['submitted']}")
    print(f"  Blocked: {stats['blocked']}")
    print(f"  Rejected: {stats['rejected']}")
    if stats['total_orders'] > 0:
        print(f"  Success Rate: {stats['submitted'] / stats['total_orders']:.1%}")
    print()
    
    # Display order history
    if len(order_executor.order_history) > 0:
        print("Order History:")
        for i, order in enumerate(order_executor.order_history, 1):
            status_emoji = {
                'SUBMITTED': '✅',
                'BLOCKED': '🚫',
                'REJECTED': '❌'
            }.get(order.status.value, '❓')
            
            print(f"  {i}. {status_emoji} {order.status.value} - "
                  f"{order.signal.signal_type.value if order.signal else 'N/A'} "
                  f"{order.quantity} shares - {order.reason}")
    
    print()
    print("=" * 80)
    print("✅ DEMO COMPLETE")
    print("=" * 80)
    print()
    print("This demonstrated the complete live trading pipeline:")
    print("  1. Historical data → Strategy")
    print("  2. Strategy generates signals")
    print("  3. OrderExecutor validates (6 safety checks)")
    print("  4. Orders submitted to TWS (mocked)")
    print()
    print("In live trading, TWS would provide real-time data and execute orders.")
    print()


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n🛑 Demo interrupted by user")
    except Exception as e:
        logger.exception(f"❌ Demo failed: {e}")
        sys.exit(1)
