"""Rename command implementation."""

import subprocess
from .base import CommandHandler, register_command, CommandContext


async def rename_command(args: list[str], context: CommandContext) -> str:
    """Handle /rename command."""
    if len(args) < 2:
        return "Usage: /rename <old_name> <new_name> [path]"
    
    old_name = args[0]
    new_name = args[1]
    path = args[2] if len(args) > 2 else "."
    
    try:
        # Use sed to rename
        result = subprocess.run(
            ["sed", "-i", f"s/\\b{old_name}\\b/{new_name}/g", path],
            capture_output=True,
            text=True,
            cwd=context.cwd
        )
        
        if result.returncode == 0:
            return f"Renamed '{old_name}' to '{new_name}' in {path}"
        else:
            return f"Error: {result.stderr}"
    
    except Exception as e:
        return f"Error: {e}"


register_command(CommandHandler(
    name="rename",
    description="Rename symbol",
    handler=rename_command
))
