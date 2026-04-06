"""Coverage command implementation."""

import subprocess
from .base import CommandHandler, register_command, CommandContext


async def coverage_command(args: list[str], context: CommandContext) -> str:
    """Handle /coverage command."""
    action = args[0] if args else "report"

    if action == "run":
        try:
            result = subprocess.run(
                ["python", "-m", "pytest", "--cov=.", "--cov-report=term-missing"],
                capture_output=True,
                text=True,
                cwd=context.cwd,
            )

            output = result.stdout
            if result.stderr:
                output += "\n" + result.stderr

            return output

        except Exception as e:
            return f"Error: {e}"

    elif action == "report":
        try:
            result = subprocess.run(
                ["python", "-m", "coverage", "report"],
                capture_output=True,
                text=True,
                cwd=context.cwd,
            )

            output = result.stdout
            if result.stderr:
                output += "\n" + result.stderr

            return output

        except Exception as e:
            return f"Error: {e}"

    elif action == "html":
        try:
            result = subprocess.run(
                ["python", "-m", "coverage", "html"],
                capture_output=True,
                text=True,
                cwd=context.cwd,
            )

            if result.returncode == 0:
                return "HTML coverage report generated in htmlcov/"
            else:
                return f"Error: {result.stderr}"

        except Exception as e:
            return f"Error: {e}"

    else:
        return f"Unknown action: {action}. Use: run, report, html"


register_command(
    CommandHandler(name="coverage", description="Run code coverage", handler=coverage_command)
)
