"""
Market status checker for US stock markets.
Checks if NYSE/NASDAQ are currently open for trading.
Includes holiday detection for accurate market status.
"""

import requests
import json
from datetime import datetime, timezone, date
import pytz
from typing import Dict, Optional

class MarketStatusChecker:
    """Check if US stock markets are open"""
    
    def __init__(self):
        self.ny_tz = pytz.timezone('America/New_York')
    
    def _get_us_market_holidays(self, year: int) -> set:
        """
        Get US stock market holidays for a given year.
        NYSE/NASDAQ observe these holidays when markets are closed.
        """
        holidays = set()
        
        # New Year's Day
        new_years = date(year, 1, 1)
        if new_years.weekday() == 5:  # Saturday
            holidays.add(date(year, 1, 3))  # Observed Monday
        elif new_years.weekday() == 6:  # Sunday
            holidays.add(date(year, 1, 2))  # Observed Monday
        else:
            holidays.add(new_years)
        
        # Martin Luther King Jr. Day (3rd Monday in January)
        jan_1 = date(year, 1, 1)
        days_after_jan_1 = (7 - jan_1.weekday()) % 7
        first_monday = jan_1.replace(day=1 + days_after_jan_1)
        mlk_day = first_monday.replace(day=first_monday.day + 14)  # 3rd Monday
        holidays.add(mlk_day)
        
        # Presidents' Day (3rd Monday in February)
        feb_1 = date(year, 2, 1)
        days_after_feb_1 = (7 - feb_1.weekday()) % 7
        first_monday_feb = feb_1.replace(day=1 + days_after_feb_1)
        presidents_day = first_monday_feb.replace(day=first_monday_feb.day + 14)  # 3rd Monday
        holidays.add(presidents_day)
        
        # Good Friday (Friday before Easter) - Complex calculation
        easter = self._calculate_easter(year)
        good_friday = easter.replace(day=easter.day - 2)
        holidays.add(good_friday)
        
        # Memorial Day (Last Monday in May)
        may_31 = date(year, 5, 31)
        days_back = (may_31.weekday() + 1) % 7
        if days_back == 0:
            days_back = 7
        memorial_day = may_31.replace(day=31 - days_back + 1)
        holidays.add(memorial_day)
        
        # Juneteenth (June 19) - Federal holiday since 2021
        if year >= 2022:  # Markets started observing in 2022
            juneteenth = date(year, 6, 19)
            if juneteenth.weekday() == 5:  # Saturday
                holidays.add(date(year, 6, 18))  # Friday
            elif juneteenth.weekday() == 6:  # Sunday
                holidays.add(date(year, 6, 20))  # Monday
            else:
                holidays.add(juneteenth)
        
        # Independence Day (July 4)
        july_4 = date(year, 7, 4)
        if july_4.weekday() == 5:  # Saturday
            holidays.add(date(year, 7, 3))  # Friday
        elif july_4.weekday() == 6:  # Sunday
            holidays.add(date(year, 7, 5))  # Monday
        else:
            holidays.add(july_4)
        
        # Labor Day (1st Monday in September)
        sep_1 = date(year, 9, 1)
        days_after_sep_1 = (7 - sep_1.weekday()) % 7
        labor_day = sep_1.replace(day=1 + days_after_sep_1)
        holidays.add(labor_day)
        
        # Thanksgiving (4th Thursday in November)
        nov_1 = date(year, 11, 1)
        days_after_nov_1 = (3 - nov_1.weekday()) % 7  # Thursday = 3
        first_thursday = nov_1.replace(day=1 + days_after_nov_1)
        thanksgiving = first_thursday.replace(day=first_thursday.day + 21)  # 4th Thursday
        holidays.add(thanksgiving)
        
        # Christmas Day (December 25)
        christmas = date(year, 12, 25)
        if christmas.weekday() == 5:  # Saturday
            holidays.add(date(year, 12, 24))  # Friday
        elif christmas.weekday() == 6:  # Sunday
            holidays.add(date(year, 12, 26))  # Monday
        else:
            holidays.add(christmas)
        
        return holidays
    
    def _calculate_easter(self, year: int) -> date:
        """Calculate Easter Sunday using the algorithm"""
        # Anonymous Gregorian algorithm
        a = year % 19
        b = year // 100
        c = year % 100
        d = b // 4
        e = b % 4
        f = (b + 8) // 25
        g = (b - f + 1) // 3
        h = (19 * a + b - d - g + 15) % 30
        i = c // 4
        k = c % 4
        l = (32 + 2 * e + 2 * i - h - k) % 7
        m = (a + 11 * h + 22 * l) // 451
        n = (h + l - 7 * m + 114) // 31
        p = (h + l - 7 * m + 114) % 31
        return date(year, n, p + 1)
    
    def _is_market_holiday(self, check_date: date) -> bool:
        """Check if a given date is a market holiday"""
        holidays = self._get_us_market_holidays(check_date.year)
        return check_date in holidays
    
    def _get_holiday_name(self, check_date: date) -> str:
        """Get the name of the holiday for a given date"""
        year = check_date.year
        
        # Check each holiday
        if check_date == date(year, 1, 1) or (check_date.month == 1 and check_date.day <= 3 and check_date.weekday() == 0):
            return "New Year's Day"
        
        # MLK Day (3rd Monday in January)
        jan_1 = date(year, 1, 1)
        days_after_jan_1 = (7 - jan_1.weekday()) % 7
        first_monday = jan_1.replace(day=1 + days_after_jan_1)
        mlk_day = first_monday.replace(day=first_monday.day + 14)
        if check_date == mlk_day:
            return "Martin Luther King Jr. Day"
        
        # Presidents' Day (3rd Monday in February)
        feb_1 = date(year, 2, 1)
        days_after_feb_1 = (7 - feb_1.weekday()) % 7
        first_monday_feb = feb_1.replace(day=1 + days_after_feb_1)
        presidents_day = first_monday_feb.replace(day=first_monday_feb.day + 14)
        if check_date == presidents_day:
            return "Presidents' Day"
        
        # Good Friday
        easter = self._calculate_easter(year)
        good_friday = easter.replace(day=easter.day - 2)
        if check_date == good_friday:
            return "Good Friday"
        
        # Memorial Day (Last Monday in May)
        may_31 = date(year, 5, 31)
        days_back = (may_31.weekday() + 1) % 7
        if days_back == 0:
            days_back = 7
        memorial_day = may_31.replace(day=31 - days_back + 1)
        if check_date == memorial_day:
            return "Memorial Day"
        
        # Juneteenth
        if year >= 2022 and ((check_date.month == 6 and check_date.day == 19) or 
                            (check_date.month == 6 and check_date.day in [18, 20] and check_date.weekday() in [0, 4])):
            return "Juneteenth"
        
        # Independence Day
        if ((check_date.month == 7 and check_date.day == 4) or 
            (check_date.month == 7 and check_date.day in [3, 5] and check_date.weekday() in [0, 4])):
            return "Independence Day"
        
        # Labor Day (1st Monday in September)
        sep_1 = date(year, 9, 1)
        days_after_sep_1 = (7 - sep_1.weekday()) % 7
        labor_day = sep_1.replace(day=1 + days_after_sep_1)
        if check_date == labor_day:
            return "Labor Day"
        
        # Thanksgiving (4th Thursday in November)
        nov_1 = date(year, 11, 1)
        days_after_nov_1 = (3 - nov_1.weekday()) % 7
        first_thursday = nov_1.replace(day=1 + days_after_nov_1)
        thanksgiving = first_thursday.replace(day=first_thursday.day + 21)
        if check_date == thanksgiving:
            return "Thanksgiving Day"
        
        # Christmas
        if ((check_date.month == 12 and check_date.day == 25) or 
            (check_date.month == 12 and check_date.day in [24, 26] and check_date.weekday() in [0, 4])):
            return "Christmas Day"
        
        return "Market Holiday"
    
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
        today = now_ny.date()
        
        # Check if it's a weekend
        if now_ny.weekday() >= 5:  # Saturday=5, Sunday=6
            return {
                'is_open': False,
                'reason': 'Weekend - Markets closed',
                'current_time_ny': now_ny.strftime('%Y-%m-%d %H:%M:%S %Z'),
                'next_open': self._get_next_open_time(now_ny)
            }
        
        # Check if it's a market holiday
        if self._is_market_holiday(today):
            holiday_name = self._get_holiday_name(today)
            return {
                'is_open': False,
                'reason': f'Market Holiday - {holiday_name}',
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
        """Get the next market open time, skipping weekends and holidays"""
        from datetime import timedelta
        
        # Start with next potential trading day
        if current_time.weekday() == 4 and current_time.hour >= 16:  # Friday after 4 PM
            next_day = current_time + timedelta(days=3)  # Next Monday
        elif current_time.weekday() >= 5:  # Weekend
            days_to_monday = 7 - current_time.weekday()
            next_day = current_time + timedelta(days=days_to_monday)
        elif current_time.hour >= 16:  # After close on weekday
            next_day = current_time + timedelta(days=1)
        else:  # Before open today
            next_day = current_time
        
        # Find the next trading day (skip holidays)
        max_attempts = 10  # Prevent infinite loop
        attempts = 0
        
        while attempts < max_attempts:
            # Check if this day is a weekend
            if next_day.weekday() >= 5:  # Weekend
                days_to_monday = 7 - next_day.weekday()
                next_day = next_day + timedelta(days=days_to_monday)
                attempts += 1
                continue
            
            # Check if this day is a holiday
            if self._is_market_holiday(next_day.date()):
                next_day = next_day + timedelta(days=1)
                attempts += 1
                continue
            
            # Found a valid trading day
            break
        
        # Set to 9:30 AM
        next_open = next_day.replace(hour=9, minute=30, second=0, microsecond=0)
        return next_open.strftime('%Y-%m-%d %H:%M:%S %Z')
    
    def _calculate_time_remaining(self, current_time, target_time_str) -> str:
        """Calculate time remaining until target time"""
        try:
            # Parse the target time string back to datetime
            if target_time_str.endswith('EST') or target_time_str.endswith('EDT'):
                target_time_str = target_time_str[:-4].strip()
            
            # For same-day opens_at (like "09:30:00 EST")
            if len(target_time_str.split()) == 1:  # Just time, no date
                target_time = current_time.replace(
                    hour=int(target_time_str.split(':')[0]),
                    minute=int(target_time_str.split(':')[1]),
                    second=int(target_time_str.split(':')[2]),
                    microsecond=0
                )
            else:  # Full datetime string
                from datetime import datetime
                target_time = datetime.strptime(target_time_str, '%Y-%m-%d %H:%M:%S')
                target_time = self.ny_tz.localize(target_time)
            
            # Calculate difference
            time_diff = target_time - current_time
            
            if time_diff.total_seconds() <= 0:
                return "Market should be open now"
            
            # Convert to hours and minutes
            total_minutes = int(time_diff.total_seconds() / 60)
            hours = total_minutes // 60
            minutes = total_minutes % 60
            
            if hours == 0:
                return f"({minutes} minutes)"
            elif minutes == 0:
                return f"({hours} hour{'s' if hours != 1 else ''})"
            else:
                return f"({hours} hour{'s' if hours != 1 else ''} and {minutes} minute{'s' if minutes != 1 else ''})"
                
        except Exception as e:
            return "(time calculation error)"
    
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
                # Calculate time until close
                now_ny = datetime.now(self.ny_tz)
                time_to_close = self._calculate_time_remaining(now_ny, status.get('closes_at', ''))
                if time_to_close and not time_to_close.startswith('(time'):
                    print(f"Time until close: {time_to_close}")
            else:
                if 'opens_at' in status:
                    print(f"Market opens at: {status['opens_at']}")
                    # Calculate time until open
                    now_ny = datetime.now(self.ny_tz)
                    time_to_open = self._calculate_time_remaining(now_ny, status['opens_at'])
                    if time_to_open and not time_to_open.startswith('(time'):
                        print(f"Time until open: {time_to_open}")
                elif 'next_open' in status:
                    print(f"Next market open: {status['next_open']}")
                    # Calculate time until next open
                    now_ny = datetime.now(self.ny_tz)
                    time_to_open = self._calculate_time_remaining(now_ny, status['next_open'])
                    if time_to_open and not time_to_open.startswith('(time'):
                        print(f"Time until open: {time_to_open}")
            
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
    checker = MarketStatusChecker()
    
    # Show current market status
    market_is_open = checker.print_market_status()
    
    # Test holiday detection for some known holidays
    print("\n" + "="*60)
    print("HOLIDAY DETECTION TEST")
    print("="*60)
    
    test_dates = [
        (date(2025, 1, 1), "New Year's Day 2025"),
        (date(2025, 1, 20), "MLK Day 2025"),
        (date(2025, 2, 17), "Presidents' Day 2025"),
        (date(2025, 4, 18), "Good Friday 2025"),
        (date(2025, 5, 26), "Memorial Day 2025"),
        (date(2025, 6, 19), "Juneteenth 2025"),
        (date(2025, 7, 4), "Independence Day 2025"),
        (date(2025, 9, 1), "Labor Day 2025"),
        (date(2025, 11, 27), "Thanksgiving 2025"),
        (date(2025, 12, 25), "Christmas Day 2025"),
    ]
    
    for test_date, description in test_dates:
        is_holiday = checker._is_market_holiday(test_date)
        holiday_name = checker._get_holiday_name(test_date) if is_holiday else "Not a holiday"
        day_name = test_date.strftime('%A')
        print(f"{test_date} ({day_name}) - {description}: {'✓ HOLIDAY' if is_holiday else '✗ Trading Day'} - {holiday_name}")
    
    print("="*60)