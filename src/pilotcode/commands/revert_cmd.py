"""Revert command implementation."""

import subprocess
from .base import CommandHandler, register_command, CommandContext


async def revert_command(args: list[str], context: CommandContext) -> str:
    """Handle /revert command."""
    if not args:
        return "Usage: /revert <commit> | /revert --continue | /revert --abort"

    action = args[0]

    if action in ("--continue", "--abort", "--quit"):
        # Revert control
        try:
            result = subprocess.run(
                ["git", "revert", action], capture_output=True, text=True, cwd=context.cwd
            )

            if result.returncode == 0:
                return f"Revert {action}:\n{result.stdout}"
            else:
                return f"Error:\n{result.stderr}"

        except Exception as e:
            return f"Error: {e}"

    else:
        # Revert commit
        commit = action
        no_edit = "--no-edit" in args

        try:
            cmd = ["git", "revert"]
            if no_edit:
                cmd.append("--no-edit")
            cmd.append(commit)

            result = subprocess.run(cmd, capture_output=True, text=True, cwd=context.cwd)

            if result.returncode == 0:
                return f"Reverted {commit}:\n{result.stdout}"
            else:
                return f"Revert failed:\n{result.stderr}"

        except Exception as e:
            return f"Error: {e}"


register_command(CommandHandler(name="revert", description="Revert commit", handler=revert_command))
