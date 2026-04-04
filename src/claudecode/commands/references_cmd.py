"""References command implementation."""

import subprocess
from .base import CommandHandler, register_command, CommandContext


async def references_command(args: list[str], context: CommandContext) -> str:
    """Handle /references command."""
    if not args:
        return "Usage: /references <symbol> [path]"
    
    symbol = args[0]
    path = args[1] if len(args) > 1 else "."
    
    try:
        # Use grep to find references
        result = subprocess.run(
            ["grep", "-rn", symbol, path],
            capture_output=True,
            text=True,
            cwd=context.cwd
        )
        
        if result.returncode == 0:
            lines = result.stdout.strip().split("\n")
            if lines:
                output = f"References to '{symbol}':\n"
                for line in lines[:30]:  # Limit output
                    output += f"  {line}\n"
                return output
            else:
                return f"No references found for '{symbol}'"
        else:
            return f"No references found for '{symbol}'"
    
    except Exception as e:
        return f"Error: {e}"


register_command(CommandHandler(
    name="references",
    description="Find references to symbol",
    handler=references_command
))
