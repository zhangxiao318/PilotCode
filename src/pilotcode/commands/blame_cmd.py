"""Blame command implementation."""

import subprocess
from .base import CommandHandler, register_command, CommandContext


async def blame_command(args: list[str], context: CommandContext) -> str:
    """Handle /blame command."""
    if not args:
        return "Usage: /blame <file>"
    
    file_path = args[0]
    
    try:
        result = subprocess.run(
            ["git", "blame", file_path],
            capture_output=True,
            text=True,
            cwd=context.cwd
        )
        
        if result.returncode == 0:
            if result.stdout:
                lines = result.stdout.strip().split("\n")
                output = f"Blame for {file_path}:\n"
                for line in lines[:50]:  # Limit output
                    # Parse blame line
                    parts = line.split(None, 2)
                    if parts:
                        commit = parts[0]
                        output += f"  {commit[:8]}: {line}\n"
                return output
            else:
                return f"No blame info for {file_path}"
        else:
            return f"Error: {result.stderr}"
    
    except Exception as e:
        return f"Error: {e}"


register_command(CommandHandler(
    name="blame",
    description="Git blame file",
    handler=blame_command
))
