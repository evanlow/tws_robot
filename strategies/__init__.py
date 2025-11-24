"""
Trading Strategies Module

Provides framework for implementing and managing trading strategies
with standardized lifecycle, signal generation, and event integration.
"""

from .signal import Signal, SignalType, SignalStrength
from .base_strategy import BaseStrategy, StrategyState, StrategyConfig
from .strategy_registry import StrategyRegistry
from .bollinger_bands import BollingerBandsStrategy
from .strategy_orchestrator import (
    StrategyOrchestrator, 
    SignalAggregator, 
    ConflictResolver, 
    AllocationManager
)

__all__ = [
    'Signal',
    'SignalType', 
    'SignalStrength',
    'BaseStrategy',
    'StrategyState',
    'StrategyConfig',
    'StrategyRegistry',
    'BollingerBandsStrategy',
    'StrategyOrchestrator',
    'SignalAggregator',
    'ConflictResolver',
    'AllocationManager'
]
