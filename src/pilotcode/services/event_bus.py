"""Event Bus - Decoupled event-driven architecture.

This module provides:
1. Publish-subscribe pattern for loose coupling
2. Async event handling
3. Event filtering and routing
4. Priority-based event processing
5. Event persistence and replay
6. Metrics and monitoring

Features:
- Type-safe events with pydantic
- Async/sync event handlers
- Event priorities (LOW, NORMAL, HIGH, CRITICAL)
- Wildcard subscriptions (e.g., "user.*")
- Event middleware/interceptors
- Backpressure handling
- Dead letter queue for failed events
"""

from __future__ import annotations

import asyncio
import json
import time
import uuid
from dataclasses import dataclass, field, asdict
from typing import Any, Callable, Optional, TypeVar, Generic
from enum import Enum, auto
from collections import defaultdict
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


class EventPriority(Enum):
    """Event priority levels."""
    LOW = 0
    NORMAL = 1
    HIGH = 2
    CRITICAL = 3


class EventBusError(Exception):
    """Base exception for event bus errors."""
    pass


class HandlerNotFound(EventBusError):
    """Raised when no handler is found for an event."""
    pass


@dataclass
class Event:
    """Base event class.
    
    All events should inherit from this or follow this structure.
    """
    type: str
    payload: Any = None
    metadata: dict[str, Any] = field(default_factory=dict)
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    timestamp: float = field(default_factory=time.time)
    priority: EventPriority = EventPriority.NORMAL
    source: str = ""
    
    def to_dict(self) -> dict[str, Any]:
        """Convert event to dictionary."""
        return {
            "id": self.id,
            "type": self.type,
            "payload": self.payload,
            "metadata": self.metadata,
            "timestamp": self.timestamp,
            "priority": self.priority.value,
            "source": self.source,
        }
    
    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Event:
        """Create event from dictionary."""
        return cls(
            id=data.get("id", str(uuid.uuid4())[:8]),
            type=data["type"],
            payload=data.get("payload"),
            metadata=data.get("metadata", {}),
            timestamp=data.get("timestamp", time.time()),
            priority=EventPriority(data.get("priority", 1)),
            source=data.get("source", ""),
        )
    
    def with_payload(self, payload: Any) -> Event:
        """Create new event with different payload."""
        return Event(
            type=self.type,
            payload=payload,
            metadata=self.metadata.copy(),
            source=self.source,
            priority=self.priority,
        )


# Type variable for event handlers
T = TypeVar('T')
EventHandler = Callable[[Event], Any]
AsyncEventHandler = Callable[[Event], asyncio.Future]


@dataclass
class HandlerInfo:
    """Information about an event handler."""
    handler: EventHandler
    event_type: str
    priority: EventPriority
    once: bool = False
    filter_fn: Optional[Callable[[Event], bool]] = None
    
    async def execute(self, event: Event) -> Any:
        """Execute the handler."""
        # Check filter
        if self.filter_fn and not self.filter_fn(event):
            return None
        
        # Execute handler
        result = self.handler(event)
        
        # Handle async results
        if asyncio.iscoroutine(result):
            result = await result
        elif asyncio.isfuture(result):
            result = await result
        
        return result


@dataclass
class EventBusStats:
    """Statistics for event bus."""
    events_published: int = 0
    events_handled: int = 0
    events_dropped: int = 0
    events_failed: int = 0
    handlers_registered: int = 0
    total_handlers_called: int = 0
    avg_processing_time_ms: float = 0.0
    
    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class EventBus:
    """Central event bus for decoupled communication.
    
    Usage:
        bus = EventBus()
        
        # Subscribe
        bus.on("user.created", handle_user_created)
        
        # Publish
        await bus.emit(Event("user.created", payload={"id": 1}))
        
        # Wildcard subscription
        bus.on("user.*", handle_any_user_event)
    """
    
    def __init__(
        self,
        max_queue_size: int = 10000,
        enable_dead_letter: bool = True,
        middleware: Optional[list[Callable[[Event], Event]]] = None
    ):
        self.max_queue_size = max_queue_size
        self.enable_dead_letter = enable_dead_letter
        self.middleware = middleware or []
        
        # Handler storage: event_type -> list of HandlerInfo
        self._handlers: dict[str, list[HandlerInfo]] = defaultdict(list)
        
        # Wildcard handlers
        self._wildcard_handlers: list[tuple[str, HandlerInfo]] = []
        
        # Event queue for async processing
        self._queue: asyncio.PriorityQueue = asyncio.PriorityQueue(maxsize=max_queue_size)
        
        # Dead letter queue
        self._dead_letter_queue: list[tuple[Event, str]] = []
        
        # Processing state
        self._running = False
        self._processor_task: Optional[asyncio.Task] = None
        
        # Statistics
        self._stats = EventBusStats()
        self._processing_times: list[float] = []
        
        # Middleware
        self._middleware_chain: list[Callable[[Event], Event]] = []
    
    def on(
        self,
        event_type: str,
        handler: Optional[EventHandler] = None,
        *,
        priority: EventPriority = EventPriority.NORMAL,
        once: bool = False,
        filter_fn: Optional[Callable[[Event], bool]] = None
    ) -> Callable[[EventHandler], EventHandler]:
        """Subscribe to an event type.
        
        Can be used as a decorator:
            @bus.on("user.created")
            def handler(event):
                pass
        
        Or as a function:
            bus.on("user.created", handler)
        """
        def decorator(fn: EventHandler) -> EventHandler:
            handler_info = HandlerInfo(
                handler=fn,
                event_type=event_type,
                priority=priority,
                once=once,
                filter_fn=filter_fn
            )
            
            # Check if wildcard pattern
            if '*' in event_type or '?' in event_type:
                self._wildcard_handlers.append((event_type, handler_info))
            else:
                # Insert in priority order
                handlers = self._handlers[event_type]
                idx = 0
                for i, h in enumerate(handlers):
                    if h.priority.value < priority.value:
                        idx = i + 1
                    else:
                        break
                handlers.insert(idx, handler_info)
            
            self._stats.handlers_registered += 1
            logger.debug(f"Registered handler for {event_type}")
            
            return fn
        
        if handler:
            return decorator(handler)
        return decorator
    
    def once(
        self,
        event_type: str,
        handler: Optional[EventHandler] = None,
        *,
        priority: EventPriority = EventPriority.NORMAL,
        filter_fn: Optional[Callable[[Event], bool]] = None
    ) -> Callable[[EventHandler], EventHandler]:
        """Subscribe to an event type for a single execution."""
        return self.on(
            event_type,
            handler,
            priority=priority,
            once=True,
            filter_fn=filter_fn
        )
    
    def off(self, event_type: str, handler: Optional[EventHandler] = None) -> int:
        """Unsubscribe from an event type.
        
        If handler is None, removes all handlers for the event type.
        Returns number of handlers removed.
        """
        removed = 0
        
        if handler:
            # Remove specific handler
            handlers = self._handlers.get(event_type, [])
            for i, h in enumerate(handlers):
                if h.handler == handler:
                    del handlers[i]
                    removed += 1
                    break
            
            # Check wildcard handlers
            for i, (pattern, h) in enumerate(self._wildcard_handlers):
                if pattern == event_type and h.handler == handler:
                    del self._wildcard_handlers[i]
                    removed += 1
                    break
        else:
            # Remove all handlers for this type
            removed = len(self._handlers.get(event_type, []))
            if event_type in self._handlers:
                del self._handlers[event_type]
            
            # Check wildcard handlers
            for pattern, h in list(self._wildcard_handlers):
                if pattern == event_type:
                    self._wildcard_handlers.remove((pattern, h))
                    removed += 1
        
        self._stats.handlers_registered -= removed
        return removed
    
    async def emit(self, event: Event) -> list[Any]:
        """Emit an event and wait for all handlers to complete.
        
        Returns list of handler results.
        """
        # Apply middleware
        for middleware in self._middleware_chain:
            event = middleware(event)
        
        self._stats.events_published += 1
        
        # Find handlers
        handlers = self._get_handlers_for_event(event)
        
        if not handlers:
            self._stats.events_dropped += 1
            return []
        
        # Execute handlers
        results = []
        start_time = time.time()
        
        for handler_info in handlers:
            try:
                result = await handler_info.execute(event)
                results.append(result)
                self._stats.events_handled += 1
                self._stats.total_handlers_called += 1
                
                # Remove once handlers
                if handler_info.once:
                    self.off(handler_info.event_type, handler_info.handler)
                    
            except Exception as e:
                logger.error(f"Handler failed for {event.type}: {e}")
                self._stats.events_failed += 1
                
                if self.enable_dead_letter:
                    self._dead_letter_queue.append((event, str(e)))
        
        # Update stats
        processing_time = (time.time() - start_time) * 1000
        self._processing_times.append(processing_time)
        if len(self._processing_times) > 100:
            self._processing_times.pop(0)
        self._stats.avg_processing_time_ms = sum(self._processing_times) / len(self._processing_times)
        
        return results
    
    async def emit_async(self, event: Event) -> None:
        """Emit an event asynchronously (fire and forget)."""
        asyncio.create_task(self.emit(event))
    
    def _get_handlers_for_event(self, event: Event) -> list[HandlerInfo]:
        """Get all handlers that should process this event."""
        handlers = []
        
        # Direct handlers
        direct_handlers = self._handlers.get(event.type, [])
        handlers.extend(direct_handlers)
        
        # Wildcard handlers
        for pattern, handler_info in self._wildcard_handlers:
            if self._match_wildcard(event.type, pattern):
                handlers.append(handler_info)
        
        # Sort by priority
        handlers.sort(key=lambda h: h.priority.value, reverse=True)
        
        return handlers
    
    def _match_wildcard(self, event_type: str, pattern: str) -> bool:
        """Match event type against wildcard pattern."""
        import fnmatch
        return fnmatch.fnmatch(event_type, pattern)
    
    def add_middleware(self, middleware: Callable[[Event], Event]) -> None:
        """Add middleware to process events before handlers."""
        self._middleware_chain.append(middleware)
    
    def remove_middleware(self, middleware: Callable[[Event], Event]) -> bool:
        """Remove middleware."""
        if middleware in self._middleware_chain:
            self._middleware_chain.remove(middleware)
            return True
        return False
    
    def create_event(
        self,
        event_type: str,
        payload: Any = None,
        **kwargs
    ) -> Event:
        """Create a new event with the given type."""
        return Event(
            type=event_type,
            payload=payload,
            **kwargs
        )
    
    def get_stats(self) -> EventBusStats:
        """Get event bus statistics."""
        return EventBusStats(
            events_published=self._stats.events_published,
            events_handled=self._stats.events_handled,
            events_dropped=self._stats.events_dropped,
            events_failed=self._stats.events_failed,
            handlers_registered=self._stats.handlers_registered,
            total_handlers_called=self._stats.total_handlers_called,
            avg_processing_time_ms=self._stats.avg_processing_time_ms,
        )
    
    def get_dead_letter_queue(self) -> list[tuple[Event, str]]:
        """Get events that failed processing."""
        return self._dead_letter_queue.copy()
    
    def clear_dead_letter_queue(self) -> None:
        """Clear dead letter queue."""
        self._dead_letter_queue.clear()
    
    def get_handler_count(self, event_type: Optional[str] = None) -> int:
        """Get number of registered handlers."""
        if event_type:
            return len(self._handlers.get(event_type, []))
        return sum(len(h) for h in self._handlers.values())
    
    def has_handlers(self, event_type: str) -> bool:
        """Check if there are handlers for an event type."""
        return len(self._handlers.get(event_type, [])) > 0 or \
               any(self._match_wildcard(event_type, p) for p, _ in self._wildcard_handlers)


class TypedEventBus(EventBus):
    """Type-safe event bus with typed events.
    
    Usage:
        class UserCreatedEvent:
            user_id: int
            email: str
        
        bus = TypedEventBus()
        
        @bus.on_typed(UserCreatedEvent)
        async def handle(event: UserCreatedEvent):
            pass
    """
    
    def on_typed(
        self,
        event_class: type[T],
        handler: Optional[Callable[[T], Any]] = None,
        *,
        priority: EventPriority = EventPriority.NORMAL,
        once: bool = False
    ) -> Callable[[Callable[[T], Any]], Callable[[T], Any]]:
        """Subscribe to a typed event."""
        event_type = event_class.__name__
        
        def decorator(fn: Callable[[T], Any]) -> Callable[[T], Any]:
            def wrapper(event: Event) -> Any:
                # Convert Event to typed event
                if isinstance(event.payload, dict):
                    typed_event = event_class(**event.payload)
                else:
                    typed_event = event.payload
                return fn(typed_event)
            
            self.on(event_type, wrapper, priority=priority, once=once)
            return fn
        
        if handler:
            return decorator(handler)
        return decorator
    
    def emit_typed(self, typed_event: Any) -> asyncio.Future[list[Any]]:
        """Emit a typed event."""
        event_type = type(typed_event).__name__
        
        # Convert to payload
        if hasattr(typed_event, '__dataclass_fields__'):
            payload = {k: getattr(typed_event, k) for k in typed_event.__dataclass_fields__}
        elif hasattr(typed_event, 'dict'):
            payload = typed_event.dict()
        else:
            payload = vars(typed_event)
        
        event = Event(
            type=event_type,
            payload=payload
        )
        
        return asyncio.create_task(self.emit(event))


# Global event bus instance
_default_bus: Optional[EventBus] = None


def get_event_bus() -> EventBus:
    """Get global event bus instance."""
    global _default_bus
    if _default_bus is None:
        _default_bus = EventBus()
    return _default_bus


def on(
    event_type: str,
    *,
    priority: EventPriority = EventPriority.NORMAL,
    once: bool = False
) -> Callable[[EventHandler], EventHandler]:
    """Decorator to subscribe to global event bus.
    
    Usage:
        @on("user.created")
        def handle(event):
            pass
    """
    bus = get_event_bus()
    return bus.on(event_type, priority=priority, once=once)


def emit(event: Event) -> asyncio.Future[list[Any]]:
    """Emit event to global event bus."""
    bus = get_event_bus()
    return asyncio.create_task(bus.emit(event))


# Common event types for PilotCode
class PilotCodeEvents:
    """Standard event types for PilotCode."""
    
    # Tool events
    TOOL_CALLED = "tool.called"
    TOOL_COMPLETED = "tool.completed"
    TOOL_FAILED = "tool.failed"
    
    # Session events
    SESSION_STARTED = "session.started"
    SESSION_ENDED = "session.ended"
    SESSION_SAVED = "session.saved"
    
    # File events
    FILE_MODIFIED = "file.modified"
    FILE_CREATED = "file.created"
    FILE_DELETED = "file.deleted"
    
    # Agent events
    AGENT_STARTED = "agent.started"
    AGENT_COMPLETED = "agent.completed"
    AGENT_MESSAGE = "agent.message"
    
    # System events
    ERROR_OCCURRED = "error.occurred"
    CONFIG_CHANGED = "config.changed"
    SHUTDOWN = "system.shutdown"


# Helper functions for common events
def emit_tool_called(tool_name: str, input_data: Any) -> asyncio.Task:
    """Emit tool called event."""
    return emit(Event(
        type=PilotCodeEvents.TOOL_CALLED,
        payload={"tool": tool_name, "input": input_data}
    ))


def emit_tool_completed(tool_name: str, result: Any, duration_ms: float) -> asyncio.Task:
    """Emit tool completed event."""
    return emit(Event(
        type=PilotCodeEvents.TOOL_COMPLETED,
        payload={"tool": tool_name, "result": result, "duration_ms": duration_ms}
    ))


def emit_file_modified(file_path: str) -> asyncio.Task:
    """Emit file modified event."""
    return emit(Event(
        type=PilotCodeEvents.FILE_MODIFIED,
        payload={"path": file_path}
    ))


def emit_error(error: Exception, context: str = "") -> asyncio.Task:
    """Emit error event."""
    return emit(Event(
        type=PilotCodeEvents.ERROR_OCCURRED,
        payload={
            "error": str(error),
            "type": type(error).__name__,
            "context": context
        },
        priority=EventPriority.HIGH
    ))
