"""Configuration package for TWS Robot.

Exposes paper/live trading configs and environment helpers at the package level.

Usage:
    from config.env_config import get_config
    from config.paper import host, port, client_id
    from config.live import host, port, client_id
"""

from config.env_config import get_config, print_config  # noqa: F401
