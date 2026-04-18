"""
Database module for TWS Robot trading platform.

Provides PostgreSQL integration using SQLAlchemy ORM for:
- Trade history and execution tracking
- Strategy configuration and state
- Performance metrics and analytics
- Market data storage
- Portfolio analytics persistence
"""

from .database import Database, get_database
from .models import (
    Trade, Position, Order, Strategy, 
    MarketData, PerformanceMetric, MarketSnapshot
)
from .realtime_pipeline import RealtimeDataManager, DataSubscription
from .fundamentals import get_fundamentals, fetch_fundamentals, fetch_price_history
from .portfolio_persistence import (
    save_portfolio_snapshot, get_latest_snapshot, get_snapshot_history,
    save_stock_analysis, get_latest_stock_analysis, get_stock_analysis_history,
    cache_fundamentals, get_cached_fundamentals,
)

__all__ = [
    'Database', 'get_database',
    'Trade', 'Position', 'Order', 'Strategy',
    'MarketData', 'PerformanceMetric', 'MarketSnapshot',
    'RealtimeDataManager', 'DataSubscription',
    'get_fundamentals', 'fetch_fundamentals', 'fetch_price_history',
    'save_portfolio_snapshot', 'get_latest_snapshot', 'get_snapshot_history',
    'save_stock_analysis', 'get_latest_stock_analysis', 'get_stock_analysis_history',
    'cache_fundamentals', 'get_cached_fundamentals',
]
