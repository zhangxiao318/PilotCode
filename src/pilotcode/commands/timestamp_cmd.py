"""Timestamp command implementation."""

from .base import CommandHandler, register_command, CommandContext
import sys
from datetime import datetime


async def timestamp_command(args: list[str], context: CommandContext) -> str:
    """Handle /timestamp command."""
    lines = [
        "Timestamp Information",
        "=" * 20,
        "",
        f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"Working directory: {context.cwd}",
        f"Python: {sys.version.split()[0]}",
    ]

    return "\n".join(lines)


register_command(
    CommandHandler(
        name="timestamp",
        description="Show current timestamp and environment info",
        handler=timestamp_command,
        aliases=["ts"],
    )
)