"""
TWS API Rate Limiting Implementation
Ensures compliance with Interactive Brokers pacing limitations
Reference: https://www.interactivebrokers.com/campus/ibkr-api-page/twsapi-doc/#requests-limitations
"""

import time
from threading import Lock
from collections import deque
from typing import Dict, Optional
import logging

class APIRateLimiter:
    """
    Enforces TWS API pacing rules:
    - Maximum 50 requests per second (for 100 market data lines)
    - Historical data: max 60 requests per 10 minutes
    - No more than 6 historical requests for same contract within 2 seconds
    - No identical historical requests within 15 seconds
    """
    
    def __init__(self, market_data_lines: int = 100):
        self.market_data_lines = market_data_lines
        self.max_requests_per_second = market_data_lines // 2
        
        # Track different types of requests
        self.general_requests = deque()  # For rate limiting per second
        self.historical_requests = deque()  # For 10-minute window
        self.contract_historical_requests = {}  # Track per-contract requests
        self.recent_historical_requests = {}  # Track identical requests
        
        self.lock = Lock()
        
        # Configure logging
        self.logger = logging.getLogger(__name__)
    
    def can_make_request(self, request_type: str = "general") -> bool:
        """Check if a request can be made without violating rate limits"""
        with self.lock:
            current_time = time.time()
            
            if request_type == "historical":
                return self._can_make_historical_request(current_time)
            else:
                return self._can_make_general_request(current_time)
    
    def record_request(self, request_type: str = "general", 
                      contract_id: Optional[str] = None,
                      request_signature: Optional[str] = None):
        """Record that a request was made"""
        with self.lock:
            current_time = time.time()
            
            if request_type == "historical":
                self._record_historical_request(current_time, contract_id, request_signature)
            else:
                self._record_general_request(current_time)
    
    def _can_make_general_request(self, current_time: float) -> bool:
        """Check general request rate limit (50 per second)"""
        # Remove requests older than 1 second
        while self.general_requests and current_time - self.general_requests[0] > 1.0:
            self.general_requests.popleft()
        
        return len(self.general_requests) < self.max_requests_per_second
    
    def _record_general_request(self, current_time: float):
        """Record a general request"""
        self.general_requests.append(current_time)
    
    def _can_make_historical_request(self, current_time: float) -> bool:
        """Check historical data request limits"""
        # Check 10-minute limit (60 requests max)
        while self.historical_requests and current_time - self.historical_requests[0] > 600:
            self.historical_requests.popleft()
        
        if len(self.historical_requests) >= 60:
            self.logger.warning("Historical request limit reached (60 per 10 minutes)")
            return False
        
        return True
    
    def _record_historical_request(self, current_time: float, 
                                 contract_id: Optional[str] = None,
                                 request_signature: Optional[str] = None):
        """Record a historical request with contract and signature tracking"""
        self.historical_requests.append(current_time)
        
        # Track per-contract requests (max 6 per 2 seconds)
        if contract_id:
            if contract_id not in self.contract_historical_requests:
                self.contract_historical_requests[contract_id] = deque()
            
            contract_queue = self.contract_historical_requests[contract_id]
            
            # Remove requests older than 2 seconds
            while contract_queue and current_time - contract_queue[0] > 2.0:
                contract_queue.popleft()
            
            contract_queue.append(current_time)
        
        # Track identical requests (15-second cooldown)
        if request_signature:
            self.recent_historical_requests[request_signature] = current_time
    
    def can_make_historical_for_contract(self, contract_id: str) -> bool:
        """Check if historical request can be made for specific contract"""
        with self.lock:
            if contract_id not in self.contract_historical_requests:
                return True
            
            current_time = time.time()
            contract_queue = self.contract_historical_requests[contract_id]
            
            # Remove old requests
            while contract_queue and current_time - contract_queue[0] > 2.0:
                contract_queue.popleft()
            
            return len(contract_queue) < 6
    
    def is_duplicate_historical_request(self, request_signature: str) -> bool:
        """Check if this historical request was made recently (15 second rule)"""
        with self.lock:
            if request_signature in self.recent_historical_requests:
                time_since_request = time.time() - self.recent_historical_requests[request_signature]
                return time_since_request < 15.0
            return False
    
    def wait_for_rate_limit(self, request_type: str = "general") -> float:
        """Calculate how long to wait before next request"""
        with self.lock:
            current_time = time.time()
            
            if request_type == "historical":
                if not self._can_make_historical_request(current_time):
                    # Calculate wait time until oldest request expires
                    if self.historical_requests:
                        oldest_request = self.historical_requests[0]
                        wait_time = 600 - (current_time - oldest_request) + 1
                        return max(0, wait_time)
            else:
                if not self._can_make_general_request(current_time):
                    return 1.0  # Wait 1 second for general requests
            
            return 0.0
    
    def cleanup_old_requests(self):
        """Periodic cleanup of old request records"""
        with self.lock:
            current_time = time.time()
            
            # Clean general requests
            while self.general_requests and current_time - self.general_requests[0] > 60:
                self.general_requests.popleft()
            
            # Clean historical requests
            while self.historical_requests and current_time - self.historical_requests[0] > 1200:
                self.historical_requests.popleft()
            
            # Clean per-contract requests
            for contract_id in list(self.contract_historical_requests.keys()):
                contract_queue = self.contract_historical_requests[contract_id]
                while contract_queue and current_time - contract_queue[0] > 10:
                    contract_queue.popleft()
                
                # Remove empty queues
                if not contract_queue:
                    del self.contract_historical_requests[contract_id]
            
            # Clean duplicate request tracking
            for signature in list(self.recent_historical_requests.keys()):
                if current_time - self.recent_historical_requests[signature] > 30:
                    del self.recent_historical_requests[signature]

# Global rate limiter instance
rate_limiter = APIRateLimiter()

def wait_for_rate_limit(request_type: str = "general", 
                       contract_id: Optional[str] = None,
                       request_signature: Optional[str] = None) -> bool:
    """
    Check rate limits and wait if necessary.
    Returns True if request can proceed, False if it should be skipped.
    """
    
    # Check if we can make the request
    if not rate_limiter.can_make_request(request_type):
        wait_time = rate_limiter.wait_for_rate_limit(request_type)
        if wait_time > 0:
            logging.info(f"Rate limit hit. Waiting {wait_time:.1f} seconds...")
            time.sleep(wait_time)
    
    # Additional checks for historical requests
    if request_type == "historical":
        if contract_id and not rate_limiter.can_make_historical_for_contract(contract_id):
            logging.warning(f"Contract {contract_id} rate limit hit (6 requests per 2 seconds)")
            return False
        
        if request_signature and rate_limiter.is_duplicate_historical_request(request_signature):
            logging.warning(f"Duplicate historical request blocked (15 second rule)")
            return False
    
    # Record the request
    rate_limiter.record_request(request_type, contract_id, request_signature)
    return True

def create_historical_request_signature(symbol: str, duration: str, bar_size: str, 
                                      what_to_show: str, end_date: str = "") -> str:
    """Create a unique signature for historical requests to detect duplicates"""
    return f"{symbol}|{duration}|{bar_size}|{what_to_show}|{end_date}"