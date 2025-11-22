"""
Strategy Templates

This module provides pre-built strategy templates that can be used as-is or
customized for specific trading needs. Each template implements a proven
trading approach with configurable parameters.

Templates:
- MovingAverageCrossStrategy: Classic dual moving average crossover
- MeanReversionStrategy: Mean reversion with Bollinger Bands
- MomentumStrategy: Trend following with momentum indicators

All templates inherit from the base Strategy class and follow best practices
for risk management, position sizing, and signal generation.
"""

from typing import Dict, List, Optional, Set
from datetime import datetime
from dataclasses import dataclass, field

from backtest.strategy import Strategy, StrategyConfig
from backtest.data_models import Bar


# ============================================================================
# Moving Average Cross Strategy
# ============================================================================

@dataclass
class MACrossConfig:
    """Configuration for Moving Average Cross strategy"""
    fast_period: int = 20
    slow_period: int = 50
    min_bars: int = 50  # Minimum bars before trading
    
    def __post_init__(self):
        """Validate configuration"""
        if self.fast_period < 2:
            raise ValueError("Fast period must be at least 2")
        if self.slow_period < 2:
            raise ValueError("Slow period must be at least 2")
        if self.fast_period >= self.slow_period:
            raise ValueError("Fast period must be less than slow period")
        if self.min_bars < self.slow_period:
            self.min_bars = self.slow_period


class MovingAverageCrossStrategy(Strategy):
    """
    Moving Average Crossover Strategy
    
    Classic dual moving average crossover system:
    - Buy when fast MA crosses above slow MA (golden cross)
    - Sell when fast MA crosses below slow MA (death cross)
    
    This is one of the most popular and well-tested trading strategies.
    It works best in trending markets and may generate false signals
    in choppy/sideways markets.
    
    Parameters:
        fast_period: Period for fast moving average (default: 20)
        slow_period: Period for slow moving average (default: 50)
        min_bars: Minimum bars required before trading (default: 50)
    
    Example:
        >>> config = StrategyConfig(initial_capital=100000)
        >>> ma_config = MACrossConfig(fast_period=20, slow_period=50)
        >>> strategy = MovingAverageCrossStrategy(config, ma_config)
    """
    
    def __init__(self, config: StrategyConfig, ma_config: Optional[MACrossConfig] = None):
        """
        Initialize Moving Average Cross strategy
        
        Args:
            config: Base strategy configuration
            ma_config: MA-specific configuration (uses defaults if None)
        """
        super().__init__(config)
        self.ma_config = ma_config or MACrossConfig()
        
        # MA values per symbol
        self.fast_ma: Dict[str, float] = {}
        self.slow_ma: Dict[str, float] = {}
        
        # Previous MA values for crossover detection
        self.prev_fast_ma: Dict[str, float] = {}
        self.prev_slow_ma: Dict[str, float] = {}
        
        # Track if we have enough bars
        self.ready_symbols: Set[str] = set()
    
    def on_bar(self, symbol: str, bar: Bar):
        """Process new bar and check for crossover signals"""
        # Get bar history for this symbol
        bars = self.get_bar_history(symbol, lookback=self.ma_config.slow_period)
        
        # Check if we have enough bars
        if len(bars) < self.ma_config.slow_period:
            return
        
        # Mark symbol as ready
        self.ready_symbols.add(symbol)
        
        # Calculate moving averages
        closes = [b.close for b in bars]
        
        fast_ma = self._calculate_sma(closes, self.ma_config.fast_period)
        slow_ma = self._calculate_sma(closes, self.ma_config.slow_period)
        
        # Store previous values
        self.prev_fast_ma[symbol] = self.fast_ma.get(symbol, fast_ma)
        self.prev_slow_ma[symbol] = self.slow_ma.get(symbol, slow_ma)
        
        # Update current values
        self.fast_ma[symbol] = fast_ma
        self.slow_ma[symbol] = slow_ma
        
        # Check for crossover signals
        self._check_signals(symbol, bar)
    
    def _calculate_sma(self, prices: List[float], period: int) -> float:
        """Calculate Simple Moving Average"""
        if len(prices) < period:
            return 0.0
        return sum(prices[-period:]) / period
    
    def _check_signals(self, symbol: str, bar: Bar):
        """Check for golden cross (buy) or death cross (sell)"""
        # Skip if no previous values
        if symbol not in self.prev_fast_ma or symbol not in self.prev_slow_ma:
            return
        
        fast = self.fast_ma[symbol]
        slow = self.slow_ma[symbol]
        prev_fast = self.prev_fast_ma[symbol]
        prev_slow = self.prev_slow_ma[symbol]
        
        # Golden Cross: fast crosses above slow (buy signal)
        if prev_fast <= prev_slow and fast > slow:
            self._handle_buy_signal(symbol, bar)
        
        # Death Cross: fast crosses below slow (sell signal)
        elif prev_fast >= prev_slow and fast < slow:
            self._handle_sell_signal(symbol, bar)
    
    def _handle_buy_signal(self, symbol: str, bar: Bar):
        """Handle golden cross buy signal"""
        # Don't buy if already long
        if self.has_position(symbol):
            return
        
        # Calculate position size
        position_size = self.calculate_position_size(symbol, bar.close)
        
        if position_size > 0:
            # Place market buy order
            self.buy(symbol, position_size)
    
    def _handle_sell_signal(self, symbol: str, bar: Bar):
        """Handle death cross sell signal"""
        # Only sell if we have a position
        if not self.has_position(symbol):
            return
        
        position = self.get_position(symbol)
        
        # Place market sell order to close position
        self.sell(symbol, position.quantity)


# ============================================================================
# Mean Reversion Strategy
# ============================================================================

@dataclass
class MeanReversionConfig:
    """Configuration for Mean Reversion strategy"""
    bb_period: int = 20  # Bollinger Bands period
    bb_std: float = 2.0  # Standard deviations for bands
    rsi_period: int = 14  # RSI period
    rsi_oversold: float = 30.0  # RSI oversold threshold
    rsi_overbought: float = 70.0  # RSI overbought threshold
    min_bars: int = 20  # Minimum bars before trading
    
    def __post_init__(self):
        """Validate configuration"""
        if self.bb_period < 2:
            raise ValueError("BB period must be at least 2")
        if self.bb_std <= 0:
            raise ValueError("BB standard deviations must be positive")
        if self.rsi_period < 2:
            raise ValueError("RSI period must be at least 2")
        if not 0 <= self.rsi_oversold <= 100:
            raise ValueError("RSI oversold must be between 0 and 100")
        if not 0 <= self.rsi_overbought <= 100:
            raise ValueError("RSI overbought must be between 0 and 100")
        if self.rsi_oversold >= self.rsi_overbought:
            raise ValueError("RSI oversold must be less than overbought")
        if self.min_bars < max(self.bb_period, self.rsi_period):
            self.min_bars = max(self.bb_period, self.rsi_period)


class MeanReversionStrategy(Strategy):
    """
    Mean Reversion Strategy with Bollinger Bands and RSI
    
    This strategy assumes that prices tend to revert to their mean after
    extreme moves. It uses two indicators:
    
    1. Bollinger Bands: Identify price extremes
       - Buy when price touches lower band (oversold)
       - Sell when price touches upper band (overbought)
    
    2. RSI (Relative Strength Index): Confirm momentum exhaustion
       - Buy when RSI < oversold threshold (default: 30)
       - Sell when RSI > overbought threshold (default: 70)
    
    Both conditions must be met for a signal. This reduces false signals
    and improves win rate.
    
    Parameters:
        bb_period: Bollinger Bands period (default: 20)
        bb_std: Standard deviations for bands (default: 2.0)
        rsi_period: RSI calculation period (default: 14)
        rsi_oversold: RSI oversold threshold (default: 30)
        rsi_overbought: RSI overbought threshold (default: 70)
    
    Example:
        >>> config = StrategyConfig(initial_capital=100000)
        >>> mr_config = MeanReversionConfig(bb_period=20, bb_std=2.0)
        >>> strategy = MeanReversionStrategy(config, mr_config)
    """
    
    def __init__(self, config: StrategyConfig, mr_config: Optional[MeanReversionConfig] = None):
        """
        Initialize Mean Reversion strategy
        
        Args:
            config: Base strategy configuration
            mr_config: Mean reversion-specific configuration
        """
        super().__init__(config)
        self.mr_config = mr_config or MeanReversionConfig()
        
        # Bollinger Bands values per symbol
        self.bb_upper: Dict[str, float] = {}
        self.bb_middle: Dict[str, float] = {}
        self.bb_lower: Dict[str, float] = {}
        
        # RSI values per symbol
        self.rsi: Dict[str, float] = {}
        
        # Track RSI calculation state
        self.rsi_gains: Dict[str, List[float]] = {}
        self.rsi_losses: Dict[str, List[float]] = {}
        
        # Track ready symbols
        self.ready_symbols: Set[str] = set()
    
    def on_bar(self, symbol: str, bar: Bar):
        """Process new bar and check for mean reversion signals"""
        # Get bar history
        lookback = max(self.mr_config.bb_period, self.mr_config.rsi_period) + 1
        bars = self.get_bar_history(symbol, lookback=lookback)
        
        # Check if we have enough bars
        if len(bars) < lookback:
            return
        
        # Mark symbol as ready
        self.ready_symbols.add(symbol)
        
        # Calculate indicators
        self._calculate_bollinger_bands(symbol, bars)
        self._calculate_rsi(symbol, bars)
        
        # Check for signals
        self._check_signals(symbol, bar)
    
    def _calculate_bollinger_bands(self, symbol: str, bars: List[Bar]):
        """Calculate Bollinger Bands"""
        closes = [b.close for b in bars[-self.mr_config.bb_period:]]
        
        # Middle band (SMA)
        middle = sum(closes) / len(closes)
        
        # Standard deviation
        variance = sum((c - middle) ** 2 for c in closes) / len(closes)
        std = variance ** 0.5
        
        # Upper and lower bands
        upper = middle + (self.mr_config.bb_std * std)
        lower = middle - (self.mr_config.bb_std * std)
        
        self.bb_upper[symbol] = upper
        self.bb_middle[symbol] = middle
        self.bb_lower[symbol] = lower
    
    def _calculate_rsi(self, symbol: str, bars: List[Bar]):
        """Calculate RSI (Relative Strength Index)"""
        closes = [b.close for b in bars]
        
        # Calculate price changes
        changes = [closes[i] - closes[i-1] for i in range(1, len(closes))]
        
        # Separate gains and losses
        gains = [max(0, change) for change in changes]
        losses = [max(0, -change) for change in changes]
        
        # Calculate average gain and loss
        period = self.mr_config.rsi_period
        if len(gains) < period:
            return
        
        avg_gain = sum(gains[-period:]) / period
        avg_loss = sum(losses[-period:]) / period
        
        # Calculate RSI
        if avg_loss == 0:
            rsi = 100.0
        else:
            rs = avg_gain / avg_loss
            rsi = 100 - (100 / (1 + rs))
        
        self.rsi[symbol] = rsi
    
    def _check_signals(self, symbol: str, bar: Bar):
        """Check for mean reversion signals"""
        # Skip if indicators not calculated
        if symbol not in self.bb_lower or symbol not in self.rsi:
            return
        
        price = bar.close
        bb_lower = self.bb_lower[symbol]
        bb_upper = self.bb_upper[symbol]
        rsi = self.rsi[symbol]
        
        # Buy signal: price at/below lower BB AND RSI oversold
        if price <= bb_lower and rsi <= self.mr_config.rsi_oversold:
            self._handle_buy_signal(symbol, bar)
        
        # Sell signal: price at/above upper BB AND RSI overbought
        elif price >= bb_upper and rsi >= self.mr_config.rsi_overbought:
            self._handle_sell_signal(symbol, bar)
    
    def _handle_buy_signal(self, symbol: str, bar: Bar):
        """Handle oversold buy signal"""
        # Don't buy if already long
        if self.has_position(symbol):
            return
        
        # Calculate position size
        position_size = self.calculate_position_size(symbol, bar.close)
        
        if position_size > 0:
            self.buy(symbol, position_size)
    
    def _handle_sell_signal(self, symbol: str, bar: Bar):
        """Handle overbought sell signal"""
        # Only sell if we have a position
        if not self.has_position(symbol):
            return
        
        position = self.get_position(symbol)
        
        self.sell(symbol, position.quantity)


# ============================================================================
# Momentum Strategy
# ============================================================================

@dataclass
class MomentumConfig:
    """Configuration for Momentum strategy"""
    lookback_period: int = 20  # Momentum lookback period
    momentum_threshold: float = 0.02  # 2% minimum momentum
    macd_fast: int = 12  # MACD fast EMA period
    macd_slow: int = 26  # MACD slow EMA period
    macd_signal: int = 9  # MACD signal line period
    min_bars: int = 26  # Minimum bars before trading
    
    def __post_init__(self):
        """Validate configuration"""
        if self.lookback_period < 2:
            raise ValueError("Lookback period must be at least 2")
        if self.momentum_threshold <= 0:
            raise ValueError("Momentum threshold must be positive")
        if self.macd_fast >= self.macd_slow:
            raise ValueError("MACD fast must be less than slow")
        if self.macd_fast < 2:
            raise ValueError("MACD fast period must be at least 2")
        if self.macd_signal < 2:
            raise ValueError("MACD signal period must be at least 2")
        if self.min_bars < max(self.lookback_period, self.macd_slow):
            self.min_bars = max(self.lookback_period, self.macd_slow)


class MomentumStrategy(Strategy):
    """
    Momentum Strategy with MACD Confirmation
    
    This strategy rides trends by identifying strong momentum:
    
    1. Rate of Change (ROC): Measures momentum
       - Buy when ROC > threshold (strong upward momentum)
       - Sell when ROC < -threshold (strong downward momentum)
    
    2. MACD: Confirms trend direction and strength
       - Buy when MACD > signal line (bullish)
       - Sell when MACD < signal line (bearish)
    
    Both conditions must be met for a signal. This ensures we only
    enter trades when momentum is strong and confirmed.
    
    Parameters:
        lookback_period: Period for momentum calculation (default: 20)
        momentum_threshold: Minimum ROC for signal (default: 0.02 = 2%)
        macd_fast: MACD fast EMA period (default: 12)
        macd_slow: MACD slow EMA period (default: 26)
        macd_signal: MACD signal line period (default: 9)
    
    Example:
        >>> config = StrategyConfig(initial_capital=100000)
        >>> mom_config = MomentumConfig(lookback_period=20, momentum_threshold=0.02)
        >>> strategy = MomentumStrategy(config, mom_config)
    """
    
    def __init__(self, config: StrategyConfig, mom_config: Optional[MomentumConfig] = None):
        """
        Initialize Momentum strategy
        
        Args:
            config: Base strategy configuration
            mom_config: Momentum-specific configuration
        """
        super().__init__(config)
        self.mom_config = mom_config or MomentumConfig()
        
        # Momentum values per symbol
        self.momentum: Dict[str, float] = {}
        
        # MACD values per symbol
        self.macd: Dict[str, float] = {}
        self.macd_signal: Dict[str, float] = {}
        self.macd_histogram: Dict[str, float] = {}
        
        # EMA state for MACD calculation
        self.ema_fast: Dict[str, float] = {}
        self.ema_slow: Dict[str, float] = {}
        self.ema_signal: Dict[str, float] = {}
        
        # Track ready symbols
        self.ready_symbols: Set[str] = set()
    
    def on_bar(self, symbol: str, bar: Bar):
        """Process new bar and check for momentum signals"""
        # Get bar history
        lookback = max(self.mom_config.lookback_period, self.mom_config.macd_slow) + self.mom_config.macd_signal
        bars = self.get_bar_history(symbol, lookback=lookback)
        
        # Check if we have enough bars
        if len(bars) < self.mom_config.min_bars:
            return
        
        # Mark symbol as ready
        self.ready_symbols.add(symbol)
        
        # Calculate indicators
        self._calculate_momentum(symbol, bars)
        self._calculate_macd(symbol, bars)
        
        # Check for signals
        self._check_signals(symbol, bar)
    
    def _calculate_momentum(self, symbol: str, bars: List[Bar]):
        """Calculate Rate of Change (ROC) momentum"""
        period = self.mom_config.lookback_period
        
        if len(bars) < period + 1:
            return
        
        current_price = bars[-1].close
        past_price = bars[-(period + 1)].close
        
        # Calculate ROC
        if past_price != 0:
            roc = (current_price - past_price) / past_price
            self.momentum[symbol] = roc
    
    def _calculate_macd(self, symbol: str, bars: List[Bar]):
        """Calculate MACD (Moving Average Convergence Divergence)"""
        closes = [b.close for b in bars]
        
        # Calculate EMAs
        fast_ema = self._calculate_ema(closes, self.mom_config.macd_fast)
        slow_ema = self._calculate_ema(closes, self.mom_config.macd_slow)
        
        # MACD line
        macd = fast_ema - slow_ema
        
        # Signal line (EMA of MACD)
        if symbol not in self.macd_signal:
            # Initialize signal line
            signal = macd
        else:
            # Update signal line with EMA
            multiplier = 2 / (self.mom_config.macd_signal + 1)
            signal = (macd * multiplier) + (self.macd_signal[symbol] * (1 - multiplier))
        
        # Histogram
        histogram = macd - signal
        
        self.macd[symbol] = macd
        self.macd_signal[symbol] = signal
        self.macd_histogram[symbol] = histogram
    
    def _calculate_ema(self, prices: List[float], period: int) -> float:
        """Calculate Exponential Moving Average"""
        if len(prices) < period:
            return 0.0
        
        # Use SMA for initial EMA
        if len(prices) == period:
            return sum(prices) / period
        
        # Calculate EMA
        multiplier = 2 / (period + 1)
        ema = prices[0]
        
        for price in prices[1:]:
            ema = (price * multiplier) + (ema * (1 - multiplier))
        
        return ema
    
    def _check_signals(self, symbol: str, bar: Bar):
        """Check for momentum signals"""
        # Skip if indicators not calculated
        if symbol not in self.momentum or symbol not in self.macd:
            return
        
        momentum = self.momentum[symbol]
        macd = self.macd[symbol]
        macd_signal = self.macd_signal[symbol]
        
        # Buy signal: strong positive momentum AND bullish MACD
        if momentum > self.mom_config.momentum_threshold and macd > macd_signal:
            self._handle_buy_signal(symbol, bar)
        
        # Sell signal: strong negative momentum AND bearish MACD
        elif momentum < -self.mom_config.momentum_threshold and macd < macd_signal:
            self._handle_sell_signal(symbol, bar)
    
    def _handle_buy_signal(self, symbol: str, bar: Bar):
        """Handle bullish momentum signal"""
        # Don't buy if already long
        if self.has_position(symbol):
            return
        
        # Calculate position size
        position_size = self.calculate_position_size(symbol, bar.close)
        
        if position_size > 0:
            self.buy(symbol, position_size)
    
    def _handle_sell_signal(self, symbol: str, bar: Bar):
        """Handle bearish momentum signal"""
        # Only sell if we have a position
        if not self.has_position(symbol):
            return
        
        position = self.get_position(symbol)
        
        self.sell(symbol, position.quantity)


# ============================================================================
# Template Registry
# ============================================================================

# Registry of available strategy templates
STRATEGY_TEMPLATES = {
    'ma_cross': MovingAverageCrossStrategy,
    'mean_reversion': MeanReversionStrategy,
    'momentum': MomentumStrategy,
}


def get_template(name: str):
    """
    Get a strategy template by name
    
    Args:
        name: Template name ('ma_cross', 'mean_reversion', 'momentum')
    
    Returns:
        Strategy class
    
    Raises:
        ValueError: If template name not found
    """
    if name not in STRATEGY_TEMPLATES:
        available = ', '.join(STRATEGY_TEMPLATES.keys())
        raise ValueError(f"Unknown template '{name}'. Available: {available}")
    
    return STRATEGY_TEMPLATES[name]


def list_templates() -> List[str]:
    """Get list of available strategy template names"""
    return list(STRATEGY_TEMPLATES.keys())

