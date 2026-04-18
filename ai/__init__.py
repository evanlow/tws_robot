"""AI package — OpenAI integration for TWS Robot.

Public API
----------
from ai.client import AIClient, get_client
from ai.prompts import Prompts
from ai.context_builder import build_trading_context
from ai.portfolio_analyzer import PortfolioAnalyzer
from ai.stock_analyzer import StockAnalyzer
"""

from ai.client import AIClient, get_client, reset_client  # noqa: F401
from ai.prompts import Prompts  # noqa: F401
from ai.context_builder import build_trading_context  # noqa: F401
from ai.portfolio_analyzer import PortfolioAnalyzer  # noqa: F401
from ai.stock_analyzer import StockAnalyzer  # noqa: F401

__all__ = [
    "AIClient", "get_client", "reset_client", "Prompts", "build_trading_context",
    "PortfolioAnalyzer", "StockAnalyzer",
]
