"""
Environment-based configuration for Interactive Brokers trading bot.
Loads configuration from .env file or environment variables.
"""

import os
from typing import Optional

def load_env_file():
    """Load .env file if it exists"""
    env_path = os.path.join(os.path.dirname(__file__), '.env')
    if os.path.exists(env_path):
        with open(env_path, 'r') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    os.environ[key.strip()] = value.strip()
        print(f"Loaded configuration from {env_path}")
    else:
        print("No .env file found, using environment variables or defaults")

def get_config(environment: Optional[str] = None):
    """Get configuration for specified environment"""
    # Load .env file first
    load_env_file()
    
    # Determine environment
    if environment is None:
        environment = os.getenv('TRADING_ENV', 'paper').lower()
    
    environment = environment.lower()
    
    if environment == 'paper':
        return {
            'host': os.getenv('PAPER_HOST', '127.0.0.1'),
            'port': int(os.getenv('PAPER_PORT', '7497')),
            'client_id': int(os.getenv('PAPER_CLIENT_ID', '0')),
            'account': os.getenv('PAPER_ACCOUNT', 'DU2746208'),
            'environment': 'paper'
        }
    elif environment == 'live':
        live_account = os.getenv('LIVE_ACCOUNT')
        if not live_account or live_account == 'YOUR_LIVE_ACCOUNT_ID':
            raise ValueError("LIVE_ACCOUNT must be set in .env file for live trading")
            
        return {
            'host': os.getenv('LIVE_HOST', '127.0.0.1'),
            'port': int(os.getenv('LIVE_PORT', '7496')),
            'client_id': int(os.getenv('LIVE_CLIENT_ID', '1')),
            'account': live_account,
            'environment': 'live'
        }
    else:
        raise ValueError(f"Invalid environment: {environment}. Use 'paper' or 'live'")

def print_config(config):
    """Print configuration safely (masks sensitive data)"""
    print(f"Environment: {config['environment']}")
    print(f"Host: {config['host']}")
    print(f"Port: {config['port']}")
    print(f"Client ID: {config['client_id']}")
    # Mask account number for security
    account = config['account']
    masked_account = f"{account[:3]}***{account[-3:]}" if len(account) > 6 else "***"
    print(f"Account: {masked_account}")

# Backward compatibility functions
def get_paper_config():
    """Get paper trading configuration"""
    return get_config('paper')

def get_live_config():
    """Get live trading configuration"""  
    return get_config('live')