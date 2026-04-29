"""
Base strategy class for all trading strategies.

Provides lifecycle management, event handling, and integration
with the event bus system.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional, Any
import logging
from decimal import Decimal

from core.event_bus import Event, EventType
from .signal import Signal, SignalType, SignalStrength


logger = logging.getLogger(__name__)


class StrategyState(Enum):
    """Strategy lifecycle states"""
    INITIALIZING = "INITIALIZING"  # Strategy is being initialized
    READY = "READY"                # Initialized, waiting to start
    RUNNING = "RUNNING"            # Actively trading
    PAUSED = "PAUSED"              # Temporarily stopped
    STOPPED = "STOPPED"            # Permanently stopped
    ERROR = "ERROR"                # Error state


@dataclass
class StrategyConfig:
    """
    Configuration for a trading strategy.
    
    Attributes:
        name: Strategy identifier
        symbols: List of symbols to trade
        enabled: Whether strategy is active
        parameters: Strategy-specific parameters
        risk_limits: Risk management settings
    
    Example:
        >>> config = StrategyConfig(
        ...     name="BollingerBands_AAPL",
        ...     symbols=["AAPL"],
        ...     enabled=True,
        ...     parameters={
        ...         "period": 20,
        ...         "std_dev": 2.0,
        ...         "rsi_period": 14
        ...     },
        ...     risk_limits={
        ...         "max_position_size": 1000,
        ...         "max_daily_loss": 500.0,
        ...         "position_sizing": "fixed"
        ...     }
        ... )
    """
    name: str
    symbols: List[str]
    enabled: bool = True
    parameters: Dict[str, Any] = field(default_factory=dict)
    risk_limits: Dict[str, Any] = field(default_factory=dict)
    account_id: str = ""
    
    def validate(self) -> bool:
        """
        Validate configuration.
        
        Returns:
            True if configuration is valid
        """
        if not self.name or not self.symbols:
            return False
        
        # Validate risk limits
        if 'max_position_size' in self.risk_limits:
            if self.risk_limits['max_position_size'] <= 0:
                return False
        
        if 'max_daily_loss' in self.risk_limits:
            if self.risk_limits['max_daily_loss'] <= 0:
                return False
        
        return True


class BaseStrategy(ABC):
    """
    Abstract base class for all trading strategies.
    
    Provides:
    - Lifecycle management (start, stop, pause, resume)
    - Event bus integration
    - Signal generation framework
    - Position and performance tracking
    - Configuration management with hot-reload
    
    Subclasses must implement:
    - on_bar(): Process new market data
    - validate_signal(): Validate signals before sending
    
    Example:
        >>> class MyStrategy(BaseStrategy):
        ...     def on_bar(self, symbol: str, bar_data: dict):
        ...         # Analyze bar_data
        ...         if condition_met:
        ...             signal = Signal(
        ...                 symbol=symbol,
        ...                 signal_type=SignalType.BUY,
        ...                 strength=SignalStrength.STRONG,
        ...                 timestamp=datetime.now()
        ...             )
        ...             self.generate_signal(signal)
        ...     
        ...     def validate_signal(self, signal: Signal) -> bool:
        ...         # Check risk limits
        ...         return signal.validate()
    """
    
    def __init__(self, config: StrategyConfig, event_bus=None):
        """
        Initialize strategy.
        
        Args:
            config: Strategy configuration
            event_bus: Event bus instance for communication
        """
        self.config = config
        self.event_bus = event_bus
        self.state = StrategyState.INITIALIZING
        
        # Performance tracking
        self.signals_generated = 0
        self.signals_accepted = 0
        self.signals_rejected = 0
        self.last_signal_time: Optional[datetime] = None
        
        # Position tracking
        self._positions: Dict[str, Dict[str, Any]] = {}
        
        # State management
        self.start_time: Optional[datetime] = None
        self.stop_time: Optional[datetime] = None
        self.error_message: Optional[str] = None
        
        # Subscribe to events if event bus provided
        if self.event_bus:
            self._subscribe_to_events()
        
        logger.info(f"Strategy {self.config.name} initialized")
        self.state = StrategyState.READY
    
    def _subscribe_to_events(self):
        """Subscribe to relevant events on the event bus"""
        if not self.event_bus:
            return
        
        # Subscribe to market data events.
        # Handlers accept a plain dict (event_data), so wrap with a lambda that
        # extracts event.data — matching the real EventBus contract where publish()
        # calls handler(event) with the full Event object.
        self.event_bus.subscribe(EventType.MARKET_DATA_RECEIVED, lambda e: self._handle_market_data(e.data))

        # Subscribe to order events
        self.event_bus.subscribe(EventType.ORDER_FILLED, lambda e: self._handle_order_filled(e.data))
        self.event_bus.subscribe(EventType.ORDER_CANCELLED, lambda e: self._handle_order_cancelled(e.data))

        # Subscribe to position updates
        self.event_bus.subscribe(EventType.POSITION_UPDATED, lambda e: self._handle_position_update(e.data))
        
        logger.debug(f"Strategy {self.config.name} subscribed to events")
    
    def start(self):
        """
        Start the strategy.
        
        Transitions state from READY, PAUSED, or STOPPED to RUNNING.
        """
        if self.state not in [StrategyState.READY, StrategyState.PAUSED, StrategyState.STOPPED]:
            logger.warning(f"Cannot start strategy from state {self.state}")
            return
        
        self.state = StrategyState.RUNNING
        self.start_time = datetime.now()
        self.stop_time = None
        
        logger.info(f"Strategy {self.config.name} started")
        
        if self.event_bus:
            self.event_bus.publish(Event(
                EventType.STRATEGY_STARTED,
                data={'strategy_name': self.config.name, 'timestamp': self.start_time.isoformat()},
                source=self.config.name,
            ))
    
    def stop(self):
        """
        Stop the strategy permanently.
        
        Transitions state to STOPPED.
        """
        if self.state == StrategyState.STOPPED:
            return
        
        self.state = StrategyState.STOPPED
        self.stop_time = datetime.now()
        
        logger.info(f"Strategy {self.config.name} stopped")
        
        if self.event_bus:
            self.event_bus.publish(Event(
                EventType.STRATEGY_STOPPED,
                data={'strategy_name': self.config.name, 'timestamp': self.stop_time.isoformat()},
                source=self.config.name,
            ))
    
    def pause(self):
        """
        Pause the strategy temporarily.
        
        Transitions state from RUNNING to PAUSED.
        """
        if self.state != StrategyState.RUNNING:
            logger.warning(f"Cannot pause strategy from state {self.state}")
            return
        
        self.state = StrategyState.PAUSED
        
        logger.info(f"Strategy {self.config.name} paused")
        
        if self.event_bus:
            self.event_bus.publish(Event(
                EventType.STRATEGY_PAUSED,
                data={'strategy_name': self.config.name, 'timestamp': datetime.now().isoformat()},
                source=self.config.name,
            ))
    
    def resume(self):
        """
        Resume the strategy from paused state.
        
        Transitions state from PAUSED to RUNNING.
        """
        if self.state != StrategyState.PAUSED:
            logger.warning(f"Cannot resume strategy from state {self.state}")
            return
        
        self.state = StrategyState.RUNNING
        
        logger.info(f"Strategy {self.config.name} resumed")
        
        if self.event_bus:
            self.event_bus.publish(Event(
                EventType.STRATEGY_RESUMED,
                data={'strategy_name': self.config.name, 'timestamp': datetime.now().isoformat()},
                source=self.config.name,
            ))
    
    def reload_config(self, new_config: StrategyConfig):
        """
        Hot-reload strategy configuration.
        
        Args:
            new_config: New configuration to apply
        """
        if not new_config.validate():
            logger.error(f"Invalid configuration for {self.config.name}")
            return
        
        old_config = self.config
        self.config = new_config
        
        logger.info(f"Strategy {self.config.name} configuration reloaded")
        
        if self.event_bus:
            self.event_bus.publish(Event(
                EventType.STRATEGY_CONFIG_RELOADED,
                data={
                    'strategy_name': self.config.name,
                    'old_config': old_config.__dict__,
                    'new_config': new_config.__dict__,
                    'timestamp': datetime.now().isoformat(),
                },
                source=self.config.name,
            ))
    
    def _handle_market_data(self, event_data: dict):
        """
        Handle market data events from event bus.
        
        Args:
            event_data: Market data event payload
        """
        if self.state != StrategyState.RUNNING:
            return
        
        symbol = event_data.get('symbol')
        if symbol not in self.config.symbols:
            return
        
        # Call subclass implementation
        try:
            self.on_bar(symbol, event_data)
        except Exception as e:
            logger.error(f"Error in on_bar for {self.config.name}: {e}")
            self.state = StrategyState.ERROR
            self.error_message = str(e)
    
    def _handle_order_filled(self, event_data: dict):
        """
        Handle order filled events.
        
        Args:
            event_data: Order filled event payload
        """
        symbol = event_data.get('symbol')
        strategy_name = event_data.get('strategy_name')
        
        # Only process events for this strategy
        if strategy_name != self.config.name:
            return
        
        logger.info(f"Order filled for {self.config.name}: {symbol}")
        
        # Update position tracking
        self._update_position(event_data)
    
    def _handle_order_cancelled(self, event_data: dict):
        """
        Handle order cancelled events.
        
        Args:
            event_data: Order cancelled event payload
        """
        strategy_name = event_data.get('strategy_name')
        
        if strategy_name != self.config.name:
            return
        
        logger.warning(f"Order cancelled for {self.config.name}")
    
    def _handle_position_update(self, event_data: dict):
        """
        Handle position update events.
        
        Args:
            event_data: Position update event payload
        """
        symbol = event_data.get('symbol')
        strategy_name = event_data.get('strategy_name')
        
        if strategy_name != self.config.name:
            return
        
        self._update_position(event_data)
    
    def _update_position(self, position_data: dict):
        """
        Update internal position tracking.
        
        Args:
            position_data: Position information
        """
        symbol = position_data.get('symbol')
        if not symbol:
            return
        
        self._positions[symbol] = {
            'quantity': position_data.get('quantity', 0),
            'avg_price': position_data.get('avg_price', 0.0),
            'market_value': position_data.get('market_value', 0.0),
            'unrealized_pnl': position_data.get('unrealized_pnl', 0.0),
            'last_update': datetime.now()
        }
    
    def generate_signal(self, signal: Signal):
        """
        Generate a trading signal.
        
        Validates signal and publishes to event bus if valid.
        
        Args:
            signal: Signal to generate
        """
        self.signals_generated += 1
        signal.strategy_name = self.config.name
        
        # Validate signal
        if not self.validate_signal(signal):
            self.signals_rejected += 1
            logger.warning(f"Signal rejected: {signal}")
            return
        
        self.signals_accepted += 1
        self.last_signal_time = signal.timestamp
        
        logger.info(f"Signal generated: {signal}")
        
        # Publish to event bus
        if self.event_bus:
            self.event_bus.publish(Event(
                EventType.SIGNAL_GENERATED,
                data=signal.to_dict(),
                source=self.config.name,
            ))
    
    def get_position(self, symbol: str) -> Optional[Dict[str, Any]]:
        """
        Get current position for a symbol.
        
        Args:
            symbol: Trading symbol
            
        Returns:
            Position information or None if no position
        """
        return self._positions.get(symbol)
    
    def has_position(self, symbol: str) -> bool:
        """
        Check if strategy has an open position for symbol.
        
        Args:
            symbol: Trading symbol
            
        Returns:
            True if position exists with non-zero quantity
        """
        position = self.get_position(symbol)
        return position is not None and position.get('quantity', 0) != 0
    
    def get_performance_summary(self) -> Dict[str, Any]:
        """
        Get strategy performance summary.
        
        Returns:
            Dictionary with performance metrics
        """
        uptime = None
        if self.start_time:
            end_time = self.stop_time or datetime.now()
            uptime = (end_time - self.start_time).total_seconds()
        
        return {
            'strategy_name': self.config.name,
            'account_id': self.config.account_id,
            'state': self.state.value,
            'signals_generated': self.signals_generated,
            'signals_accepted': self.signals_accepted,
            'signals_rejected': self.signals_rejected,
            'acceptance_rate': (self.signals_accepted / self.signals_generated 
                               if self.signals_generated > 0 else 0.0),
            'uptime_seconds': uptime,
            'active_positions': len([p for p in self._positions.values() 
                                    if p.get('quantity', 0) != 0]),
            'last_signal_time': self.last_signal_time.isoformat() 
                               if self.last_signal_time else None
        }
    
    # Abstract methods that subclasses must implement
    
    @abstractmethod
    def on_bar(self, symbol: str, bar_data: dict):
        """
        Process new bar data for a symbol.
        
        Called when new market data arrives. Subclasses should implement
        their trading logic here and call generate_signal() when appropriate.
        
        Args:
            symbol: Trading symbol
            bar_data: Dictionary containing OHLCV and other market data
                {
                    'timestamp': datetime,
                    'open': float,
                    'high': float,
                    'low': float,
                    'close': float,
                    'volume': int,
                    ...
                }
        """
        pass
    
    @abstractmethod
    def validate_signal(self, signal: Signal) -> bool:
        """
        Validate a signal before sending.
        
        Subclasses should implement risk checks, position size validation,
        and any other signal validation logic.
        
        Args:
            signal: Signal to validate
            
        Returns:
            True if signal is valid and should be sent
        """
        pass
    
    def __str__(self) -> str:
        """String representation"""
        return f"Strategy({self.config.name}, state={self.state.value})"
    
    def __repr__(self) -> str:
        """Detailed representation"""
        return (f"BaseStrategy(name='{self.config.name}', "
                f"state={self.state.value}, "
                f"symbols={self.config.symbols})")
