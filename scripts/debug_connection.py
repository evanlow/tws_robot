"""
Debug TWS Connection - Try multiple client IDs and check for errors
"""


import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
del _os, _sys

import threading
import time
from ibapi.client import EClient
from ibapi.wrapper import EWrapper
from config.env_config import get_config

class DebugWrapper(EWrapper):
    def __init__(self):
        super().__init__()
        self.connected = False
        self.errors = []
        
    def connectAck(self):
        print("✅ connectAck() received")
        
    def nextValidId(self, orderId):
        print(f"✅ nextValidId() received: {orderId}")
        self.connected = True
        
    def error(self, reqId, errorCode, errorString, advancedOrderRejectJson=""):
        msg = f"Error {errorCode}: {errorString}"
        print(f"🔴 {msg}")
        self.errors.append(msg)
        
    def connectionClosed(self):
        print("⚠️  connectionClosed() called")

class DebugClient(EClient):
    def __init__(self, wrapper):
        super().__init__(wrapper)

def try_client_id(client_id, timeout=5):
    """Try connecting with a specific client ID"""
    
    print(f"\n🔄 Trying Client ID: {client_id}")
    print("-" * 30)
    
    config = get_config('live')
    wrapper = DebugWrapper()
    client = DebugClient(wrapper)
    
    try:
        # Try to connect
        print(f"🔌 Connecting to {config['host']}:{config['port']} with ID {client_id}...")
        
        # Use a thread to prevent hanging
        def connect_thread():
            try:
                client.connect(config['host'], config['port'], client_id)
                client.run()
            except Exception as e:
                print(f"❌ Connection thread error: {e}")
        
        thread = threading.Thread(target=connect_thread, daemon=True)
        thread.start()
        
        # Wait for connection
        start_time = time.time()
        while (time.time() - start_time) < timeout:
            if wrapper.connected:
                elapsed = time.time() - start_time
                print(f"✅ SUCCESS with Client ID {client_id} in {elapsed:.1f}s!")
                client.disconnect()
                return True
                
            if wrapper.errors:
                print(f"❌ Failed with errors:")
                for error in wrapper.errors[-3:]:  # Show last 3 errors
                    print(f"   {error}")
                client.disconnect()
                return False
                
            time.sleep(0.1)
        
        print(f"⏰ Timeout after {timeout}s")
        if client.isConnected():
            client.disconnect()
        return False
        
    except Exception as e:
        print(f"❌ Exception: {e}")
        return False

def main():
    print("🔍 DEBUG TWS CONNECTION - Multiple Client IDs")
    print("=" * 50)
    
    # Try different client IDs (starting with 0 which is often recommended)
    client_ids = [0, 1, 2, 3, 10, 100, 999]
    
    for cid in client_ids:
        success = try_client_id(cid, timeout=3)
        if success:
            print(f"\n🎉 Found working Client ID: {cid}")
            print("   You can now use this ID in your trading bot!")
            break
        time.sleep(1)  # Brief pause between attempts
    else:
        print(f"\n❌ No client IDs worked. Possible issues:")
        print("   1. TWS needs to be restarted after API settings change")
        print("   2. Another application is using the API")
        print("   3. API is still not fully enabled")
        print("   4. Firewall blocking the connection")
        print("\n💡 Try restarting TWS and running this test again")

if __name__ == "__main__":
    main()