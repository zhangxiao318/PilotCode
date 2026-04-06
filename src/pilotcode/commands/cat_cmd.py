"""Cat command implementation."""

from pathlib import Path
from .base import CommandHandler, register_command, CommandContext


async def cat_command(args: list[str], context: CommandContext) -> str:
    """Handle /cat command."""
    if not args:
        return "Usage: /cat <file_path> [lines]"

    file_path = args[0]
    max_lines = int(args[1]) if len(args) > 1 else None

    try:
        path = Path(file_path)
        if not path.is_absolute():
            path = Path(context.cwd) / path

        if not path.exists():
            return f"File not found: {file_path}"

        if not path.is_file():
            return f"Not a file: {file_path}"

        with open(path, "r", encoding="utf-8", errors="replace") as f:
            if max_lines:
                lines = []
                for i, line in enumerate(f):
                    if i >= max_lines:
                        break
                    lines.append(line)
                content = "".join(lines)
                if next(f, None):
                    content += "\n... (truncated)"
            else:
                content = f.read()

        # Limit output size
        if len(content) > 5000:
            content = content[:5000] + "\n... (truncated)"

        # Format as code block
        ext = path.suffix.lstrip(".")
        return f"```{ext}\n{content}\n```"

    except Exception as e:
        return f"Error reading file: {e}"


register_command(
    CommandHandler(name="cat", description="Display file contents", handler=cat_command)
)
