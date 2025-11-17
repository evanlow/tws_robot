"""
TWS API Contract Definition Best Practices
Ensures proper contract specifications following IB documentation
"""

from ibapi.contract import Contract
from typing import Optional, Dict, List
import re
import logging

class ContractBuilder:
    """
    Build properly formatted contracts following TWS API best practices:
    - Proper exchange specifications
    - Correct currency settings
    - Complete contract definitions
    - Options contract validation
    """
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        
        # Common exchanges for different asset types
        self.stock_exchanges = {
            'US': 'SMART',  # Smart routing for best execution
            'NYSE': 'NYSE',
            'NASDAQ': 'NASDAQ', 
            'ARCA': 'ARCA',
            'BATS': 'BATS',
            'IEX': 'IEX'
        }
        
        self.option_exchanges = {
            'US': 'SMART',  # Let IB route to best options exchange
            'CBOE': 'CBOE',
            'ISE': 'ISE',
            'ARCA': 'ARCA',
            'BOX': 'BOX'
        }
        
        self.futures_exchanges = {
            'CME': 'CME',
            'CBOT': 'CBOT',
            'NYMEX': 'NYMEX',
            'COMEX': 'COMEX',
            'ICE': 'ICE'
        }
    
    def create_stock_contract(self, symbol: str, exchange: str = 'SMART', 
                            currency: str = 'USD', primary_exchange: Optional[str] = None) -> Contract:
        """
        Create a properly formatted stock contract
        
        Args:
            symbol: Stock symbol (e.g., 'AAPL', 'MSFT')
            exchange: Trading exchange ('SMART' for smart routing)
            currency: Currency denomination
            primary_exchange: Primary exchange for the stock
        """
        contract = Contract()
        contract.symbol = symbol.upper()
        contract.secType = 'STK'
        contract.currency = currency.upper()
        contract.exchange = exchange.upper()
        
        if primary_exchange:
            contract.primaryExchange = primary_exchange.upper()
        
        self.logger.debug(f"Created stock contract: {symbol} on {exchange}")
        return contract
    
    def create_option_contract(self, symbol: str, expiry: str, strike: float, 
                             right: str, exchange: str = 'SMART', 
                             currency: str = 'USD', multiplier: str = '100') -> Contract:
        """
        Create a properly formatted options contract
        
        Args:
            symbol: Underlying symbol
            expiry: Expiration date in YYYYMMDD format
            strike: Strike price
            right: 'C' for Call, 'P' for Put
            exchange: Options exchange
            currency: Currency
            multiplier: Contract multiplier (usually 100 for equity options)
        """
        if not self._validate_option_params(expiry, strike, right):
            raise ValueError("Invalid option parameters")
        
        contract = Contract()
        contract.symbol = symbol.upper()
        contract.secType = 'OPT'
        contract.lastTradeDateOrContractMonth = expiry
        contract.strike = float(strike)
        contract.right = right.upper()
        contract.exchange = exchange.upper()
        contract.currency = currency.upper()
        contract.multiplier = str(multiplier)
        
        self.logger.debug(f"Created option contract: {symbol} {expiry} {strike}{right}")
        return contract
    
    def create_futures_contract(self, symbol: str, exchange: str, 
                              lastTradeDateOrContractMonth: str,
                              currency: str = 'USD', multiplier: Optional[str] = None) -> Contract:
        """Create futures contract"""
        contract = Contract()
        contract.symbol = symbol.upper()
        contract.secType = 'FUT'
        contract.exchange = exchange.upper()
        contract.currency = currency.upper()
        contract.lastTradeDateOrContractMonth = lastTradeDateOrContractMonth
        
        if multiplier:
            contract.multiplier = str(multiplier)
        
        return contract
    
    def create_forex_contract(self, symbol: str, currency: str = 'USD') -> Contract:
        """Create forex contract (e.g., EUR.USD)"""
        contract = Contract()
        contract.symbol = symbol.upper()
        contract.secType = 'CASH'
        contract.currency = currency.upper()
        contract.exchange = 'IDEALPRO'  # Standard for forex
        
        return contract
    
    def create_crypto_contract(self, symbol: str, currency: str = 'USD') -> Contract:
        """Create cryptocurrency contract"""
        contract = Contract()
        contract.symbol = symbol.upper()
        contract.secType = 'CRYPTO'
        contract.currency = currency.upper()
        contract.exchange = 'PAXOS'  # IBKR's crypto exchange
        
        return contract
    
    def parse_option_symbol(self, option_symbol: str) -> Dict:
        """
        Parse option symbol from portfolio format to contract parameters
        Example: 'GOOG  260320P00200000' -> {'symbol': 'GOOG', 'expiry': '20260320', 'right': 'P', 'strike': 200.0}
        """
        try:
            # Remove extra spaces and normalize
            cleaned = ' '.join(option_symbol.split())
            
            # Match pattern: SYMBOL YYMMDD[C|P]NNNNNNNN
            pattern = r'^([A-Z]+)\s+(\d{6})([CP])(\d{8})$'
            match = re.match(pattern, cleaned)
            
            if not match:
                raise ValueError(f"Invalid option symbol format: {option_symbol}")
            
            symbol, date_part, right, strike_part = match.groups()
            
            # Convert YY to YYYY (assuming 20YY for now)
            year = '20' + date_part[:2]
            month = date_part[2:4]
            day = date_part[4:6]
            expiry = year + month + day
            
            # Convert strike (last 8 digits represent strike * 1000)
            strike = int(strike_part) / 1000.0
            
            return {
                'symbol': symbol,
                'expiry': expiry,
                'right': right,
                'strike': strike
            }
            
        except Exception as e:
            self.logger.error(f"Error parsing option symbol '{option_symbol}': {e}")
            raise
    
    def create_option_from_symbol(self, option_symbol: str, 
                                 exchange: str = 'SMART') -> Contract:
        """Create option contract from portfolio symbol"""
        params = self.parse_option_symbol(option_symbol)
        
        return self.create_option_contract(
            symbol=params['symbol'],
            expiry=params['expiry'],
            strike=params['strike'],
            right=params['right'],
            exchange=exchange
        )
    
    def _validate_option_params(self, expiry: str, strike: float, right: str) -> bool:
        """Validate option parameters"""
        # Check expiry format (YYYYMMDD)
        if not re.match(r'^\d{8}$', expiry):
            self.logger.error(f"Invalid expiry format: {expiry}. Expected YYYYMMDD")
            return False
        
        # Check strike
        if strike <= 0:
            self.logger.error(f"Invalid strike price: {strike}")
            return False
        
        # Check right
        if right.upper() not in ['C', 'P', 'CALL', 'PUT']:
            self.logger.error(f"Invalid option right: {right}")
            return False
        
        return True
    
    def get_contract_description(self, contract: Contract) -> str:
        """Get human-readable contract description"""
        if contract.secType == 'STK':
            return f"{contract.symbol} Stock ({contract.currency})"
        elif contract.secType == 'OPT':
            right_name = 'Call' if contract.right == 'C' else 'Put'
            return f"{contract.symbol} {contract.lastTradeDateOrContractMonth} ${contract.strike} {right_name}"
        elif contract.secType == 'FUT':
            return f"{contract.symbol} Future {contract.lastTradeDateOrContractMonth}"
        elif contract.secType == 'CASH':
            return f"{contract.symbol} Forex"
        elif contract.secType == 'CRYPTO':
            return f"{contract.symbol} Crypto"
        else:
            return f"{contract.symbol} {contract.secType}"
    
    def normalize_contract_for_data(self, contract: Contract) -> Contract:
        """
        Normalize contract for market data requests following IB best practices
        """
        normalized = Contract()
        normalized.symbol = contract.symbol
        normalized.secType = contract.secType
        normalized.currency = contract.currency
        
        # For market data, use SMART routing when possible
        if contract.secType == 'STK':
            normalized.exchange = 'SMART'
            # Include primary exchange if available for better routing
            if hasattr(contract, 'primaryExchange') and contract.primaryExchange:
                normalized.primaryExchange = contract.primaryExchange
        elif contract.secType == 'OPT':
            normalized.exchange = 'SMART'
            normalized.lastTradeDateOrContractMonth = contract.lastTradeDateOrContractMonth
            normalized.strike = contract.strike
            normalized.right = contract.right
            normalized.multiplier = getattr(contract, 'multiplier', '100')
        else:
            # For other types, use the specified exchange
            normalized.exchange = contract.exchange
            
            # Copy other relevant fields
            if hasattr(contract, 'lastTradeDateOrContractMonth'):
                normalized.lastTradeDateOrContractMonth = contract.lastTradeDateOrContractMonth
            if hasattr(contract, 'strike'):
                normalized.strike = contract.strike
            if hasattr(contract, 'right'):
                normalized.right = contract.right
            if hasattr(contract, 'multiplier'):
                normalized.multiplier = contract.multiplier
        
        return normalized

def create_contract_from_portfolio_data(contract_data: Contract, 
                                      contract_builder: ContractBuilder = None) -> Contract:
    """
    Create a properly formatted contract from portfolio data
    Handles the conversion from portfolio contract format to trading format
    """
    if not contract_builder:
        contract_builder = ContractBuilder()
    
    try:
        # Use the existing contract data but normalize it
        return contract_builder.normalize_contract_for_data(contract_data)
        
    except Exception as e:
        logging.error(f"Error creating contract from portfolio data: {e}")
        # Return original contract as fallback
        return contract_data

# Global contract builder instance
contract_builder = ContractBuilder()