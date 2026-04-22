"""Four-layer UI display framework.

Provides shared types and helpers for normalizing how all UI modes
(REPL, Simple CLI, TUI v2, Web) present information to the user.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class DisplayLayer(str, Enum):
    """The four display layers every UI must support."""

    STATUS = "status"  # Persistent state bar (tokens, model, etc.)
    CONVERSATIONAL = "conversational"  # Chat stream (user/assistant/tool)
    SYSTEM = "system"  # Ephemeral notices/warnings/errors
    INTERACTIVE = "interactive"  # Blocking input requests


@dataclass
class DisplayEvent:
    """A single item to be rendered by the UI.

    Attributes:
        layer: Which of the four layers this belongs to.
        type: Specific event type within the layer (e.g., "assistant_chunk").
        payload: Arbitrary data for the renderer (content, metadata, etc.).
        timestamp: When the event was created (for ordering / dedup).
    """

    layer: DisplayLayer
    type: str
    payload: dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)

    # Convenience helpers
    @property
    def content(self) -> str:
        return str(self.payload.get("content", ""))

    @property
    def is_streaming(self) -> bool:
        return bool(self.payload.get("is_streaming", False))

    @property
    def is_complete(self) -> bool:
        return bool(self.payload.get("is_complete", True))


# Common event type constants to avoid string typos across UI modes.

# Conversational layer
class ConversationalType:
    USER_INPUT = "user_input"
    ASSISTANT_CHUNK = "assistant_chunk"
    ASSISTANT_COMPLETE = "assistant_complete"
    THINKING = "thinking"
    TOOL_USE = "tool_use"
    TOOL_RESULT = "tool_result"


# System layer
class SystemType:
    NOTIFICATION = "notification"
    WARNING = "warning"
    ERROR = "error"
    PROGRESS = "progress"
    MAX_ITERATIONS_REACHED = "max_iterations_reached"
    LOOP_DETECTED = "loop_detected"


# Interactive layer
class InteractiveType:
    PERMISSION_REQUEST = "permission_request"
    USER_QUESTION = "user_question"
    CONFIRMATION = "confirmation"


# Status layer (placeholder for future use)
class StatusType:
    TOKEN_UPDATE = "token_update"
    MODEL_CHANGE = "model_change"
    PROCESSING_STATE = "processing_state"
    SESSION_INFO = "session_info"


def make_conversational(
    type: str,
    content: str = "",
    is_streaming: bool = False,
    is_complete: bool = True,
    **kwargs: Any,
) -> DisplayEvent:
    """Factory for conversational layer events."""
    payload = {"content": content, "is_streaming": is_streaming, "is_complete": is_complete, **kwargs}
    return DisplayEvent(layer=DisplayLayer.CONVERSATIONAL, type=type, payload=payload)


def make_system(type: str, content: str = "", **kwargs: Any) -> DisplayEvent:
    """Factory for system layer events."""
    return DisplayEvent(layer=DisplayLayer.SYSTEM, type=type, payload={"content": content, **kwargs})


def make_interactive(type: str, prompt: str = "", **kwargs: Any) -> DisplayEvent:
    """Factory for interactive layer events."""
    return DisplayEvent(layer=DisplayLayer.INTERACTIVE, type=type, payload={"prompt": prompt, **kwargs})


def make_status(type: str, **kwargs: Any) -> DisplayEvent:
    """Factory for status layer events."""
    return DisplayEvent(layer=DisplayLayer.STATUS, type=type, payload=kwargs)
