"""Find command implementation."""

import os
import fnmatch
from pathlib import Path
from .base import CommandHandler, register_command, CommandContext


async def find_command(args: list[str], context: CommandContext) -> str:
    """Handle /find command."""
    if not args:
        return "Usage: /find <pattern> [path]"

    pattern = args[0]
    search_path = args[1] if len(args) > 1 else "."

    path = Path(search_path).expanduser().resolve()

    if not path.exists():
        return f"Path not found: {search_path}"

    matches = []

    try:
        for root, dirs, files in os.walk(path):
            # Skip hidden and common ignore directories
            dirs[:] = [
                d
                for d in dirs
                if not d.startswith(".")
                and d not in ["node_modules", "__pycache__", "venv", ".git"]
            ]

            for filename in files:
                if fnmatch.fnmatch(filename.lower(), pattern.lower()):
                    full_path = Path(root) / filename
                    rel_path = full_path.relative_to(path)
                    matches.append(str(rel_path))

            # Limit results
            if len(matches) > 100:
                matches = matches[:100]
                matches.append("... (more results truncated)")
                break

    except Exception as e:
        return f"Error: {e}"

    if not matches:
        return f"No files matching '{pattern}' found"

    lines = [f"Found {len(matches)} files matching '{pattern}':", ""]
    for m in matches[:50]:
        lines.append(f"  {m}")

    if len(matches) > 50:
        lines.append(f"\n... and {len(matches) - 50} more")

    return "\n".join(lines)


register_command(
    CommandHandler(
        name="find", description="Find files by pattern", handler=find_command, aliases=["search"]
    )
)
