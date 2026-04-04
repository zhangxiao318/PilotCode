"""Cp command implementation."""

import shutil
from pathlib import Path
from .base import CommandHandler, register_command, CommandContext


async def cp_command(args: list[str], context: CommandContext) -> str:
    """Handle /cp command."""
    if len(args) < 2:
        return "Usage: /cp <source> <destination>"
    
    source = args[0]
    dest = args[1]
    
    try:
        src_path = Path(source)
        if not src_path.is_absolute():
            src_path = Path(context.cwd) / src_path
        
        dst_path = Path(dest)
        if not dst_path.is_absolute():
            dst_path = Path(context.cwd) / dst_path
        
        if not src_path.exists():
            return f"Source not found: {source}"
        
        if src_path.is_dir():
            shutil.copytree(src_path, dst_path, dirs_exist_ok=True)
            return f"Copied directory: {source} -> {dest}"
        else:
            shutil.copy2(src_path, dst_path)
            return f"Copied: {source} -> {dest}"
    
    except Exception as e:
        return f"Error: {e}"


register_command(CommandHandler(
    name="cp",
    description="Copy file or directory",
    handler=cp_command,
    aliases=["copy"]
))
