"""Pwd command implementation."""

from .base import CommandHandler, register_command, CommandContext


async def pwd_command(args: list[str], context: CommandContext) -> str:
    """Handle /pwd command."""
    return f"Current directory: {context.cwd}"


register_command(CommandHandler(
    name="pwd",
    description="Print working directory",
    handler=pwd_command
))
