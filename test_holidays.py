"""
Test script to simulate market status on holidays
"""
import sys
sys.path.append('.')

from market_status import MarketStatusChecker
from datetime import datetime
import pytz

def test_holiday_simulation():
    """Simulate market status on specific dates"""
    checker = MarketStatusChecker()
    
    # Test Christmas Day 2025 (Thursday)
    print("Simulating Christmas Day 2025 (Thursday, December 25)...")
    
    # Create a mock datetime for Christmas Day at 10 AM
    ny_tz = pytz.timezone('America/New_York')
    christmas_morning = ny_tz.localize(datetime(2025, 12, 25, 10, 0, 0))
    
    # Temporarily override the current time for testing
    original_method = checker._check_by_time
    
    def mock_check_by_time():
        return {
            'is_open': False,
            'reason': 'Market Holiday - Christmas Day',
            'current_time_ny': christmas_morning.strftime('%Y-%m-%d %H:%M:%S %Z'),
            'next_open': checker._get_next_open_time(christmas_morning)
        }
    
    checker._check_by_time = mock_check_by_time
    
    # Test the output
    status = checker.get_market_status_api()
    if status:
        print("\n" + "="*60)
        print("SIMULATED MARKET STATUS - CHRISTMAS DAY")
        print("="*60)
        print(f"Status: {'OPEN' if status['is_open'] else 'CLOSED'}")
        print(f"Reason: {status['reason']}")
        print(f"Current Time (NY): {status['current_time_ny']}")
        if 'next_open' in status:
            print(f"Next market open: {status['next_open']}")
        print("="*60)
    
    # Restore original method
    checker._check_by_time = original_method

if __name__ == "__main__":
    test_holiday_simulation()