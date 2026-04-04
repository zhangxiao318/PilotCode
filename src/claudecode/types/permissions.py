"""Permission system type definitions."""

from typing import Literal, Any
from pydantic import BaseModel, Field


PermissionMode = Literal[
    "default",          # Default: follow rules
    "dontAsk",          # Don't ask: auto-deny dangerous ops
    "acceptEdits",      # Accept edits: auto-allow file edits
    "bypassPermissions", # Bypass permissions
    "plan",             # Plan mode
    "auto",             # Auto mode (requires classifier)
]

PermissionBehavior = Literal["allow", "ask", "deny"]
PermissionRuleSource = Literal["user", "project", "system"]


class PermissionRuleValue(BaseModel):
    """Value for a permission rule."""
    tool_name: str
    rule_content: str | None = None  # Optional content pattern like "Bash(git *)"


class PermissionRule(BaseModel):
    """Permission rule definition."""
    source: PermissionRuleSource
    rule_behavior: PermissionBehavior
    rule_value: PermissionRuleValue


class PermissionResult(BaseModel):
    """Result of a permission check."""
    behavior: PermissionBehavior
    updated_input: dict[str, Any] | None = None
    message: str | None = None


class AdditionalWorkingDirectory(BaseModel):
    """Additional working directory for permissions."""
    path: str
    recursive: bool = True


class ToolPermissionContext(BaseModel):
    """Context for tool permission checks."""
    mode: PermissionMode = "default"
    additional_working_directories: dict[str, AdditionalWorkingDirectory] = Field(default_factory=dict)
    always_allow_rules: dict[str, list[PermissionRule]] = Field(default_factory=dict)
    always_deny_rules: dict[str, list[PermissionRule]] = Field(default_factory=dict)
    always_ask_rules: dict[str, list[PermissionRule]] = Field(default_factory=dict)
    is_bypass_permissions_mode_available: bool = False
    is_auto_mode_available: bool = False
    stripped_dangerous_rules: dict[str, list[PermissionRule]] | None = None
    should_avoid_permission_prompts: bool = False
    await_automated_checks_before_dialog: bool = False
    pre_plan_mode: PermissionMode | None = None

    class Config:
        frozen = True


class PermissionDecision(BaseModel):
    """Decision from permission check."""
    decision: PermissionBehavior
    reason: str | None = None
    updated_input: dict[str, Any] | None = None


def get_empty_tool_permission_context() -> ToolPermissionContext:
    """Get empty tool permission context."""
    return ToolPermissionContext()
