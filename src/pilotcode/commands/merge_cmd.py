"""Merge command implementation."""

import subprocess
from .base import CommandHandler, register_command, CommandContext


async def merge_command(args: list[str], context: CommandContext) -> str:
    """Handle /merge command."""
    if not args:
        return "Usage: /merge <branch> [--no-ff]"

    branch = args[0]
    no_ff = "--no-ff" in args

    try:
        cmd = ["git", "merge"]
        if no_ff:
            cmd.append("--no-ff")
        cmd.append(branch)

        result = subprocess.run(
            cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=context.cwd
        )

        if result.returncode == 0:
            return f"Merged {branch}:\n{result.stdout}"
        else:
            return f"Merge failed:\n{result.stderr}"

    except Exception as e:
        return f"Error: {e}"


register_command(CommandHandler(name="merge", description="Merge branch", handler=merge_command))
