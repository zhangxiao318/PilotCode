"""References command implementation."""

import os
import subprocess
from pathlib import Path
from .base import CommandHandler, register_command, CommandContext


async def references_command(args: list[str], context: CommandContext) -> str:
    """Handle /references command."""
    if not args:
        return "Usage: /references <symbol> [path]"

    symbol = args[0]
    path = args[1] if len(args) > 1 else "."

    try:
        # Try grep first (works on Linux with native grep, or Windows with WSL/Git Bash)
        result = subprocess.run(
            ["grep", "-rn", symbol, path], capture_output=True, text=True, cwd=context.cwd
        )

        if result.returncode == 0 and result.stdout.strip():
            lines = result.stdout.strip().split("\n")
            output = f"References to '{symbol}':\n"
            for line in lines[:30]:  # Limit output
                output += f"  {line}\n"
            return output
    except Exception:
        pass  # Fall through to Python implementation

    # Fallback: Python implementation (cross-platform)
    try:
        search_path = Path(context.cwd) / path
        search_path = search_path.resolve()

        if not search_path.exists():
            return f"Path not found: {path}"

        matches = []

        if search_path.is_file():
            files = [search_path]
        else:
            # Collect files to search
            files = []
            for root, dirs, filenames in os.walk(search_path):
                # Skip hidden and common ignore directories
                dirs[:] = [
                    d
                    for d in dirs
                    if not d.startswith(".")
                    and d not in ["node_modules", "__pycache__", "venv", ".git"]
                ]

                for filename in filenames:
                    if filename.startswith(".") or not any(
                        filename.endswith(ext)
                        for ext in [
                            ".py",
                            ".js",
                            ".ts",
                            ".java",
                            ".cpp",
                            ".c",
                            ".h",
                            ".hpp",
                            ".go",
                            ".rs",
                            ".rb",
                            ".php",
                        ]
                    ):
                        continue
                    files.append(Path(root) / filename)

        # Search in files
        for file_path in files:
            try:
                content = file_path.read_text(encoding="utf-8", errors="replace")
                lines = content.split("\n")

                for line_num, line in enumerate(lines, 1):
                    if symbol in line:
                        rel_path = (
                            file_path.relative_to(search_path)
                            if search_path in file_path.parents
                            else file_path.name
                        )
                        matches.append(f"{rel_path}:{line_num}:{line.strip()}")

                if len(matches) >= 100:  # Limit matches
                    break
            except Exception:
                continue

        if matches:
            output = f"References to '{symbol}':\n"
            for match in matches[:30]:
                output += f"  {match}\n"
            if len(matches) > 30:
                output += f"  ... and {len(matches) - 30} more\n"
            return output
        else:
            return f"No references found for '{symbol}'"

    except Exception as e:
        return f"Error: {e}"


register_command(
    CommandHandler(
        name="references", description="Find references to symbol", handler=references_command
    )
)
