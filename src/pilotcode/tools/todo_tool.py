"""Unified todo management tool with persistence and Task system integration.

Provides full CRUD for todos and bidirectional sync with the Task system:
- Creating a todo can optionally spawn a background Task
- Task completion automatically updates linked todo status
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from .base import ToolResult, ToolUseContext, build_tool
from .registry import register_tool


class TodoStatus(str, Enum):
    """Status of a todo item."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    DONE = "done"
    CANCELLED = "cancelled"


# ------------------------------------------------------------------
# Persistence helpers
# ------------------------------------------------------------------


def _todos_path() -> Path:
    from pilotcode.utils.paths import get_data_dir

    return get_data_dir() / "todos.json"


def load_todos() -> dict[str, dict[str, Any]]:
    path = _todos_path()
    if not path.exists():
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_todos(todos: dict[str, dict[str, Any]]) -> None:
    path = _todos_path()
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(todos, f, ensure_ascii=False, indent=2, default=str)
    except Exception:
        pass


# ------------------------------------------------------------------
# Task sync helper
# ------------------------------------------------------------------


def _sync_with_task(todo: dict[str, Any]) -> dict[str, Any]:
    """If a todo is linked to a Task, pull the latest status."""
    task_id = todo.get("linked_task_id")
    if not task_id:
        return todo

    try:
        # Delayed import to avoid circular dependency
        task_tools = __import__("pilotcode.tools.task_tools", fromlist=["_tasks"])
        _tasks = getattr(task_tools, "_tasks", {})
        TaskStatus = getattr(task_tools, "TaskStatus", None)
        if TaskStatus is None:
            return todo

        task = _tasks.get(task_id)
        if task:
            mapping = {
                TaskStatus.PENDING: TodoStatus.PENDING,
                TaskStatus.RUNNING: TodoStatus.IN_PROGRESS,
                TaskStatus.COMPLETED: TodoStatus.DONE,
                TaskStatus.FAILED: TodoStatus.CANCELLED,
                TaskStatus.CANCELLED: TodoStatus.CANCELLED,
            }
            new_status = mapping.get(task.status)
            if new_status and new_status.value != todo.get("status"):
                todo["status"] = new_status.value
                todo["updated_at"] = datetime.now(timezone.utc).isoformat()
    except Exception:
        pass
    return todo


# ------------------------------------------------------------------
# Input / Output schemas
# ------------------------------------------------------------------


class TodoWriteInput(BaseModel):
    """Input for TodoWrite tool."""

    todos: list[dict[str, Any]] = Field(
        description="List of todos to create or update. Each todo may have: id, content, status (pending/in_progress/done/cancelled), priority (1-3), linked_task_id, create_task (bool) to auto-spawn a background Task."
    )


class TodoListInput(BaseModel):
    """Input for TodoList tool."""

    status: str | None = Field(default=None, description="Filter by status")
    limit: int = Field(default=20, description="Max results")


class TodoGetInput(BaseModel):
    """Input for TodoGet tool."""

    todo_id: str = Field(description="Todo ID to retrieve")


class TodoDeleteInput(BaseModel):
    """Input for TodoDelete tool."""

    todo_id: str = Field(description="Todo ID to delete")


class TodoOutput(BaseModel):
    """Output from todo tools."""

    todo_id: str
    content: str
    status: str
    priority: int = 2
    linked_task_id: str | None = None
    created_at: str
    updated_at: str


# ------------------------------------------------------------------
# Tool implementations
# ------------------------------------------------------------------


async def todo_write_call(
    input_data: TodoWriteInput,
    context: ToolUseContext,
    can_use_tool: Any,
    parent_message: Any,
    on_progress: Any,
) -> ToolResult[dict[str, Any]]:
    """Create or update todos, with optional Task spawning."""
    todos = load_todos()
    updated = []
    created_task_ids: list[str] = []

    for item in input_data.todos:
        todo_id = item.get("id") or item.get("todo_id") or str(uuid.uuid4())[:8]
        now = datetime.now(timezone.utc).isoformat()

        existing = todos.get(todo_id, {})
        content = item.get("content") or existing.get("content", "")
        status_str = item.get("status") or existing.get("status", TodoStatus.PENDING.value)
        priority = item.get("priority", existing.get("priority", 2))
        linked_task_id = item.get("linked_task_id", existing.get("linked_task_id"))

        # Auto-create a background Task if requested
        if item.get("create_task") and not linked_task_id:
            try:
                from .task_tools import task_create_call, TaskCreateInput

                task_result = await task_create_call(
                    TaskCreateInput(description=content, command=item.get("command")),
                    context,
                    can_use_tool,
                    parent_message,
                    on_progress,
                )
                if task_result.data:
                    linked_task_id = task_result.data.task_id
                    created_task_ids.append(linked_task_id)
                    status_str = TodoStatus.IN_PROGRESS.value
            except Exception:
                pass

        todo = {
            "todo_id": todo_id,
            "content": content,
            "status": status_str,
            "priority": priority,
            "linked_task_id": linked_task_id,
            "created_at": existing.get("created_at", now),
            "updated_at": now,
        }
        todos[todo_id] = todo
        updated.append(todo)

    save_todos(todos)

    return ToolResult(
        data={
            "updated": len(updated),
            "todos": updated,
            "created_task_ids": created_task_ids,
        }
    )


async def todo_list_call(
    input_data: TodoListInput,
    context: ToolUseContext,
    can_use_tool: Any,
    parent_message: Any,
    on_progress: Any,
) -> ToolResult[dict[str, Any]]:
    """List todos with optional filtering."""
    todos = load_todos()
    items = list(todos.values())

    # Sync statuses from linked tasks
    for item in items:
        _sync_with_task(item)

    if input_data.status:
        items = [t for t in items if t.get("status") == input_data.status]

    # Sort by priority asc, then updated_at desc
    items.sort(key=lambda t: (t.get("priority", 2), t.get("updated_at", "")), reverse=False)
    items = items[: input_data.limit]

    save_todos(todos)
    return ToolResult(data={"todos": items, "total": len(todos)})


async def todo_get_call(
    input_data: TodoGetInput,
    context: ToolUseContext,
    can_use_tool: Any,
    parent_message: Any,
    on_progress: Any,
) -> ToolResult[dict[str, Any]]:
    """Get a single todo by ID."""
    todos = load_todos()
    todo = todos.get(input_data.todo_id)
    if not todo:
        return ToolResult(data={}, error=f"Todo '{input_data.todo_id}' not found")

    _sync_with_task(todo)
    save_todos(todos)
    return ToolResult(data=todo)


async def todo_delete_call(
    input_data: TodoDeleteInput,
    context: ToolUseContext,
    can_use_tool: Any,
    parent_message: Any,
    on_progress: Any,
) -> ToolResult[dict[str, Any]]:
    """Delete a todo by ID."""
    todos = load_todos()
    if input_data.todo_id not in todos:
        return ToolResult(data={}, error=f"Todo '{input_data.todo_id}' not found")

    removed = todos.pop(input_data.todo_id)
    save_todos(todos)
    return ToolResult(data={"deleted": input_data.todo_id, "content": removed.get("content")})


# ------------------------------------------------------------------
# Unified Todo tool (replaces TodoWrite/TodoList/TodoGet/TodoDelete)
# ------------------------------------------------------------------


class TodoInput(BaseModel):
    """Input for unified Todo tool."""

    action: str = Field(description="Action: write, list, get, delete")
    todos: list[dict[str, Any]] | None = Field(
        default=None,
        description="For write: list of todos to create/update. Each item may have id, content, status, priority, linked_task_id, create_task, command.",
    )
    status: str | None = Field(default=None, description="For list: filter by status")
    limit: int = Field(default=20, description="For list: max results")
    todo_id: str | None = Field(default=None, description="For get/delete: todo ID")


class TodoOutputUnified(BaseModel):
    """Unified output for Todo tool."""

    result: dict[str, Any] = Field(default_factory=dict, description="Result data")
    message: str = Field(default="", description="Status message")


async def todo_call(
    input_data: TodoInput,
    context: ToolUseContext,
    can_use_tool: Any,
    parent_message: Any,
    on_progress: Any,
) -> ToolResult[TodoOutputUnified]:
    """Unified todo handler."""
    action = input_data.action.lower()

    if action == "write":
        if not input_data.todos:
            return ToolResult(data=TodoOutputUnified(), error="todos required for write")
        result = await todo_write_call(
            TodoWriteInput(todos=input_data.todos),
            context,
            can_use_tool,
            parent_message,
            on_progress,
        )
        return ToolResult(
            data=TodoOutputUnified(
                result=result.data if result.data else {},
                message=f"Updated {result.data.get('updated', 0)} todo(s)",
            ),
            error=result.error,
        )

    elif action == "list":
        result = await todo_list_call(
            TodoListInput(status=input_data.status, limit=input_data.limit),
            context,
            can_use_tool,
            parent_message,
            on_progress,
        )
        return ToolResult(
            data=TodoOutputUnified(
                result=result.data if result.data else {},
                message=f"Listed {result.data.get('total', 0)} todo(s)",
            ),
            error=result.error,
        )

    elif action == "get":
        if not input_data.todo_id:
            return ToolResult(data=TodoOutputUnified(), error="todo_id required for get")
        result = await todo_get_call(
            TodoGetInput(todo_id=input_data.todo_id),
            context,
            can_use_tool,
            parent_message,
            on_progress,
        )
        return ToolResult(
            data=TodoOutputUnified(
                result=result.data if result.data else {}, message="Todo retrieved"
            ),
            error=result.error,
        )

    elif action == "delete":
        if not input_data.todo_id:
            return ToolResult(data=TodoOutputUnified(), error="todo_id required for delete")
        result = await todo_delete_call(
            TodoDeleteInput(todo_id=input_data.todo_id),
            context,
            can_use_tool,
            parent_message,
            on_progress,
        )
        return ToolResult(
            data=TodoOutputUnified(
                result=result.data if result.data else {},
                message=f"Deleted todo {input_data.todo_id}",
            ),
            error=result.error,
        )

    else:
        return ToolResult(data=TodoOutputUnified(), error=f"Unknown action: {action}")


TodoTool = build_tool(
    name="Todo",
    description=lambda x, o: f"Todo {x.action}",
    input_schema=TodoInput,
    output_schema=TodoOutputUnified,
    call=todo_call,
    aliases=["todo"],
    search_hint="Manage todo items: write, list, get, delete",
    is_read_only=lambda x: x.action in ("list", "get") if x else True,
    is_concurrency_safe=lambda x: x.action in ("list", "get") if x else True,
    render_tool_use_message=lambda x, o: f"📝 Todo {x.action}",
)

register_tool(TodoTool)

# Legacy fine-grained tools (kept importable but no longer registered)
TodoWriteTool = build_tool(
    name="TodoWrite",
    description=lambda x, o: f"Updating {len(x.todos)} todo item(s)",
    input_schema=TodoWriteInput,
    output_schema=dict,
    call=todo_write_call,
    aliases=["todo_write"],
    search_hint="Create or update todo items",
    is_read_only=lambda _: False,
    is_concurrency_safe=lambda _: True,
    render_tool_use_message=lambda x, o: f"📝 Updating {len(x.todos)} todo(s)",
)

TodoListTool = build_tool(
    name="TodoList",
    description=lambda x, o: "Listing todos",
    input_schema=TodoListInput,
    output_schema=dict,
    call=todo_list_call,
    aliases=["todos", "list_todos"],
    search_hint="List all todo items",
    is_read_only=lambda _: True,
    is_concurrency_safe=lambda _: True,
    render_tool_use_message=lambda x, o: "📋 Listing todos",
)

TodoGetTool = build_tool(
    name="TodoGet",
    description=lambda x, o: f"Getting todo {x.todo_id}",
    input_schema=TodoGetInput,
    output_schema=dict,
    call=todo_get_call,
    aliases=["get_todo"],
    search_hint="Get a single todo by ID",
    is_read_only=lambda _: True,
    is_concurrency_safe=lambda _: True,
    render_tool_use_message=lambda x, o: f"🔍 Getting todo {x.todo_id}",
)

TodoDeleteTool = build_tool(
    name="TodoDelete",
    description=lambda x, o: f"Deleting todo {x.todo_id}",
    input_schema=TodoDeleteInput,
    output_schema=dict,
    call=todo_delete_call,
    aliases=["delete_todo"],
    search_hint="Delete a todo item",
    is_read_only=lambda _: False,
    is_concurrency_safe=lambda _: True,
    render_tool_use_message=lambda x, o: f"🗑️ Deleting todo {x.todo_id}",
)

# register_tool(TodoWriteTool)  # Merged into Todo
# register_tool(TodoListTool)
# register_tool(TodoGetTool)
# register_tool(TodoDeleteTool)
