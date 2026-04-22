"""Hook manager for tool execution."""

from enum import Enum, auto
from typing import Any, Callable, Awaitable
from dataclasses import dataclass, field
from datetime import datetime


class HookType(Enum):
    """Types of hooks."""

    PRE_TOOL_USE = auto()
    POST_TOOL_USE = auto()
    PRE_AGENT_RUN = auto()
    POST_AGENT_RUN = auto()
    ON_ERROR = auto()
    ON_PERMISSION_DENIED = auto()


@dataclass
class HookContext:
    """Context passed to hooks."""

    tool_name: str | None = None
    tool_input: dict | None = None
    tool_output: Any | None = None
    agent_id: str | None = None
    error: Exception | None = None
    metadata: dict = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.now)

    def copy(self) -> "HookContext":
        """Create a copy of the context."""
        return HookContext(
            tool_name=self.tool_name,
            tool_input=self.tool_input.copy() if self.tool_input else None,
            tool_output=self.tool_output,
            agent_id=self.agent_id,
            error=self.error,
            metadata=self.metadata.copy(),
            timestamp=datetime.now(),
        )


@dataclass
class HookResult:
    """Result from hook execution."""

    allow_execution: bool = True
    modified_input: dict | None = None
    modified_output: Any | None = None
    message: str | None = None


HookCallback = Callable[[HookContext], Awaitable[HookResult]]


class HookManager:
    """Manages tool execution hooks."""

    def __init__(self):
        self._hooks: dict[HookType, list[tuple[int, HookCallback]]] = {
            hook_type: [] for hook_type in HookType
        }
        self._enabled = True

    def register(
        self,
        hook_type: HookType,
        callback: HookCallback,
        priority: int = 0,
    ):
        """Register a hook callback."""
        self._hooks[hook_type].append((priority, callback))
        # Sort by priority (higher first)
        self._hooks[hook_type].sort(key=lambda x: -x[0])

    def unregister(
        self,
        hook_type: HookType,
        callback: HookCallback,
    ):
        """Unregister a hook callback."""
        self._hooks[hook_type] = [(p, cb) for p, cb in self._hooks[hook_type] if cb != callback]

    def enable(self):
        """Enable hooks."""
        self._enabled = True

    def disable(self):
        """Disable hooks."""
        self._enabled = False

    def is_enabled(self) -> bool:
        """Check if hooks are enabled."""
        return self._enabled

    async def execute_hooks(
        self,
        hook_type: HookType,
        context: HookContext,
    ) -> HookResult:
        """Execute all hooks of a given type."""
        if not self._enabled:
            return HookResult(allow_execution=True)

        result = HookResult(allow_execution=True)

        for priority, callback in self._hooks[hook_type]:
            try:
                hook_result = await callback(context)

                # Merge results
                if not hook_result.allow_execution:
                    result.allow_execution = False

                if hook_result.modified_input is not None:
                    result.modified_input = hook_result.modified_input
                    context.tool_input = hook_result.modified_input

                if hook_result.modified_output is not None:
                    result.modified_output = hook_result.modified_output

                if hook_result.message:
                    result.message = hook_result.message

                # Stop if execution denied
                if not result.allow_execution:
                    break

            except Exception as e:
                # Log error but continue with other hooks
                import logging
                logging.getLogger("pilotcode.hooks").warning(
                    "Hook error (%s): %s", hook_type.name, e, exc_info=True
                )

        return result

    async def on_pre_tool_use(
        self,
        tool_name: str,
        tool_input: dict,
        agent_id: str | None = None,
    ) -> tuple[bool, dict]:
        """Call pre-tool-use hooks.

        Returns:
            Tuple of (should_execute, modified_input)
        """
        context = HookContext(
            tool_name=tool_name,
            tool_input=tool_input,
            agent_id=agent_id,
        )

        result = await self.execute_hooks(HookType.PRE_TOOL_USE, context)

        if result.modified_input:
            return result.allow_execution, result.modified_input
        return result.allow_execution, tool_input

    async def on_post_tool_use(
        self,
        tool_name: str,
        tool_input: dict,
        tool_output: Any,
        agent_id: str | None = None,
    ) -> Any:
        """Call post-tool-use hooks."""
        context = HookContext(
            tool_name=tool_name,
            tool_input=tool_input,
            tool_output=tool_output,
            agent_id=agent_id,
        )

        result = await self.execute_hooks(HookType.POST_TOOL_USE, context)

        if result.modified_output is not None:
            return result.modified_output
        return tool_output

    async def on_pre_agent_run(
        self,
        agent_id: str,
        prompt: str,
    ) -> tuple[bool, str]:
        """Call pre-agent-run hooks."""
        context = HookContext(
            agent_id=agent_id,
            metadata={"prompt": prompt},
        )

        result = await self.execute_hooks(HookType.PRE_AGENT_RUN, context)

        modified_prompt = (
            result.modified_input.get("prompt", prompt) if result.modified_input else prompt
        )
        return result.allow_execution, modified_prompt

    async def on_post_agent_run(
        self,
        agent_id: str,
        output: str,
    ) -> str:
        """Call post-agent-run hooks."""
        context = HookContext(
            agent_id=agent_id,
            tool_output=output,
        )

        result = await self.execute_hooks(HookType.POST_AGENT_RUN, context)

        if result.modified_output is not None:
            return str(result.modified_output)
        return output

    async def on_error(
        self,
        error: Exception,
        tool_name: str | None = None,
        agent_id: str | None = None,
    ):
        """Call error hooks."""
        context = HookContext(
            error=error,
            tool_name=tool_name,
            agent_id=agent_id,
        )

        await self.execute_hooks(HookType.ON_ERROR, context)

    def decorator(
        self,
        hook_type: HookType,
        priority: int = 0,
    ):
        """Decorator for registering hooks."""

        def wrapper(func: HookCallback) -> HookCallback:
            self.register(hook_type, func, priority)
            return func

        return wrapper


# Global hook manager instance
_hook_manager: HookManager | None = None


def get_hook_manager() -> HookManager:
    """Get global hook manager."""
    global _hook_manager
    if _hook_manager is None:
        _hook_manager = HookManager()
    return _hook_manager


# Convenience decorators
def pre_tool_use(priority: int = 0):
    """Decorator for pre-tool-use hooks."""

    def decorator(func):
        get_hook_manager().register(HookType.PRE_TOOL_USE, func, priority)
        return func

    return decorator


def post_tool_use(priority: int = 0):
    """Decorator for post-tool-use hooks."""

    def decorator(func):
        get_hook_manager().register(HookType.POST_TOOL_USE, func, priority)
        return func

    return decorator


def pre_agent_run(priority: int = 0):
    """Decorator for pre-agent-run hooks."""

    def decorator(func):
        get_hook_manager().register(HookType.PRE_AGENT_RUN, func, priority)
        return func

    return decorator


def post_agent_run(priority: int = 0):
    """Decorator for post-agent-run hooks."""

    def decorator(func):
        get_hook_manager().register(HookType.POST_AGENT_RUN, func, priority)
        return func

    return decorator


def on_error(priority: int = 0):
    """Decorator for error hooks."""

    def decorator(func):
        get_hook_manager().register(HookType.ON_ERROR, func, priority)
        return func

    return decorator
