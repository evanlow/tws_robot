"""
Execution module for tws_robot.

Provides adapters for connecting strategies to live/paper trading.
"""

from .paper_adapter import PaperTradingAdapter, TwsTradingAdapter
from .risk_monitor import RealTimeRiskMonitor, PortfolioRisk, RiskAlert

__all__ = [
    'PaperTradingAdapter',
    'TwsTradingAdapter',
    'RealTimeRiskMonitor',
    'PortfolioRisk',
    'RiskAlert'
]
