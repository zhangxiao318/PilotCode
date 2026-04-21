"""Coverage command implementation."""

import asyncio
from .base import CommandHandler, register_command, CommandContext
from .async_runner import run_command_streaming


async def coverage_command(args: list[str], context: CommandContext) -> str:
    """Handle /coverage command."""
    action = args[0] if args else "report"

    if action == "run":
        try:
            returncode, stdout, stderr = await run_command_streaming(
                ["python", "-m", "pytest", "--cov=.", "--cov-report=term-missing"],
                cwd=context.cwd,
                total_timeout=300,
                inactivity_timeout=30,
            )

            output = stdout
            if stderr:
                output += "\n" + stderr

            return output

        except asyncio.CancelledError:
            return "Coverage run cancelled by user"
        except Exception as e:
            return f"Error: {e}"

    elif action == "report":
        try:
            returncode, stdout, stderr = await run_command_streaming(
                ["python", "-m", "coverage", "report"],
                cwd=context.cwd,
                total_timeout=60,
                inactivity_timeout=15,
            )

            output = stdout
            if stderr:
                output += "\n" + stderr

            return output

        except asyncio.CancelledError:
            return "Coverage report cancelled by user"
        except Exception as e:
            return f"Error: {e}"

    elif action == "html":
        try:
            returncode, stdout, stderr = await run_command_streaming(
                ["python", "-m", "coverage", "html"],
                cwd=context.cwd,
                total_timeout=60,
                inactivity_timeout=15,
            )

            if returncode == 0:
                return "HTML coverage report generated in htmlcov/"
            else:
                return f"Error: {stderr}"

        except asyncio.CancelledError:
            return "Coverage HTML generation cancelled by user"
        except Exception as e:
            return f"Error: {e}"

    else:
        return f"Unknown action: {action}. Use: run, report, html"


register_command(
    CommandHandler(name="coverage", description="Run code coverage", handler=coverage_command)
)
