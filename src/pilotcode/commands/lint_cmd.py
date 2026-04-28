"""Lint command implementation."""

import subprocess
from .base import CommandHandler, register_command, CommandContext


async def lint_command(args: list[str], context: CommandContext) -> str:
    """Handle /lint command.

    Usage:
        /lint                      Lint current directory
        /lint src/foo.py           Lint specific file
        /lint --fix                Auto-fix issues (ruff)
        /lint src/ --fix           Fix issues in directory
    """
    if not args:
        args = ["."]

    try:
        # Try ruff first (passes through all args, e.g. --fix)
        result = subprocess.run(
            ["ruff", "check", *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            cwd=context.cwd,
        )

        output = ""
        if result.stdout:
            output += result.stdout
        if result.stderr:
            output += "\n" + result.stderr

        if result.returncode == 0 and not output.strip():
            return "No linting issues found with ruff!"

        if output:
            return f"Ruff results:\n{output}"

        # Try flake8
        target = args[0] if args[0] != "--fix" else "."
        result2 = subprocess.run(
            ["flake8", target],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            cwd=context.cwd,
        )

        output2 = ""
        if result2.stdout:
            output2 += result2.stdout
        if result2.stderr:
            output2 += "\n" + result2.stderr

        if result2.returncode == 0 and not output2.strip():
            return "No linting issues found with flake8!"

        if output2:
            return f"Flake8 results:\n{output2}"

        return "Error: No linter found (ruff or flake8)"

    except Exception as e:
        return f"Error: {e}"


register_command(
    CommandHandler(
        name="lint",
        description="Lint code with ruff/flake8 (use --fix to auto-fix)",
        handler=lint_command,
    )
)
