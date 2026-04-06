"""Cd command implementation."""

import os
from pathlib import Path
from .base import CommandHandler, register_command, CommandContext


async def cd_command(args: list[str], context: CommandContext) -> str:
    """Handle /cd command."""
    if not args:
        return f"Current directory: {context.cwd}"

    target = args[0]

    try:
        path = Path(target)
        if not path.is_absolute():
            path = Path(context.cwd) / path

        path = path.resolve()

        if not path.exists():
            return f"Directory not found: {target}"

        if not path.is_dir():
            return f"Not a directory: {target}"

        # Change directory
        os.chdir(str(path))
        context.cwd = str(path)

        return f"Changed to: {path}"

    except Exception as e:
        return f"Error: {e}"


register_command(CommandHandler(name="cd", description="Change directory", handler=cd_command))
