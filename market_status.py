"""
Market status checker for US stock markets.
Checks if NYSE/NASDAQ are currently open for trading.
"""

import requests
import json
from datetime import datetime, timezone
import pytz
from typing import Dict, Optional

class MarketStatusChecker:
    """Check if US stock markets are open"""
    
    def __init__(self):
        self.ny_tz = pytz.timezone('America/New_York')
    
    def get_market_status_api(self) -> Optional[Dict]:
        """
        Get market status from a free API service.
        Using marketstack.com free tier (no API key needed for basic info)
        """
        try:
            # Alternative free APIs you can use:
            # 1. Alpha Vantage (requires free API key)
            # 2. Financial Modeling Prep (requires free API key)  
            # 3. Yahoo Finance (unofficial, may be rate limited)
            
            # Using a simple approach - check current time in NY timezone
            return self._check_by_time()
            
        except Exception as e:
            print(f"API request failed: {e}")
            return self._check_by_time()
    
    def _check_by_time(self) -> Dict:
        """
        Check market status based on time rules.
        NYSE/NASDAQ: 9:30 AM - 4:00 PM ET, Monday-Friday (excluding holidays)
        """
        now_ny = datetime.now(self.ny_tz)
        
        # Check if it's a weekend
        if now_ny.weekday() >= 5:  # Saturday=5, Sunday=6
            return {
                'is_open': False,
                'reason': 'Weekend - Markets closed',
                'current_time_ny': now_ny.strftime('%Y-%m-%d %H:%M:%S %Z'),
                'next_open': self._get_next_open_time(now_ny)
            }
        
        # Check if it's during market hours (9:30 AM - 4:00 PM ET)
        market_open = now_ny.replace(hour=9, minute=30, second=0, microsecond=0)
        market_close = now_ny.replace(hour=16, minute=0, second=0, microsecond=0)
        
        if market_open <= now_ny <= market_close:
            return {
                'is_open': True,
                'reason': 'Markets are OPEN for regular trading',
                'current_time_ny': now_ny.strftime('%Y-%m-%d %H:%M:%S %Z'),
                'closes_at': market_close.strftime('%H:%M:%S %Z')
            }
        elif now_ny < market_open:
            return {
                'is_open': False,
                'reason': 'Pre-market - Regular trading starts at 9:30 AM ET',
                'current_time_ny': now_ny.strftime('%Y-%m-%d %H:%M:%S %Z'),
                'opens_at': market_open.strftime('%H:%M:%S %Z')
            }
        else:  # After market close
            return {
                'is_open': False,
                'reason': 'After-hours - Regular trading ended at 4:00 PM ET',
                'current_time_ny': now_ny.strftime('%Y-%m-%d %H:%M:%S %Z'),
                'next_open': self._get_next_open_time(now_ny)
            }
    
    def _get_next_open_time(self, current_time) -> str:
        """Get the next market open time"""
        # If it's Friday after close or weekend, next open is Monday 9:30 AM
        if current_time.weekday() == 4 and current_time.hour >= 16:  # Friday after 4 PM
            days_ahead = 3  # Next Monday
        elif current_time.weekday() >= 5:  # Weekend
            days_ahead = 7 - current_time.weekday()  # Days until Monday
        else:  # Weekday before open or after close
            days_ahead = 1 if current_time.hour >= 16 else 0
        
        next_open = current_time.replace(hour=9, minute=30, second=0, microsecond=0)
        if days_ahead > 0:
            next_open = next_open.replace(day=current_time.day + days_ahead)
        
        return next_open.strftime('%Y-%m-%d %H:%M:%S %Z')
    
    def print_market_status(self) -> bool:
        """Print market status and return True if open"""
        status = self.get_market_status_api()
        
        if status:
            print("\n" + "="*60)
            print("US STOCK MARKET STATUS")
            print("="*60)
            print(f"Status: {'OPEN' if status['is_open'] else 'CLOSED'}")
            print(f"Reason: {status['reason']}")
            print(f"Current Time (NY): {status['current_time_ny']}")
            
            if status['is_open']:
                print(f"Market closes at: {status.get('closes_at', 'N/A')}")
            else:
                if 'opens_at' in status:
                    print(f"Market opens at: {status['opens_at']}")
                elif 'next_open' in status:
                    print(f"Next market open: {status['next_open']}")
            
            print("="*60)
            
            if not status['is_open']:
                print("Note: You may experience limited market data and execution delays")
                print("when markets are closed. Paper trading and historical data remain available.")
            
            print()
            
            return status['is_open']
        else:
            print("Unable to determine market status")
            return False

# Convenience function
def check_market_status() -> bool:
    """Quick check if markets are open"""
    checker = MarketStatusChecker()
    return checker.print_market_status()

if __name__ == "__main__":
    # Test the market status checker
    check_market_status()