"""Branch command implementation."""

import subprocess
from .base import CommandHandler, register_command, CommandContext


async def branch_command(args: list[str], context: CommandContext) -> str:
    """Handle /branch command."""
    if not args:
        # List branches
        try:
            result = subprocess.run(
                ["git", "branch", "-vv"], capture_output=True, text=True, cwd=context.cwd
            )

            if result.returncode == 0:
                return f"Branches:\n{result.stdout}"
            else:
                return f"Error: {result.stderr}"

        except Exception as e:
            return f"Error: {e}"

    action = args[0]

    if action in ("create", "c"):
        if len(args) < 2:
            return "Usage: /branch create <branch_name>"

        branch_name = args[1]

        try:
            result = subprocess.run(
                ["git", "branch", branch_name], capture_output=True, text=True, cwd=context.cwd
            )

            if result.returncode == 0:
                return f"Created branch: {branch_name}"
            else:
                return f"Error: {result.stderr}"

        except Exception as e:
            return f"Error: {e}"

    elif action in ("switch", "s", "checkout"):
        if len(args) < 2:
            return "Usage: /branch switch <branch_name>"

        branch_name = args[1]

        try:
            result = subprocess.run(
                ["git", "switch", branch_name], capture_output=True, text=True, cwd=context.cwd
            )

            if result.returncode == 0:
                return f"Switched to branch: {branch_name}"
            else:
                # Try checkout if switch fails
                result = subprocess.run(
                    ["git", "checkout", branch_name],
                    capture_output=True,
                    text=True,
                    cwd=context.cwd,
                )
                if result.returncode == 0:
                    return f"Switched to branch: {branch_name}"
                return f"Error: {result.stderr}"

        except Exception as e:
            return f"Error: {e}"

    elif action in ("delete", "d"):
        if len(args) < 2:
            return "Usage: /branch delete <branch_name>"

        branch_name = args[1]

        try:
            result = subprocess.run(
                ["git", "branch", "-d", branch_name],
                capture_output=True,
                text=True,
                cwd=context.cwd,
            )

            if result.returncode == 0:
                return f"Deleted branch: {branch_name}"
            else:
                return f"Error: {result.stderr}"

        except Exception as e:
            return f"Error: {e}"

    else:
        return f"Unknown action: {action}. Use: create, switch, delete"


register_command(
    CommandHandler(
        name="branch", description="Branch management", handler=branch_command, aliases=["br"]
    )
)
