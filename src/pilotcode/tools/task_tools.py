"""Task management tools (TaskCreate, TaskGet, TaskList, TaskUpdate, TaskStop, TaskResume).

Features:
- Full CRUD + background execution via subprocess
- Persistence to disk (~/.pilotcode/data/tasks.json)
- Automatic recovery on startup ( orphaned RUNNING tasks marked FAILED )
- Resume / restart for interrupted or failed tasks
- Bidirectional sync with TodoWrite (task completion updates linked todos)
"""

from __future__ import annotations

import asyncio
import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from .base import ToolResult, ToolUseContext, build_tool
from .registry import register_tool


class TaskStatus(str, Enum):
    """Task status."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


# ------------------------------------------------------------------
# Persistence helpers
# ------------------------------------------------------------------


def _tasks_path() -> Path:
    from pilotcode.utils.paths import get_data_dir

    return get_data_dir() / "tasks.json"


def _task_handles_path() -> Path:
    """We only persist metadata; handles are ephemeral."""
    from pilotcode.utils.paths import get_data_dir

    return get_data_dir() / "task_handles.json"


def _serialize_task(task: Task) -> dict[str, Any]:
    """Serialize a Task to dict (exclude non-serializable fields)."""
    return {
        "task_id": task.task_id,
        "description": task.description,
        "status": task.status.value,
        "command": task.command,
        "created_at": task.created_at.isoformat() if task.created_at else None,
        "started_at": task.started_at.isoformat() if task.started_at else None,
        "completed_at": task.completed_at.isoformat() if task.completed_at else None,
        "result": task.result,
        "error": task.error,
        "restart_count": task.restart_count,
    }


def _deserialize_task(data: dict[str, Any]) -> Task:
    """Reconstruct a Task from dict."""
    from datetime import datetime as _dt

    def _parse(dt_str: str | None) -> _dt | None:
        if not dt_str:
            return None
        try:
            return _dt.fromisoformat(dt_str)
        except Exception:
            return None

    return Task(
        task_id=data.get("task_id", ""),
        description=data.get("description", ""),
        status=TaskStatus(data.get("status", "pending")),
        command=data.get("command"),
        created_at=_parse(data.get("created_at")) or _dt.now(timezone.utc),
        started_at=_parse(data.get("started_at")),
        completed_at=_parse(data.get("completed_at")),
        result=data.get("result"),
        error=data.get("error"),
        restart_count=data.get("restart_count", 0),
    )


def _save_all_tasks() -> None:
    """Persist all tasks to disk."""
    try:
        payload = {tid: _serialize_task(t) for tid, t in _tasks.items()}
        with open(_tasks_path(), "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2, default=str)
    except Exception:
        pass


def _load_all_tasks() -> dict[str, Task]:
    """Load tasks from disk."""
    path = _tasks_path()
    if not path.exists():
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            payload = json.load(f)
        return {tid: _deserialize_task(t) for tid, t in payload.items()}
    except Exception:
        return {}


# ------------------------------------------------------------------
# Startup recovery
# ------------------------------------------------------------------


def _recover_tasks_on_startup() -> None:
    """Load persisted tasks and mark orphaned RUNNING tasks as FAILED."""
    global _tasks
    recovered = _load_all_tasks()
    fixed = 0
    for task in recovered.values():
        if task.status == TaskStatus.RUNNING:
            task.status = TaskStatus.FAILED
            task.error = (
                task.error or ""
            ) + "\n[Recovered] Process was terminated when PilotCode exited."
            task.completed_at = datetime.now(timezone.utc)
            fixed += 1
    if fixed:
        _save_all_tasks()
    _tasks.update(recovered)


# ------------------------------------------------------------------
# Core Task dataclass
# ------------------------------------------------------------------


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
    command: str | None = None
    restart_count: int = 0


# Global state
_tasks: dict[str, Task] = {}
_task_handles: dict[str, asyncio.Task] = {}

# Recover on module load
_recover_tasks_on_startup()


# ------------------------------------------------------------------
# Internal helpers
# ------------------------------------------------------------------


def _update_linked_todo(task: Task) -> None:
    """When a Task finishes, update any linked Todo."""
    try:
        # Delayed import to avoid circular dependency
        from .todo_tool import load_todos, save_todos

        todos = load_todos()
        changed = False
        for todo in todos.values():
            if todo.get("linked_task_id") == task.task_id:
                mapping = {
                    TaskStatus.COMPLETED: "done",
                    TaskStatus.FAILED: "cancelled",
                    TaskStatus.CANCELLED: "cancelled",
                    TaskStatus.RUNNING: "in_progress",
                    TaskStatus.PENDING: "pending",
                }
                new_status = mapping.get(task.status, todo.get("status"))
                if new_status != todo.get("status"):
                    todo["status"] = new_status
                    todo["updated_at"] = datetime.now(timezone.utc).isoformat()
                    changed = True
        if changed:
            save_todos(todos)
    except Exception:
        pass


async def _run_task(task: Task, command: str | None = None) -> None:
    """Run task in background."""
    cmd = command or task.command
    if not cmd:
        task.status = TaskStatus.FAILED
        task.error = "No command to execute"
        task.completed_at = datetime.now(timezone.utc)
        _save_all_tasks()
        _update_linked_todo(task)
        return

    task.command = cmd
    task.status = TaskStatus.RUNNING
    task.started_at = datetime.now(timezone.utc)
    _save_all_tasks()

    try:
        process = await asyncio.create_subprocess_shell(
            cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        task.process = process

        try:
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=300)
        except asyncio.TimeoutError:
            process.kill()
            await process.wait()
            task.error = "Task timed out after 300 seconds"
            task.status = TaskStatus.FAILED
            task.completed_at = datetime.now(timezone.utc)
            _save_all_tasks()
            _update_linked_todo(task)
            return

        task.result = stdout.decode("utf-8", errors="replace") if stdout else ""
        if stderr:
            task.error = stderr.decode("utf-8", errors="replace")

        task.status = TaskStatus.COMPLETED if process.returncode == 0 else TaskStatus.FAILED
        task.completed_at = datetime.now(timezone.utc)

    except asyncio.CancelledError:
        if task.process and task.process.returncode is None:
            task.process.kill()
            await task.process.wait()
        task.status = TaskStatus.CANCELLED
        task.completed_at = datetime.now(timezone.utc)
        raise
    except Exception as e:
        task.error = str(e)
        task.status = TaskStatus.FAILED
        task.completed_at = datetime.now(timezone.utc)
    finally:
        _save_all_tasks()
        _update_linked_todo(task)


# ------------------------------------------------------------------
# Input / Output schemas
# ------------------------------------------------------------------


class TaskCreateInput(BaseModel):
    """Input for TaskCreate tool."""

    description: str = Field(description="Task description")
    command: str | None = Field(
        default=None,
        description="Shell command to execute in background. Use Bash tool for foreground execution.",
    )
    file_path: str | None = Field(default=None, description="File to execute (legacy)")


class TaskCreateOutput(BaseModel):
    """Output from TaskCreate tool."""

    task_id: str
    description: str
    status: str


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
    command: str | None
    restart_count: int
    created_at: str
    started_at: str | None
    completed_at: str | None


class TaskListInput(BaseModel):
    """Input for TaskList tool."""

    status: str | None = Field(default=None, description="Filter by status")
    limit: int = Field(default=10, description="Maximum number of tasks")


class TaskListOutput(BaseModel):
    """Output from TaskList tool."""

    tasks: list[dict]
    total: int


class TaskStopInput(BaseModel):
    """Input for TaskStop tool."""

    task_id: str = Field(description="Task ID to stop")


class TaskStopOutput(BaseModel):
    """Output from TaskStop tool."""

    task_id: str
    success: bool
    message: str


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


class TaskResumeInput(BaseModel):
    """Input for TaskResume / TaskRestart tool."""

    task_id: str = Field(description="Task ID to resume or restart")
    force_restart: bool = Field(
        default=False,
        description="If True, restart even if running or completed. If False, only resume pending/failed/cancelled tasks.",
    )


class TaskResumeOutput(BaseModel):
    """Output from TaskResume tool."""

    task_id: str
    success: bool
    status: str
    message: str


# ------------------------------------------------------------------
# Tool implementations
# ------------------------------------------------------------------


async def task_create_call(
    input_data: TaskCreateInput,
    context: ToolUseContext,
    can_use_tool: Any,
    parent_message: Any,
    on_progress: Any,
) -> ToolResult[TaskCreateOutput]:
    """Create a new task."""
    task_id = str(uuid.uuid4())[:8]

    task = Task(
        task_id=task_id,
        description=input_data.description,
        status=TaskStatus.PENDING,
        created_at=datetime.now(timezone.utc),
        command=input_data.command,
    )

    _tasks[task_id] = task
    _save_all_tasks()

    if input_data.command:
        task.status = TaskStatus.RUNNING
        task.started_at = datetime.now(timezone.utc)
        task.restart_count = task.restart_count + 1

        task_handle = asyncio.create_task(_run_task(task, input_data.command))
        _task_handles[task_id] = task_handle

        def on_done(t):
            _task_handles.pop(task_id, None)

        task_handle.add_done_callback(on_done)

    return ToolResult(
        data=TaskCreateOutput(
            task_id=task_id, description=input_data.description, status=task.status.value
        )
    )


async def task_get_call(
    input_data: TaskGetInput,
    context: ToolUseContext,
    can_use_tool: Any,
    parent_message: Any,
    on_progress: Any,
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
                command=None,
                restart_count=0,
                created_at="",
                started_at=None,
                completed_at=None,
            ),
            error=f"Task {input_data.task_id} not found",
        )

    return ToolResult(
        data=TaskGetOutput(
            task_id=task.task_id,
            description=task.description,
            status=task.status.value,
            result=task.result,
            error=task.error,
            command=task.command,
            restart_count=task.restart_count,
            created_at=task.created_at.isoformat() if task.created_at else "",
            started_at=task.started_at.isoformat() if task.started_at else None,
            completed_at=task.completed_at.isoformat() if task.completed_at else None,
        )
    )


async def task_list_call(
    input_data: TaskListInput,
    context: ToolUseContext,
    can_use_tool: Any,
    parent_message: Any,
    on_progress: Any,
) -> ToolResult[TaskListOutput]:
    """List tasks."""
    tasks = list(_tasks.values())

    if input_data.status:
        tasks = [t for t in tasks if t.status.value == input_data.status]

    tasks.sort(key=lambda t: t.created_at, reverse=True)
    tasks = tasks[: input_data.limit]

    task_list = [
        {
            "task_id": t.task_id,
            "description": t.description,
            "status": t.status.value,
            "command": t.command,
            "restart_count": t.restart_count,
            "created_at": t.created_at.isoformat() if t.created_at else "",
        }
        for t in tasks
    ]

    return ToolResult(data=TaskListOutput(tasks=task_list, total=len(_tasks)))


async def task_stop_call(
    input_data: TaskStopInput,
    context: ToolUseContext,
    can_use_tool: Any,
    parent_message: Any,
    on_progress: Any,
) -> ToolResult[TaskStopOutput]:
    """Stop a running task."""
    task = _tasks.get(input_data.task_id)

    if not task:
        return ToolResult(
            data=TaskStopOutput(
                task_id=input_data.task_id,
                success=False,
                message=f"Task {input_data.task_id} not found",
            )
        )

    if task.status != TaskStatus.RUNNING:
        return ToolResult(
            data=TaskStopOutput(
                task_id=input_data.task_id,
                success=False,
                message=f"Task is not running (status: {task.status.value})",
            )
        )

    task_handle = _task_handles.pop(input_data.task_id, None)
    if task_handle and not task_handle.done():
        task_handle.cancel()
        try:
            await asyncio.wait_for(task_handle, timeout=2)
        except (asyncio.TimeoutError, asyncio.CancelledError):
            pass

    if task.process:
        task.process.terminate()
        try:
            await asyncio.wait_for(task.process.wait(), timeout=5)
        except asyncio.TimeoutError:
            task.process.kill()

    task.status = TaskStatus.CANCELLED
    task.completed_at = datetime.now(timezone.utc)
    _save_all_tasks()
    _update_linked_todo(task)

    return ToolResult(
        data=TaskStopOutput(
            task_id=input_data.task_id, success=True, message=f"Task {input_data.task_id} stopped"
        )
    )


async def task_update_call(
    input_data: TaskUpdateInput,
    context: ToolUseContext,
    can_use_tool: Any,
    parent_message: Any,
    on_progress: Any,
) -> ToolResult[TaskUpdateOutput]:
    """Update a task."""
    task = _tasks.get(input_data.task_id)

    if not task:
        return ToolResult(
            data=TaskUpdateOutput(
                task_id=input_data.task_id, description="", status="", message=""
            ),
            error=f"Task {input_data.task_id} not found",
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
                    message="",
                ),
                error=f"Invalid status: {input_data.status}",
            )

    _save_all_tasks()
    return ToolResult(
        data=TaskUpdateOutput(
            task_id=task.task_id,
            description=task.description,
            status=task.status.value,
            message=f"Task {input_data.task_id} updated",
        )
    )


async def task_resume_call(
    input_data: TaskResumeInput,
    context: ToolUseContext,
    can_use_tool: Any,
    parent_message: Any,
    on_progress: Any,
) -> ToolResult[TaskResumeOutput]:
    """Resume or restart a task."""
    task = _tasks.get(input_data.task_id)

    if not task:
        return ToolResult(
            data=TaskResumeOutput(
                task_id=input_data.task_id,
                success=False,
                status="not_found",
                message=f"Task {input_data.task_id} not found",
            )
        )

    if not task.command:
        return ToolResult(
            data=TaskResumeOutput(
                task_id=input_data.task_id,
                success=False,
                status=task.status.value,
                message="Task has no command to execute",
            )
        )

    if task.status == TaskStatus.RUNNING and not input_data.force_restart:
        return ToolResult(
            data=TaskResumeOutput(
                task_id=input_data.task_id,
                success=False,
                status=task.status.value,
                message="Task is already running. Use force_restart=True to restart.",
            )
        )

    # Cancel existing handle if any
    if input_data.force_restart and task.status == TaskStatus.RUNNING:
        old_handle = _task_handles.pop(input_data.task_id, None)
        if old_handle and not old_handle.done():
            old_handle.cancel()
            try:
                await asyncio.wait_for(old_handle, timeout=2)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                pass
        if task.process and task.process.returncode is None:
            task.process.kill()
            try:
                await asyncio.wait_for(task.process.wait(), timeout=5)
            except asyncio.TimeoutError:
                pass

    # Reset state and re-run
    task.result = None
    task.error = None
    task.completed_at = None
    task.status = TaskStatus.RUNNING
    task.started_at = datetime.now(timezone.utc)
    task.restart_count = task.restart_count + 1
    _save_all_tasks()

    task_handle = asyncio.create_task(_run_task(task, task.command))
    _task_handles[input_data.task_id] = task_handle

    def on_done(t):
        _task_handles.pop(input_data.task_id, None)

    task_handle.add_done_callback(on_done)

    return ToolResult(
        data=TaskResumeOutput(
            task_id=task.task_id,
            success=True,
            status=TaskStatus.RUNNING.value,
            message=f"Task {task.task_id} resumed (restart #{task.restart_count})",
        )
    )


# ------------------------------------------------------------------
# Unified Task tool
# ------------------------------------------------------------------


class TaskInput(BaseModel):
    """Input for unified Task tool."""

    action: str = Field(description="Action: create, get, list, stop, update, output, resume")
    description: str | None = Field(default=None, description="For create: task description")
    command: str | None = Field(default=None, description="For create/resume: shell command")
    file_path: str | None = Field(default=None, description="For create: file to execute")
    task_id: str | None = Field(default=None, description="For get/stop/update/output/resume")
    status: str | None = Field(default=None, description="For update: new status")
    limit: int = Field(default=10, description="For list: max results")
    follow: bool = Field(default=False, description="For output: follow in real-time")
    tail: int | None = Field(default=None, description="For output: get last N lines")
    force_restart: bool = Field(
        default=False, description="For resume: force restart even if running"
    )


class TaskOutputUnified(BaseModel):
    """Unified output for Task tool."""

    result: dict[str, Any] = Field(default_factory=dict, description="Result data")
    message: str = Field(default="", description="Status message")


async def task_call(
    input_data: TaskInput,
    context: ToolUseContext,
    can_use_tool: Any,
    parent_message: Any,
    on_progress: Any,
) -> ToolResult[TaskOutputUnified]:
    """Unified task handler."""
    action = input_data.action.lower()

    if action == "create":
        result = await task_create_call(
            TaskCreateInput(
                description=input_data.description or "",
                command=input_data.command,
                file_path=input_data.file_path,
            ),
            context,
            can_use_tool,
            parent_message,
            on_progress,
        )
        return ToolResult(
            data=TaskOutputUnified(
                result=result.data.model_dump() if result.data else {}, message="Task created"
            ),
            error=result.error,
        )

    elif action == "get":
        if not input_data.task_id:
            return ToolResult(data=TaskOutputUnified(), error="task_id required for get")
        result = await task_get_call(
            TaskGetInput(task_id=input_data.task_id),
            context,
            can_use_tool,
            parent_message,
            on_progress,
        )
        return ToolResult(
            data=TaskOutputUnified(
                result=result.data.model_dump() if result.data else {}, message="Task retrieved"
            ),
            error=result.error,
        )

    elif action == "list":
        result = await task_list_call(
            TaskListInput(status=None, limit=input_data.limit),
            context,
            can_use_tool,
            parent_message,
            on_progress,
        )
        return ToolResult(
            data=TaskOutputUnified(
                result=result.data.model_dump() if result.data else {}, message="Tasks listed"
            ),
            error=result.error,
        )

    elif action == "stop":
        if not input_data.task_id:
            return ToolResult(data=TaskOutputUnified(), error="task_id required for stop")
        result = await task_stop_call(
            TaskStopInput(task_id=input_data.task_id),
            context,
            can_use_tool,
            parent_message,
            on_progress,
        )
        return ToolResult(
            data=TaskOutputUnified(
                result=result.data.model_dump() if result.data else {}, message="Task stopped"
            ),
            error=result.error,
        )

    elif action == "update":
        if not input_data.task_id:
            return ToolResult(data=TaskOutputUnified(), error="task_id required for update")
        result = await task_update_call(
            TaskUpdateInput(
                task_id=input_data.task_id,
                description=input_data.description,
                status=input_data.status,
            ),
            context,
            can_use_tool,
            parent_message,
            on_progress,
        )
        return ToolResult(
            data=TaskOutputUnified(
                result=result.data.model_dump() if result.data else {}, message="Task updated"
            ),
            error=result.error,
        )

    elif action == "output":
        if not input_data.task_id:
            return ToolResult(data=TaskOutputUnified(), error="task_id required for output")
        from .task_output_tool import task_output_call, TaskOutputInput

        result = await task_output_call(
            TaskOutputInput(
                task_id=input_data.task_id, follow=input_data.follow, tail=input_data.tail
            ),
            context,
            can_use_tool,
            parent_message,
            on_progress,
        )
        return ToolResult(
            data=TaskOutputUnified(
                result=result.data.model_dump() if result.data else {},
                message="Task output retrieved",
            ),
            error=result.error,
        )

    elif action == "resume":
        if not input_data.task_id:
            return ToolResult(data=TaskOutputUnified(), error="task_id required for resume")
        result = await task_resume_call(
            TaskResumeInput(task_id=input_data.task_id, force_restart=input_data.force_restart),
            context,
            can_use_tool,
            parent_message,
            on_progress,
        )
        return ToolResult(
            data=TaskOutputUnified(
                result=result.data.model_dump() if result.data else {}, message="Task resumed"
            ),
            error=result.error,
        )

    else:
        return ToolResult(data=TaskOutputUnified(), error=f"Unknown action: {action}")


# ------------------------------------------------------------------
# Tool registration
# ------------------------------------------------------------------

TaskTool = build_tool(
    name="Task",
    description=lambda x, o: f"Task {x.action}",
    input_schema=TaskInput,
    output_schema=TaskOutputUnified,
    call=task_call,
    aliases=["task"],
    is_read_only=lambda x: x.action in ("get", "list", "output") if x else True,
    is_concurrency_safe=lambda x: x.action in ("get", "list", "output") if x else True,
)

register_tool(TaskTool)

# Legacy fine-grained tools (not registered to avoid cluttering the tool pool,
# but kept importable for backward compatibility).
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

TaskResumeTool = build_tool(
    name="TaskResume",
    description=lambda x, o: f"Resuming task {x.task_id}",
    input_schema=TaskResumeInput,
    output_schema=TaskResumeOutput,
    call=task_resume_call,
    aliases=["task_resume", "restart"],
    is_read_only=lambda _: False,
    is_concurrency_safe=lambda _: False,
)

# register_tool(TaskCreateTool)  # Merged into Task
# register_tool(TaskGetTool)
# register_tool(TaskListTool)
# register_tool(TaskStopTool)
# register_tool(TaskUpdateTool)
# register_tool(TaskResumeTool)


async def cleanup_all_tasks():
    """Cancel and cleanup all running tasks. Used for testing."""
    global _task_handles, _tasks

    for task_id, handle in list(_task_handles.items()):
        if not handle.done():
            handle.cancel()
            try:
                await asyncio.wait_for(handle, timeout=1)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                pass
    _task_handles.clear()

    for task in list(_tasks.values()):
        if task.process and task.process.returncode is None:
            task.process.kill()
            try:
                await asyncio.wait_for(task.process.wait(), timeout=1)
            except asyncio.TimeoutError:
                pass
    _tasks.clear()
    _save_all_tasks()
