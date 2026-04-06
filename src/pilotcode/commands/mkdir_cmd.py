"""Mkdir command implementation."""

from pathlib import Path
from .base import CommandHandler, register_command, CommandContext


async def mkdir_command(args: list[str], context: CommandContext) -> str:
    """Handle /mkdir command."""
    if not args:
        return "Usage: /mkdir <directory>"

    dir_path = args[0]

    try:
        path = Path(dir_path)
        if not path.is_absolute():
            path = Path(context.cwd) / path

        path.mkdir(parents=True, exist_ok=True)

        return f"Created directory: {path}"

    except Exception as e:
        return f"Error: {e}"


register_command(
    CommandHandler(name="mkdir", description="Create directory", handler=mkdir_command)
)
