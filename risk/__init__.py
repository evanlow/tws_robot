"""
Risk management module for TWS Robot.

This module provides comprehensive risk management capabilities including:
- Position sizing (Kelly, Fixed %, Risk Parity)
- Drawdown protection and monitoring
- Correlation analysis for portfolio risk
- Real-time risk limits enforcement
- Emergency stop functionality

Week 3 Implementation.
"""

from .risk_manager import RiskManager, Position, RiskStatus, RiskMetrics
from .position_sizer import (
    PositionSizer,
    PositionSizeResult,
    FixedPercentSizer,
    KellySizer,
    RiskBasedSizer,
    RiskParitySizer,
    PositionSizerFactory
)
from .drawdown_control import (
    DrawdownMonitor,
    DrawdownMetrics,
    DrawdownEvent,
    DrawdownSeverity
)

__all__ = [
    'RiskManager',
    'Position',
    'RiskStatus',
    'RiskMetrics',
    'PositionSizer',
    'PositionSizeResult',
    'FixedPercentSizer',
    'KellySizer',
    'RiskBasedSizer',
    'RiskParitySizer',
    'PositionSizerFactory',
    'DrawdownMonitor',
    'DrawdownMetrics',
    'DrawdownEvent',
    'DrawdownSeverity',
]
