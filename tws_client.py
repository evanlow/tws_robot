from ibapi.client import *
from ibapi.wrapper import *
from ibapi.contract import Contract

from datetime import datetime
from time import sleep
from threading import Thread
import signal
import sys
import argparse

from env_config import get_config
from market_status import check_market_status

# Dynamic dictionaries that will be populated based on portfolio positions
contract_request_dictionary = {}
history_request_dictionary = {}

# Global flag for graceful shutdown
shutdown_flag = False

def signal_handler(sig, frame):
    """Handle Ctrl+C gracefully"""
    global shutdown_flag
    print('\nShutdown signal received. Disconnecting gracefully...')
    shutdown_flag = True

# Register signal handler for Ctrl+C
signal.signal(signal.SIGINT, signal_handler)

# EClient sends requests to TWS
# EWrapper handles incoming messages
class TradeApp(EWrapper, EClient):
    def __init__(self, config):
        EClient.__init__(self, self)
        self.config = config

        # custom attributes
        self.account_balance = None
        self.account_equity = None
        self.portfolio = {}
        self.connected = False
        self.portfolio_loaded = False
        self.market_data_requested = False

        self.marketdata = {}
        self.ohlc_data = {}
        
        # Request ID counters
        self.next_market_data_id = 1
        self.next_historical_data_id = 4001

    def connectAck(self):
        """Called when connection is established"""
        print("Connection established successfully!")
        self.connected = True

    def connectionClosed(self):
        """Called when connection is closed"""
        print("Connection closed.")
        self.connected = False

    def error(self, reqId: TickerId, errorCode: int, errorString: str, advancedOrderRejectJson="", *args):
        """Handle errors"""
        print(f"Error {errorCode}: {errorString}")
        if errorCode in [502, 503, 504]:  # Connection errors
            self.connected = False

    # EWrapper Functions
    def updateAccountValue(self, key: str, val: str, currency: str, accountName: str):
        if key == 'TotalCashBalance' and currency == 'BASE':
            self.account_balance = val
        elif key == 'NetLiquidationByCurrency' and currency == 'BASE':
            self.account_equity = val

    def updatePortfolio(self, contract: Contract, position: Decimal, marketPrice: float, marketValue: float,
                        averageCost: float, unrealizedPNL: float, realizedPNL: float, accountName: str):
        symbol = contract.localSymbol or contract.symbol
        self.portfolio[symbol] = {
            'position': decimalMaxString(position),
            'marketPrice': floatMaxString(marketPrice),
            'marketValue': floatMaxString(marketValue),
            'averageCost': floatMaxString(averageCost),
            'unrealizedPNL': floatMaxString(unrealizedPNL),
            'realizedPNL': floatMaxString(realizedPNL),
            'contract': contract  # Store contract for market data requests
        }

    def accountDownloadEnd(self, accountName: str):
        """Called when account update is complete"""
        self.portfolio_loaded = True
        print(f"Portfolio loaded with {len(self.portfolio)} positions")
        
        # Now request market data for portfolio positions
        if not self.market_data_requested and self.portfolio:
            self._request_portfolio_market_data()

    def _request_portfolio_market_data(self):
        """Request market data for all portfolio positions"""
        global contract_request_dictionary, history_request_dictionary
        
        print("Requesting market data for portfolio positions...")
        
        # Count non-zero positions
        active_positions = {symbol: data for symbol, data in self.portfolio.items() 
                          if float(data['position']) != 0}
        
        if not active_positions:
            print("No active positions found in portfolio.")
            print("Adding SPY as default market data for monitoring...")
            # Add SPY as default when no positions
            self._add_default_market_data()
            return
        
        for symbol, position_data in active_positions.items():
            # Set up market data request
            req_id = self.next_market_data_id
            contract = position_data['contract']
            
            # Update global dictionaries
            contract_request_dictionary[req_id] = symbol
            history_request_dictionary[self.next_historical_data_id] = symbol
            
            # Initialize data structures
            self.marketdata[symbol] = {}
            self.ohlc_data[symbol] = {}
            
            # Request real-time market data
            self.reqMktData(req_id, contract, "", False, False, [])
            
            # Request historical data
            self.reqHistoricalData(self.next_historical_data_id, contract, "", "1 D", "1 min", "TRADES", 1, 2, True, [])
            
            print(f"Requested market data for {symbol} (Position: {position_data['position']})")
            
            self.next_market_data_id += 1
            self.next_historical_data_id += 1
            
            sleep(0.1)  # Small delay between requests
        
        self.market_data_requested = True

    def _add_default_market_data(self):
        """Add default market data (SPY) when no portfolio positions exist"""
        global contract_request_dictionary, history_request_dictionary
        
        # Create SPY contract
        spy_contract = Contract()
        spy_contract.symbol = 'SPY'
        spy_contract.secType = 'STK'
        spy_contract.currency = 'USD'
        spy_contract.exchange = 'ARCA'
        
        req_id = self.next_market_data_id
        symbol = 'SPY'
        
        # Update global dictionaries
        contract_request_dictionary[req_id] = symbol
        history_request_dictionary[self.next_historical_data_id] = symbol
        
        # Initialize data structures
        self.marketdata[symbol] = {}
        self.ohlc_data[symbol] = {}
        
        # Request market data
        self.reqMktData(req_id, spy_contract, "", False, False, [])
        self.reqHistoricalData(self.next_historical_data_id, spy_contract, "", "1 D", "1 min", "TRADES", 1, 2, True, [])
        
        print(f"Added default market data for {symbol}")
        self.market_data_requested = True

    def tickPrice(self, reqId: TickerId, tickType: TickType, price: float, attrib: TickAttrib):
        if tickType == 1:
            self.marketdata[contract_request_dictionary[reqId]]['bid'] = price
        elif tickType == 2:
            self.marketdata[contract_request_dictionary[reqId]]['ask'] = price
        elif tickType == 4:
            self.marketdata[contract_request_dictionary[reqId]]['last'] = price

    def historicalData(self, reqId: int, bar: BarData):
        time = bar.date
        self.ohlc_data[history_request_dictionary[reqId]][time] = {
            'open': bar.open, 
            'high': bar.high, 
            'low': bar.low,
            'close': bar.close, 
            'volume': decimalMaxString(bar.volume)
        }

    def graceful_disconnect(self):
        """Gracefully disconnect from TWS"""
        print("Initiating graceful disconnect...")
        try:
            # Cancel market data subscriptions
            for req_id in contract_request_dictionary.keys():
                self.cancelMktData(req_id)
                print(f"Cancelled market data for request ID {req_id}")
            
            # Stop account updates
            self.reqAccountUpdates(False, self.config['account'])
            print("Stopped account updates")
            
            # Disconnect
            self.disconnect()
            print("Disconnected from TWS")
            
        except Exception as e:
            print(f"Error during disconnect: {e}")


def run_with_timeout(app, timeout_seconds=None):
    """Run the application with optional timeout"""
    if timeout_seconds is None:
        print("Starting application with no timeout...")
        print("Press Ctrl+C to exit gracefully")
    else:
        print(f"Starting application with {timeout_seconds} second timeout...")
        print("Press Ctrl+C anytime to exit gracefully")
    
    start_time = datetime.now()
    
    while not shutdown_flag:
        current_time = datetime.now()
        elapsed = (current_time - start_time).total_seconds()
        
        # Check timeout only if timeout_seconds is specified
        if timeout_seconds is not None and elapsed > timeout_seconds:
            print(f"\nTimeout reached ({timeout_seconds} seconds). Exiting...")
            break
            
        # Check connection status
        if not app.connected:
            print("Connection lost. Exiting...")
            break
        
        timeout_info = f" (Elapsed: {elapsed:.1f}s)" if timeout_seconds is None else f" (Elapsed: {elapsed:.1f}s/{timeout_seconds}s)"
        print(f'Current Time: {current_time}{timeout_info}')
        print('Balance:', app.account_balance)
        print('Equity:', app.account_equity)
        
        # Enhanced portfolio display
        if app.portfolio:
            active_positions = {symbol: data for symbol, data in app.portfolio.items() 
                              if float(data['position']) != 0}
            print(f'Portfolio: {len(active_positions)} active positions out of {len(app.portfolio)} total')
            for symbol, data in active_positions.items():
                print(f'  {symbol}: {data["position"]} shares @ ${data["marketPrice"]} (P&L: ${data["unrealizedPNL"]})')
        else:
            print('Portfolio: Loading...')
        
        # Enhanced market data display
        if app.marketdata:
            print(f'Market Data: {len(app.marketdata)} symbols')
            for symbol, data in app.marketdata.items():
                bid = data.get('bid', 'N/A')
                ask = data.get('ask', 'N/A')
                last = data.get('last', 'N/A')
                print(f'  {symbol}: Bid ${bid} | Ask ${ask} | Last ${last}')
        else:
            print('Market Data: Waiting for data...')
        
        print('OHLC Data length:', {k: len(v) for k, v in app.ohlc_data.items()})
        print('---\n')
        
        sleep(1)
    
    # Graceful shutdown
    app.graceful_disconnect()


if __name__ == '__main__':
    # Parse command line arguments
    parser = argparse.ArgumentParser(description='TWS Python Client with optional timeout')
    parser.add_argument('--timeout', '-t', type=int, default=None, 
                       help='Timeout in seconds (default: no timeout)')
    parser.add_argument('--no-timeout', action='store_true', 
                       help='Run without timeout (same as not specifying --timeout)')
    parser.add_argument('--env', '-e', choices=['paper', 'live'], default=None,
                       help='Trading environment: paper or live (default: from .env file)')
    parser.add_argument('--show-config', action='store_true',
                       help='Show configuration and exit')
    parser.add_argument('--skip-market-check', action='store_true',
                       help='Skip market status check at startup')
    
    args = parser.parse_args()
    
    try:
        # Load configuration
        config = get_config(args.env)
        
        if args.show_config:
            from env_config import print_config
            print_config(config)
            sys.exit(0)
        
        # Check market status (unless skipped)
        if not args.skip_market_check:
            print("Checking US market status...")
            market_is_open = check_market_status()
            
            # For live trading, give extra warning if markets are closed
            if config['environment'] == 'live' and not market_is_open:
                print("\nWARNING: You are connecting to LIVE trading while markets are closed!")
                print("This may result in limited market data and delayed order execution.")
                print("Consider using paper trading for testing during closed hours.\n")
                
                try:
                    response = input("Do you want to continue with LIVE trading? (y/N): ").lower().strip()
                    if response not in ['y', 'yes']:
                        print("Exiting for safety...")
                        sys.exit(0)
                    else:
                        print("Proceeding with LIVE trading during closed hours...")
                except (EOFError, KeyboardInterrupt):
                    print("\nExiting...")
                    sys.exit(0)
        
        # Determine timeout value
        timeout_seconds = None if args.no_timeout else args.timeout
        
        print("TWS Python Client - Environment Configuration Version")
        print("=" * 60)
        print(f"Environment: {config['environment'].upper()}")
        print(f"Host: {config['host']}:{config['port']}")
        account_masked = f"{config['account'][:3]}***{config['account'][-3:]}" if len(config['account']) > 6 else "***"
        print(f"Account: {account_masked}")
        print("=" * 60)
        
        app = TradeApp(config)
        
        # Connect to TWS
        print(f"Connecting to TWS at {config['host']}:{config['port']} with client ID {config['client_id']}")
        app.connect(config['host'], config['port'], config['client_id'])
        sleep(2)  # Give time for connection

        # Start the API thread
        app_thread = Thread(target=app.run, daemon=True)
        app_thread.start()
        sleep(1)

        if not app.connected:
            print("Failed to establish connection. Please check TWS/Gateway is running.")
            sys.exit(1)

        # Request account updates (this will trigger portfolio loading)
        app.reqAccountUpdates(True, config['account'])

        # Wait for portfolio to load
        print("Loading portfolio positions...")
        max_wait = 10  # Maximum wait time in seconds
        wait_time = 0
        while not app.portfolio_loaded and wait_time < max_wait:
            sleep(0.5)
            wait_time += 0.5
            
        if not app.portfolio_loaded:
            print("Warning: Portfolio data not loaded within timeout")
        
        # Give additional time for market data requests to be processed
        sleep(3)

        # Run with optional timeout
        run_with_timeout(app, timeout_seconds)
        
    except KeyboardInterrupt:
        print("\nKeyboard interrupt received")
        app.graceful_disconnect()
    except Exception as e:
        print(f"Unexpected error: {e}")
        if 'app' in locals():
            app.graceful_disconnect()
    finally:
        print("Application terminated.")
        sys.exit(0)