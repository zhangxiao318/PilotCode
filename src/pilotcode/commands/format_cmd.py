"""Format command implementation."""

import subprocess
from .base import CommandHandler, register_command, CommandContext


async def format_command(args: list[str], context: CommandContext) -> str:
    """Handle /format command.

    Usage:
        /format                    Format current directory
        /format src/foo.py         Format specific file
        /format src/ --diff        Show diff without writing (black)
    """
    if not args:
        args = ["."]

    try:
        # Try black first (passes through all args)
        result = subprocess.run(
            ["black", *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            cwd=context.cwd,
        )

        if result.returncode == 0 or result.returncode == 1:
            # black returns 1 when files were reformatted (normal)
            out = result.stdout or ""
            err = result.stderr or ""
            if not out.strip() and not err.strip():
                return "Formatted with black: Done"
            return f"Formatted with black:\n{out}{err}"

        # Try autopep8 if black not available
        target = args[0]
        result2 = subprocess.run(
            ["autopep8", "--in-place", "--recursive", target],
            capture_output=True,
            text=True,
            cwd=context.cwd,
        )

        if result2.returncode == 0:
            return f"Formatted with autopep8: {target}"

        return "Error: No formatter found (black or autopep8)"

    except Exception as e:
        return f"Error: {e}"


register_command(
    CommandHandler(
        name="format",
        description="Format code with black (passes extra args through)",
        handler=format_command,
    )
)
