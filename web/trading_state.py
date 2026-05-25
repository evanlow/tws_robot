"""Explicit trading state model.

Provides a formal enum of all possible trading states to avoid
confusing connection status with execution readiness.
"""

from enum import Enum


class TradingState(str, Enum):
    """Explicit states for the trading system lifecycle."""

    DISCONNECTED = "DISCONNECTED"
    CONNECTION_FAILED = "CONNECTION_FAILED"
    CONNECTED_READ_ONLY = "CONNECTED_READ_ONLY"
    PAPER_TRADING_ENABLED = "PAPER_TRADING_ENABLED"
    LIVE_TRADING_ARMED = "LIVE_TRADING_ARMED"
    LIVE_TRADING_ACTIVE = "LIVE_TRADING_ACTIVE"
    EMERGENCY_STOP = "EMERGENCY_STOP"

    @property
    def allows_order_submission(self) -> bool:
        """Return True if this state permits new order submission."""
        return self in (
            TradingState.PAPER_TRADING_ENABLED,
            TradingState.LIVE_TRADING_ARMED,
            TradingState.LIVE_TRADING_ACTIVE,
        )
