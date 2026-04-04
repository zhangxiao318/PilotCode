"""Format command implementation."""

import subprocess
from .base import CommandHandler, register_command, CommandContext


async def format_command(args: list[str], context: CommandContext) -> str:
    """Handle /format command."""
    target = args[0] if args else "."
    
    try:
        # Try black first
        result = subprocess.run(
            ["black", target],
            capture_output=True,
            text=True,
                cwd=context.cwd
        )
        
        if result.returncode == 0:
            return f"Formatted with black:\n{result.stdout or 'Done'}"
        
        # Try autopep8 if black not available
        result2 = subprocess.run(
            ["autopep8", "--in-place", "--recursive", target],
            capture_output=True,
            text=True,
            cwd=context.cwd
        )
        
        if result2.returncode == 0:
            return f"Formatted with autopep8: {target}"
        
        return "Error: No formatter found (black or autopep8)"
    
    except Exception as e:
        return f"Error: {e}"


register_command(CommandHandler(
    name="format",
    description="Format code with black",
    handler=format_command
))
