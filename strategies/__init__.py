"""
Trading Strategies Module

Provides framework for implementing and managing trading strategies
with standardized lifecycle, signal generation, and event integration.
"""

from .signal import Signal, SignalType, SignalStrength
from .base_strategy import BaseStrategy, StrategyState, StrategyConfig
from .strategy_registry import StrategyRegistry
from .bollinger_bands import BollingerBandsStrategy
from .inferred_strategies import (
    CoveredCallStrategy,
    ProtectivePutStrategy,
    IronCondorStrategy,
    BullCallSpreadStrategy,
    BearPutSpreadStrategy,
    BullPutSpreadStrategy,
    StraddleStrategy,
    StrangleStrategy,
    LongEquityStrategy,
    ShortEquityStrategy,
    LongCallStrategy,
    ShortCallStrategy,
    LongPutStrategy,
    ShortPutStrategy,
    INFERRED_STRATEGY_CLASSES,
)
from .strategy_orchestrator import (
    StrategyOrchestrator, 
    SignalAggregator, 
    ConflictResolver, 
    AllocationManager
)
from .comparison_dashboard import (
    StrategyComparator,
    ComparisonMetrics,
    ComparisonDashboard,
    MetricType,
    RankingCriteria
)
from .performance_attribution import (
    PerformanceAttribution,
    AttributionBreakdown,
    TradeAttribution,
    AttributionMetric,
    AttributionPeriod
)
from .health_monitor import (
    HealthMonitor,
    HealthMetrics,
    HealthStatus,
    HealthAlert,
    AlertLevel,
    DegradationDetector
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
    'AllocationManager',
    'StrategyComparator',
    'ComparisonMetrics',
    'ComparisonDashboard',
    'MetricType',
    'RankingCriteria',
    'PerformanceAttribution',
    'AttributionBreakdown',
    'TradeAttribution',
    'AttributionMetric',
    'AttributionPeriod',
    'HealthMonitor',
    'HealthMetrics',
    'HealthStatus',
    'HealthAlert',
    'AlertLevel',
    'DegradationDetector',
    'CoveredCallStrategy',
    'ProtectivePutStrategy',
    'IronCondorStrategy',
    'BullCallSpreadStrategy',
    'BearPutSpreadStrategy',
    'BullPutSpreadStrategy',
    'StraddleStrategy',
    'StrangleStrategy',
    'LongEquityStrategy',
    'ShortEquityStrategy',
    'LongCallStrategy',
    'ShortCallStrategy',
    'LongPutStrategy',
    'ShortPutStrategy',
    'INFERRED_STRATEGY_CLASSES',
]
