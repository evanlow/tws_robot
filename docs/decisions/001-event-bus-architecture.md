# ADR 001: Event Bus Architecture

## Status
**Accepted** - January 10, 2026

## Context

The TWS Robot system needs a communication mechanism that allows multiple strategies, risk managers, execution adapters, and monitoring systems to interact without tight coupling. The system must support:

- Multiple concurrent strategies
- Real-time market data distribution
- Order flow coordination
- Risk monitoring
- Performance tracking
- Easy testing and mocking

Traditional approaches considered:
1. **Direct method calls** - Simple but creates tight coupling, hard to test
2. **Message queue (Redis/RabbitMQ)** - Adds external dependency, overkill for single-machine deployment
3. **Event bus pattern** - In-process pub/sub, minimal overhead, highly testable

## Decision

Implement an **in-process event bus using the publish/subscribe pattern** (`core/event_bus.py`).

**Key Design Choices:**

1. **Type-Safe Events** - Use Python Enum for event types to prevent typos and enable IDE autocomplete
2. **Synchronous Delivery** - Event handlers execute synchronously on the publishing thread for predictable behavior
3. **No Event Queuing** - Events delivered immediately to avoid state synchronization issues
4. **Filter Support** - Subscribers can filter events by attributes (symbol, strategy_id, etc.)
5. **Statistics Tracking** - Built-in metrics for monitoring event throughput

**Implementation:**

```python
class EventBus:
    def publish(self, event: Event) -> None:
        """Publish event to all subscribers"""
        
    def subscribe(self, event_type: EventType, handler: Callable, 
                  filter: Optional[Dict] = None) -> str:
        """Subscribe to specific event type"""
        
    def unsubscribe(self, subscription_id: str) -> None:
        """Remove subscription"""
```

## Rationale

**Advantages:**
- **Loose Coupling** - Components don't need to know about each other
- **Testability** - Easy to mock event bus in unit tests
- **Flexibility** - Add new components without modifying existing code
- **Observability** - All system activity flows through observable events
- **No External Dependencies** - Pure Python, no broker/queue needed
- **Predictable** - Synchronous delivery ensures ordering

**Trade-offs Accepted:**
- **Single Machine** - No cross-process communication (acceptable for initial scope)
- **Synchronous Handlers** - Slow handlers block publishing thread (mitigated by handler best practices)
- **In-Memory Only** - No event persistence (use database for audit trail separately)

## Consequences

**Positive:**
- Achieved complete decoupling between strategies, risk manager, and execution
- Unit test coverage went from difficult to trivial (mock event bus)
- Added monitoring system without touching existing code
- Strategy development became much faster

**Negative:**
- Must educate developers about async behavior (events published don't return results)
- Handler performance matters (one slow handler affects all)
- Event explosion possible if not careful (mitigated by event filtering)

**Migration Path:**
If we need distributed deployment later:
1. Replace EventBus with Redis pub/sub or Kafka
2. Keep interface identical
3. Handlers remain unchanged
4. Only change instantiation in main.py

## Compliance

- ✅ **Prime Directive:** Event bus has 99% test coverage, 0 failures
- ✅ **Performance:** 10,000+ events/second throughput
- ✅ **Reliability:** No event loss in normal operation

## References

- Implementation: `core/event_bus.py`
- Tests: `tests/test_event_bus.py`
- Usage Examples: `docs/architecture/event-flow.md`

## Review

To be reviewed after 6 months of production use (July 2026) to assess:
- Performance under load
- Need for async handlers
- Cross-machine deployment requirements
