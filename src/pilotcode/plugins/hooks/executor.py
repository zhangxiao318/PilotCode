"""Hook executor for integrating hooks with tool execution.

This module provides the bridge between the hook system and the actual
tool execution flow in PilotCode.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Optional

if TYPE_CHECKING:
    from .manager import HookManager

from .types import HookContext, HookType, AggregatedHookResult


class HookExecutor:
    """Executes hooks at appropriate points in the tool lifecycle.

    This integrates the hook system with PilotCode's tool execution.

    Usage:
        executor = HookExecutor(get_hook_manager())

        # Before tool execution
        result = await executor.before_tool(tool_name, tool_input)
        if not result.allow_execution:
            return  # Tool was blocked

        # Use modified input
        tool_input = result.modified_input or tool_input

        # Execute tool...
        output = await tool.execute(tool_input)

        # After tool execution
        output = await executor.after_tool(tool_name, tool_input, output)
    """

    def __init__(self, hook_manager: Optional[HookManager] = None):
        if hook_manager is None:
            from .manager import get_hook_manager

            hook_manager = get_hook_manager()
        self.hook_manager = hook_manager

    async def before_tool(
        self,
        tool_name: str,
        tool_input: dict[str, Any],
        agent_id: Optional[str] = None,
        session_id: Optional[str] = None,
        **kwargs,
    ) -> AggregatedHookResult:
        """Execute PreToolUse hooks.

        Args:
            tool_name: Name of the tool being called
            tool_input: Tool arguments
            agent_id: Optional agent ID
            session_id: Optional session ID
            **kwargs: Additional context

        Returns:
            Aggregated hook results
        """
        context = HookContext(
            hook_type=HookType.PRE_TOOL_USE,
            tool_name=tool_name,
            tool_input=tool_input,
            agent_id=agent_id,
            session_id=session_id,
            metadata=kwargs,
        )

        return await self.hook_manager.execute_hooks(HookType.PRE_TOOL_USE, context)

    async def after_tool(
        self,
        tool_name: str,
        tool_input: dict[str, Any],
        tool_output: Any,
        agent_id: Optional[str] = None,
        session_id: Optional[str] = None,
        **kwargs,
    ) -> Any:
        """Execute PostToolUse hooks and return (possibly modified) output.

        Args:
            tool_name: Name of the tool that was called
            tool_input: Tool arguments
            tool_output: Tool output
            agent_id: Optional agent ID
            session_id: Optional session ID
            **kwargs: Additional context

        Returns:
            Possibly modified tool output
        """
        context = HookContext(
            hook_type=HookType.POST_TOOL_USE,
            tool_name=tool_name,
            tool_input=tool_input,
            tool_output=tool_output,
            agent_id=agent_id,
            session_id=session_id,
            metadata=kwargs,
        )

        result = await self.hook_manager.execute_hooks(HookType.POST_TOOL_USE, context)

        # Return modified output if any
        if result.modified_output is not None:
            return result.modified_output
        return tool_output

    async def on_tool_failure(
        self,
        tool_name: str,
        tool_input: dict[str, Any],
        error: Exception,
        agent_id: Optional[str] = None,
        **kwargs,
    ) -> AggregatedHookResult:
        """Execute PostToolUseFailure hooks.

        Args:
            tool_name: Name of the tool that failed
            tool_input: Tool arguments
            error: The exception that occurred
            agent_id: Optional agent ID
            **kwargs: Additional context

        Returns:
            Aggregated hook results
        """
        context = HookContext(
            hook_type=HookType.POST_TOOL_USE_FAILURE,
            tool_name=tool_name,
            tool_input=tool_input,
            tool_error=error,
            agent_id=agent_id,
            metadata=kwargs,
        )

        return await self.hook_manager.execute_hooks(HookType.POST_TOOL_USE_FAILURE, context)

    async def on_session_start(
        self,
        session_id: Optional[str] = None,
        cwd: Optional[str] = None,
        **kwargs,
    ) -> AggregatedHookResult:
        """Execute SessionStart hooks.

        Args:
            session_id: Optional session ID
            cwd: Current working directory
            **kwargs: Additional context

        Returns:
            Aggregated hook results with initial user message if any
        """
        context = HookContext(
            hook_type=HookType.SESSION_START,
            session_id=session_id,
            cwd=cwd,
            metadata=kwargs,
        )

        return await self.hook_manager.execute_hooks(HookType.SESSION_START, context)

    async def on_user_prompt(
        self,
        user_prompt: str,
        session_id: Optional[str] = None,
        **kwargs,
    ) -> tuple[str, AggregatedHookResult]:
        """Execute UserPromptSubmit hooks.

        Args:
            user_prompt: The user's prompt
            session_id: Optional session ID
            **kwargs: Additional context

        Returns:
            Tuple of (possibly modified prompt, hook results)
        """
        context = HookContext(
            hook_type=HookType.USER_PROMPT_SUBMIT,
            user_prompt=user_prompt,
            session_id=session_id,
            metadata=kwargs,
        )

        result = await self.hook_manager.execute_hooks(HookType.USER_PROMPT_SUBMIT, context)

        # Return modified prompt if any
        if result.modified_input and "user_prompt" in result.modified_input:
            return result.modified_input["user_prompt"], result
        return user_prompt, result

    async def on_permission_request(
        self,
        permission_type: str,
        details: dict[str, Any],
        **kwargs,
    ) -> AggregatedHookResult:
        """Execute PermissionRequest hooks.

        Hooks can auto-approve or deny permissions.

        Args:
            permission_type: Type of permission being requested
            details: Permission details
            **kwargs: Additional context

        Returns:
            Aggregated hook results with permission decision
        """
        context = HookContext(
            hook_type=HookType.PERMISSION_REQUEST,
            permission_type=permission_type,
            metadata={"details": details, **kwargs},
        )

        return await self.hook_manager.execute_hooks(HookType.PERMISSION_REQUEST, context)

    async def on_cwd_change(
        self,
        new_cwd: str,
        old_cwd: Optional[str] = None,
        **kwargs,
    ) -> AggregatedHookResult:
        """Execute CwdChanged hooks.

        Args:
            new_cwd: New current working directory
            old_cwd: Previous working directory
            **kwargs: Additional context

        Returns:
            Aggregated hook results
        """
        context = HookContext(
            hook_type=HookType.CWD_CHANGED,
            cwd=new_cwd,
            metadata={"old_cwd": old_cwd, **kwargs},
        )

        return await self.hook_manager.execute_hooks(HookType.CWD_CHANGED, context)

    async def on_file_change(
        self,
        file_path: str,
        change_type: str = "modified",  # created, modified, deleted
        **kwargs,
    ) -> AggregatedHookResult:
        """Execute FileChanged hooks.

        Args:
            file_path: Path to the changed file
            change_type: Type of change
            **kwargs: Additional context

        Returns:
            Aggregated hook results
        """
        context = HookContext(
            hook_type=HookType.FILE_CHANGED,
            file_path=file_path,
            metadata={"change_type": change_type, **kwargs},
        )

        return await self.hook_manager.execute_hooks(HookType.FILE_CHANGED, context)


# Convenience function for decorating tools with hook execution
def with_hooks(tool_func):
    """Decorator to automatically execute hooks around a tool function.

    This is a simplified version - full integration would require
    modifying the tool execution framework.
    """

    async def wrapper(*args, **kwargs):
        executor = HookExecutor()
        tool_name = tool_func.__name__
        tool_input = kwargs

        # Pre-tool hooks
        pre_result = await executor.before_tool(tool_name, tool_input)
        if not pre_result.allow_execution:
            raise PermissionError(f"Tool {tool_name} blocked by hooks: {pre_result.stop_reason}")

        # Use modified input
        if pre_result.modified_input:
            kwargs = pre_result.modified_input

        try:
            # Execute tool
            result = await tool_func(*args, **kwargs)

            # Post-tool hooks
            result = await executor.after_tool(tool_name, kwargs, result)

            return result

        except Exception as e:
            # Failure hooks
            await executor.on_tool_failure(tool_name, kwargs, e)
            raise

    return wrapper
