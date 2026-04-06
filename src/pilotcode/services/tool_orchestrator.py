"""Tool orchestration service.

Implements advanced tool execution:
1. Concurrent execution of read-only tools
2. Dependency-aware sequencing
3. Progress tracking
"""

import asyncio
from dataclasses import dataclass, field
from typing import Any, Callable, Awaitable
from enum import Enum

from ..tools.base import Tool, ToolUseContext, ToolResult
from ..tools.registry import get_tool_by_name
from ..services.tool_cache import get_tool_cache


class ExecutionMode(Enum):
    """Tool execution mode."""

    SEQUENTIAL = "sequential"
    PARALLEL = "parallel"
    AUTO = "auto"  # Decide based on tool properties


@dataclass
class ToolExecution:
    """A tool to be executed."""

    tool_name: str
    tool_input: dict[str, Any]
    execution_id: str
    depends_on: list[str] = field(default_factory=list)
    result: ToolResult | None = None
    error: str | None = None
    completed: bool = False


@dataclass
class ExecutionBatch:
    """Batch of tools to execute together."""

    tools: list[ToolExecution]
    mode: ExecutionMode
    is_concurrent_safe: bool


class ToolOrchestrator:
    """Orchestrates tool execution with concurrency support."""

    def __init__(self, max_concurrency: int = 5, use_cache: bool = True):
        self.max_concurrency = max_concurrency
        self.use_cache = use_cache
        self._cache = get_tool_cache() if use_cache else None
        self._execution_history: list[dict[str, Any]] = []

    def analyze_batch(self, tool_calls: list[tuple[str, dict[str, Any]]]) -> list[ExecutionBatch]:
        """Analyze tool calls and group into execution batches.

        Groups consecutive read-only tools for parallel execution.
        """
        if not tool_calls:
            return []

        batches: list[ExecutionBatch] = []
        current_batch: list[ToolExecution] = []
        current_is_safe = True

        for i, (name, input_data) in enumerate(tool_calls):
            tool = get_tool_by_name(name)
            if tool is None:
                continue

            # Parse input to Pydantic model for proper validation
            try:
                parsed_input = tool.input_schema(**input_data)
                is_safe = tool.is_concurrency_safe(parsed_input)
            except Exception:
                # If parsing fails, assume not safe
                is_safe = False

            exec_item = ToolExecution(
                tool_name=name, tool_input=input_data, execution_id=f"exec_{i}"
            )

            if not current_batch:
                # Start new batch
                current_batch = [exec_item]
                current_is_safe = is_safe
            elif current_is_safe and is_safe:
                # Can add to current parallel batch
                current_batch.append(exec_item)
            else:
                # Finish current batch and start new one
                batches.append(
                    ExecutionBatch(
                        tools=current_batch,
                        mode=(
                            ExecutionMode.PARALLEL if current_is_safe else ExecutionMode.SEQUENTIAL
                        ),
                        is_concurrent_safe=current_is_safe,
                    )
                )
                current_batch = [exec_item]
                current_is_safe = is_safe

        # Don't forget last batch
        if current_batch:
            batches.append(
                ExecutionBatch(
                    tools=current_batch,
                    mode=ExecutionMode.PARALLEL if current_is_safe else ExecutionMode.SEQUENTIAL,
                    is_concurrent_safe=current_is_safe,
                )
            )

        return batches

    async def execute_batch(
        self,
        batch: ExecutionBatch,
        context: ToolUseContext,
        permission_callback: Callable[[str, dict], Awaitable[dict]],
        progress_callback: Callable[[str, Any], None] | None = None,
    ) -> list[ToolExecution]:
        """Execute a batch of tools."""
        if batch.mode == ExecutionMode.PARALLEL and batch.is_concurrent_safe:
            return await self._execute_parallel(
                batch.tools, context, permission_callback, progress_callback
            )
        else:
            return await self._execute_sequential(
                batch.tools, context, permission_callback, progress_callback
            )

    async def _execute_parallel(
        self,
        executions: list[ToolExecution],
        context: ToolUseContext,
        permission_callback: Callable[[str, dict], Awaitable[dict]],
        progress_callback: Callable[[str, Any], None] | None = None,
    ) -> list[ToolExecution]:
        """Execute tools in parallel with semaphore limiting."""
        semaphore = asyncio.Semaphore(self.max_concurrency)

        async def execute_with_limit(exec_item: ToolExecution) -> ToolExecution:
            async with semaphore:
                return await self._execute_single(
                    exec_item, context, permission_callback, progress_callback
                )

        # Execute all in parallel
        results = await asyncio.gather(
            *[execute_with_limit(e) for e in executions], return_exceptions=True
        )

        # Handle results
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                executions[i].error = str(result)
                executions[i].completed = False
            else:
                executions[i] = result

        return executions

    async def _execute_sequential(
        self,
        executions: list[ToolExecution],
        context: ToolUseContext,
        permission_callback: Callable[[str, dict], Awaitable[dict]],
        progress_callback: Callable[[str, Any], None] | None = None,
    ) -> list[ToolExecution]:
        """Execute tools one at a time."""
        results = []
        for exec_item in executions:
            result = await self._execute_single(
                exec_item, context, permission_callback, progress_callback
            )
            results.append(result)
        return results

    async def _execute_single(
        self,
        exec_item: ToolExecution,
        context: ToolUseContext,
        permission_callback: Callable[[str, dict], Awaitable[dict]],
        progress_callback: Callable[[str, Any], None] | None = None,
    ) -> ToolExecution:
        """Execute a single tool."""
        tool = get_tool_by_name(exec_item.tool_name)
        if tool is None:
            exec_item.error = f"Tool {exec_item.tool_name} not found"
            return exec_item

        # Check cache first
        if self._cache and tool.is_read_only(exec_item.tool_input):
            cached = self._cache.get(exec_item.tool_name, exec_item.tool_input)
            if cached is not None:
                exec_item.result = cached
                exec_item.completed = True
                return exec_item

        # Notify progress
        if progress_callback:
            progress_callback(
                "started", {"tool": exec_item.tool_name, "id": exec_item.execution_id}
            )

        try:
            # Validate input
            parsed_input = tool.input_schema(**exec_item.tool_input)

            # Execute
            result = await tool.call(
                parsed_input,
                context,
                permission_callback,
                None,  # parent_message
                lambda p: progress_callback("progress", p) if progress_callback else None,
            )

            exec_item.result = result
            exec_item.completed = True

            # Cache result if applicable
            if self._cache and tool.is_read_only(exec_item.tool_input) and not result.is_error:
                self._cache.set(exec_item.tool_name, exec_item.tool_input, result)

        except Exception as e:
            exec_item.error = str(e)
            exec_item.completed = False

        # Notify completion
        if progress_callback:
            progress_callback(
                "completed",
                {
                    "tool": exec_item.tool_name,
                    "id": exec_item.execution_id,
                    "success": exec_item.completed and exec_item.result is not None,
                },
            )

        return exec_item

    async def execute(
        self,
        tool_calls: list[tuple[str, dict[str, Any]]],
        context: ToolUseContext,
        permission_callback: Callable[[str, dict], Awaitable[dict]],
        progress_callback: Callable[[str, Any], None] | None = None,
    ) -> list[ToolExecution]:
        """Execute multiple tool calls with intelligent batching."""
        batches = self.analyze_batch(tool_calls)

        all_results: list[ToolExecution] = []
        for batch in batches:
            results = await self.execute_batch(
                batch, context, permission_callback, progress_callback
            )
            all_results.extend(results)

        return all_results

    def get_stats(self) -> dict[str, Any]:
        """Get execution statistics."""
        stats = {
            "total_executions": len(self._execution_history),
        }
        if self._cache:
            stats["cache"] = self._cache.get_stats()
        return stats


# Global orchestrator
_orchestrator: ToolOrchestrator | None = None


def get_tool_orchestrator() -> ToolOrchestrator:
    """Get global tool orchestrator."""
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = ToolOrchestrator()
    return _orchestrator
