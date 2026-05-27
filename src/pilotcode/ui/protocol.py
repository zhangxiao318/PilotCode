"""Three-channel UIProtocol interface for MVC service layer.

Defines the contract between SessionService (Controller) and any View
(SimpleCLI, TUI v2, Web). The protocol uses three semantic channels:

    Channel 1 - Block Events:   Conversational + system layer lifecycle events.
    Channel 2 - Status Updates: Persistent UI region updates (status bar, context usage).
    Channel 3 - Interactive:    Blocking/async user requests with return values.

Channel mapping to the four-layer display model (ui/layers.py):
    CONVERSATIONAL -> Channel 1 (on_block_event) with kind=ASSISTANT/THINKING/TOOL_CALL/TOOL_RESULT
    SYSTEM         -> Channel 1 (on_block_event) with kind=SYSTEM
    STATUS         -> Channel 2 (on_status_update)
    INTERACTIVE    -> Channel 3 (request_permission / request_user_input)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Protocol

# ---------------------------------------------------------------------------
# Channel 1: Block lifecycle events
# ---------------------------------------------------------------------------


class BlockKind(str, Enum):
    """Semantic type of a block event.

    Each kind maps to existing UI message types:
    - SimpleCLI:  print() with emoji prefixes
    - TUI v2:     UIMessageType enum values
    - Web:        JSON ``type`` field values
    """

    ASSISTANT = "assistant"  # LLM streaming response
    THINKING = "thinking"  # Thinking/reasoning block (DeepSeek, Qwen3)
    TOOL_CALL = "tool_call"  # Tool invocation start
    TOOL_RESULT = "tool_result"  # Tool execution result
    SYSTEM = "system"  # System notification / warning / error
    PLAN_PROGRESS = "plan_progress"  # P-EVR orchestration progress


class BlockPhase(str, Enum):
    """Lifecycle phase of a block.

    open  -> block is starting (e.g. streaming_start)
    delta -> incremental content update (e.g. streaming_chunk)
    close -> block is complete (e.g. streaming_complete)
    """

    OPEN = "open"
    DELTA = "delta"
    CLOSE = "close"


@dataclass
class BlockEvent:
    """Block-lifecycle event for the conversational + system layers.

    ``block_id`` groups related events: open/delta/close share the same id.
    ``kind`` determines the semantic type.
    ``phase`` determines the lifecycle stage.

    Mapping per UI:
    - SimpleCLI: open=print(header), delta=print(text), close=print(footer)
    - TUI v2:    open=create UIMessage, delta=update UIMessage, close=finalize
    - Web:       open={"type":"streaming_start"}, delta={"type":"streaming_chunk"},
                 close={"type":"streaming_complete"}
    """

    block_id: str
    kind: BlockKind
    phase: BlockPhase
    content: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Channel 2: Status region updates
# ---------------------------------------------------------------------------


@dataclass
class StatusUpdate:
    """Update for persistent UI regions (status bar, context usage).

    SimpleCLI ignores these (no status bar).
    TUI v2 maps to reactive StatusBar properties.
    Web maps to ``{"type": "context_usage", ...}`` JSON.
    """

    token_count: int = 0
    context_window: int = 0
    max_output_tokens: int = 0
    is_processing: bool = False
    session_id: str = ""
    status_text: str = ""  # e.g. "Processing...", "Ready"
    model_name: str = ""  # Current model name (for status bar display)
    thinking_mode: bool = False  # Whether thinking mode is active


# ---------------------------------------------------------------------------
# Channel 3: Interactive request result types
# ---------------------------------------------------------------------------


@dataclass
class PermissionResult:
    """Result from a permission request (Channel 3)."""

    allowed: bool
    for_session: bool = False  # "Allow for this session" choice


# ---------------------------------------------------------------------------
# UIProtocol interface
# ---------------------------------------------------------------------------


class UIProtocol(Protocol):
    """Three-channel interface between SessionService and any View.

    Channel 1 - Block Events:   conversational + system layer events
    Channel 2 - Status Updates: persistent UI region updates
    Channel 3 - Interactive:     blocking/async user requests with return values
    """

    # --- Channel 1: Block lifecycle ---

    async def on_block_event(self, event: BlockEvent) -> None:
        """Receive a block-lifecycle event.

        Mapping per UI:
        - SimpleCLI: open=print(header), delta=print(text), close=print(footer)
        - TUI v2:    open=create UIMessage, delta=update UIMessage, close=finalize
        - Web:       open={"type":"streaming_start"}, delta={"type":"streaming_chunk"},
                     close={"type":"streaming_complete"}
        """
        ...

    # --- Channel 2: Status region ---

    async def on_status_update(self, update: StatusUpdate) -> None:
        """Update persistent UI regions.

        SimpleCLI: no-op (no status bar)
        TUI v2:    StatusBar.set_token_count(), set_processing(), etc.
        Web:       {"type": "context_usage", ...}
        """
        ...

    # --- Channel 3: Interactive requests ---

    async def request_permission(
        self, tool_name: str, params: dict, risk_level: str
    ) -> PermissionResult:
        """Ask user for tool permission.

        SimpleCLI: blocking input() [Y/n]
        TUI v2:    InlinePermissionRequest widget
        Web:       WebSocket permission_request -> permission_result round-trip
        """
        ...

    async def request_user_input(self, question: str, options: list[str] | None = None) -> str:
        """Ask user a question with optional choices.

        SimpleCLI: blocking input()
        TUI v2:    InlineAskUserRequest widget
        Web:       WebSocket question -> answer round-trip
        """
        ...

    # --- Error channel ---

    async def on_error(self, error: str) -> None:
        """Notify view of an unhandled error during processing.

        Maps to:
        - SimpleCLI: print("❌ Error: ...")
        - TUI v2:    UIMessage(ERROR)
        - Web:       {"type":"streaming_error"}
        """
        ...
