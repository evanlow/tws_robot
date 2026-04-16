"""
Database module for TWS Robot trading platform.

Provides PostgreSQL integration using SQLAlchemy ORM for:
- Trade history and execution tracking
- Strategy configuration and state
- Performance metrics and analytics
- Market data storage
"""

from .database import Database, get_database
from .models import (
    Trade, Position, Order, Strategy, 
    MarketData, PerformanceMetric, MarketSnapshot
)
from .realtime_pipeline import RealtimeDataManager, DataSubscription

__all__ = [
    'Database', 'get_database',
    'Trade', 'Position', 'Order', 'Strategy',
    'MarketData', 'PerformanceMetric', 'MarketSnapshot',
    'RealtimeDataManager', 'DataSubscription'
]
