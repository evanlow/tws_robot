"""Live trading configuration for TWS Robot.

This configuration connects to Interactive Brokers TWS live trading account.
USE WITH EXTREME CAUTION - executes real trades with real capital.

Configuration:
    host: TWS API host (localhost)
    port: TWS API port (7496 for live trading, currently 7497 for paper)
    client_id: Unique client identifier for this connection
    ib_account: IB live trading account number

Safety:
    - Verify port is correct before live trading
    - Ensure risk controls are active
    - Monitor positions continuously
    - Have emergency stop procedures ready

Usage:
    Only import this config for validated strategies in production.
    Requires additional safety checks and monitoring.
"""

host = '127.0.0.1'
port = 7497  # Demo 7497 / Live 7496
client_id = 3
ib_account = 'DU2746208'