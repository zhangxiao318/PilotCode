"""UI framework - Four-layer display architecture.

All UI modes (REPL, Simple CLI, TUI v2, Web) render content through
four unified layers:

    ┌──────────────────────────────────────┐
    │  1. Status Layer                      │
    │     - Token usage, model info, budget │
    │     - Session duration, git branch    │
    │     - Persistent status bar / panel   │
    ├──────────────────────────────────────┤
    │  2. Conversational Layer              │
    │     - User input, assistant response  │
    │     - Thinking content                │
    │     - Tool calls and results          │
    │     - Time-ordered chat stream        │
    ├──────────────────────────────────────┤
    │  3. System Layer                      │
    │     - Notifications (auto-compact)    │
    │     - Warnings (context limit)        │
    │     - Progress indicators             │
    │     - Errors and exceptions           │
    ├──────────────────────────────────────┤
    │  4. Interactive Layer                 │
    │     - Permission requests             │
    │     - User questions / choices        │
    │     - Modal dialogs / inline prompts  │
    └──────────────────────────────────────┘

The three-channel UIProtocol (protocol.py) maps these layers to channels:
    CONVERSATIONAL -> Channel 1 (on_block_event)
    SYSTEM         -> Channel 1 (on_block_event, kind=SYSTEM)
    STATUS         -> Channel 2 (on_status_update)
    INTERACTIVE    -> Channel 3 (request_permission / request_user_input)
"""

# New three-channel protocol types (preferred)
from .protocol import (
    BlockEvent,
    BlockKind,
    BlockPhase,
    PermissionResult,
    StatusUpdate,
    UIProtocol,
)

# Session config and command result types
from .config import (
    CommandAction,
    CommandResult,
    SessionConfig,
)

# Session service (shared Controller)
from .session_service import SessionService

# Legacy four-layer display types (deprecated - use protocol.py types instead)
from .layers import (
    ConversationalType,
    DisplayEvent,
    DisplayLayer,
    InteractiveType,
    StatusType,
    SystemType,
    make_conversational,
    make_interactive,
    make_status,
    make_system,
)

__all__ = [
    # Three-channel protocol (preferred)
    "BlockEvent",
    "BlockKind",
    "BlockPhase",
    "PermissionResult",
    "StatusUpdate",
    "UIProtocol",
    # Session config and command results
    "CommandAction",
    "CommandResult",
    "SessionConfig",
    # Session service
    "SessionService",
    # Legacy four-layer (deprecated)
    "ConversationalType",
    "DisplayEvent",
    "DisplayLayer",
    "InteractiveType",
    "StatusType",
    "SystemType",
    "make_conversational",
    "make_interactive",
    "make_status",
    "make_system",
]
