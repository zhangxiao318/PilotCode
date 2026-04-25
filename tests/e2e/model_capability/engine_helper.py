"""QueryEngine + ToolExecutor full-loop helper for Layer 2 capability tests.

This module provides `run_with_tools()`, which executes the complete cycle:
    submit_message -> detect ToolUseMessage -> execute tool -> add_tool_result -> repeat

Unlike the raw QueryEngine (which only *requests* tools), this helper actually
*executes* them, making it suitable for end-to-end coding/planning tests.
"""

from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass, field
from typing import Any

from pilotcode.query_engine import QueryEngine
from pilotcode.permissions.tool_executor import ToolExecutor, ToolExecutionResult
from pilotcode.tools.base import ToolUseContext, ToolResult
from pilotcode.permissions.permission_manager import (
    PermissionManager,
    PermissionRequest,
    PermissionLevel,
)

# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class ToolCallInfo:
    """Record of a single tool call within a run."""

    name: str
    params: dict[str, Any]
    execution_success: bool
    execution_result: str = ""
    execution_error: str | None = None
    turn: int = 0


@dataclass
class ToolRunResult:
    """Result of a complete run_with_tools() session."""

    final_response: str = ""
    tool_calls: list[ToolCallInfo] = field(default_factory=list)
    turn_count: int = 0
    error: str | None = None
    diagnostics: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Permission helper
# ---------------------------------------------------------------------------


async def _auto_allow_permission(request: PermissionRequest) -> PermissionLevel:
    """Auto-approve all permission requests (safe for isolated tests)."""
    return PermissionLevel.ALWAYS_ALLOW


# ---------------------------------------------------------------------------
# Tool result serialization
# ---------------------------------------------------------------------------


def _serialize_tool_result(tool_name: str, exec_result: ToolExecutionResult) -> tuple[str, bool]:
    """Convert a ToolExecutionResult into a string for the LLM + error flag."""
    if not exec_result.success:
        # Execution failed (validation error, exception, etc.)
        return f"Tool execution failed: {exec_result.message}", True

    result: ToolResult | None = exec_result.result
    if result is None:
        return "Tool returned no result.", False

    if result.is_error:
        # Tool returned an error in its data (e.g. FileEdit string not found)
        if result.output_for_assistant:
            return result.output_for_assistant, True
        # Fallback: dump the data model
        data = result.data
        if hasattr(data, "model_dump"):
            return json.dumps(data.model_dump(), ensure_ascii=False, default=str), True
        return str(data), True

    # Success
    if result.output_for_assistant:
        return result.output_for_assistant, False

    data = result.data
    if hasattr(data, "model_dump"):
        return json.dumps(data.model_dump(), ensure_ascii=False, default=str), False
    return str(data), False


# ---------------------------------------------------------------------------
# read_file_state tracking
# ---------------------------------------------------------------------------


def _update_read_file_state(
    read_file_state: dict[str, Any],
    tool_name: str,
    params: dict[str, Any],
    exec_result: ToolExecutionResult,
) -> None:
    """Track which files have been read, for FileEdit/FileWrite validation."""
    if tool_name in ("FileRead", "read") and exec_result.success:
        # Extract file path from params
        path = params.get("file_path") or params.get("path")
        if path:
            read_file_state[path] = {
                "timestamp": time.time(),
                "hash": "",  # hash not critical for tests
            }
    elif tool_name in ("FileWrite", "write", "FileEdit", "edit") and exec_result.success:
        # FileWrite auto-adds to read_file_state in its call function,
        # but we also track it here for safety
        path = params.get("file_path") or params.get("path")
        if path:
            read_file_state[path] = {
                "timestamp": time.time(),
                "hash": "",
            }


# ---------------------------------------------------------------------------
# Core runner
# ---------------------------------------------------------------------------


async def run_with_tools(
    query_engine: QueryEngine,
    query: str,
    timeout: float = 120.0,
    max_turns: int = 15,
    continue_prompt: str | None = None,
) -> ToolRunResult:
    """Run a query through QueryEngine with full tool execution loop.

    Args:
        query_engine: The QueryEngine instance (with tools configured).
        query: Initial user query.
        timeout: Max total time for the entire run (all turns).
        max_turns: Safety limit to prevent infinite loops.
        continue_prompt: Prompt sent after tool results to let the LLM continue.
            If None, a strong default is used that reminds the model of the task.

    Returns:
        ToolRunResult with final response, tool call history, and diagnostics.
    """
    result = ToolRunResult()
    tool_executor = ToolExecutor()

    # Auto-approve all permissions for testing
    tool_executor.permission_manager.set_permission_callback(_auto_allow_permission)

    # Build ToolUseContext from QueryEngine config
    ctx = ToolUseContext(
        get_app_state=query_engine.config.get_app_state,
        set_app_state=query_engine.config.set_app_state,
        read_file_state={},
    )

    deadline = asyncio.get_event_loop().time() + timeout
    current_query = query
    is_continue_query = False

    # Build a strong continue prompt that references the original task.
    # DeepSeek V4 tends to give a "final answer" after receiving tool results
    # instead of continuing with more tool calls. We explicitly override this.
    _continue_prompt = continue_prompt or (
        f"The original request was: {query}\n\n"
        "You have received the tool results above. "
        "The task is NOT complete yet — you MUST continue by making additional tool calls "
        "(FileRead, FileEdit, FileWrite, Bash, etc.) as needed. "
        "Do NOT provide a final summary or explanation until you have fully completed the request."
    )

    for turn in range(1, max_turns + 1):
        remaining = deadline - asyncio.get_event_loop().time()
        if remaining <= 0:
            result.error = f"Total timeout ({timeout}s) exceeded after {turn - 1} turns"
            break

        result.turn_count = turn
        pending_tools: list[tuple[str, dict[str, Any]]] = []
        assistant_chunks: list[str] = []

        # ------------------------------------------------------------------
        # Step 1: Submit message and collect LLM response
        # ------------------------------------------------------------------
        try:
            async for qres in query_engine.submit_message(current_query):
                msg = qres.message
                msg_type = msg.__class__.__name__

                if msg_type == "AssistantMessage":
                    if hasattr(msg, "content") and isinstance(msg.content, str):
                        assistant_chunks.append(msg.content)
                elif msg_type == "ToolUseMessage":
                    pending_tools.append((msg.tool_use_id, dict(msg.input)))
        except asyncio.TimeoutError:
            result.error = f"Timeout on turn {turn} (submit_message)"
            break
        except Exception as e:
            result.error = f"Exception on turn {turn}: {type(e).__name__}: {e}"
            break

        # If no tools pending, the LLM has given a final answer
        if not pending_tools:
            result.final_response = "".join(assistant_chunks)
            break

        # ------------------------------------------------------------------
        # Step 2: Execute each pending tool
        # ------------------------------------------------------------------
        for tool_use_id, params in pending_tools:
            # Prefer the tool name from the ToolUseMessage itself; some model formats
            # incorrectly embed a 'name' key inside params that is not the tool name.
            tool_name = "unknown"
            for msg in reversed(query_engine.messages):
                if (
                    msg.__class__.__name__ == "ToolUseMessage"
                    and getattr(msg, "tool_use_id", None) == tool_use_id
                ):
                    tool_name = getattr(msg, "name", tool_name)
                    break
            # Guard against weird model output where msg.name is not a real tool
            if tool_name == "unknown" and "name" in params:
                tool_name = params["name"]

            try:
                exec_result = await asyncio.wait_for(
                    tool_executor.execute_tool_by_name(tool_name, params, context=ctx),
                    timeout=max(remaining, 30.0),
                )
            except asyncio.TimeoutError:
                exec_result = ToolExecutionResult(
                    success=False,
                    result=None,
                    permission_granted=True,
                    message="Tool execution timed out",
                    tool_name=tool_name,
                )
            except Exception as e:
                exec_result = ToolExecutionResult(
                    success=False,
                    result=None,
                    permission_granted=True,
                    message=f"Tool execution exception: {type(e).__name__}: {e}",
                    tool_name=tool_name,
                )

            content, is_error = _serialize_tool_result(tool_name, exec_result)

            # Record the tool call
            info = ToolCallInfo(
                name=tool_name,
                params=params,
                execution_success=exec_result.success and not is_error,
                execution_result=content,
                execution_error=content if is_error else None,
                turn=turn,
            )
            result.tool_calls.append(info)

            # Add result back to QueryEngine
            query_engine.add_tool_result(tool_use_id, content, is_error=is_error)

            # Update read_file_state for FileEdit/FileWrite validation
            _update_read_file_state(ctx.read_file_state, tool_name, params, exec_result)

        # ------------------------------------------------------------------
        # Step 3: Prepare next turn
        # ------------------------------------------------------------------
        current_query = _continue_prompt
        is_continue_query = True

    else:
        # max_turns reached without breaking
        result.error = f"Max turns ({max_turns}) reached"

    # If we never collected a final response, use accumulated chunks
    if not result.final_response and assistant_chunks:
        result.final_response = "".join(assistant_chunks)

    # Populate diagnostics
    result.diagnostics["max_turns_reached"] = result.turn_count >= max_turns
    result.diagnostics["timeout_reached"] = result.error and "timeout" in result.error.lower()
    result.diagnostics["tool_count"] = len(result.tool_calls)
    result.diagnostics["failed_tools"] = [
        tc.name for tc in result.tool_calls if not tc.execution_success
    ]

    return result
