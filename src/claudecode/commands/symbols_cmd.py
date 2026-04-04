"""Symbols command implementation."""

import subprocess
from .base import CommandHandler, register_command, CommandContext


async def symbols_command(args: list[str], context: CommandContext) -> str:
    """Handle /symbols command."""
    if not args:
        return "Usage: /symbols <file>"
    
    file_path = args[0]
    
    # Try ctags
    try:
        result = subprocess.run(
            ["ctags", "-x", "--python-kinds=-i", file_path],
            capture_output=True,
            text=True,
            cwd=context.cwd
        )
        
        if result.returncode == 0:
            lines = result.stdout.strip().split("\n")
            if lines:
                output = f"Symbols in {file_path}:\n"
                for line in lines[:50]:  # Limit output
                    parts = line.split(None, 2)
                    if len(parts) >= 3:
                        name, kind, location = parts[0], parts[1], parts[2]
                        output += f"  {kind}: {name}\n"
                return output
            else:
                return f"No symbols found in {file_path}"
        
        # Fallback: grep for def/class
        result2 = subprocess.run(
            ["grep", "-n", "^[[:space:]]*\(def\\|class\\)", file_path],
            capture_output=True,
            text=True,
            cwd=context.cwd
        )
        
        if result2.returncode == 0:
            return f"Symbols in {file_path}:\n{result2.stdout}"
        
        return f"Error: Could not extract symbols from {file_path}"
    
    except Exception as e:
        return f"Error: {e}"


register_command(CommandHandler(
    name="symbols",
    description="Show symbols in file",
    handler=symbols_command
))
