"""Test command implementation."""

import subprocess
from .base import CommandHandler, register_command, CommandContext


async def test_command(args: list[str], context: CommandContext) -> str:
    """Handle /test command."""
    if args:
        # Run specific test
        test_path = args[0]

        try:
            result = subprocess.run(
                ["python", "-m", "pytest", test_path, "-v"],
                capture_output=True,
                text=True,
                cwd=context.cwd,
            )

            output = result.stdout
            if result.stderr:
                output += "\n" + result.stderr

            if result.returncode == 0:
                return f"Tests passed:\n{output}"
            else:
                return f"Tests failed:\n{output}"

        except Exception as e:
            return f"Error: {e}"

    else:
        # Run all tests
        try:
            result = subprocess.run(
                ["python", "-m", "pytest", "-v"], capture_output=True, text=True, cwd=context.cwd
            )

            output = result.stdout
            if result.stderr:
                output += "\n" + result.stderr

            if result.returncode == 0:
                return f"All tests passed:\n{output}"
            else:
                return f"Some tests failed:\n{output}"

        except Exception as e:
            return f"Error: {e}"


register_command(CommandHandler(name="test", description="Run tests", handler=test_command))
