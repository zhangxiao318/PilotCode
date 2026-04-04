"""Hook system for tool execution lifecycle."""

from .hook_manager import (
    HookManager,
    get_hook_manager,
    HookType,
    HookContext,
    HookResult,
)
from .builtin_hooks import (
    setup_builtin_hooks,
    LoggingHook,
    CostTrackingHook,
    PermissionCheckHook,
)

__all__ = [
    "HookManager",
    "get_hook_manager",
    "HookType",
    "HookContext",
    "HookResult",
    "setup_builtin_hooks",
    "LoggingHook",
    "CostTrackingHook",
    "PermissionCheckHook",
]
