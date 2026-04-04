"""Agent hooks for pre/post execution."""

from enum import Enum
from typing import Any, Callable
from dataclasses import dataclass
from datetime import datetime


class HookType(Enum):
    """Types of agent hooks."""
    PRE_AGENT_RUN = "pre_agent_run"
    POST_AGENT_RUN = "post_agent_run"
    PRE_TOOL_USE = "pre_tool_use"
    POST_TOOL_USE = "post_tool_use"
    ON_AGENT_ERROR = "on_agent_error"
    ON_AGENT_STATUS_CHANGE = "on_agent_status_change"


@dataclass
class HookContext:
    """Context passed to hooks."""
    agent_id: str | None
    tool_name: str | None
    tool_input: dict | None
    tool_output: Any | None
    error: Exception | None
    metadata: dict
    timestamp: str


class AgentHooks:
    """Collection of hooks for agent lifecycle."""
    
    def __init__(self):
        self._hooks: dict[HookType, list[Callable]] = {
            hook_type: [] for hook_type in HookType
        }
    
    def register(
        self,
        hook_type: HookType,
        callback: Callable[[HookContext], Any],
        priority: int = 0,
    ):
        """Register a hook callback."""
        self._hooks[hook_type].append((priority, callback))
        # Sort by priority (higher priority first)
        self._hooks[hook_type].sort(key=lambda x: -x[0])
    
    def unregister(
        self,
        hook_type: HookType,
        callback: Callable[[HookContext], Any],
    ):
        """Unregister a hook callback."""
        self._hooks[hook_type] = [
            (p, cb) for p, cb in self._hooks[hook_type]
            if cb != callback
        ]
    
    async def execute(
        self,
        hook_type: HookType,
        context: HookContext,
    ) -> HookContext:
        """Execute all hooks of a type."""
        for priority, callback in self._hooks[hook_type]:
            try:
                result = callback(context)
                # Handle async callbacks
                if hasattr(result, '__await__'):
                    result = await result
                
                # If hook returns a context, use it
                if result is not None and isinstance(result, HookContext):
                    context = result
                    
            except Exception as e:
                # Log but don't stop other hooks
                print(f"Hook error ({hook_type.value}): {e}")
        
        return context
    
    def execute_sync(
        self,
        hook_type: HookType,
        context: HookContext,
    ) -> HookContext:
        """Execute hooks synchronously."""
        for priority, callback in self._hooks[hook_type]:
            try:
                result = callback(context)
                if result is not None and isinstance(result, HookContext):
                    context = result
            except Exception as e:
                print(f"Hook error ({hook_type.value}): {e}")
        
        return context


class HookManager:
    """Global hook manager."""
    
    def __init__(self):
        self.agent_hooks = AgentHooks()
        self._enabled = True
    
    def enable(self):
        """Enable hooks."""
        self._enabled = True
    
    def disable(self):
        """Disable hooks."""
        self._enabled = False
    
    def is_enabled(self) -> bool:
        """Check if hooks are enabled."""
        return self._enabled
    
    def register_pre_agent_run(
        self,
        callback: Callable[[HookContext], Any],
        priority: int = 0,
    ):
        """Register pre-agent-run hook."""
        self.agent_hooks.register(HookType.PRE_AGENT_RUN, callback, priority)
    
    def register_post_agent_run(
        self,
        callback: Callable[[HookContext], Any],
        priority: int = 0,
    ):
        """Register post-agent-run hook."""
        self.agent_hooks.register(HookType.POST_AGENT_RUN, callback, priority)
    
    def register_pre_tool_use(
        self,
        callback: Callable[[HookContext], Any],
        priority: int = 0,
    ):
        """Register pre-tool-use hook."""
        self.agent_hooks.register(HookType.PRE_TOOL_USE, callback, priority)
    
    def register_post_tool_use(
        self,
        callback: Callable[[HookContext], Any],
        priority: int = 0,
    ):
        """Register post-tool-use hook."""
        self.agent_hooks.register(HookType.POST_TOOL_USE, callback, priority)
    
    def register_on_error(
        self,
        callback: Callable[[HookContext], Any],
        priority: int = 0,
    ):
        """Register error hook."""
        self.agent_hooks.register(HookType.ON_AGENT_ERROR, callback, priority)
    
    def register_on_status_change(
        self,
        callback: Callable[[HookContext], Any],
        priority: int = 0,
    ):
        """Register status change hook."""
        self.agent_hooks.register(HookType.ON_AGENT_STATUS_CHANGE, callback, priority)
    
    async def on_pre_agent_run(self, agent_id: str, metadata: dict | None = None) -> HookContext:
        """Call pre-agent-run hooks."""
        if not self._enabled:
            return HookContext(
                agent_id=agent_id,
                tool_name=None,
                tool_input=None,
                tool_output=None,
                error=None,
                metadata=metadata or {},
                timestamp=datetime.now().isoformat(),
            )
        
        context = HookContext(
            agent_id=agent_id,
            tool_name=None,
            tool_input=None,
            tool_output=None,
            error=None,
            metadata=metadata or {},
            timestamp=datetime.now().isoformat(),
        )
        return await self.agent_hooks.execute(HookType.PRE_AGENT_RUN, context)
    
    async def on_post_agent_run(
        self,
        agent_id: str,
        output: Any,
        metadata: dict | None = None,
    ) -> HookContext:
        """Call post-agent-run hooks."""
        context = HookContext(
            agent_id=agent_id,
            tool_name=None,
            tool_input=None,
            tool_output=output,
            error=None,
            metadata=metadata or {},
            timestamp=datetime.now().isoformat(),
        )
        return await self.agent_hooks.execute(HookType.POST_AGENT_RUN, context)
    
    async def on_pre_tool_use(
        self,
        agent_id: str | None,
        tool_name: str,
        tool_input: dict,
        metadata: dict | None = None,
    ) -> tuple[bool, dict]:
        """Call pre-tool-use hooks.
        
        Returns:
            Tuple of (should_execute, modified_input)
        """
        context = HookContext(
            agent_id=agent_id,
            tool_name=tool_name,
            tool_input=tool_input,
            tool_output=None,
            error=None,
            metadata=metadata or {},
            timestamp=datetime.now().isoformat(),
        )
        
        if not self._enabled:
            return True, tool_input
        
        result = await self.agent_hooks.execute(HookType.PRE_TOOL_USE, context)
        
        # Check if tool should be denied
        if result.metadata.get("deny_tool", False):
            return False, result.tool_input or tool_input
        
        return True, result.tool_input or tool_input
    
    async def on_post_tool_use(
        self,
        agent_id: str | None,
        tool_name: str,
        tool_input: dict,
        tool_output: Any,
        metadata: dict | None = None,
    ) -> Any:
        """Call post-tool-use hooks."""
        context = HookContext(
            agent_id=agent_id,
            tool_name=tool_name,
            tool_input=tool_input,
            tool_output=tool_output,
            error=None,
            metadata=metadata or {},
            timestamp=datetime.now().isoformat(),
        )
        
        if not self._enabled:
            return tool_output
        
        result = await self.agent_hooks.execute(HookType.POST_TOOL_USE, context)
        return result.tool_output if result.tool_output is not None else tool_output
    
    async def on_agent_error(
        self,
        agent_id: str,
        error: Exception,
        metadata: dict | None = None,
    ) -> HookContext:
        """Call error hooks."""
        context = HookContext(
            agent_id=agent_id,
            tool_name=None,
            tool_input=None,
            tool_output=None,
            error=error,
            metadata=metadata or {},
            timestamp=datetime.now().isoformat(),
        )
        return await self.agent_hooks.execute(HookType.ON_AGENT_ERROR, context)
    
    def create_context(
        self,
        agent_id: str | None = None,
        tool_name: str | None = None,
        tool_input: dict | None = None,
        tool_output: Any | None = None,
        error: Exception | None = None,
        metadata: dict | None = None,
    ) -> HookContext:
        """Create a hook context."""
        return HookContext(
            agent_id=agent_id,
            tool_name=tool_name,
            tool_input=tool_input,
            tool_output=tool_output,
            error=error,
            metadata=metadata or {},
            timestamp=datetime.now().isoformat(),
        )


# Global hook manager
_hook_manager: HookManager | None = None


def get_hook_manager() -> HookManager:
    """Get global hook manager."""
    global _hook_manager
    if _hook_manager is None:
        _hook_manager = HookManager()
    return _hook_manager


# Convenience decorators
def pre_agent_run(priority: int = 0):
    """Decorator for pre-agent-run hooks."""
    def decorator(func: Callable):
        get_hook_manager().register_pre_agent_run(func, priority)
        return func
    return decorator


def post_agent_run(priority: int = 0):
    """Decorator for post-agent-run hooks."""
    def decorator(func: Callable):
        get_hook_manager().register_post_agent_run(func, priority)
        return func
    return decorator


def pre_tool_use(priority: int = 0):
    """Decorator for pre-tool-use hooks."""
    def decorator(func: Callable):
        get_hook_manager().register_pre_tool_use(func, priority)
        return func
    return decorator


def post_tool_use(priority: int = 0):
    """Decorator for post-tool-use hooks."""
    def decorator(func: Callable):
        get_hook_manager().register_post_tool_use(func, priority)
        return func
    return decorator
