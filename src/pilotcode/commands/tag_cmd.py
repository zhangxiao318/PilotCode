"""Tag command implementation."""

import subprocess
from .base import CommandHandler, register_command, CommandContext


async def tag_command(args: list[str], context: CommandContext) -> str:
    """Handle /tag command."""
    if not args:
        # List tags
        try:
            result = subprocess.run(
                ["git", "tag", "-l"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                cwd=context.cwd,
            )

            if result.returncode == 0:
                if result.stdout.strip():
                    return f"Tags:\n{result.stdout}"
                else:
                    return "No tags"
            else:
                return f"Error: {result.stderr}"

        except Exception as e:
            return f"Error: {e}"

    action = args[0]

    if action == "create":
        if len(args) < 2:
            return "Usage: /tag create <tag_name> [message]"

        tag_name = args[1]
        message = " ".join(args[2:]) if len(args) > 2 else tag_name

        try:
            result = subprocess.run(
                ["git", "tag", "-a", tag_name, "-m", message],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                cwd=context.cwd,
            )

            if result.returncode == 0:
                return f"Created tag: {tag_name}"
            else:
                return f"Error: {result.stderr}"

        except Exception as e:
            return f"Error: {e}"

    elif action == "delete":
        if len(args) < 2:
            return "Usage: /tag delete <tag_name>"

        tag_name = args[1]

        try:
            result = subprocess.run(
                ["git", "tag", "-d", tag_name],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                cwd=context.cwd,
            )

            if result.returncode == 0:
                return f"Deleted tag: {tag_name}"
            else:
                return f"Error: {result.stderr}"

        except Exception as e:
            return f"Error: {e}"

    elif action == "push":
        try:
            result = subprocess.run(
                ["git", "push", "origin", "--tags"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                cwd=context.cwd,
            )

            if result.returncode == 0:
                return "Tags pushed to remote"
            else:
                return f"Error: {result.stderr}"

        except Exception as e:
            return f"Error: {e}"

    else:
        return f"Unknown action: {action}. Use: create, delete, push"


register_command(CommandHandler(name="tag", description="Git tag operations", handler=tag_command))
