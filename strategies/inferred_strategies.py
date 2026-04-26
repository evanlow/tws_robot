"""
Strategy classes for positions auto-detected (inferred) from the portfolio.

These strategies represent recognised multi-leg and single-leg patterns that
the PositionAnalyzer identifies from live positions.  They do not generate
new entry signals; instead they monitor the existing positions and support
the standard strategy lifecycle (start / stop / pause / resume).

Each class is a thin subclass of BaseStrategy that satisfies the abstract
interface.  Instances are created when the user clicks "Adopt" on an inferred
strategy card so that the position is tracked in the StrategyRegistry.
"""

from typing import Dict, Type

from strategies.base_strategy import BaseStrategy
from strategies.signal import Signal


class _InferredBase(BaseStrategy):
    """Shared base for all inferred (position-tracking) strategies.

    Subclasses only need to set ``strategy_label`` for logging purposes.
    """

    strategy_label: str = "Inferred"

    def on_bar(self, symbol: str, bar_data: dict) -> None:
        """No-op: inferred strategies track existing positions, not trade."""
        pass

    def validate_signal(self, signal: Signal) -> bool:
        """Delegate to Signal.validate() for consistent signal model enforcement."""
        if signal is None:
            return False
        return signal.validate()


class CoveredCallStrategy(_InferredBase):
    """Long stock + short call on the same underlying (income/exit strategy)."""

    strategy_label = "CoveredCall"


class ProtectivePutStrategy(_InferredBase):
    """Long stock + long put on the same underlying (downside hedge)."""

    strategy_label = "ProtectivePut"


class IronCondorStrategy(_InferredBase):
    """Short call spread + short put spread (range-bound premium collection)."""

    strategy_label = "IronCondor"


class BullCallSpreadStrategy(_InferredBase):
    """Long lower-strike call + short higher-strike call (bullish debit spread)."""

    strategy_label = "BullCallSpread"


class BearPutSpreadStrategy(_InferredBase):
    """Long higher-strike put + short lower-strike put (bearish debit spread)."""

    strategy_label = "BearPutSpread"


class BullPutSpreadStrategy(_InferredBase):
    """Short higher-strike put + long lower-strike put (bullish credit spread)."""

    strategy_label = "BullPutSpread"


class StraddleStrategy(_InferredBase):
    """Long call + long put at the same strike (volatility play)."""

    strategy_label = "Straddle"


class StrangleStrategy(_InferredBase):
    """Long OTM call + long OTM put (low-cost volatility play)."""

    strategy_label = "Strangle"


class LongEquityStrategy(_InferredBase):
    """Plain long stock position."""

    strategy_label = "LongEquity"


class ShortEquityStrategy(_InferredBase):
    """Plain short stock position."""

    strategy_label = "ShortEquity"


class LongCallStrategy(_InferredBase):
    """Naked long call option."""

    strategy_label = "LongCall"


class ShortCallStrategy(_InferredBase):
    """Naked short call option."""

    strategy_label = "ShortCall"


class LongPutStrategy(_InferredBase):
    """Naked long put option."""

    strategy_label = "LongPut"


class ShortPutStrategy(_InferredBase):
    """Naked short put option."""

    strategy_label = "ShortPut"


# Mapping from strategy_type string (as produced by PositionAnalyzer) to class.
INFERRED_STRATEGY_CLASSES: Dict[str, Type[BaseStrategy]] = {
    "CoveredCall": CoveredCallStrategy,
    "ProtectivePut": ProtectivePutStrategy,
    "IronCondor": IronCondorStrategy,
    "BullCallSpread": BullCallSpreadStrategy,
    "BearPutSpread": BearPutSpreadStrategy,
    "BullPutSpread": BullPutSpreadStrategy,
    "Straddle": StraddleStrategy,
    "Strangle": StrangleStrategy,
    "LongEquity": LongEquityStrategy,
    "ShortEquity": ShortEquityStrategy,
    "LongCall": LongCallStrategy,
    "ShortCall": ShortCallStrategy,
    "LongPut": LongPutStrategy,
    "ShortPut": ShortPutStrategy,
}
