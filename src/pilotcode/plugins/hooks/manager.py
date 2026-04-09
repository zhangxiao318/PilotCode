"""Hook manager for registering and managing hooks.

This is the main interface for the hook system.
"""

from __future__ import annotations

import asyncio
import functools
from typing import Optional

from .types import (
    HookType,
    HookContext,
    HookResult,
    HookCallback,
    RegisteredHook,
    AggregatedHookResult,
    HookError,
)


class HookManager:
    """Manages plugin hooks.
    
    Allows registering callbacks for lifecycle events and executing them
    in priority order.
    
    Example:
        manager = HookManager()
        
        @manager.register(HookType.PRE_TOOL_USE, priority=10)
        async def log_tool_use(context: HookContext) -> HookResult:
            print(f"Tool: {context.tool_name}")
            return HookResult()
    """
    
    def __init__(self):
        # Organize hooks by type
        self._hooks: dict[HookType, list[RegisteredHook]] = {
            hook_type: [] for hook_type in HookType
        }
        self._enabled = True
        self._execution_count = 0
    
    def register(
        self,
        hook_type: HookType,
        callback: Optional[HookCallback] = None,
        *,
        name: Optional[str] = None,
        priority: int = 0,
        timeout: Optional[float] = None,
        async_hook: bool = False,
        plugin_source: Optional[str] = None,
    ) -> HookCallback:
        """Register a hook callback.
        
        Can be used as a decorator or direct function call.
        
        Args:
            hook_type: Type of event to hook into
            callback: The async function to call
            name: Optional name for the hook
            priority: Execution priority (higher = earlier)
            timeout: Timeout for hook execution
            async_hook: Whether this is an async hook
            plugin_source: Which plugin registered this hook
            
        Returns:
            The callback (for decorator use)
        """
        def decorator(func: HookCallback) -> HookCallback:
            hook_name = name or func.__name__
            
            registered = RegisteredHook(
                name=hook_name,
                callback=func,
                priority=priority,
                plugin_source=plugin_source,
                timeout=timeout,
                async_hook=async_hook,
            )
            
            self._hooks[hook_type].append(registered)
            # Sort by priority (descending)
            self._hooks[hook_type].sort(key=lambda h: -h.priority)
            
            return func
        
        if callback is not None:
            return decorator(callback)
        return decorator
    
    def unregister(
        self,
        hook_type: HookType,
        callback: HookCallback,
    ) -> bool:
        """Unregister a hook callback.
        
        Args:
            hook_type: Type of hook
            callback: The callback to remove
            
        Returns:
            True if removed, False if not found
        """
        hooks = self._hooks[hook_type]
        original_len = len(hooks)
        self._hooks[hook_type] = [
            h for h in hooks if h.callback != callback
        ]
        return len(self._hooks[hook_type]) < original_len
    
    def unregister_by_name(
        self,
        hook_type: Optional[HookType] = None,
        name: Optional[str] = None,
        plugin_source: Optional[str] = None,
    ) -> int:
        """Unregister hooks by name or plugin source.
        
        Args:
            hook_type: Specific type to search, or all if None
            name: Hook name to match
            plugin_source: Plugin source to match
            
        Returns:
            Number of hooks removed
        """
        types_to_search = [hook_type] if hook_type else list(HookType)
        removed = 0
        
        for ht in types_to_search:
            if ht is None:
                continue
            original_len = len(self._hooks[ht])
            self._hooks[ht] = [
                h for h in self._hooks[ht]
                if not (
                    (name and h.name == name) or
                    (plugin_source and h.plugin_source == plugin_source)
                )
            ]
            removed += original_len - len(self._hooks[ht])
        
        return removed
    
    def clear(self, hook_type: Optional[HookType] = None) -> None:
        """Clear all hooks of a type, or all hooks if type is None."""
        if hook_type:
            self._hooks[hook_type] = []
        else:
            for ht in HookType:
                self._hooks[ht] = []
    
    def list_hooks(
        self,
        hook_type: Optional[HookType] = None,
    ) -> list[RegisteredHook]:
        """List registered hooks.
        
        Args:
            hook_type: Filter by type, or all if None
            
        Returns:
            List of registered hooks
        """
        if hook_type:
            return list(self._hooks[hook_type])
        
        all_hooks = []
        for hooks in self._hooks.values():
            all_hooks.extend(hooks)
        return all_hooks
    
    def get_hooks_for_type(self, hook_type: HookType) -> list[RegisteredHook]:
        """Get hooks for a specific type."""
        return list(self._hooks[hook_type])
    
    def enable(self) -> None:
        """Enable hook execution."""
        self._enabled = True
    
    def disable(self) -> None:
        """Disable hook execution."""
        self._enabled = False
    
    def is_enabled(self) -> bool:
        """Check if hooks are enabled."""
        return self._enabled
    
    async def execute_hooks(
        self,
        hook_type: HookType,
        context: HookContext,
    ) -> AggregatedHookResult:
        """Execute all hooks of a given type.
        
        Args:
            hook_type: Type of hooks to execute
            context: Execution context
            
        Returns:
            Aggregated result from all hooks
        """
        result = AggregatedHookResult()
        
        if not self._enabled:
            return result
        
        hooks = self._hooks[hook_type]
        if not hooks:
            return result
        
        self._execution_count += 1
        
        for hook in hooks:
            try:
                hook_result = await self._execute_single_hook(hook, context)
                
                # Aggregate results
                self._aggregate_result(result, hook_result, context)
                
                # Stop if execution blocked
                if not result.allow_execution:
                    result.stop_reason = hook_result.stop_reason or f"Blocked by hook: {hook.name}"
                    break
                    
            except Exception as e:
                # Log error but continue with other hooks
                error_msg = f"Hook {hook.name} failed: {e}"
                result.blocking_errors.append(error_msg)
                # Don't block execution for hook errors unless explicitly configured
        
        return result
    
    async def _execute_single_hook(
        self,
        hook: RegisteredHook,
        context: HookContext,
    ) -> HookResult:
        """Execute a single hook with timeout."""
        if hook.timeout:
            try:
                return await asyncio.wait_for(
                    hook.callback(context),
                    timeout=hook.timeout,
                )
            except asyncio.TimeoutError:
                return HookResult(
                    allow_execution=True,
                    error=f"Hook {hook.name} timed out after {hook.timeout}s",
                )
        else:
            return await hook.callback(context)
    
    def _aggregate_result(
        self,
        aggregated: AggregatedHookResult,
        result: HookResult,
        context: HookContext,
    ) -> None:
        """Aggregate a single hook result into the combined result."""
        # Execution control (AND logic - any block blocks all)
        if not result.allow_execution:
            aggregated.allow_execution = False
        
        if not result.continue_after:
            aggregated.continue_after = False
        
        # Messages
        if result.message:
            aggregated.messages.append(result.message)
        if result.system_message:
            aggregated.system_messages.append(result.system_message)
        
        # Modified values (last non-None wins)
        if result.modified_input is not None:
            aggregated.modified_input = result.modified_input
            context.tool_input = result.modified_input
        
        if result.modified_output is not None:
            aggregated.modified_output = result.modified_output
        
        # Permission decision (last non-passthrough wins)
        if result.permission_decision:
            if result.permission_decision.behavior != "passthrough":
                aggregated.permission_decision = result.permission_decision
        
        # Additional context
        if result.additional_context:
            aggregated.additional_contexts.append(result.additional_context)
        
        # Retry (OR logic - any retry means retry)
        if result.retry:
            aggregated.retry = True
    
    # Convenience methods for specific hook types
    
    async def on_pre_tool_use(
        self,
        tool_name: str,
        tool_input: dict,
        **kwargs,
    ) -> AggregatedHookResult:
        """Execute PreToolUse hooks."""
        context = HookContext(
            hook_type=HookType.PRE_TOOL_USE,
            tool_name=tool_name,
            tool_input=tool_input,
            **kwargs,
        )
        return await self.execute_hooks(HookType.PRE_TOOL_USE, context)
    
    async def on_post_tool_use(
        self,
        tool_name: str,
        tool_input: dict,
        tool_output: Any,
        **kwargs,
    ) -> AggregatedHookResult:
        """Execute PostToolUse hooks."""
        context = HookContext(
            hook_type=HookType.POST_TOOL_USE,
            tool_name=tool_name,
            tool_input=tool_input,
            tool_output=tool_output,
            **kwargs,
        )
        return await self.execute_hooks(HookType.POST_TOOL_USE, context)
    
    async def on_session_start(self, **kwargs) -> AggregatedHookResult:
        """Execute SessionStart hooks."""
        context = HookContext(
            hook_type=HookType.SESSION_START,
            **kwargs,
        )
        return await self.execute_hooks(HookType.SESSION_START, context)
    
    async def on_user_prompt_submit(
        self,
        user_prompt: str,
        **kwargs,
    ) -> AggregatedHookResult:
        """Execute UserPromptSubmit hooks."""
        context = HookContext(
            hook_type=HookType.USER_PROMPT_SUBMIT,
            user_prompt=user_prompt,
            **kwargs,
        )
        return await self.execute_hooks(HookType.USER_PROMPT_SUBMIT, context)
    
    async def on_permission_request(
        self,
        permission_type: str,
        **kwargs,
    ) -> AggregatedHookResult:
        """Execute PermissionRequest hooks."""
        context = HookContext(
            hook_type=HookType.PERMISSION_REQUEST,
            permission_type=permission_type,
            **kwargs,
        )
        return await self.execute_hooks(HookType.PERMISSION_REQUEST, context)


# Global hook manager instance
_hook_manager: Optional[HookManager] = None


def get_hook_manager() -> HookManager:
    """Get global hook manager instance."""
    global _hook_manager
    if _hook_manager is None:
        _hook_manager = HookManager()
    return _hook_manager
