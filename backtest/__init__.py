"""
Backtesting Module

This module provides comprehensive backtesting capabilities for trading strategies
with full risk management integration.

Components:
- HistoricalDataManager: Load and manage historical market data
- MarketSimulator: Replay historical market conditions
- Strategy: Base class for strategy implementation
- BacktestEngine: Execute backtests with risk system integration
- PerformanceAnalyzer: Calculate comprehensive performance statistics
- PerformanceVisualizer: Create performance charts and dashboards
- ProfileManager: Multi-profile comparison and optimization

Author: TWS Robot Development Team
Date: November 2025
Week 4 Day 1-3: Backtesting Foundation, Engine Core & Performance Analytics
"""

from .data_models import Bar, MarketData, BarSeries, TimeFrame, Trade, Position
from .data_manager import HistoricalDataManager
from .market_simulator import MarketSimulator, FillSimulator, Order
from .strategy import Strategy, StrategyConfig, StrategyState
from .engine import BacktestEngine, BacktestConfig, BacktestResult, EquityPoint
from .performance import (
    TradeDirection,
    DrawdownPeriod,
    PerformanceMetrics,
    PerformanceAnalyzer,
    ReportGenerator
)
from .visualization import PerformanceVisualizer

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
    
    # Performance Analytics (Day 3)
    'TradeDirection',
    'DrawdownPeriod',
    'PerformanceMetrics',
    'PerformanceAnalyzer',
    'ReportGenerator',
    'PerformanceVisualizer',
]

__version__ = '1.2.0'
