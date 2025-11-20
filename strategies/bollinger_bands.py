"""
Bollinger Bands Mean Reversion Strategy

Trades based on price deviation from Bollinger Bands:
- Buy when price touches lower band (oversold)
- Sell when price touches upper band (overbought)
- Close positions at middle band (mean reversion)

Strategy Parameters:
- period: Moving average period (default: 20)
- std_dev: Standard deviation multiplier (default: 2.0)
- min_volume: Minimum volume threshold
- position_size: Position size as percentage of equity
"""

import logging
from typing import Dict, List, Optional
from datetime import datetime
import pandas as pd
import numpy as np

from strategies.base_strategy import BaseStrategy
from strategies.signal import Signal, SignalType, SignalStrength

logger = logging.getLogger(__name__)


class BollingerBandsStrategy(BaseStrategy):
    """
    Bollinger Bands mean reversion strategy.
    
    Entry Signals:
    - LONG: Price crosses below lower band
    - SHORT: Price crosses above upper band
    
    Exit Signals:
    - Close when price returns to middle band
    
    Risk Management:
    - Stop loss at 2% from entry
    - Take profit at middle band
    - Position sizing based on equity
    
    Example:
        >>> strategy = BollingerBandsStrategy(
        ...     name="BB_Strategy",
        ...     symbols=["AAPL", "MSFT"],
        ...     period=20,
        ...     std_dev=2.0
        ... )
        >>> strategy.start()
        >>> strategy.on_bar("AAPL", bar_data)
    """
    
    def __init__(
        self,
        name: str = "bollinger_bands",
        symbols: Optional[List[str]] = None,
        period: int = 20,
        std_dev: float = 2.0,
        min_volume: int = 100000,
        position_size: float = 0.1,  # 10% of equity per position
        stop_loss_pct: float = 0.02,  # 2% stop loss
        **kwargs
    ):
        """
        Initialize Bollinger Bands strategy.
        
        Args:
            name: Strategy name
            symbols: List of symbols to trade
            period: Moving average period
            std_dev: Standard deviation multiplier for bands
            min_volume: Minimum volume threshold
            position_size: Position size as percentage of equity
            stop_loss_pct: Stop loss percentage from entry
            **kwargs: Additional parameters for base strategy
        """
        # Create strategy config
        from strategies.base_strategy import StrategyConfig
        config = StrategyConfig(
            name=name,
            symbols=symbols or [],
            enabled=True,
            parameters={
                'period': period,
                'std_dev': std_dev,
                'min_volume': min_volume,
                'position_size': position_size,
                'stop_loss_pct': stop_loss_pct
            }
        )
        
        super().__init__(config=config)
        
        self.period = period
        self.std_dev = std_dev
        self.min_volume = min_volume
        self.position_size = position_size
        self.stop_loss_pct = stop_loss_pct
        
        # Price history for each symbol
        self.price_history: Dict[str, List[float]] = {}
        self.volume_history: Dict[str, List[int]] = {}
        
        # Indicator values
        self.upper_band: Dict[str, float] = {}
        self.middle_band: Dict[str, float] = {}
        self.lower_band: Dict[str, float] = {}
        
        # Previous bar data for cross detection
        self.prev_close: Dict[str, float] = {}
        self.prev_upper: Dict[str, float] = {}
        self.prev_lower: Dict[str, float] = {}
        
        # Signals for backtesting
        self.signals_to_emit: List[Signal] = []
        
        logger.info(
            f"BollingerBandsStrategy initialized: period={period}, "
            f"std_dev={std_dev}, min_volume={min_volume}"
        )
    
    def start(self):
        """Start the strategy"""
        super().start()
        logger.info(f"Strategy {self.config.name} started with {len(self.config.symbols)} symbols")
    
    def stop(self):
        """Stop the strategy"""
        super().stop()
        logger.info(f"Strategy {self.config.name} stopped")
    
    def on_bar(self, symbol: str, bar: Dict) -> None:
        """
        Process new bar data.
        
        Args:
            symbol: Trading symbol
            bar: Bar data with keys: timestamp, open, high, low, close, volume
        """
        from strategies.base_strategy import StrategyState
        if self.state != StrategyState.RUNNING:
            return
        
        # Extract bar data
        close = bar['close']
        volume = bar.get('volume', 0)
        timestamp = bar['timestamp']
        
        # Initialize history if needed
        if symbol not in self.price_history:
            self.price_history[symbol] = []
            self.volume_history[symbol] = []
        
        # Update price history
        self.price_history[symbol].append(close)
        self.volume_history[symbol].append(volume)
        
        # Keep only required history (period + 1 for cross detection)
        max_history = self.period + 10
        if len(self.price_history[symbol]) > max_history:
            self.price_history[symbol] = self.price_history[symbol][-max_history:]
            self.volume_history[symbol] = self.volume_history[symbol][-max_history:]
        
        # Need enough data to calculate indicators
        if len(self.price_history[symbol]) < self.period:
            logger.debug(
                f"{symbol}: Collecting data ({len(self.price_history[symbol])}/{self.period})"
            )
            return
        
        # Calculate Bollinger Bands
        prices = np.array(self.price_history[symbol])
        sma = np.mean(prices[-self.period:])
        std = np.std(prices[-self.period:])
        
        upper = sma + (self.std_dev * std)
        lower = sma - (self.std_dev * std)
        
        # Store current bands
        self.upper_band[symbol] = upper
        self.middle_band[symbol] = sma
        self.lower_band[symbol] = lower
        
        # Check volume threshold
        if volume < self.min_volume:
            logger.debug(f"{symbol}: Volume too low ({volume} < {self.min_volume})")
            return
        
        # Generate signals based on band crosses
        # For backtesting, emit all signals and let the engine manage positions
        self._check_entry_signals(symbol, close, upper, lower, timestamp)
        self._check_exit_signals(symbol, close, sma, timestamp)
        
        # Store previous values for next bar
        self.prev_close[symbol] = close
        self.prev_upper[symbol] = upper
        self.prev_lower[symbol] = lower
    
    def _check_entry_signals(
        self,
        symbol: str,
        close: float,
        upper: float,
        lower: float,
        timestamp: datetime
    ) -> None:
        """
        Check for entry signals.
        
        Args:
            symbol: Trading symbol
            close: Current close price
            upper: Upper Bollinger Band
            lower: Lower Bollinger Band
            timestamp: Current timestamp
        """
        # Need previous data for cross detection
        if symbol not in self.prev_close:
            return
        
        prev_close = self.prev_close[symbol]
        prev_lower = self.prev_lower.get(symbol, lower)
        prev_upper = self.prev_upper.get(symbol, upper)
        
        # Long signal: Price crosses below lower band (oversold)
        if prev_close >= prev_lower and close < lower:
            logger.info(
                f"{symbol}: LONG signal at {close:.2f} "
                f"(lower band: {lower:.2f})"
            )
            signal = Signal(
                symbol=symbol,
                signal_type=SignalType.BUY,
                strength=SignalStrength.STRONG,
                timestamp=timestamp,
                target_price=close,
                stop_loss=close * (1 - self.stop_loss_pct),
                take_profit=self.middle_band[symbol],
                quantity=None,
                reason='price_below_lower_band',
                indicators={
                    'lower_band': lower,
                    'middle_band': self.middle_band[symbol],
                    'upper_band': upper
                },
                strategy_name=self.config.name,
                confidence=0.85
            )
            self.generate_signal(signal)
        
        # Short signal: Price crosses above upper band (overbought)
        elif prev_close <= prev_upper and close > upper:
            logger.info(
                f"{symbol}: SHORT signal at {close:.2f} "
                f"(upper band: {upper:.2f})"
            )
            signal = Signal(
                symbol=symbol,
                signal_type=SignalType.SELL,
                strength=SignalStrength.STRONG,
                timestamp=timestamp,
                target_price=close,
                stop_loss=close * (1 + self.stop_loss_pct),
                take_profit=self.middle_band[symbol],
                quantity=None,
                reason='price_above_upper_band',
                indicators={
                    'lower_band': lower,
                    'middle_band': self.middle_band[symbol],
                    'upper_band': upper
                },
                strategy_name=self.config.name,
                confidence=0.85
            )
            self.generate_signal(signal)
    
    def _check_exit_signals(
        self,
        symbol: str,
        close: float,
        middle: float,
        timestamp: datetime
    ) -> None:
        """
        Check for exit signals.
        
        Args:
            symbol: Trading symbol
            close: Current close price
            middle: Middle band (SMA)
            timestamp: Current timestamp
        """
        # Exit long when price reaches middle band (emit signal regardless of current position)
        # The backtest engine will determine if the signal is valid based on actual positions
        if close >= middle:
            logger.info(
                f"{symbol}: EXIT LONG at {close:.2f} "
                f"(middle band: {middle:.2f})"
            )
            signal = Signal(
                symbol=symbol,
                signal_type=SignalType.SELL,
                strength=SignalStrength.MODERATE,
                timestamp=timestamp,
                target_price=close,
                stop_loss=None,
                take_profit=None,
                quantity=None,
                reason='mean_reversion_long',
                indicators={'middle_band': middle},
                strategy_name=self.config.name,
                confidence=0.75
            )
            self.generate_signal(signal)
        
        # Exit short when price reaches middle band (emit signal regardless of current position)
        # The backtest engine will determine if the signal is valid based on actual positions
        if close <= middle:
            logger.info(
                f"{symbol}: EXIT SHORT at {close:.2f} "
                f"(middle band: {middle:.2f})"
            )
            signal = Signal(
                symbol=symbol,
                signal_type=SignalType.BUY,
                strength=SignalStrength.MODERATE,
                timestamp=timestamp,
                target_price=close,
                stop_loss=None,
                take_profit=None,
                quantity=None,
                reason='mean_reversion_short',
                indicators={'middle_band': middle},
                strategy_name=self.config.name,
                confidence=0.75
            )
            self.generate_signal(signal)
    
    def get_indicator_values(self, symbol: str) -> Dict:
        """
        Get current indicator values for a symbol.
        
        Args:
            symbol: Trading symbol
            
        Returns:
            Dictionary with indicator values
        """
        if symbol not in self.middle_band:
            return {}
        
        return {
            'upper_band': self.upper_band.get(symbol, 0.0),
            'middle_band': self.middle_band.get(symbol, 0.0),
            'lower_band': self.lower_band.get(symbol, 0.0),
            'period': self.period,
            'std_dev': self.std_dev
        }
    
    def validate_signal(self, signal: Signal) -> bool:
        """
        Validate a trading signal.
        
        Args:
            signal: Signal to validate
            
        Returns:
            True if signal is valid
        """
        # Basic validation - ensure we have indicator values
        if signal.symbol not in self.middle_band:
            return False
        
        # Ensure signal price is reasonable
        if signal.target_price is None or signal.target_price <= 0:
            return False
        
        return True
    
    def generate_signal(self, signal: Signal):
        """
        Generate a trading signal for backtesting.
        
        Args:
            signal: Trading signal to emit
        """
        if self.validate_signal(signal):
            self.signals_to_emit.append(signal)
            logger.debug(f"Signal generated: {signal.signal_type.value} {signal.symbol}")
        else:
            logger.warning(f"Invalid signal rejected: {signal.symbol} {signal.signal_type.value}")
    
    def reset(self) -> None:
        """Reset strategy state"""
        super().reset()
        self.price_history.clear()
        self.volume_history.clear()
        self.upper_band.clear()
        self.middle_band.clear()
        self.lower_band.clear()
        self.prev_close.clear()
        self.prev_upper.clear()
        self.prev_lower.clear()
        self.signals_to_emit.clear()
        logger.info(f"Strategy {self.config.name} reset")
