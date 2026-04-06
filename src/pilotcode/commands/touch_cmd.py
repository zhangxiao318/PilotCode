"""Touch command implementation."""

from pathlib import Path
from .base import CommandHandler, register_command, CommandContext


async def touch_command(args: list[str], context: CommandContext) -> str:
    """Handle /touch command."""
    if not args:
        return "Usage: /touch <file>"

    file_path = args[0]

    try:
        path = Path(file_path)
        if not path.is_absolute():
            path = Path(context.cwd) / path

        path.touch(exist_ok=True)
        return f"Touched: {path}"

    except Exception as e:
        return f"Error: {e}"


register_command(
    CommandHandler(
        name="touch", description="Create empty file or update timestamp", handler=touch_command
    )
)
