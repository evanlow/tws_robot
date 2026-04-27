"""
Event Bus for decoupled, event-driven communication between modules.

The Event Bus pattern enables loose coupling by allowing modules to communicate
through events rather than direct method calls. This improves testability,
maintainability, and allows for easy addition of new features.

Usage:
    # Create event bus
    bus = EventBus()
    
    # Subscribe to events
    def handle_order_fill(event):
        print(f"Order filled: {event.data}")
    
    bus.subscribe(EventType.ORDER_FILLED, handle_order_fill)
    
    # Publish events
    bus.publish(Event(EventType.ORDER_FILLED, data={"orderId": 123}))
"""

from enum import Enum, auto
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional
from datetime import datetime
import logging
import threading
from collections import defaultdict

logger = logging.getLogger(__name__)


class EventType(Enum):
    """Event types for the trading system."""
    
    # Connection Events
    CONNECTION_ESTABLISHED = auto()
    CONNECTION_LOST = auto()
    CONNECTION_RECONNECTING = auto()
    CONNECTION_FAILED = auto()
    API_READY = auto()
    
    # Market Data Events
    MARKET_DATA_RECEIVED = auto()
    TICK_PRICE = auto()
    TICK_SIZE = auto()
    HISTORICAL_DATA = auto()
    HISTORICAL_DATA_END = auto()
    
    # Order Events
    ORDER_SUBMITTED = auto()
    ORDER_ACCEPTED = auto()
    ORDER_FILLED = auto()
    ORDER_PARTIALLY_FILLED = auto()
    ORDER_CANCELLED = auto()
    ORDER_REJECTED = auto()
    ORDER_STATUS_UPDATE = auto()
    
    # Position Events
    POSITION_OPENED = auto()
    POSITION_UPDATED = auto()
    POSITION_CLOSED = auto()
    
    # Account Events
    ACCOUNT_UPDATE = auto()
    PORTFOLIO_UPDATE = auto()
    PNL_UPDATE = auto()
    
    # Strategy Events
    STRATEGY_STARTED = auto()
    STRATEGY_STOPPED = auto()
    STRATEGY_PAUSED = auto()
    STRATEGY_RESUMED = auto()
    STRATEGY_CONFIG_RELOADED = auto()
    STRATEGY_ERROR = auto()
    SIGNAL_GENERATED = auto()
    
    # Risk Events
    RISK_LIMIT_WARNING = auto()
    RISK_LIMIT_BREACHED = auto()
    POSITION_SIZE_CHECK = auto()
    
    # System Events
    SYSTEM_ERROR = auto()
    SYSTEM_WARNING = auto()
    SYSTEM_INFO = auto()
    HEARTBEAT = auto()


@dataclass
class Event:
    """
    Event object containing type, data, and metadata.
    
    Attributes:
        event_type: The type of event from EventType enum
        data: Event-specific data (order details, market data, etc.)
        timestamp: When the event was created
        source: Optional identifier of event source module
        correlation_id: Optional ID for correlating related events
    """
    event_type: EventType
    data: Any = None
    timestamp: datetime = None
    source: Optional[str] = None
    correlation_id: Optional[str] = None
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now()
    
    def __repr__(self):
        return (f"Event(type={self.event_type.name}, "
                f"source={self.source}, "
                f"time={self.timestamp.strftime('%H:%M:%S.%f')[:-3]})")


class EventBus:
    """
    Thread-safe Event Bus for pub-sub messaging between components.
    
    Features:
    - Thread-safe subscription and publishing
    - Multiple subscribers per event type
    - Event history for debugging
    - Statistics tracking
    - Wildcard subscriptions (subscribe to all events)
    """
    
    def __init__(self, max_history: int = 1000):
        """
        Initialize Event Bus.
        
        Args:
            max_history: Maximum number of events to keep in history
        """
        self._subscribers: Dict[EventType, List[Callable]] = defaultdict(list)
        self._wildcard_subscribers: List[Callable] = []
        self._event_history: List[Event] = []
        self._max_history = max_history
        self._lock = threading.RLock()
        self._stats = defaultdict(int)
        logger.info("Event Bus initialized")
    
    def subscribe(self, event_type: EventType, handler: Callable[[Event], None]) -> None:
        """
        Subscribe to events of a specific type.
        
        Args:
            event_type: The type of events to subscribe to
            handler: Callable that takes an Event object
        
        Example:
            def my_handler(event):
                print(f"Received: {event}")
            
            bus.subscribe(EventType.ORDER_FILLED, my_handler)
        """
        with self._lock:
            if handler not in self._subscribers[event_type]:
                self._subscribers[event_type].append(handler)
                logger.debug(f"Subscribed {handler.__name__} to {event_type.name}")
    
    def subscribe_all(self, handler: Callable[[Event], None]) -> None:
        """
        Subscribe to all events (wildcard subscription).
        
        Args:
            handler: Callable that takes an Event object
        
        Example:
            def log_all(event):
                print(f"Event: {event}")
            
            bus.subscribe_all(log_all)
        """
        with self._lock:
            if handler not in self._wildcard_subscribers:
                self._wildcard_subscribers.append(handler)
                logger.debug(f"Subscribed {handler.__name__} to ALL events")
    
    def unsubscribe(self, event_type: EventType, handler: Callable[[Event], None]) -> None:
        """
        Unsubscribe from events of a specific type.
        
        Args:
            event_type: The type of events to unsubscribe from
            handler: The handler to remove
        """
        with self._lock:
            if handler in self._subscribers[event_type]:
                self._subscribers[event_type].remove(handler)
                logger.debug(f"Unsubscribed {handler.__name__} from {event_type.name}")
    
    def unsubscribe_all(self, handler: Callable[[Event], None]) -> None:
        """
        Unsubscribe from all events.
        
        Args:
            handler: The handler to remove
        """
        with self._lock:
            if handler in self._wildcard_subscribers:
                self._wildcard_subscribers.remove(handler)
                logger.debug(f"Unsubscribed {handler.__name__} from ALL events")
    
    def publish(self, event: Event) -> None:
        """
        Publish an event to all subscribers.
        
        Args:
            event: The Event object to publish
        
        Example:
            event = Event(EventType.ORDER_FILLED, data={"orderId": 123})
            bus.publish(event)
        """
        with self._lock:
            # Add to history
            self._event_history.append(event)
            if len(self._event_history) > self._max_history:
                self._event_history.pop(0)
            
            # Update stats
            self._stats[event.event_type] += 1
            self._stats['total'] += 1
            
            # Get subscribers
            handlers = self._subscribers[event.event_type].copy()
            wildcard_handlers = self._wildcard_subscribers.copy()
        
        # Call handlers outside lock to avoid deadlocks
        all_handlers = handlers + wildcard_handlers
        
        for handler in all_handlers:
            try:
                handler(event)
            except Exception as e:
                logger.error(f"Error in event handler {handler.__name__}: {e}", 
                           exc_info=True)
        
        logger.debug(f"Published {event.event_type.name} to {len(all_handlers)} handlers")
    
    def get_history(self, event_type: Optional[EventType] = None, 
                   limit: int = 100) -> List[Event]:
        """
        Get event history, optionally filtered by type.
        
        Args:
            event_type: Optional filter by event type
            limit: Maximum number of events to return
        
        Returns:
            List of Event objects (most recent first)
        """
        with self._lock:
            history = self._event_history.copy()
        
        if event_type:
            history = [e for e in history if e.event_type == event_type]
        
        return list(reversed(history[-limit:]))
    
    def get_stats(self) -> Dict[str, int]:
        """
        Get event statistics.
        
        Returns:
            Dictionary with event counts by type
        """
        with self._lock:
            return dict(self._stats)
    
    def clear_history(self) -> None:
        """Clear event history."""
        with self._lock:
            self._event_history.clear()
            logger.debug("Event history cleared")
    
    def clear_stats(self) -> None:
        """Clear event statistics."""
        with self._lock:
            self._stats.clear()
            logger.debug("Event statistics cleared")
    
    def get_subscriber_count(self, event_type: Optional[EventType] = None) -> int:
        """
        Get number of subscribers for an event type or all types.
        
        Args:
            event_type: Optional event type to check, None for total
        
        Returns:
            Number of subscribers
        """
        with self._lock:
            if event_type:
                return len(self._subscribers[event_type])
            else:
                return sum(len(subs) for subs in self._subscribers.values())


# Global event bus instance (singleton pattern)
_global_event_bus: Optional[EventBus] = None


def get_event_bus() -> EventBus:
    """
    Get or create the global event bus instance.
    
    Returns:
        The global EventBus instance
    """
    global _global_event_bus
    if _global_event_bus is None:
        _global_event_bus = EventBus()
    return _global_event_bus


def reset_event_bus() -> None:
    """Reset the global event bus (useful for testing)."""
    global _global_event_bus
    _global_event_bus = None


if __name__ == "__main__":
    # Example usage
    logging.basicConfig(level=logging.DEBUG)
    
    bus = EventBus()
    
    # Example handlers
    def handle_order_fill(event: Event):
        print(f"✅ Order filled: {event.data}")
    
    def handle_connection(event: Event):
        print(f"🔌 Connection: {event.event_type.name}")
    
    def log_all_events(event: Event):
        print(f"📋 Log: {event}")
    
    # Subscribe to specific events
    bus.subscribe(EventType.ORDER_FILLED, handle_order_fill)
    bus.subscribe(EventType.CONNECTION_ESTABLISHED, handle_connection)
    
    # Subscribe to all events
    bus.subscribe_all(log_all_events)
    
    # Publish some events
    bus.publish(Event(EventType.CONNECTION_ESTABLISHED, source="TWS"))
    bus.publish(Event(EventType.ORDER_FILLED, data={"orderId": 123, "shares": 100}))
    bus.publish(Event(EventType.MARKET_DATA_RECEIVED, data={"symbol": "AAPL", "price": 150.25}))
    
    # Show statistics
    print("\nEvent Statistics:")
    for event_type, count in bus.get_stats().items():
        print(f"  {event_type}: {count}")
    
    print(f"\nTotal subscribers: {bus.get_subscriber_count()}")
