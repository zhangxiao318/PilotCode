"""Remote command implementation."""

import subprocess
from .base import CommandHandler, register_command, CommandContext


async def remote_command(args: list[str], context: CommandContext) -> str:
    """Handle /remote command."""
    if not args:
        # List remotes
        try:
            result = subprocess.run(
                ["git", "remote", "-v"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                cwd=context.cwd,
            )

            if result.returncode == 0:
                if result.stdout.strip():
                    return f"Remotes:\n{result.stdout}"
                else:
                    return "No remotes configured"
            else:
                return f"Error: {result.stderr}"

        except Exception as e:
            return f"Error: {e}"

    action = args[0]

    if action == "add":
        if len(args) < 3:
            return "Usage: /remote add <name> <url>"

        name = args[1]
        url = args[2]

        try:
            result = subprocess.run(
                ["git", "remote", "add", name, url],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                cwd=context.cwd,
            )

            if result.returncode == 0:
                return f"Added remote: {name} -> {url}"
            else:
                return f"Error: {result.stderr}"

        except Exception as e:
            return f"Error: {e}"

    elif action == "remove":
        if len(args) < 2:
            return "Usage: /remote remove <name>"

        name = args[1]

        try:
            result = subprocess.run(
                ["git", "remote", "remove", name],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                cwd=context.cwd,
            )

            if result.returncode == 0:
                return f"Removed remote: {name}"
            else:
                return f"Error: {result.stderr}"

        except Exception as e:
            return f"Error: {e}"

    elif action == "fetch":
        remote = args[1] if len(args) > 1 else "origin"

        try:
            result = subprocess.run(
                ["git", "fetch", remote],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                cwd=context.cwd,
            )

            if result.returncode == 0:
                return f"Fetched from {remote}"
            else:
                return f"Error: {result.stderr}"

        except Exception as e:
            return f"Error: {e}"

    elif action == "pull":
        remote = args[1] if len(args) > 1 else "origin"
        branch = args[2] if len(args) > 2 else ""

        cmd = ["git", "pull", remote]
        if branch:
            cmd.append(branch)

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                cwd=context.cwd,
            )

            if result.returncode == 0:
                return f"Pulled from {remote}:\n{result.stdout}"
            else:
                return f"Error: {result.stderr}"

        except Exception as e:
            return f"Error: {e}"

    elif action == "push":
        remote = args[1] if len(args) > 1 else "origin"
        branch = args[2] if len(args) > 2 else ""

        cmd = ["git", "push", remote]
        if branch:
            cmd.append(branch)

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                cwd=context.cwd,
            )

            if result.returncode == 0:
                return f"Pushed to {remote}:\n{result.stdout}"
            else:
                return f"Error: {result.stderr}"

        except Exception as e:
            return f"Error: {e}"

    else:
        return f"Unknown action: {action}. Use: add, remove, fetch, pull, push"


register_command(
    CommandHandler(name="remote", description="Git remote operations", handler=remote_command)
)
