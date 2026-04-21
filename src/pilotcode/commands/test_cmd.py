"""Test command implementation."""

__test__ = False  # Prevent pytest from collecting this module

import asyncio
import os
from .base import CommandHandler, register_command, CommandContext
from .async_runner import run_command_streaming


async def test_command(args: list[str], context: CommandContext) -> str:
    """Handle /test command."""
    # Detect if we're running inside pytest to avoid recursion
    if os.environ.get("PYTEST_CURRENT_TEST"):
        return "[dim]Skipping test command during pytest run[/dim]"

    cmd = ["python", "-m", "pytest", "-v"]
    total_timeout = 120

    if args:
        # Run specific test
        test_path = args[0]
        cmd.append(test_path)
        total_timeout = 60

    try:
        returncode, stdout, stderr = await run_command_streaming(
            cmd,
            cwd=context.cwd,
            total_timeout=total_timeout,
            inactivity_timeout=30,
        )

        output = stdout
        if stderr:
            output += "\n" + stderr

        if returncode == 0:
            return f"Tests passed:\n{output}"
        else:
            return f"Tests failed:\n{output}"

    except asyncio.TimeoutError:
        return f"Tests timed out after {total_timeout} seconds"
    except asyncio.CancelledError:
        return "Tests cancelled by user"
    except Exception as e:
        return f"Error: {e}"


register_command(CommandHandler(name="test", description="Run tests", handler=test_command))
