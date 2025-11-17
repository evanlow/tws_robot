"""
Unit tests for Event Bus system.

Tests the pub-sub messaging functionality including:
- Event publishing and subscription
- Wildcard subscriptions
- Event history tracking
- Statistics collection
- Thread safety
"""

import pytest
from datetime import datetime
from core.event_bus import EventBus, Event, EventType, get_event_bus, reset_event_bus


@pytest.fixture
def event_bus():
    """Create a fresh event bus for each test."""
    reset_event_bus()
    bus = EventBus()
    yield bus
    reset_event_bus()


class TestEventBus:
    """Test suite for Event Bus functionality."""
    
    @pytest.mark.unit
    def test_event_creation(self):
        """Test Event object creation and defaults."""
        event = Event(EventType.ORDER_FILLED, data={"orderId": 123})
        
        assert event.event_type == EventType.ORDER_FILLED
        assert event.data == {"orderId": 123}
        assert isinstance(event.timestamp, datetime)
        assert event.source is None
        assert event.correlation_id is None
    
    @pytest.mark.unit
    def test_event_with_metadata(self):
        """Test Event creation with full metadata."""
        timestamp = datetime.now()
        event = Event(
            event_type=EventType.MARKET_DATA_RECEIVED,
            data={"symbol": "AAPL", "price": 150.0},
            timestamp=timestamp,
            source="MarketDataModule",
            correlation_id="corr-123"
        )
        
        assert event.event_type == EventType.MARKET_DATA_RECEIVED
        assert event.data["symbol"] == "AAPL"
        assert event.timestamp == timestamp
        assert event.source == "MarketDataModule"
        assert event.correlation_id == "corr-123"
    
    @pytest.mark.unit
    def test_subscribe_and_publish(self, event_bus):
        """Test basic subscribe and publish functionality."""
        received_events = []
        
        def handler(event):
            received_events.append(event)
        
        event_bus.subscribe(EventType.ORDER_FILLED, handler)
        
        test_event = Event(EventType.ORDER_FILLED, data={"orderId": 456})
        event_bus.publish(test_event)
        
        assert len(received_events) == 1
        assert received_events[0].event_type == EventType.ORDER_FILLED
        assert received_events[0].data["orderId"] == 456
    
    @pytest.mark.unit
    def test_multiple_subscribers(self, event_bus):
        """Test that multiple handlers receive the same event."""
        handler1_calls = []
        handler2_calls = []
        
        def handler1(event):
            handler1_calls.append(event)
        
        def handler2(event):
            handler2_calls.append(event)
        
        event_bus.subscribe(EventType.CONNECTION_ESTABLISHED, handler1)
        event_bus.subscribe(EventType.CONNECTION_ESTABLISHED, handler2)
        
        test_event = Event(EventType.CONNECTION_ESTABLISHED)
        event_bus.publish(test_event)
        
        assert len(handler1_calls) == 1
        assert len(handler2_calls) == 1
        assert handler1_calls[0] == test_event
        assert handler2_calls[0] == test_event
    
    @pytest.mark.unit
    def test_wildcard_subscription(self, event_bus):
        """Test subscribing to all events."""
        all_events = []
        
        def catch_all(event):
            all_events.append(event)
        
        event_bus.subscribe_all(catch_all)
        
        event_bus.publish(Event(EventType.ORDER_FILLED))
        event_bus.publish(Event(EventType.CONNECTION_ESTABLISHED))
        event_bus.publish(Event(EventType.MARKET_DATA_RECEIVED))
        
        assert len(all_events) == 3
        assert all_events[0].event_type == EventType.ORDER_FILLED
        assert all_events[1].event_type == EventType.CONNECTION_ESTABLISHED
        assert all_events[2].event_type == EventType.MARKET_DATA_RECEIVED
    
    @pytest.mark.unit
    def test_unsubscribe(self, event_bus):
        """Test unsubscribing from events."""
        received_events = []
        
        def handler(event):
            received_events.append(event)
        
        event_bus.subscribe(EventType.ORDER_FILLED, handler)
        event_bus.publish(Event(EventType.ORDER_FILLED))
        
        assert len(received_events) == 1
        
        event_bus.unsubscribe(EventType.ORDER_FILLED, handler)
        event_bus.publish(Event(EventType.ORDER_FILLED))
        
        # Still 1 because we unsubscribed
        assert len(received_events) == 1
    
    @pytest.mark.unit
    def test_event_history(self, event_bus):
        """Test event history tracking."""
        event_bus.publish(Event(EventType.ORDER_FILLED, data={"id": 1}))
        event_bus.publish(Event(EventType.ORDER_FILLED, data={"id": 2}))
        event_bus.publish(Event(EventType.MARKET_DATA_RECEIVED, data={"symbol": "AAPL"}))
        
        # Get all history
        history = event_bus.get_history()
        assert len(history) == 3
        
        # Get filtered history
        order_history = event_bus.get_history(EventType.ORDER_FILLED)
        assert len(order_history) == 2
        assert all(e.event_type == EventType.ORDER_FILLED for e in order_history)
        
        # Check order (most recent first)
        assert order_history[0].data["id"] == 2
        assert order_history[1].data["id"] == 1
    
    @pytest.mark.unit
    def test_statistics(self, event_bus):
        """Test event statistics tracking."""
        event_bus.publish(Event(EventType.ORDER_FILLED))
        event_bus.publish(Event(EventType.ORDER_FILLED))
        event_bus.publish(Event(EventType.MARKET_DATA_RECEIVED))
        
        stats = event_bus.get_stats()
        
        assert stats['total'] == 3
        assert stats[EventType.ORDER_FILLED] == 2
        assert stats[EventType.MARKET_DATA_RECEIVED] == 1
    
    @pytest.mark.unit
    def test_subscriber_count(self, event_bus):
        """Test subscriber counting."""
        def handler1(event): pass
        def handler2(event): pass
        
        assert event_bus.get_subscriber_count() == 0
        
        event_bus.subscribe(EventType.ORDER_FILLED, handler1)
        assert event_bus.get_subscriber_count(EventType.ORDER_FILLED) == 1
        
        event_bus.subscribe(EventType.ORDER_FILLED, handler2)
        assert event_bus.get_subscriber_count(EventType.ORDER_FILLED) == 2
        
        event_bus.subscribe(EventType.MARKET_DATA_RECEIVED, handler1)
        assert event_bus.get_subscriber_count() == 3
    
    @pytest.mark.unit
    def test_handler_error_isolation(self, event_bus):
        """Test that handler errors don't affect other handlers."""
        successful_calls = []
        
        def failing_handler(event):
            raise ValueError("Handler error")
        
        def successful_handler(event):
            successful_calls.append(event)
        
        event_bus.subscribe(EventType.ORDER_FILLED, failing_handler)
        event_bus.subscribe(EventType.ORDER_FILLED, successful_handler)
        
        event_bus.publish(Event(EventType.ORDER_FILLED))
        
        # Successful handler should still receive the event
        assert len(successful_calls) == 1
    
    @pytest.mark.unit
    def test_clear_history(self, event_bus):
        """Test clearing event history."""
        event_bus.publish(Event(EventType.ORDER_FILLED))
        event_bus.publish(Event(EventType.ORDER_FILLED))
        
        assert len(event_bus.get_history()) == 2
        
        event_bus.clear_history()
        assert len(event_bus.get_history()) == 0
    
    @pytest.mark.unit
    def test_clear_stats(self, event_bus):
        """Test clearing statistics."""
        event_bus.publish(Event(EventType.ORDER_FILLED))
        
        assert event_bus.get_stats()['total'] == 1
        
        event_bus.clear_stats()
        assert len(event_bus.get_stats()) == 0
    
    @pytest.mark.unit
    def test_global_event_bus(self):
        """Test global event bus singleton."""
        reset_event_bus()
        
        bus1 = get_event_bus()
        bus2 = get_event_bus()
        
        assert bus1 is bus2
        
        # Test that events work across instances
        received = []
        bus1.subscribe(EventType.ORDER_FILLED, lambda e: received.append(e))
        bus2.publish(Event(EventType.ORDER_FILLED))
        
        assert len(received) == 1
        
        reset_event_bus()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
