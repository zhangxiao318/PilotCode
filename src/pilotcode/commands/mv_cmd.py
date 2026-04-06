"""Mv command implementation."""

from pathlib import Path
from .base import CommandHandler, register_command, CommandContext


async def mv_command(args: list[str], context: CommandContext) -> str:
    """Handle /mv command."""
    if len(args) < 2:
        return "Usage: /mv <source> <destination>"

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

        src_path.rename(dst_path)
        return f"Moved: {source} -> {dest}"

    except Exception as e:
        return f"Error: {e}"


register_command(
    CommandHandler(
        name="mv",
        description="Move/rename file or directory",
        handler=mv_command,
        aliases=["move", "rename_file"],
    )
)
