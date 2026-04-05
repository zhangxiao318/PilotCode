"""Task management tools (TaskCreate, TaskGet, TaskList, TaskUpdate, TaskStop)."""

import asyncio
import uuid
from typing import Any
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pydantic import BaseModel, Field

from .base import Tool, ToolResult, ToolUseContext, build_tool
from .registry import register_tool


class TaskStatus(str, Enum):
    """Task status."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


# Task storage
_tasks: dict[str, "Task"] = {}


@dataclass
class Task:
    """Background task."""
    task_id: str
    description: str
    status: TaskStatus
    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    result: str | None = None
    error: str | None = None
    process: asyncio.subprocess.Process | None = None


class TaskCreateInput(BaseModel):
    """Input for TaskCreate tool."""
    description: str = Field(description="Task description")
    command: str | None = Field(default=None, description="Command to execute")
    file_path: str | None = Field(default=None, description="File to execute")


class TaskCreateOutput(BaseModel):
    """Output from TaskCreate tool."""
    task_id: str
    description: str
    status: str


async def task_create_call(
    input_data: TaskCreateInput,
    context: ToolUseContext,
    can_use_tool: Any,
    parent_message: Any,
    on_progress: Any
) -> ToolResult[TaskCreateOutput]:
    """Create a new task."""
    task_id = str(uuid.uuid4())[:8]
    
    task = Task(
        task_id=task_id,
        description=input_data.description,
        status=TaskStatus.PENDING,
        created_at=datetime.now()
    )
    
    _tasks[task_id] = task
    
    # Start task execution if command provided
    if input_data.command:
        task.status = TaskStatus.RUNNING
        task.started_at = datetime.now()
        
        # Start in background
        asyncio.create_task(_run_task(task, input_data.command))
    
    return ToolResult(data=TaskCreateOutput(
        task_id=task_id,
        description=input_data.description,
        status=task.status.value
    ))


async def _run_task(task: Task, command: str) -> None:
    """Run task in background."""
    try:
        process = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        task.process = process
        stdout, stderr = await process.communicate()
        
        task.result = stdout.decode('utf-8', errors='replace')
        if stderr:
            task.error = stderr.decode('utf-8', errors='replace')
        
        task.status = TaskStatus.COMPLETED if process.returncode == 0 else TaskStatus.FAILED
        task.completed_at = datetime.now()
    
    except Exception as e:
        task.error = str(e)
        task.status = TaskStatus.FAILED
        task.completed_at = datetime.now()


class TaskGetInput(BaseModel):
    """Input for TaskGet tool."""
    task_id: str = Field(description="Task ID")


class TaskGetOutput(BaseModel):
    """Output from TaskGet tool."""
    task_id: str
    description: str
    status: str
    result: str | None
    error: str | None
    created_at: str
    started_at: str | None
    completed_at: str | None


async def task_get_call(
    input_data: TaskGetInput,
    context: ToolUseContext,
    can_use_tool: Any,
    parent_message: Any,
    on_progress: Any
) -> ToolResult[TaskGetOutput]:
    """Get task status."""
    task = _tasks.get(input_data.task_id)
    
    if not task:
        return ToolResult(
            data=TaskGetOutput(
                task_id=input_data.task_id,
                description="",
                status="not_found",
                result=None,
                error=None,
                created_at="",
                started_at=None,
                completed_at=None
            ),
            error=f"Task {input_data.task_id} not found"
        )
    
    return ToolResult(data=TaskGetOutput(
        task_id=task.task_id,
        description=task.description,
        status=task.status.value,
        result=task.result,
        error=task.error,
        created_at=task.created_at.isoformat(),
        started_at=task.started_at.isoformat() if task.started_at else None,
        completed_at=task.completed_at.isoformat() if task.completed_at else None
    ))


class TaskListInput(BaseModel):
    """Input for TaskList tool."""
    status: str | None = Field(default=None, description="Filter by status")
    limit: int = Field(default=10, description="Maximum number of tasks")


class TaskListOutput(BaseModel):
    """Output from TaskList tool."""
    tasks: list[dict]
    total: int


async def task_list_call(
    input_data: TaskListInput,
    context: ToolUseContext,
    can_use_tool: Any,
    parent_message: Any,
    on_progress: Any
) -> ToolResult[TaskListOutput]:
    """List tasks."""
    tasks = list(_tasks.values())
    
    if input_data.status:
        tasks = [t for t in tasks if t.status.value == input_data.status]
    
    # Sort by created_at descending
    tasks.sort(key=lambda t: t.created_at, reverse=True)
    tasks = tasks[:input_data.limit]
    
    task_list = [
        {
            "task_id": t.task_id,
            "description": t.description,
            "status": t.status.value,
            "created_at": t.created_at.isoformat()
        }
        for t in tasks
    ]
    
    return ToolResult(data=TaskListOutput(
        tasks=task_list,
        total=len(_tasks)
    ))


class TaskStopInput(BaseModel):
    """Input for TaskStop tool."""
    task_id: str = Field(description="Task ID to stop")


class TaskStopOutput(BaseModel):
    """Output from TaskStop tool."""
    task_id: str
    success: bool
    message: str


async def task_stop_call(
    input_data: TaskStopInput,
    context: ToolUseContext,
    can_use_tool: Any,
    parent_message: Any,
    on_progress: Any
) -> ToolResult[TaskStopOutput]:
    """Stop a task."""
    task = _tasks.get(input_data.task_id)
    
    if not task:
        return ToolResult(data=TaskStopOutput(
            task_id=input_data.task_id,
            success=False,
            message=f"Task {input_data.task_id} not found"
        ))
    
    if task.status != TaskStatus.RUNNING:
        return ToolResult(data=TaskStopOutput(
            task_id=input_data.task_id,
            success=False,
            message=f"Task is not running (status: {task.status.value})"
        ))
    
    if task.process:
        task.process.terminate()
        try:
            await asyncio.wait_for(task.process.wait(), timeout=5)
        except asyncio.TimeoutError:
            task.process.kill()
    
    task.status = TaskStatus.CANCELLED
    task.completed_at = datetime.now()
    
    return ToolResult(data=TaskStopOutput(
        task_id=input_data.task_id,
        success=True,
        message=f"Task {input_data.task_id} stopped"
    ))


class TaskUpdateInput(BaseModel):
    """Input for TaskUpdate tool."""
    task_id: str = Field(description="Task ID")
    description: str | None = Field(default=None, description="New description")
    status: str | None = Field(default=None, description="New status")


class TaskUpdateOutput(BaseModel):
    """Output from TaskUpdate tool."""
    task_id: str
    description: str
    status: str
    message: str


async def task_update_call(
    input_data: TaskUpdateInput,
    context: ToolUseContext,
    can_use_tool: Any,
    parent_message: Any,
    on_progress: Any
) -> ToolResult[TaskUpdateOutput]:
    """Update a task."""
    task = _tasks.get(input_data.task_id)
    
    if not task:
        return ToolResult(
            data=TaskUpdateOutput(
                task_id=input_data.task_id,
                description="",
                status="",
                message=""
            ),
            error=f"Task {input_data.task_id} not found"
        )
    
    if input_data.description:
        task.description = input_data.description
    
    if input_data.status:
        try:
            task.status = TaskStatus(input_data.status)
        except ValueError:
            return ToolResult(
                data=TaskUpdateOutput(
                    task_id=input_data.task_id,
                    description=task.description,
                    status=task.status.value,
                    message=""
                ),
                error=f"Invalid status: {input_data.status}"
            )
    
    return ToolResult(data=TaskUpdateOutput(
        task_id=task.task_id,
        description=task.description,
        status=task.status.value,
        message=f"Task {input_data.task_id} updated"
    ))


# Register task tools
TaskCreateTool = build_tool(
    name="TaskCreate",
    description=lambda x, o: f"Creating task: {x.description[:50]}",
    input_schema=TaskCreateInput,
    output_schema=TaskCreateOutput,
    call=task_create_call,
    aliases=["task_create"],
    is_read_only=lambda _: False,
    is_concurrency_safe=lambda _: True,
)

TaskGetTool = build_tool(
    name="TaskGet",
    description=lambda x, o: f"Getting task {x.task_id}",
    input_schema=TaskGetInput,
    output_schema=TaskGetOutput,
    call=task_get_call,
    aliases=["task_get"],
    is_read_only=lambda _: True,
    is_concurrency_safe=lambda _: True,
)

TaskListTool = build_tool(
    name="TaskList",
    description=lambda x, o: "Listing tasks",
    input_schema=TaskListInput,
    output_schema=TaskListOutput,
    call=task_list_call,
    aliases=["task_list", "tasks"],
    is_read_only=lambda _: True,
    is_concurrency_safe=lambda _: True,
)

TaskStopTool = build_tool(
    name="TaskStop",
    description=lambda x, o: f"Stopping task {x.task_id}",
    input_schema=TaskStopInput,
    output_schema=TaskStopOutput,
    call=task_stop_call,
    aliases=["task_stop", "kill"],
    is_read_only=lambda _: False,
    is_concurrency_safe=lambda _: False,
)

TaskUpdateTool = build_tool(
    name="TaskUpdate",
    description=lambda x, o: f"Updating task {x.task_id}",
    input_schema=TaskUpdateInput,
    output_schema=TaskUpdateOutput,
    call=task_update_call,
    aliases=["task_update"],
    is_read_only=lambda _: False,
    is_concurrency_safe=lambda _: True,
)

register_tool(TaskCreateTool)
register_tool(TaskGetTool)
register_tool(TaskListTool)
register_tool(TaskStopTool)
register_tool(TaskUpdateTool)
