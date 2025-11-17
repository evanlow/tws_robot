"""
Minimal TWS API Connection Test
Tests the actual TWS API connection with detailed logging and timeout
"""

import threading
import time
from ibapi.client import EClient
from ibapi.wrapper import EWrapper
from env_config import get_config

class MinimalWrapper(EWrapper):
    def __init__(self):
        super().__init__()
        self.connected = False
        self.connection_time = None
        self.next_valid_id = None
        
    def connectAck(self):
        print("✅ connectAck() received - Connection acknowledged")
        
    def connectionClosed(self):
        print("⚠️  connectionClosed() called")
        self.connected = False
        
    def error(self, reqId, errorCode, errorString, advancedOrderRejectJson=""):
        print(f"❌ Error - ID: {reqId}, Code: {errorCode}, Msg: {errorString}")
        
    def nextValidId(self, orderId):
        print(f"✅ nextValidId() received: {orderId}")
        self.next_valid_id = orderId
        self.connected = True
        self.connection_time = time.time()

class MinimalClient(EClient):
    def __init__(self, wrapper):
        super().__init__(wrapper)

def test_minimal_connection(env='live', timeout=10):
    """Test minimal TWS API connection with timeout"""
    
    print(f"🔄 Testing minimal TWS API connection ({env})...")
    
    # Get config
    config = get_config(env)
    print(f"📡 Connecting to {config['host']}:{config['port']} (Account: {config['account'][:3]}***{config['account'][-3:]})")
    
    # Create wrapper and client
    wrapper = MinimalWrapper()
    client = MinimalClient(wrapper)
    
    # Connection tracking
    start_time = time.time()
    
    try:
        # Connect
        print("🔌 Calling client.connect()...")
        client.connect(config['host'], config['port'], clientId=999)
        
        # Start message processing in separate thread
        print("🧵 Starting API message thread...")
        api_thread = threading.Thread(target=client.run, daemon=True)
        api_thread.start()
        
        # Wait for connection with timeout
        print(f"⏰ Waiting for connection (timeout: {timeout}s)...")
        wait_start = time.time()
        
        while not wrapper.connected and (time.time() - wait_start) < timeout:
            if not client.isConnected():
                print("❌ Client reports not connected")
                break
            time.sleep(0.1)
        
        elapsed = time.time() - start_time
        
        if wrapper.connected:
            print(f"✅ SUCCESS! Connected in {elapsed:.2f}s")
            print(f"   Next Valid Order ID: {wrapper.next_valid_id}")
            
            # Test a simple request
            print("📊 Testing account summary request...")
            client.reqAccountSummary(1, "All", "$LEDGER")
            time.sleep(2)
            
            return True
        else:
            print(f"❌ TIMEOUT! Failed to connect within {timeout}s")
            print(f"   Client connected: {client.isConnected()}")
            print(f"   Wrapper connected: {wrapper.connected}")
            return False
            
    except Exception as e:
        print(f"❌ EXCEPTION: {e}")
        return False
        
    finally:
        if client.isConnected():
            print("🔌 Disconnecting...")
            client.disconnect()
            time.sleep(1)

def main():
    print("="*60)
    print("MINIMAL TWS API CONNECTION TEST")
    print("="*60)
    
    # Test live connection (since our diagnostic showed it's available)
    success = test_minimal_connection('live', timeout=15)
    
    if success:
        print("\n🎉 Connection test PASSED!")
        print("   → Your enhanced TWS client should work")
        print("   → API is responding normally")
    else:
        print("\n⚠️  Connection test FAILED!")
        print("   → Check TWS API settings:")
        print("     - Go to TWS → File → Global Configuration → API → Settings")
        print("     - Ensure 'Enable ActiveX and Socket Clients' is checked")
        print("     - Check 'Socket port' matches 7496 (live) or 7497 (paper)")
        print("     - Verify 'Master API client ID' is not conflicting")
        print("     - Try a different client ID if issues persist")

if __name__ == "__main__":
    main()