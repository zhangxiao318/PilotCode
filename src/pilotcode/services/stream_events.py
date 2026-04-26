"""Stream event types for fine-grained LLM output observation.

Inspired by OpenCode's SessionProcessor event stream — decouples
stream production (QueryEngine) from consumption (REPL, TUI, Headless, Web).
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any, Literal


@dataclass
class StreamEvent:
    """A single event in the LLM stream lifecycle.

    Events are published by QueryEngine during streaming and consumed
    by UI layers for real-time rendering, logging, or side-effects.
    """

    type: Literal[
        "reasoning_start",
        "reasoning_delta",
        "reasoning_end",
        "text_delta",
        "text_end",
        "tool_call_start",
        "tool_call_complete",
        "tool_result",
        "tool_error",
        "error",
        "finish_step",
    ]
    data: dict[str, Any] = field(default_factory=dict)

    # Convenience constructors ------------------------------------------------

    @classmethod
    def reasoning_start(cls, reasoning_id: str = "") -> StreamEvent:
        return cls("reasoning_start", {"reasoning_id": reasoning_id})

    @classmethod
    def reasoning_delta(cls, text: str, reasoning_id: str = "") -> StreamEvent:
        return cls("reasoning_delta", {"text": text, "reasoning_id": reasoning_id})

    @classmethod
    def reasoning_end(cls, reasoning_id: str = "") -> StreamEvent:
        return cls("reasoning_end", {"reasoning_id": reasoning_id})

    @classmethod
    def text_delta(cls, text: str) -> StreamEvent:
        return cls("text_delta", {"text": text})

    @classmethod
    def text_end(cls) -> StreamEvent:
        return cls("text_end", {})

    @classmethod
    def tool_call_start(
        cls, tool_call_id: str, tool_name: str, tool_input: dict[str, Any]
    ) -> StreamEvent:
        return cls(
            "tool_call_start",
            {"tool_call_id": tool_call_id, "tool_name": tool_name, "tool_input": tool_input},
        )

    @classmethod
    def tool_call_complete(
        cls, tool_call_id: str, tool_name: str, tool_input: dict[str, Any]
    ) -> StreamEvent:
        return cls(
            "tool_call_complete",
            {"tool_call_id": tool_call_id, "tool_name": tool_name, "tool_input": tool_input},
        )

    @classmethod
    def tool_result(cls, tool_call_id: str, output: str) -> StreamEvent:
        return cls("tool_result", {"tool_call_id": tool_call_id, "output": output})

    @classmethod
    def tool_error(cls, tool_call_id: str, error: str) -> StreamEvent:
        return cls("tool_error", {"tool_call_id": tool_call_id, "error": error})

    @classmethod
    def error(cls, exception: Exception) -> StreamEvent:
        return cls("error", {"exception": exception, "message": str(exception)})

    @classmethod
    def finish_step(
        cls, usage: dict[str, int] | None = None, finish_reason: str | None = None
    ) -> StreamEvent:
        return cls(
            "finish_step",
            {"usage": usage or {}, "finish_reason": finish_reason or ""},
        )


class EventBus:
    """Simple asyncio.Queue-based event bus for stream events.

    Producer (QueryEngine) puts events; consumers (REPL, TUI, etc.) get them.
    Supports multiple concurrent consumers via queue reference sharing.
    """

    def __init__(self, maxsize: int = 0):
        self._queue: asyncio.Queue[StreamEvent] = asyncio.Queue(maxsize=maxsize)

    async def emit(self, event: StreamEvent) -> None:
        """Publish an event.  Never blocks (unbounded queue by default)."""
        await self._queue.put(event)

    async def get(self) -> StreamEvent:
        """Consume the next event."""
        return await self._queue.get()

    def get_nowait(self) -> StreamEvent | None:
        """Non-blocking get; returns None if queue is empty."""
        try:
            return self._queue.get_nowait()
        except asyncio.QueueEmpty:
            return None

    @property
    def queue(self) -> asyncio.Queue[StreamEvent]:
        """Expose the underlying queue for external consumers."""
        return self._queue
