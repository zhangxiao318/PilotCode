"""TaskOutput tool for retrieving task results."""

from typing import Any
from pydantic import BaseModel, Field

from .base import ToolResult, ToolUseContext, build_tool
from .registry import register_tool
from .task_tools import _tasks


class TaskOutputInput(BaseModel):
    """Input for TaskOutput tool."""

    task_id: str = Field(description="Task ID to get output from")
    follow: bool = Field(default=False, description="Follow output in real-time")
    tail: int | None = Field(default=None, description="Get last N lines of output")


class TaskOutputOutput(BaseModel):
    """Output from TaskOutput tool."""

    task_id: str
    status: str
    stdout: str
    stderr: str
    complete: bool


async def task_output_call(
    input_data: TaskOutputInput,
    context: ToolUseContext,
    can_use_tool: Any,
    parent_message: Any,
    on_progress: Any,
) -> ToolResult[TaskOutputOutput]:
    """Get task output."""

    if input_data.task_id not in _tasks:
        return ToolResult(
            data=TaskOutputOutput(
                task_id=input_data.task_id, status="not_found", stdout="", stderr="", complete=False
            ),
            error=f"Task not found: {input_data.task_id}",
        )

    task = _tasks[input_data.task_id]

    stdout = task.result or ""
    stderr = task.error or ""

    # Tail if requested
    if input_data.tail and stdout:
        lines = stdout.split("\n")
        stdout = "\n".join(lines[-input_data.tail :])

    return ToolResult(
        data=TaskOutputOutput(
            task_id=input_data.task_id,
            status=task.status.value,
            stdout=stdout,
            stderr=stderr,
            complete=task.status.value in ["completed", "failed", "cancelled"],
        )
    )


TaskOutputTool = build_tool(
    name="TaskOutput",
    description=lambda x, o: f"Get output for task {x.task_id}",
    input_schema=TaskOutputInput,
    output_schema=TaskOutputOutput,
    call=task_output_call,
    aliases=["task_output", "task_log"],
    is_read_only=lambda _: True,
    is_concurrency_safe=lambda _: True,
)

register_tool(TaskOutputTool)
