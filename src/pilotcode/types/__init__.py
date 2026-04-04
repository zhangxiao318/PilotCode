"""Core type definitions for PilotCode."""

from .base import (
    UUID,
    AgentId,
    ToolName,
    CommandName,
    SessionId,
    Timestamp,
    JSONValue,
    JSONObject,
)
from .message import (
    Message,
    UserMessage,
    AssistantMessage,
    SystemMessage,
    ToolUseMessage,
    ToolResultMessage,
    ProgressMessage,
    AttachmentMessage,
    ContentBlock,
    TextBlock,
    ToolUseBlock,
    ToolResultBlock,
)
from .permissions import (
    PermissionMode,
    PermissionResult,
    PermissionBehavior,
    PermissionRule,
    PermissionRuleSource,
    PermissionRuleValue,
    ToolPermissionContext,
    PermissionDecision,
)
from .command import (
    Command,
    CommandType,
    PromptCommand,
    LocalCommand,
    LocalJSXCommand,
    CommandContext,
)
from .hooks import (
    HookProgress,
    PromptRequest,
    PromptResponse,
)

__all__ = [
    # Base types
    "UUID",
    "AgentId", 
    "ToolName",
    "CommandName",
    "SessionId",
    "Timestamp",
    "JSONValue",
    "JSONObject",
    # Messages
    "Message",
    "UserMessage",
    "AssistantMessage",
    "SystemMessage",
    "ToolUseMessage",
    "ToolResultMessage",
    "ProgressMessage",
    "AttachmentMessage",
    "ContentBlock",
    "TextBlock",
    "ToolUseBlock",
    "ToolResultBlock",
    # Permissions
    "PermissionMode",
    "PermissionResult",
    "PermissionBehavior",
    "PermissionRule",
    "PermissionRuleSource",
    "PermissionRuleValue",
    "ToolPermissionContext",
    "PermissionDecision",
    # Commands
    "Command",
    "CommandType",
    "PromptCommand",
    "LocalCommand",
    "LocalJSXCommand",
    "CommandContext",
    # Hooks
    "HookProgress",
    "PromptRequest",
    "PromptResponse",
]
