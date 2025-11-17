"""
Non-blocking TWS API Connection Test
Uses threading and timeouts to prevent hanging
"""

import threading
import time
import signal
import sys
from ibapi.client import EClient
from ibapi.wrapper import EWrapper
from env_config import get_config

class TimeoutException(Exception):
    pass

def timeout_handler(signum, frame):
    raise TimeoutException("Connection attempt timed out")

class QuickWrapper(EWrapper):
    def __init__(self):
        super().__init__()
        self.connection_state = "disconnected"  # disconnected, connecting, connected, failed
        self.error_messages = []
        
    def connectAck(self):
        print("✅ TWS API handshake successful")
        self.connection_state = "connected"
        
    def nextValidId(self, orderId):
        print(f"✅ Ready to trade! Next Order ID: {orderId}")
        self.connection_state = "ready"
        
    def error(self, reqId, errorCode, errorString, advancedOrderRejectJson=""):
        error_msg = f"Error {errorCode}: {errorString}"
        print(f"❌ {error_msg}")
        self.error_messages.append(error_msg)
        
        # Common connection errors that indicate failure
        if errorCode in [502, 503, 504, 1100, 2104, 2106, 2158]:
            self.connection_state = "failed"

class QuickClient(EClient):
    def __init__(self, wrapper):
        super().__init__(wrapper)
        self.connection_thread = None
        
    def start_connection_thread(self, host, port, client_id):
        """Start connection in a separate thread to avoid blocking"""
        self.connection_thread = threading.Thread(
            target=self._connect_worker, 
            args=(host, port, client_id),
            daemon=True
        )
        self.connection_thread.start()
        
    def _connect_worker(self, host, port, client_id):
        """Worker thread for connection"""
        try:
            print(f"🔌 Attempting connection to {host}:{port}...")
            self.connect(host, port, client_id)
            self.run()  # Start message processing
        except Exception as e:
            print(f"❌ Connection thread error: {e}")

def quick_connection_test(timeout=8):
    """Quick non-blocking connection test"""
    
    print("🚀 QUICK TWS CONNECTION TEST (Non-blocking)")
    print("="*50)
    
    # Get live config (we know from diagnostics that it's available)
    config = get_config('live')
    print(f"📡 Target: {config['host']}:{config['port']} (Account: {config['account'][:3]}***)")
    
    # Create client with timeout protection
    wrapper = QuickWrapper()
    client = QuickClient(wrapper)
    
    start_time = time.time()
    
    try:
        # Start non-blocking connection
        client.start_connection_thread(config['host'], config['port'], 888)
        
        # Monitor connection with timeout
        print(f"⏰ Monitoring connection (timeout: {timeout}s)...")
        
        while (time.time() - start_time) < timeout:
            elapsed = time.time() - start_time
            
            if wrapper.connection_state == "ready":
                print(f"✅ SUCCESS! Connected and ready in {elapsed:.1f}s")
                return True
                
            elif wrapper.connection_state == "connected":
                print(f"🔄 Connected, waiting for ready state... ({elapsed:.1f}s)")
                
            elif wrapper.connection_state == "failed":
                print(f"❌ Connection failed in {elapsed:.1f}s")
                if wrapper.error_messages:
                    print("   Last errors:")
                    for msg in wrapper.error_messages[-3:]:
                        print(f"   - {msg}")
                return False
                
            time.sleep(0.2)
        
        # Timeout reached
        elapsed = time.time() - start_time
        print(f"⏰ TIMEOUT after {elapsed:.1f}s")
        print(f"   State: {wrapper.connection_state}")
        print(f"   Client connected: {client.isConnected()}")
        
        return False
        
    except Exception as e:
        print(f"❌ Test exception: {e}")
        return False
        
    finally:
        try:
            if client.isConnected():
                print("🔌 Cleaning up connection...")
                client.disconnect()
        except:
            pass

def diagnose_connection_issue():
    """Provide diagnosis and suggestions"""
    print("\n🔍 CONNECTION DIAGNOSIS:")
    print("-" * 30)
    
    # Test raw socket again to confirm
    import socket
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(3)
        result = sock.connect_ex(('127.0.0.1', 7496))
        sock.close()
        
        if result == 0:
            print("✅ Raw socket connection: OK")
            print("❓ Issue is likely with TWS API configuration")
            print("\n💡 SUGGESTED FIXES:")
            print("1. Check TWS API Settings:")
            print("   - File → Global Configuration → API → Settings")
            print("   - Ensure 'Enable ActiveX and Socket Clients' is checked")
            print("   - Verify socket port is 7496 for live trading")
            print("   - Try changing 'Master API client ID' to 0")
            print("   - Uncheck 'Read-Only API' if checked")
            print("\n2. Restart TWS and try again")
            print("3. Try a different client ID (current: 888)")
            print("4. Check if another application is using the API")
        else:
            print("❌ Raw socket connection: FAILED")
            print("   TWS may have stopped or port changed")
            
    except Exception as e:
        print(f"❌ Socket test error: {e}")

if __name__ == "__main__":
    success = quick_connection_test()
    
    if not success:
        diagnose_connection_issue()
    else:
        print("\n🎉 Your TWS API is working correctly!")
        print("   → You can now test your enhanced trading bot")