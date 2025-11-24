"""Paper trading configuration for TWS Robot.

This configuration connects to Interactive Brokers TWS paper trading account.
Used for strategy validation and testing without real capital.

Configuration:
    host: TWS API host (localhost)
    port: TWS API port (7497 for paper trading)
    client_id: Unique client identifier for this connection
    ib_account: IB paper trading account number

Usage:
    Import this config when running in paper trading mode.
    Ensures all trades execute against paper account only.
"""

host = '127.0.0.1'
port = 7497  # Demo 7497 / Live 7496
client_id = 0
ib_account = 'DU2746208'