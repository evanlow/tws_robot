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

__all__ = [
    'RiskManager',
    'Position',
    'RiskStatus',
    'RiskMetrics',
]
