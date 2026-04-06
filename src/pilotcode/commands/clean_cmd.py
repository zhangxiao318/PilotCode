"""Clean command implementation."""

import subprocess
from .base import CommandHandler, register_command, CommandContext


async def clean_command(args: list[str], context: CommandContext) -> str:
    """Handle /clean command."""
    dry_run = "-n" in args or "--dry-run" in args or not args
    force = "-f" in args or "--force" in args

    try:
        cmd = ["git", "clean"]

        if dry_run:
            cmd.append("-n")
        elif force:
            cmd.append("-f")
        else:
            cmd.append("-n")  # Default to dry-run

        cmd.append("-d")  # Remove untracked directories

        result = subprocess.run(cmd, capture_output=True, text=True, cwd=context.cwd)

        if result.returncode == 0:
            output = result.stdout
            if not output.strip():
                return "No untracked files to remove"

            if dry_run:
                return f"Would remove (dry-run):\n{output}"
            else:
                return f"Removed:\n{output}"
        else:
            return f"Error: {result.stderr}"

    except Exception as e:
        return f"Error: {e}"


register_command(
    CommandHandler(name="clean", description="Clean untracked files", handler=clean_command)
)
