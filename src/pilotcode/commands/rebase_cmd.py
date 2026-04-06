"""Rebase command implementation."""

import subprocess
from .base import CommandHandler, register_command, CommandContext


async def rebase_command(args: list[str], context: CommandContext) -> str:
    """Handle /rebase command."""
    if not args:
        return "Usage: /rebase <branch> | /rebase --continue | /rebase --abort"

    action = args[0]

    if action in ("--continue", "--abort", "--skip"):
        # Rebase control
        try:
            result = subprocess.run(
                ["git", "rebase", action], capture_output=True, text=True, cwd=context.cwd
            )

            if result.returncode == 0:
                return f"Rebase {action}:\n{result.stdout}"
            else:
                return f"Error:\n{result.stderr}"

        except Exception as e:
            return f"Error: {e}"

    else:
        # Start rebase
        branch = action

        try:
            result = subprocess.run(
                ["git", "rebase", branch], capture_output=True, text=True, cwd=context.cwd
            )

            if result.returncode == 0:
                return f"Rebased onto {branch}:\n{result.stdout}"
            else:
                return f"Rebase failed:\n{result.stderr}"

        except Exception as e:
            return f"Error: {e}"


register_command(CommandHandler(name="rebase", description="Rebase branch", handler=rebase_command))
