"""
Quick TWS Connection Test Utility
Tests connection to TWS/Gateway with timeout and better error reporting
"""

import socket
import time
from datetime import datetime
import pytz
from env_config import get_config

def test_socket_connection(host, port, timeout=5):
    """Test raw socket connection to TWS/Gateway"""
    try:
        print(f"Testing socket connection to {host}:{port}...")
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        
        start_time = time.time()
        result = sock.connect_ex((host, port))
        connect_time = time.time() - start_time
        
        sock.close()
        
        if result == 0:
            print(f"✅ Socket connection successful in {connect_time:.2f}s")
            return True
        else:
            print(f"❌ Socket connection failed (Error: {result})")
            return False
            
    except socket.timeout:
        print(f"⏰ Socket connection timed out after {timeout}s")
        return False
    except Exception as e:
        print(f"❌ Socket connection error: {e}")
        return False

def check_maintenance_window():
    """Check if we're likely in a maintenance window"""
    ny_tz = pytz.timezone('America/New_York')
    now = datetime.now(ny_tz)
    
    print(f"\n🕐 Current time: {now.strftime('%Y-%m-%d %H:%M:%S %Z')} ({now.strftime('%A')})")
    
    # IBKR maintenance windows (approximate)
    is_weekend = now.weekday() >= 5  # Saturday=5, Sunday=6
    is_late_night = now.hour >= 23 or now.hour <= 6
    is_saturday_night = now.weekday() == 5 and now.hour >= 22
    is_sunday_early = now.weekday() == 6 and now.hour <= 8
    
    maintenance_likely = is_saturday_night or is_sunday_early
    
    if maintenance_likely:
        print("⚠️  Likely in weekly maintenance window (Sat 10PM - Sun 8AM ET)")
        print("   → Server may be unavailable or unstable")
    elif is_weekend and is_late_night:
        print("⚠️  Weekend late night - reduced server availability possible")
    elif is_weekend:
        print("ℹ️  Weekend - some services may have reduced availability")
    else:
        print("✅ Normal trading hours window - servers should be available")
    
    return maintenance_likely

def test_all_configurations():
    """Test both paper and live configurations"""
    
    print("="*60)
    print("TWS CONNECTION DIAGNOSTIC TEST")
    print("="*60)
    
    # Check maintenance window
    in_maintenance = check_maintenance_window()
    
    # Test both configurations
    configs = {
        'Paper Trading': get_config('paper'),
        'Live Trading': get_config('live')
    }
    
    results = {}
    
    for name, config in configs.items():
        print(f"\n📊 Testing {name}:")
        print(f"   Host: {config['host']}:{config['port']}")
        print(f"   Account: {config['account'][:3]}***{config['account'][-3:]}")
        
        success = test_socket_connection(config['host'], config['port'], timeout=3)
        results[name] = success
        
        if not success and not in_maintenance:
            print("   💡 Suggestions:")
            print("      - Check if TWS/Gateway is running")
            print("      - Verify API is enabled in TWS Global Configuration")
            print("      - Confirm correct port number")
            if name == 'Live Trading':
                print("      - Ensure you're logged into live account in TWS")
            else:
                print("      - Ensure you're in paper trading mode in TWS")
    
    # Summary
    print(f"\n{'='*60}")
    print("SUMMARY:")
    for name, success in results.items():
        status = "✅ AVAILABLE" if success else "❌ UNAVAILABLE"
        print(f"  {name}: {status}")
    
    if in_maintenance and not any(results.values()):
        print("\n⏰ All connections failed during likely maintenance window.")
        print("   → Try again after Sunday 8:00 AM ET")
        print("   → Check IBKR system status: https://www.interactivebrokers.com/en/software/systemStatus.php")
    
    if any(results.values()):
        available_configs = [name for name, success in results.items() if success]
        print(f"\n🚀 Ready to test with: {', '.join(available_configs)}")
        return True
    else:
        print(f"\n⚠️  No connections available at this time")
        return False

if __name__ == "__main__":
    test_all_configurations()