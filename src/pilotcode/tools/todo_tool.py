"""Todo write tool for tracking tasks."""

from typing import Any
from pydantic import BaseModel, Field
from enum import Enum

from .base import Tool, ToolResult, ToolUseContext, build_tool
from .registry import register_tool


class TodoStatus(str, Enum):
    """Status of a todo item."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    DONE = "done"


class TodoInput(BaseModel):
    """Input for TodoWrite tool."""

    todos: list[dict[str, Any]] = Field(
        description="List of todos to update. Each todo should have 'id', 'content', and 'status'"
    )


class TodoOutput(BaseModel):
    """Output from TodoWrite tool."""

    updated: int
    todos: list[dict[str, Any]]


# Global todo storage (in real implementation, this would be in AppState)
_todo_storage: dict[str, dict[str, Any]] = {}


async def todo_write_call(
    input_data: TodoInput,
    context: ToolUseContext,
    can_use_tool: Any,
    parent_message: Any,
    on_progress: Any,
) -> ToolResult[TodoOutput]:
    """Write/update todos."""
    global _todo_storage

    updated = 0
    for todo in input_data.todos:
        todo_id = todo.get("id")
        if todo_id:
            _todo_storage[todo_id] = todo
            updated += 1

    return ToolResult(data=TodoOutput(updated=updated, todos=list(_todo_storage.values())))


async def todo_description(input_data: TodoInput, options: dict[str, Any]) -> str:
    """Get description for todo write."""
    count = len(input_data.todos)
    return f"Updating {count} todo item(s)"


def render_todo_use(input_data: TodoInput, options: dict[str, Any]) -> str:
    """Render todo tool use message."""
    count = len(input_data.todos)
    return f"📝 Updating {count} todo(s)"


# Create the TodoWrite tool
TodoWriteTool = build_tool(
    name="TodoWrite",
    description=todo_description,
    input_schema=TodoInput,
    output_schema=TodoOutput,
    call=todo_write_call,
    aliases=["todo", "task"],
    search_hint="Create or update todo items",
    is_read_only=lambda _: False,
    is_concurrency_safe=lambda _: True,
    render_tool_use_message=render_todo_use,
)

# Register the tool
register_tool(TodoWriteTool)
