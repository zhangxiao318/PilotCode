"""Rm command implementation."""

from pathlib import Path
from .base import CommandHandler, register_command, CommandContext


async def rm_command(args: list[str], context: CommandContext) -> str:
    """Handle /rm command."""
    if not args:
        return "Usage: /rm <path> [-r]"

    target_path = args[0]
    recursive = "-r" in args or "-R" in args

    try:
        path = Path(target_path)
        if not path.is_absolute():
            path = Path(context.cwd) / path

        if not path.exists():
            return f"Path not found: {target_path}"

        if path.is_dir():
            if recursive:
                import shutil

                shutil.rmtree(path)
                return f"Removed directory: {target_path}"
            else:
                return "Use -r flag to remove directories"
        else:
            path.unlink()
            return f"Removed: {target_path}"

    except Exception as e:
        return f"Error: {e}"


register_command(
    CommandHandler(
        name="rm",
        description="Remove file or directory",
        handler=rm_command,
        aliases=["remove", "del"],
    )
)
