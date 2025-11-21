"""
Backtesting Module

This module provides comprehensive backtesting capabilities for trading strategies
with full risk management integration.

Components:
- HistoricalDataManager: Load and manage historical market data
- MarketSimulator: Replay historical market conditions
- BacktestEngine: Execute backtests with risk system integration
- PerformanceMetrics: Calculate comprehensive performance statistics
- ProfileManager: Multi-profile comparison and optimization

Author: TWS Robot Development Team
Date: November 2025
Week 4 Day 1: Backtesting Foundation
"""

from .data_models import Bar, MarketData, TimeFrame
from .data_manager import HistoricalDataManager
from .market_simulator import MarketSimulator, FillSimulator

__all__ = [
    'Bar',
    'MarketData',
    'TimeFrame',
    'HistoricalDataManager',
    'MarketSimulator',
    'FillSimulator',
]

__version__ = '1.0.0'
