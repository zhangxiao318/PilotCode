"""Session configuration and command result types for the MVC service layer.

SessionConfig is a mutable, reactive configuration object that UI views can
modify to change session behavior (model, thinking mode, tool reinforcement, etc.).
Changes propagate to QueryEngine via SessionService's reverse-channel methods.

CommandResult is the typed return value from SessionService.handle_command(),
allowing the View to handle UI-specific side effects (clear, quit, reload, etc.).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

# ---------------------------------------------------------------------------
# SessionConfig
# ---------------------------------------------------------------------------


@dataclass
class SessionConfig:
    """Reactive session configuration -- UI can modify, SessionService observes.

    Replaces the scattered auto_allow, max_iterations, mode_policy, etc.
    constructor parameters with a single mutable config object.

    UI views call SessionService.set_model() / update_config() to change
    settings (reverse channel). SessionService applies changes to QueryEngine
    and notifies views via StatusUpdate.
    """

    # --- Model settings ---
    model_name: str = ""  # Current model name (empty = use default)
    thinking_mode: bool = False  # Enable reasoning/thinking output
    context_window: int = 0  # 0 = auto-detect from model config

    # --- Execution settings ---
    auto_allow: bool = False  # Auto-allow tool execution
    max_iterations: int = 50  # Max tool-use iterations per query
    mode_policy: str = "manual"  # "auto" | "manual" -- PLAN mode entry policy

    # --- Feature flags ---
    tool_reinforcement: bool = True  # Re-prompt if model ignores tool request
    auto_compact: bool = True  # Auto context compression
    auto_save: bool = True  # Auto-save after each exchange
    loop_guard: bool = True  # Doom-loop detection
    compilation_verify: bool = True  # Post-edit compilation check

    # --- Permission mode ---
    permission_mode: str = "default"  # "default" | "ultra_slim" | etc.

    # --- Project context ---
    cwd: str = ""  # Working directory for the session

    # --- Session initialization ---
    restore_on_start: bool = False  # Restore last session on startup (default: new session)
    session_id: str = ""  # Specific session ID to restore (empty = new session)

    def update(self, **kwargs: Any) -> list[str]:
        """Bulk update config fields. Returns list of changed field names.

        Only accepts fields that exist on SessionConfig. Unknown keys are ignored.
        """
        changed: list[str] = []
        for key, value in kwargs.items():
            if hasattr(self, key) and getattr(self, key) != value:
                setattr(self, key, value)
                changed.append(key)
        return changed


# ---------------------------------------------------------------------------
# CommandResult
# ---------------------------------------------------------------------------


class CommandAction(str, Enum):
    """Action that the View should take after command execution."""

    CONTINUE = "continue"  # Normal flow, display message
    QUIT = "quit"  # User requested exit
    CLEAR = "clear"  # Clear conversation history
    RELOAD = "reload"  # Reload session / QueryEngine
    SWITCH_SESSION = "switch_session"  # Switch to a different session
    EXECUTED = "executed"  # Command executed (no side effect)
    UNKNOWN = "unknown"  # Command not recognized
    ERROR = "error"  # Command execution failed


@dataclass
class CommandResult:
    """Result from SessionService.handle_command().

    The ``action`` field tells the View what side effect to perform.
    The ``message`` field is a display string for the user.
    Additional fields carry data for specific actions.
    """

    action: CommandAction
    message: str = ""
    session_id: str = ""  # For SWITCH_SESSION action
    project_path: str = ""  # For RELOAD action
    data: dict[str, Any] = field(default_factory=dict)  # Extra data for UI-specific handling
