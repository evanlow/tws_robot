"""
Core modules for TWS Robot trading platform.

This package contains the foundational components:
- Event Bus: Event-driven communication system
- Connection: TWS API connection management
- Rate Limiter: API request pacing
- Order Manager: Order lifecycle tracking
- Contract Builder: Multi-asset contract creation
"""

from .event_bus import EventBus, Event, EventType
from .connection import EnhancedTWSConnection
from .rate_limiter import APIRateLimiter
from .order_manager import OrderManager, OrderRecord
from .contract_builder import ContractBuilder

__all__ = [
    'EventBus', 'Event', 'EventType',
    'EnhancedTWSConnection',
    'APIRateLimiter',
    'OrderManager', 'OrderRecord',
    'ContractBuilder'
]
