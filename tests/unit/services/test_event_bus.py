"""Tests for Event Bus service."""

import pytest
import asyncio
from dataclasses import dataclass
from typing import List, Any

from pilotcode.services.event_bus import (
    EventBus,
    Event,
    EventPriority,
    TypedEventBus,
    PilotCodeEvents,
    get_event_bus,
    on,
    emit,
    emit_tool_called,
    emit_tool_completed,
    emit_file_modified,
    emit_error,
)


class TestEventBusBasic:
    """Test basic event bus functionality."""

    @pytest.fixture
    def bus(self):
        """Create a fresh event bus."""
        return EventBus()

    @pytest.mark.asyncio
    async def test_emit_and_handle(self, bus):
        """Test basic emit and handle functionality."""
        results = []

        @bus.on("test.event")
        def handler(event):
            results.append(event.payload)

        event = Event("test.event", payload="test_data")
        await bus.emit(event)

        assert results == ["test_data"]

    @pytest.mark.asyncio
    async def test_multiple_handlers(self, bus):
        """Test multiple handlers for same event."""
        results = []

        @bus.on("test.event")
        def handler1(event):
            results.append("handler1")

        @bus.on("test.event")
        def handler2(event):
            results.append("handler2")

        await bus.emit(Event("test.event"))

        assert "handler1" in results
        assert "handler2" in results

    @pytest.mark.asyncio
    async def test_async_handler(self, bus):
        """Test async event handler."""
        results = []

        @bus.on("test.event")
        async def handler(event):
            await asyncio.sleep(0.01)
            results.append(event.payload)

        await bus.emit(Event("test.event", payload="async_data"))

        assert results == ["async_data"]

    @pytest.mark.asyncio
    async def test_handler_priority(self, bus):
        """Test handler priority ordering."""
        results = []

        @bus.on("test.event", priority=EventPriority.LOW)
        def low_handler(event):
            results.append("low")

        @bus.on("test.event", priority=EventPriority.HIGH)
        def high_handler(event):
            results.append("high")

        @bus.on("test.event", priority=EventPriority.NORMAL)
        def normal_handler(event):
            results.append("normal")

        await bus.emit(Event("test.event"))

        # High priority should be first
        assert results[0] == "high"

    @pytest.mark.asyncio
    async def test_once_handler(self, bus):
        """Test once handler (runs only once)."""
        results = []

        @bus.once("test.event")
        def handler(event):
            results.append("called")

        await bus.emit(Event("test.event"))
        await bus.emit(Event("test.event"))

        assert results.count("called") == 1

    @pytest.mark.asyncio
    async def test_off_handler(self, bus):
        """Test unsubscribing handlers."""
        results = []

        def handler(event):
            results.append("called")

        bus.on("test.event", handler)
        await bus.emit(Event("test.event"))

        bus.off("test.event", handler)
        await bus.emit(Event("test.event"))

        assert results.count("called") == 1

    @pytest.mark.asyncio
    async def test_off_all_handlers(self, bus):
        """Test unsubscribing all handlers for event type."""
        results = []

        @bus.on("test.event")
        def handler1(event):
            results.append("handler1")

        @bus.on("test.event")
        def handler2(event):
            results.append("handler2")

        bus.off("test.event")
        await bus.emit(Event("test.event"))

        assert len(results) == 0

    @pytest.mark.asyncio
    async def test_wildcard_subscription(self, bus):
        """Test wildcard event subscription."""
        results = []

        @bus.on("user.*")
        def handler(event):
            results.append(event.type)

        await bus.emit(Event("user.created", payload="user1"))
        await bus.emit(Event("user.updated", payload="user2"))
        await bus.emit(Event("post.created", payload="post1"))

        assert "user.created" in results
        assert "user.updated" in results
        assert "post.created" not in results


class TestEventBusFilters:
    """Test event filtering."""

    @pytest.fixture
    def bus(self):
        return EventBus()

    @pytest.mark.asyncio
    async def test_filter_function(self, bus):
        """Test event filter function."""
        results = []

        def filter_high_priority(event):
            return event.payload.get("priority", 0) > 5

        @bus.on("test.event", filter_fn=filter_high_priority)
        def handler(event):
            results.append(event.payload)

        await bus.emit(Event("test.event", payload={"priority": 10}))
        await bus.emit(Event("test.event", payload={"priority": 3}))

        assert len(results) == 1
        assert results[0]["priority"] == 10

    @pytest.mark.asyncio
    async def test_complex_filter(self, bus):
        """Test complex filter conditions."""
        results = []

        def filter_user_admin(event):
            payload = event.payload or {}
            return payload.get("role") == "admin"

        @bus.on("user.action", filter_fn=filter_user_admin)
        def handler(event):
            results.append(event.payload)

        await bus.emit(Event("user.action", payload={"role": "admin", "action": "delete"}))
        await bus.emit(Event("user.action", payload={"role": "user", "action": "read"}))
        await bus.emit(Event("user.action", payload={"role": "admin", "action": "update"}))

        assert len(results) == 2
        assert all(r["role"] == "admin" for r in results)


class TestEventBusMiddleware:
    """Test event middleware."""

    @pytest.fixture
    def bus(self):
        return EventBus()

    @pytest.mark.asyncio
    async def test_middleware(self, bus):
        """Test middleware processing."""
        results = []

        def add_timestamp(event):
            event.metadata["processed_at"] = 12345
            return event

        bus.add_middleware(add_timestamp)

        @bus.on("test.event")
        def handler(event):
            results.append(event.metadata.get("processed_at"))

        await bus.emit(Event("test.event"))

        assert results[0] == 12345

    @pytest.mark.asyncio
    async def test_multiple_middleware(self, bus):
        """Test multiple middleware functions."""
        results = []

        def middleware1(event):
            event.metadata["step1"] = True
            return event

        def middleware2(event):
            event.metadata["step2"] = True
            return event

        bus.add_middleware(middleware1)
        bus.add_middleware(middleware2)

        @bus.on("test.event")
        def handler(event):
            results.append(event.metadata)

        await bus.emit(Event("test.event"))

        assert results[0]["step1"] is True
        assert results[0]["step2"] is True

    @pytest.mark.asyncio
    async def test_remove_middleware(self, bus):
        """Test removing middleware."""
        results = []

        def middleware(event):
            event.metadata["modified"] = True
            return event

        bus.add_middleware(middleware)
        bus.remove_middleware(middleware)

        @bus.on("test.event")
        def handler(event):
            results.append(event.metadata.get("modified"))

        await bus.emit(Event("test.event"))

        assert results[0] is None


class TestEventBusStats:
    """Test event bus statistics."""

    @pytest.fixture
    def bus(self):
        return EventBus()

    @pytest.mark.asyncio
    async def test_stats_tracking(self, bus):
        """Test statistics tracking."""

        @bus.on("test.event")
        def handler(event):
            return event.payload

        await bus.emit(Event("test.event", payload="data1"))
        await bus.emit(Event("test.event", payload="data2"))

        stats = bus.get_stats()

        assert stats.events_published == 2
        assert stats.events_handled == 2
        assert stats.total_handlers_called == 2

    @pytest.mark.asyncio
    async def test_dropped_events(self, bus):
        """Test dropped events tracking."""
        # No handlers registered
        await bus.emit(Event("unknown.event"))

        stats = bus.get_stats()

        assert stats.events_dropped == 1

    @pytest.mark.asyncio
    async def test_failed_events(self, bus):
        """Test failed events tracking."""

        @bus.on("test.event")
        def failing_handler(event):
            raise ValueError("Test error")

        await bus.emit(Event("test.event"))

        stats = bus.get_stats()

        assert stats.events_failed == 1

    @pytest.mark.asyncio
    async def test_dead_letter_queue(self, bus):
        """Test dead letter queue."""

        @bus.on("test.event")
        def failing_handler(event):
            raise ValueError("Test error")

        await bus.emit(Event("test.event", payload="test"))

        dlq = bus.get_dead_letter_queue()

        assert len(dlq) == 1
        assert dlq[0][0].payload == "test"
        assert "Test error" in dlq[0][1]

    def test_handler_count(self, bus):
        """Test handler count."""
        assert bus.get_handler_count() == 0

        @bus.on("event1")
        def handler1(event):
            pass

        @bus.on("event2")
        def handler2(event):
            pass

        @bus.on("event1")
        def handler3(event):
            pass

        assert bus.get_handler_count("event1") == 2
        assert bus.get_handler_count("event2") == 1
        assert bus.get_handler_count() == 3

    def test_has_handlers(self, bus):
        """Test checking if event has handlers."""
        assert not bus.has_handlers("test.event")

        @bus.on("test.event")
        def handler(event):
            pass

        assert bus.has_handlers("test.event")


class TestEventSerialization:
    """Test event serialization."""

    def test_event_to_dict(self):
        """Test converting event to dictionary."""
        event = Event(
            type="test.event",
            payload={"key": "value"},
            source="test_source",
            priority=EventPriority.HIGH,
        )

        data = event.to_dict()

        assert data["type"] == "test.event"
        assert data["payload"] == {"key": "value"}
        assert data["source"] == "test_source"
        assert data["priority"] == 2
        assert "id" in data
        assert "timestamp" in data

    def test_event_from_dict(self):
        """Test creating event from dictionary."""
        data = {
            "type": "test.event",
            "payload": {"key": "value"},
            "source": "test_source",
            "priority": 2,
            "id": "test123",
            "timestamp": 12345.0,
            "metadata": {},
        }

        event = Event.from_dict(data)

        assert event.type == "test.event"
        assert event.payload == {"key": "value"}
        assert event.source == "test_source"
        assert event.priority == EventPriority.HIGH
        assert event.id == "test123"
        assert event.timestamp == 12345.0


class TestTypedEventBus:
    """Test typed event bus."""

    @dataclass
    class UserCreatedEvent:
        user_id: int
        email: str

    @dataclass
    class OrderPlacedEvent:
        order_id: str
        amount: float

    @pytest.fixture
    def bus(self):
        return TypedEventBus()

    @pytest.mark.asyncio
    async def test_typed_event_subscription(self, bus):
        """Test typed event subscription."""
        results = []

        @bus.on_typed(self.UserCreatedEvent)
        def handler(event: self.UserCreatedEvent):
            results.append((event.user_id, event.email))

        await bus.emit_typed(self.UserCreatedEvent(user_id=1, email="test@example.com"))

        assert len(results) == 1
        assert results[0] == (1, "test@example.com")

    @pytest.mark.asyncio
    async def test_multiple_typed_events(self, bus):
        """Test multiple typed event types."""
        user_results = []
        order_results = []

        @bus.on_typed(self.UserCreatedEvent)
        def user_handler(event: self.UserCreatedEvent):
            user_results.append(event.user_id)

        @bus.on_typed(self.OrderPlacedEvent)
        def order_handler(event: self.OrderPlacedEvent):
            order_results.append(event.order_id)

        await bus.emit_typed(self.UserCreatedEvent(user_id=1, email="test@test.com"))
        await bus.emit_typed(self.OrderPlacedEvent(order_id="ORD-123", amount=100.0))

        assert user_results == [1]
        assert order_results == ["ORD-123"]


class TestGlobalEventBus:
    """Test global event bus instance."""

    def test_get_event_bus(self):
        """Test getting global event bus."""
        bus1 = get_event_bus()
        bus2 = get_event_bus()

        assert bus1 is bus2

    @pytest.mark.asyncio
    async def test_global_decorator(self):
        """Test global on decorator."""
        results = []

        @on("global.test")
        def handler(event):
            results.append(event.payload)

        await emit(Event("global.test", payload="global_data"))

        assert results == ["global_data"]


class TestEventHelpers:
    """Test event helper functions."""

    @pytest.mark.asyncio
    async def test_emit_tool_called(self):
        """Test emit_tool_called helper."""
        results = []

        bus = get_event_bus()
        bus.off(PilotCodeEvents.TOOL_CALLED)

        @bus.on(PilotCodeEvents.TOOL_CALLED)
        def handler(event):
            results.append(event.payload)

        task = emit_tool_called("read_file", {"path": "/test"})
        await task

        assert len(results) == 1
        assert results[0]["tool"] == "read_file"

    @pytest.mark.asyncio
    async def test_emit_tool_completed(self):
        """Test emit_tool_completed helper."""
        results = []

        bus = get_event_bus()
        bus.off(PilotCodeEvents.TOOL_COMPLETED)

        @bus.on(PilotCodeEvents.TOOL_COMPLETED)
        def handler(event):
            results.append(event.payload)

        task = emit_tool_completed("read_file", {"content": "test"}, 150.0)
        await task

        assert len(results) == 1
        assert results[0]["tool"] == "read_file"
        assert results[0]["duration_ms"] == 150.0

    @pytest.mark.asyncio
    async def test_emit_file_modified(self):
        """Test emit_file_modified helper."""
        results = []

        bus = get_event_bus()
        bus.off(PilotCodeEvents.FILE_MODIFIED)

        @bus.on(PilotCodeEvents.FILE_MODIFIED)
        def handler(event):
            results.append(event.payload)

        task = emit_file_modified("/path/to/file.py")
        await task

        assert len(results) == 1
        assert results[0]["path"] == "/path/to/file.py"

    @pytest.mark.asyncio
    async def test_emit_error(self):
        """Test emit_error helper."""
        results = []

        bus = get_event_bus()
        bus.off(PilotCodeEvents.ERROR_OCCURRED)

        @bus.on(PilotCodeEvents.ERROR_OCCURRED)
        def handler(event):
            results.append(event.payload)

        task = emit_error(ValueError("Test error"), "test_context")
        await task

        assert len(results) == 1
        assert results[0]["error"] == "Test error"
        assert results[0]["type"] == "ValueError"
        assert results[0]["context"] == "test_context"


class TestEventBusErrorHandling:
    """Test event bus error handling."""

    @pytest.fixture
    def bus(self):
        return EventBus()

    @pytest.mark.asyncio
    async def test_handler_exception_not_propagated(self, bus):
        """Test that handler exceptions don't break other handlers."""
        results = []

        @bus.on("test.event")
        def failing_handler(event):
            raise ValueError("Handler error")

        @bus.on("test.event")
        def good_handler(event):
            results.append("good")

        # Should not raise
        await bus.emit(Event("test.event"))

        assert results == ["good"]

    @pytest.mark.asyncio
    async def test_async_handler_exception(self, bus):
        """Test async handler exception handling."""
        results = []

        @bus.on("test.event")
        async def failing_handler(event):
            raise ValueError("Async error")

        @bus.on("test.event")
        async def good_handler(event):
            results.append("good")

        await bus.emit(Event("test.event"))

        assert results == ["good"]

    @pytest.mark.asyncio
    async def test_clear_dead_letter_queue(self, bus):
        """Test clearing dead letter queue."""

        @bus.on("test.event")
        def failing_handler(event):
            raise ValueError("Error")

        await bus.emit(Event("test.event"))
        assert len(bus.get_dead_letter_queue()) == 1

        bus.clear_dead_letter_queue()
        assert len(bus.get_dead_letter_queue()) == 0


class TestPilotCodeEvents:
    """Test PilotCode event constants."""

    def test_event_constants(self):
        """Test all event constants are defined."""
        assert PilotCodeEvents.TOOL_CALLED == "tool.called"
        assert PilotCodeEvents.TOOL_COMPLETED == "tool.completed"
        assert PilotCodeEvents.TOOL_FAILED == "tool.failed"
        assert PilotCodeEvents.SESSION_STARTED == "session.started"
        assert PilotCodeEvents.SESSION_ENDED == "session.ended"
        assert PilotCodeEvents.FILE_MODIFIED == "file.modified"
        assert PilotCodeEvents.FILE_CREATED == "file.created"
        assert PilotCodeEvents.FILE_DELETED == "file.deleted"
        assert PilotCodeEvents.AGENT_STARTED == "agent.started"
        assert PilotCodeEvents.AGENT_COMPLETED == "agent.completed"
        assert PilotCodeEvents.ERROR_OCCURRED == "error.occurred"
        assert PilotCodeEvents.CONFIG_CHANGED == "config.changed"
        assert PilotCodeEvents.SHUTDOWN == "system.shutdown"
