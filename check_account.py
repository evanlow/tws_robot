"""
Quick Account Status Check

Connects to your IBKR account and displays:
- Account balance
- Current positions
- Buying power
- P&L (if available)
"""

from ibapi.client import EClient
from ibapi.wrapper import EWrapper
from ibapi.contract import Contract
from datetime import datetime
from time import sleep
from threading import Thread
import signal
import sys

from env_config import get_config

# Global flag for graceful shutdown
shutdown_flag = False

def signal_handler(sig, frame):
    global shutdown_flag
    print('\nShutdown requested...')
    shutdown_flag = True

signal.signal(signal.SIGINT, signal_handler)

class AccountChecker(EWrapper, EClient):
    def __init__(self, config):
        EClient.__init__(self, self)
        self.config = config
        
        # Account data
        self.account_values = {}
        self.positions = []
        self.account_summary = {}
        self.ready = False
        self.data_received = False
        
    def connectAck(self):
        print("[OK] Connected to TWS/Gateway")
        
    def nextValidId(self, orderId):
        print(f"[OK] Connection ready (Order ID: {orderId})")
        self.ready = True
        
        # Request account updates
        self.reqAccountUpdates(True, self.config['account'])
        
    def updateAccountValue(self, key, val, currency, accountName):
        """Called for each account value update"""
        if currency == 'USD' or currency == '':
            self.account_values[key] = val
            
    def updatePortfolio(self, contract, position, marketPrice, marketValue,
                       averageCost, unrealizedPNL, realizedPNL, accountName):
        """Called for each position"""
        self.positions.append({
            'symbol': contract.symbol,
            'secType': contract.secType,
            'position': position,
            'avgCost': averageCost,
            'marketPrice': marketPrice,
            'marketValue': marketValue,
            'unrealizedPNL': unrealizedPNL,
            'realizedPNL': realizedPNL
        })
        
    def accountDownloadEnd(self, accountName):
        """Called when account data download is complete"""
        print(f"[OK] Account data received for {accountName}")
        self.data_received = True
        
    def error(self, reqId, errorTime, errorCode, errorString, advancedOrderRejectJson=""):
        """Handle errors - updated signature with errorTime parameter"""
        if errorCode in [2104, 2106, 2158]:  # Connection info messages
            print(f"[INFO] {errorString}")
        elif errorCode == 2119:  # Market data farm disconnected
            print(f"[INFO] {errorString}")
        elif errorCode == 504:  # Not connected
            pass  # Ignore, we're handling disconnect
        else:
            print(f"[ERROR {errorCode}] {errorString}")

def main():
    print("="*70)
    print("IBKR ACCOUNT STATUS CHECK")
    print("="*70)
    print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Parse command line argument
    env = 'paper'  # default
    if len(sys.argv) > 1:
        arg = sys.argv[1].lower()
        if arg in ['live', 'l']:
            env = 'live'
        elif arg in ['paper', 'p']:
            env = 'paper'
        else:
            print(f"\nUsage: python check_account.py [paper|live]")
            print(f"Unknown argument: {arg}")
            return
    
    # Get config
    try:
        config = get_config(env)
        print(f"\nEnvironment: {env.upper()}")
        print(f"Connecting to: {config['host']}:{config['port']}")
        print(f"Account: {config['account']}")
    except Exception as e:
        print(f"[ERROR] Failed to load configuration: {e}")
        return
    
    # Create client
    app = AccountChecker(config)
    
    # Connect
    try:
        print("\nConnecting...")
        app.connect(config['host'], config['port'], clientId=999)
        
        # Start message processing thread
        api_thread = Thread(target=app.run, daemon=True)
        api_thread.start()
        
        # Wait for connection
        print("Waiting for connection...")
        timeout = 0
        while not app.ready and timeout < 50:
            sleep(0.1)
            timeout += 1
            
        if not app.ready:
            print("[ERROR] Connection timeout")
            return
            
        # Wait for account data
        print("Downloading account data...")
        timeout = 0
        while not app.data_received and timeout < 100:
            sleep(0.1)
            timeout += 1
            
        if not app.data_received:
            print("[WARNING] Account data not fully received, showing partial data...")
        
        # Display results
        print("\n" + "="*70)
        print("ACCOUNT INFORMATION")
        print("="*70)
        
        # Key account values
        important_keys = [
            'NetLiquidation', 'TotalCashValue', 'TotalCashBalance',
            'CashBalance', 'AvailableFunds', 'BuyingPower', 
            'GrossPositionValue', 'StockMarketValue',
            'UnrealizedPnL', 'RealizedPnL', 'Cushion'
        ]
        
        print("\nAccount Values:")
        found_any = False
        for key in important_keys:
            if key in app.account_values:
                found_any = True
                value = app.account_values[key]
                try:
                    # Try to format as currency if numeric
                    num_value = float(value)
                    print(f"  {key:25s}: ${num_value:,.2f}")
                except:
                    print(f"  {key:25s}: {value}")
        
        if not found_any:
            print("  (No standard account values received)")
            print("  Checking alternative keys...")
            # Check for values by currency
            for key, value in app.account_values.items():
                if 'NetLiquidationByCurrency' in key or 'CashBalance' in key:
                    try:
                        num_value = float(value)
                        print(f"  {key:25s}: ${num_value:,.2f}")
                    except:
                        print(f"  {key:25s}: {value}")
        
        # Positions
        if app.positions:
            print(f"\nCurrent Positions ({len(app.positions)}):")
            print("-" * 70)
            for pos in app.positions:
                print(f"  {pos['symbol']:6s} {pos['secType']:6s}")
                print(f"    Position: {pos['position']} shares")
                print(f"    Avg Cost: ${pos['avgCost']:.2f}")
                print(f"    Market Price: ${pos['marketPrice']:.2f}")
                print(f"    Market Value: ${pos['marketValue']:,.2f}")
                print(f"    Unrealized P&L: ${pos['unrealizedPNL']:,.2f}")
                if pos['realizedPNL'] != 0:
                    print(f"    Realized P&L: ${pos['realizedPNL']:,.2f}")
                print()
        else:
            print("\nNo current positions")
        
        # Other account values (less important)
        print("\nOther Account Information:")
        for key, value in app.account_values.items():
            if key not in important_keys:
                print(f"  {key}: {value}")
        
        print("\n" + "="*70)
        print("STATUS CHECK COMPLETE")
        print("="*70)
        
    except Exception as e:
        print(f"[ERROR] {e}")
        import traceback
        traceback.print_exc()
    finally:
        # Disconnect
        print("\nDisconnecting...")
        app.reqAccountUpdates(False, config['account'])
        app.disconnect()
        sleep(0.5)

if __name__ == '__main__':
    main()
