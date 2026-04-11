"""Symbols command implementation."""

import re
import subprocess
from pathlib import Path
from .base import CommandHandler, register_command, CommandContext


async def symbols_command(args: list[str], context: CommandContext) -> str:
    """Handle /symbols command."""
    if not args:
        return "Usage: /symbols <file>"

    file_path = args[0]

    # Try ctags first
    try:
        result = subprocess.run(
            ["ctags", "-x", "--python-kinds=-i", file_path],
            capture_output=True,
            text=True,
            cwd=context.cwd,
        )

        if result.returncode == 0:
            lines = result.stdout.strip().split("\n")
            if lines:
                output = f"Symbols in {file_path}:\n"
                for line in lines[:50]:  # Limit output
                    parts = line.split(None, 2)
                    if len(parts) >= 3:
                        name, kind, _location = parts[0], parts[1], parts[2]
                        output += f"  {kind}: {name}\n"
                return output
            else:
                return f"No symbols found in {file_path}"
    except Exception:
        pass  # Fall through to fallback

    # Fallback: Python implementation using regex (cross-platform)
    try:
        path = Path(file_path)
        if not path.is_absolute():
            path = Path(context.cwd) / path

        if not path.exists():
            return f"File not found: {file_path}"

        content = path.read_text(encoding="utf-8", errors="replace")
        lines = content.split("\n")

        symbols = []
        # Pattern for Python def/class
        pattern = re.compile(r"^[ \t]*(def|class)[ \t]+(\w+)")

        for line_num, line in enumerate(lines, 1):
            match = pattern.match(line)
            if match:
                kind = match.group(1)  # def or class
                name = match.group(2)  # function/class name
                symbols.append((kind, name, line_num))

        if symbols:
            output = f"Symbols in {file_path}:\n"
            for kind, name, line_num in symbols[:50]:
                output += f"  {kind}: {name} (line {line_num})\n"
            return output
        else:
            return f"No symbols found in {file_path}"

    except Exception as e:
        return f"Error: Could not extract symbols from {file_path}: {e}"


register_command(
    CommandHandler(name="symbols", description="Show symbols in file", handler=symbols_command)
)
