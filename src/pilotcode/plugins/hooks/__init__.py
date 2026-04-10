"""Hook system for plugin lifecycle events.

Provides a comprehensive hook system compatible with ClaudeCode's hook protocol.

Example usage:
    from pilotcode.plugins.hooks import HookManager, HookType

    manager = HookManager()

    @manager.register(HookType.PRE_TOOL_USE)
    async def my_hook(context: HookContext) -> HookResult:
        # Modify tool input or block execution
        return HookResult(allow_execution=True)
"""

from .manager import HookManager, get_hook_manager
from .types import (
    HookType,
    HookContext,
    HookResult,
    HookCallback,
    PermissionDecision,
    AggregatedHookResult,
)
from .executor import HookExecutor
from .builtin import register_builtin_hooks

__all__ = [
    "HookManager",
    "get_hook_manager",
    "HookExecutor",
    "HookType",
    "HookContext",
    "HookResult",
    "HookCallback",
    "PermissionDecision",
    "AggregatedHookResult",
    "register_builtin_hooks",
]
