"""Head command implementation."""

from pathlib import Path
from .base import CommandHandler, register_command, CommandContext


async def head_command(args: list[str], context: CommandContext) -> str:
    """Handle /head command."""
    if not args:
        return "Usage: /head <file> [lines=10]"
    
    file_path = args[0]
    lines = int(args[1]) if len(args) > 1 else 10
    
    try:
        path = Path(file_path)
        if not path.is_absolute():
            path = Path(context.cwd) / path
        
        if not path.exists():
            return f"File not found: {file_path}"
        
        with open(path, 'r', encoding='utf-8', errors='replace') as f:
            content = ''.join(f.readline() for _ in range(lines))
        
        ext = path.suffix.lstrip('.')
        return f"```{ext}\n{content}\n```"
    
    except Exception as e:
        return f"Error: {e}"


register_command(CommandHandler(
    name="head",
    description="Show first lines of file",
    handler=head_command
))
