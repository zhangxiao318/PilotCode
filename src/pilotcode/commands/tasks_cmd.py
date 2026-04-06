"""Tasks command implementation."""

from .base import CommandHandler, register_command, CommandContext
from ..tools.task_tools import _tasks, TaskStatus


async def tasks_command(args: list[str], context: CommandContext) -> str:
    """Handle /tasks command."""
    if not _tasks:
        return "No tasks"

    # Status filter
    status_filter = None
    if args:
        status_filter = args[0].lower()

    lines = ["Tasks:", ""]

    for task_id, task in sorted(_tasks.items(), key=lambda x: x[1].created_at, reverse=True):
        if status_filter and task.status.value != status_filter:
            continue

        status_icon = {
            TaskStatus.PENDING: "⏳",
            TaskStatus.RUNNING: "▶️",
            TaskStatus.COMPLETED: "✅",
            TaskStatus.FAILED: "❌",
            TaskStatus.CANCELLED: "🚫",
        }.get(task.status, "❓")

        lines.append(f"  {status_icon} {task_id}: {task.description[:50]} ({task.status.value})")

    return "\n".join(lines)


register_command(
    CommandHandler(
        name="tasks",
        description="List background tasks",
        handler=tasks_command,
        aliases=["jobs", "bg"],
    )
)
