"""Hook system types.

Compatible with ClaudeCode's hook protocol.
"""

from __future__ import annotations

from enum import Enum
from dataclasses import dataclass, field
from typing import Any, Callable, Awaitable, Optional
from datetime import datetime


class HookType(Enum):
    """Types of lifecycle hooks.

    Mirrors ClaudeCode's hook event types.
    """

    # Tool execution hooks
    PRE_TOOL_USE = "PreToolUse"
    POST_TOOL_USE = "PostToolUse"
    POST_TOOL_USE_FAILURE = "PostToolUseFailure"

    # Session lifecycle hooks
    SESSION_START = "SessionStart"
    SETUP = "Setup"

    # User interaction hooks
    USER_PROMPT_SUBMIT = "UserPromptSubmit"
    PERMISSION_REQUEST = "PermissionRequest"
    PERMISSION_DENIED = "PermissionDenied"

    # Agent hooks
    SUBAGENT_START = "SubagentStart"

    # File system hooks
    CWD_CHANGED = "CwdChanged"
    FILE_CHANGED = "FileChanged"

    # Notification hooks
    NOTIFICATION = "Notification"
    ELICITATION = "Elicitation"
    ELICITATION_RESULT = "ElicitationResult"


@dataclass
class PermissionDecision:
    """Permission decision from a hook."""

    behavior: str  # 'allow', 'deny', 'ask', 'passthrough'
    updated_input: Optional[dict[str, Any]] = None
    updated_permissions: Optional[list[dict]] = None
    message: Optional[str] = None
    interrupt: bool = False


@dataclass
class HookContext:
    """Context passed to hooks.

    Contains information about the current execution context.
    """

    # Hook type that triggered
    hook_type: HookType

    # Tool information (for tool-related hooks)
    tool_name: Optional[str] = None
    tool_input: Optional[dict[str, Any]] = None
    tool_output: Any = None
    tool_error: Optional[Exception] = None

    # Session information
    session_id: Optional[str] = None
    user_prompt: Optional[str] = None

    # Agent information
    agent_id: Optional[str] = None
    agent_prompt: Optional[str] = None

    # File information
    file_path: Optional[str] = None
    cwd: Optional[str] = None

    # Permission information
    permission_type: Optional[str] = None
    permission_result: Optional[PermissionDecision] = None

    # Additional context
    metadata: dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.now)

    def copy(self) -> "HookContext":
        """Create a copy of the context."""
        return HookContext(
            hook_type=self.hook_type,
            tool_name=self.tool_name,
            tool_input=self.tool_input.copy() if self.tool_input else None,
            tool_output=self.tool_output,
            tool_error=self.tool_error,
            session_id=self.session_id,
            user_prompt=self.user_prompt,
            agent_id=self.agent_id,
            agent_prompt=self.agent_prompt,
            file_path=self.file_path,
            cwd=self.cwd,
            permission_type=self.permission_type,
            permission_result=self.permission_result,
            metadata=self.metadata.copy(),
            timestamp=datetime.now(),
        )


@dataclass
class HookResult:
    """Result from executing a hook.

    Hooks return this to influence system behavior.
    """

    # Execution control
    allow_execution: bool = True
    continue_after: bool = True

    # Modified data
    modified_input: Optional[dict[str, Any]] = None
    modified_output: Any = None

    # Messages
    message: Optional[str] = None
    system_message: Optional[str] = None
    stop_reason: Optional[str] = None

    # Permission decision
    permission_decision: Optional[PermissionDecision] = None

    # Additional context to add
    additional_context: Optional[str] = None

    # Error handling
    retry: bool = False
    error: Optional[str] = None

    # For async hooks
    async_operation: bool = False
    async_timeout: Optional[float] = None


@dataclass
class AggregatedHookResult:
    """Aggregated result from multiple hooks."""

    # Combined execution control
    allow_execution: bool = True
    continue_after: bool = True

    # All messages
    messages: list[str] = field(default_factory=list)
    system_messages: list[str] = field(default_factory=list)

    # Blocking errors
    blocking_errors: list[str] = field(default_factory=list)

    # Final modified values (last non-None wins)
    modified_input: Optional[dict[str, Any]] = None
    modified_output: Any = None

    # Permission (last non-passthrough wins)
    permission_decision: Optional[PermissionDecision] = None

    # Combined context
    additional_contexts: list[str] = field(default_factory=list)

    # Stop reason (first blocking wins)
    stop_reason: Optional[str] = None

    # Error handling
    retry: bool = False


# Type alias for hook callbacks
HookCallback = Callable[[HookContext], Awaitable[HookResult]]


@dataclass
class RegisteredHook:
    """Internal representation of a registered hook."""

    name: str
    callback: HookCallback
    priority: int = 0
    plugin_source: Optional[str] = None
    timeout: Optional[float] = None
    async_hook: bool = False


class HookError(Exception):
    """Error in hook execution."""

    pass


class HookTimeoutError(HookError):
    """Hook execution timed out."""

    pass


class HookValidationError(HookError):
    """Hook configuration is invalid."""

    pass
