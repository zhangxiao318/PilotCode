"""Test command implementation."""

import subprocess
import os
from .base import CommandHandler, register_command, CommandContext


async def test_command(args: list[str], context: CommandContext) -> str:
    """Handle /test command."""
    # Detect if we're running inside pytest to avoid recursion
    if os.environ.get("PYTEST_CURRENT_TEST"):
        return "[dim]Skipping test command during pytest run[/dim]"

    if args:
        # Run specific test
        test_path = args[0]

        try:
            result = subprocess.run(
                ["python", "-m", "pytest", test_path, "-v"],
                capture_output=True,
                text=True,
                cwd=context.cwd,
                timeout=60,  # Add timeout to prevent hanging
            )

            output = result.stdout
            if result.stderr:
                output += "\n" + result.stderr

            if result.returncode == 0:
                return f"Tests passed:\n{output}"
            else:
                return f"Tests failed:\n{output}"

        except subprocess.TimeoutExpired:
            return "Tests timed out after 60 seconds"
        except Exception as e:
            return f"Error: {e}"

    else:
        # Run all tests
        try:
            result = subprocess.run(
                ["python", "-m", "pytest", "-v"],
                capture_output=True,
                text=True,
                cwd=context.cwd,
                timeout=120,  # Add timeout to prevent hanging
            )

            output = result.stdout
            if result.stderr:
                output += "\n" + result.stderr

            if result.returncode == 0:
                return f"All tests passed:\n{output}"
            else:
                return f"Some tests failed:\n{output}"

        except subprocess.TimeoutExpired:
            return "Tests timed out after 120 seconds"
        except Exception as e:
            return f"Error: {e}"


register_command(CommandHandler(name="test", description="Run tests", handler=test_command))
