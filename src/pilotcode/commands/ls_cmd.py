"""Ls command implementation."""

from pathlib import Path
from datetime import datetime
from .base import CommandHandler, register_command, CommandContext


async def ls_command(args: list[str], context: CommandContext) -> str:
    """Handle /ls command."""
    path = args[0] if args else "."

    try:
        target = Path(path)
        if not target.is_absolute():
            target = Path(context.cwd) / target

        target = target.resolve()

        if not target.exists():
            return f"Path not found: {path}"

        if target.is_file():
            stat = target.stat()
            return f"{target.name}\n  Size: {stat.st_size} bytes\n  Modified: {datetime.fromtimestamp(stat.st_mtime)}"

        # List directory
        entries = []
        for item in target.iterdir():
            stat = item.stat()
            size = stat.st_size if item.is_file() else "<dir>"
            mtime = datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M")

            prefix = "📁" if item.is_dir() else "📄"
            entries.append((item.name, size, mtime, prefix))

        # Sort: directories first, then files
        entries.sort(key=lambda x: (not x[3] == "📁", x[0].lower()))

        lines = [f"Contents of {target}:", ""]

        for name, size, mtime, prefix in entries:
            size_str = f"{size:>10}" if isinstance(size, int) else f"{size:>10}"
            lines.append(f"{prefix} {name:30} {size_str}  {mtime}")

        return "\n".join(lines)

    except Exception as e:
        return f"Error: {e}"


register_command(
    CommandHandler(
        name="ls",
        description="List directory contents",
        handler=ls_command,
        aliases=["dir", "list"],
    )
)
