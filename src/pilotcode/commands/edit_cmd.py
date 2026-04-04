"""Edit command implementation."""

from pathlib import Path
from .base import CommandHandler, register_command, CommandContext


async def edit_command(args: list[str], context: CommandContext) -> str:
    """Handle /edit command."""
    if len(args) < 3:
        return """Usage: /edit <file> <old_text> <new_text>

Example:
  /edit main.py "print('hello')" "print('world')"
"""
    
    file_path = args[0]
    old_text = args[1]
    new_text = args[2]
    
    try:
        path = Path(file_path)
        if not path.is_absolute():
            path = Path(context.cwd) / path
        
        if not path.exists():
            return f"File not found: {file_path}"
        
        with open(path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        if old_text not in content:
            return f"Text not found in file: {old_text[:50]}..."
        
        new_content = content.replace(old_text, new_text, 1)
        
        with open(path, 'w', encoding='utf-8') as f:
            f.write(new_content)
        
        return f"Edited: {file_path}\nReplaced: {old_text[:50]}...\nWith: {new_text[:50]}..."
    
    except Exception as e:
        return f"Error: {e}"


register_command(CommandHandler(
    name="edit",
    description="Edit file (simple replace)",
    handler=edit_command
))
