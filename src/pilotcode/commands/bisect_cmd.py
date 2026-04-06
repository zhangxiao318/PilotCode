"""Bisect command implementation."""

import subprocess
from .base import CommandHandler, register_command, CommandContext


async def bisect_command(args: list[str], context: CommandContext) -> str:
    """Handle /bisect command."""
    if not args:
        return "Usage: /bisect start|good|bad|reset|log"

    action = args[0]

    if action == "start":
        try:
            result = subprocess.run(
                ["git", "bisect", "start"], capture_output=True, text=True, cwd=context.cwd
            )

            if result.returncode == 0:
                return "Bisect started"
            else:
                return f"Error: {result.stderr}"

        except Exception as e:
            return f"Error: {e}"

    elif action == "good":
        commit = args[1] if len(args) > 1 else "HEAD"

        try:
            result = subprocess.run(
                ["git", "bisect", "good", commit], capture_output=True, text=True, cwd=context.cwd
            )

            if result.returncode == 0:
                return f"Marked {commit} as good\n{result.stdout}"
            else:
                return f"Error: {result.stderr}"

        except Exception as e:
            return f"Error: {e}"

    elif action == "bad":
        commit = args[1] if len(args) > 1 else "HEAD"

        try:
            result = subprocess.run(
                ["git", "bisect", "bad", commit], capture_output=True, text=True, cwd=context.cwd
            )

            if result.returncode == 0:
                return f"Marked {commit} as bad\n{result.stdout}"
            else:
                return f"Error: {result.stderr}"

        except Exception as e:
            return f"Error: {e}"

    elif action == "reset":
        try:
            result = subprocess.run(
                ["git", "bisect", "reset"], capture_output=True, text=True, cwd=context.cwd
            )

            if result.returncode == 0:
                return "Bisect reset"
            else:
                return f"Error: {result.stderr}"

        except Exception as e:
            return f"Error: {e}"

    elif action == "log":
        try:
            result = subprocess.run(
                ["git", "bisect", "log"], capture_output=True, text=True, cwd=context.cwd
            )

            if result.returncode == 0:
                return f"Bisect log:\n{result.stdout}"
            else:
                return f"Error: {result.stderr}"

        except Exception as e:
            return f"Error: {e}"

    else:
        return f"Unknown action: {action}. Use: start, good, bad, reset, log"


register_command(
    CommandHandler(name="bisect", description="Git bisect operations", handler=bisect_command)
)
