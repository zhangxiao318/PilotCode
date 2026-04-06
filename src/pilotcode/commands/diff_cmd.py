"""Diff command implementation."""

import subprocess
from .base import CommandHandler, register_command, CommandContext


async def diff_command(args: list[str], context: CommandContext) -> str:
    """Handle /diff command."""
    if args:
        # Diff specific files or commits
        try:
            result = subprocess.run(
                ["git", "diff"] + args, capture_output=True, text=True, cwd=context.cwd
            )

            if result.returncode == 0:
                if result.stdout:
                    return result.stdout[:5000]  # Limit output
                else:
                    return "No differences"
            else:
                return f"Error: {result.stderr}"

        except Exception as e:
            return f"Error: {e}"

    else:
        # Show current diff
        try:
            result = subprocess.run(
                ["git", "diff"], capture_output=True, text=True, cwd=context.cwd
            )

            if result.returncode == 0:
                if result.stdout:
                    return result.stdout[:5000]  # Limit output
                else:
                    return "No changes"
            else:
                return f"Error: {result.stderr}"

        except Exception as e:
            return f"Error: {e}"


register_command(CommandHandler(name="diff", description="Show git diff", handler=diff_command))
