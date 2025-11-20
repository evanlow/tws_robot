"""
Backtesting package for strategy evaluation.

Provides historical data management and backtesting engine
for testing trading strategies against past market data.
"""

from .historical_data import BarData, HistoricalDataManager
from .backtest_engine import (
    BacktestEngine,
    BacktestResults,
    BacktestOrder,
    BacktestPosition,
    BacktestTrade,
    OrderStatus
)
from .performance_analytics import PerformanceAnalytics, DrawdownPeriod

__all__ = [
    'BarData',
    'HistoricalDataManager',
    'BacktestEngine',
    'BacktestResults',
    'BacktestOrder',
    'BacktestPosition',
    'BacktestTrade',
    'OrderStatus',
    'PerformanceAnalytics',
    'DrawdownPeriod'
]
