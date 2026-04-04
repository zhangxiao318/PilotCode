"""Tail command implementation."""

from pathlib import Path
from collections import deque
from .base import CommandHandler, register_command, CommandContext


async def tail_command(args: list[str], context: CommandContext) -> str:
    """Handle /tail command."""
    if not args:
        return "Usage: /tail <file> [lines=10]"
    
    file_path = args[0]
    lines = int(args[1]) if len(args) > 1 else 10
    
    try:
        path = Path(file_path)
        if not path.is_absolute():
            path = Path(context.cwd) / path
        
        if not path.exists():
            return f"File not found: {file_path}"
        
        with open(path, 'r', encoding='utf-8', errors='replace') as f:
            last_lines = deque(f, maxlen=lines)
        
        content = ''.join(last_lines)
        ext = path.suffix.lstrip('.')
        return f"```{ext}\n{content}\n```"
    
    except Exception as e:
        return f"Error: {e}"


register_command(CommandHandler(
    name="tail",
    description="Show last lines of file",
    handler=tail_command
))
