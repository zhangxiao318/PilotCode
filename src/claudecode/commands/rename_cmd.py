"""Rename command implementation."""

import os
from datetime import datetime
from .base import CommandHandler, register_command, CommandContext


_sessions = {}  # In-memory session store


async def rename_command(args: list[str], context: CommandContext) -> str:
    """Handle /rename command."""
    if not args:
        return "Usage: /rename <new_name>"
    
    new_name = " ".join(args)
    
    # Would update session name in storage
    # For now, just acknowledge
    return f"Session renamed to: {new_name}"


register_command(CommandHandler(
    name="rename",
    description="Rename current session",
    handler=rename_command
))
