"""
Backtesting Module

This module provides comprehensive backtesting capabilities for trading strategies
with full risk management integration.

Components:
- HistoricalDataManager: Load and manage historical market data
- MarketSimulator: Replay historical market conditions
- Strategy: Base class for strategy implementation
- BacktestEngine: Execute backtests with risk system integration
- PerformanceMetrics: Calculate comprehensive performance statistics
- ProfileManager: Multi-profile comparison and optimization

Author: TWS Robot Development Team
Date: November 2025
Week 4 Day 1-2: Backtesting Foundation & Engine Core
"""

from .data_models import Bar, MarketData, BarSeries, TimeFrame, Trade, Position
from .data_manager import HistoricalDataManager
from .market_simulator import MarketSimulator, FillSimulator, Order
from .strategy import Strategy, StrategyConfig, StrategyState
from .engine import BacktestEngine, BacktestConfig, BacktestResult, EquityPoint

__all__ = [
    # Data models
    'Bar',
    'MarketData',
    'BarSeries',
    'TimeFrame',
    'Trade',
    'Position',
    
    # Data management
    'HistoricalDataManager',
    
    # Market simulation
    'MarketSimulator',
    'FillSimulator',
    'Order',
    
    # Strategy
    'Strategy',
    'StrategyConfig',
    'StrategyState',
    
    # Engine
    'BacktestEngine',
    'BacktestConfig',
    'BacktestResult',
    'EquityPoint',
]

__version__ = '1.1.0'
