"""
Execution module for tws_robot.

Provides adapters for connecting strategies to live/paper trading.
"""

from .paper_adapter import PaperTradingAdapter

__all__ = ['PaperTradingAdapter']
