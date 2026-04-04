"""Wc command implementation."""

from pathlib import Path
from .base import CommandHandler, register_command, CommandContext


async def wc_command(args: list[str], context: CommandContext) -> str:
    """Handle /wc command."""
    if not args:
        return "Usage: /wc <file>"
    
    file_path = args[0]
    
    try:
        path = Path(file_path)
        if not path.is_absolute():
            path = Path(context.cwd) / path
        
        if not path.exists():
            return f"File not found: {file_path}"
        
        with open(path, 'r', encoding='utf-8', errors='replace') as f:
            content = f.read()
        
        lines = content.count('\n')
        words = len(content.split())
        chars = len(content)
        
        return f"{path.name}:\n  Lines: {lines}\n  Words: {words}\n  Characters: {chars}"
    
    except Exception as e:
        return f"Error: {e}"


register_command(CommandHandler(
    name="wc",
    description="Count lines, words, characters",
    handler=wc_command
))
