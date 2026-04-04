"""Version command implementation."""

from .base import CommandHandler, register_command, CommandContext
import sys


async def version_command(args: list[str], context: CommandContext) -> str:
    """Handle /version command."""
    lines = [
        "PilotCode v0.2.0",
        "",
        "Python rewrite of Claude Code",
        "",
        f"Python: {sys.version}",
        "",
        "Components:",
        "  - Tools: 36 implemented",
        "  - Commands: 25 implemented",
        "  - Core: asyncio, pydantic, rich",
        "",
        "License: MIT"
    ]
    
    return "\n".join(lines)


register_command(CommandHandler(
    name="version",
    description="Show version information",
    handler=version_command,
    aliases=["v", "--version"]
))
