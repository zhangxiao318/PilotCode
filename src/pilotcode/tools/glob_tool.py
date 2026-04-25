"""Glob tool for finding files matching patterns."""

import asyncio
import os
import fnmatch
from pathlib import Path
from typing import Any
from pydantic import BaseModel, Field

from .base import ToolResult, ToolUseContext, build_tool
from .registry import register_tool


class GlobInput(BaseModel):
    """Input for Glob tool."""

    pattern: str = Field(description="Glob pattern to match files (e.g., '*.py', 'src/**/*.ts')")
    path: str | None = Field(default=None, description="Directory to search in (default: cwd)")
    limit: int = Field(default=100, description="Maximum number of files to return")
    offset: int = Field(default=0, description="Number of results to skip")


class GlobOutput(BaseModel):
    """Output from Glob tool."""

    filenames: list[str]
    total_count: int
    truncated: bool


def matches_glob_pattern(file_path: Path, pattern: str) -> bool:
    """Check if file path matches glob pattern."""
    # Handle **/ prefix for recursive matching
    if pattern.startswith("**/") or "/**/" in pattern:
        parts = pattern.split("**/")
        if len(parts) == 2:
            suffix = parts[1]
            return fnmatch.fnmatch(file_path.name, suffix)

    return fnmatch.fnmatch(file_path.name, pattern) or fnmatch.fnmatch(str(file_path), pattern)


def _glob_sync(pattern: str, search_path: str, limit: int = 100, offset: int = 0) -> GlobOutput:
    """Synchronous glob implementation (runs in thread pool)."""
    path = Path(search_path).expanduser().resolve()

    if not path.exists():
        return GlobOutput(
            filenames=[], total_count=0, truncated=False, error=f"Path not found: {search_path}"
        )

    if not path.is_dir():
        return GlobOutput(
            filenames=[],
            total_count=0,
            truncated=False,
            error=f"Path is not a directory: {search_path}",
        )

    try:
        matches = []

        # Directories to skip during recursive search
        SKIP_DIRS = {
            "node_modules",
            "__pycache__",
            ".git",
            ".venv",
            "venv",
            "dist",
            "build",
            ".tox",
            ".pytest_cache",
            ".mypy_cache",
            "site-packages",
            "egg-info",
            ".eggs",
            "target",
        }

        # Handle recursive patterns
        if "**" in pattern:
            # Recursive search
            suffix = pattern.replace("**/", "").replace("**\\", "")
            for root, dirs, files in os.walk(path):
                # Skip hidden directories and common ignore patterns
                dirs[:] = [d for d in dirs if not d.startswith(".") and d not in SKIP_DIRS]

                for file in files:
                    if file.startswith("."):
                        continue
                    file_path = Path(root) / file
                    try:
                        rel_path = file_path.relative_to(path)
                    except ValueError:
                        continue
                    if fnmatch.fnmatch(str(rel_path), pattern) or fnmatch.fnmatch(file, suffix):
                        matches.append(str(rel_path))
        else:
            # Non-recursive search
            for item in path.iterdir():
                if item.is_file():
                    if fnmatch.fnmatch(item.name, pattern):
                        matches.append(item.name)

        # Sort matches
        matches.sort()

        total_count = len(matches)

        # Apply offset and limit
        if offset > 0:
            matches = matches[offset:]

        truncated = len(matches) > limit
        if limit > 0:
            matches = matches[:limit]

        return GlobOutput(filenames=matches, total_count=total_count, truncated=truncated)
    except Exception as e:
        return GlobOutput(filenames=[], total_count=0, truncated=False, error=str(e))


async def glob_files(
    pattern: str, search_path: str, limit: int = 100, offset: int = 0
) -> GlobOutput:
    """Find files matching glob pattern (async wrapper around sync implementation)."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _glob_sync, pattern, search_path, limit, offset)


async def glob_call(
    input_data: GlobInput,
    context: ToolUseContext,
    can_use_tool: Any,
    parent_message: Any,
    on_progress: Any,
) -> ToolResult[GlobOutput]:
    """Execute glob search."""
    # Determine search path
    search_path = input_data.path

    # Get base path (cwd or specified path)
    if search_path is None:
        if context.get_app_state:
            app_state = context.get_app_state()
            base_path = getattr(app_state, "cwd", os.getcwd())
        else:
            base_path = os.getcwd()
    elif not os.path.isabs(search_path):
        if context.get_app_state:
            app_state = context.get_app_state()
            cwd = getattr(app_state, "cwd", os.getcwd())
            base_path = os.path.join(cwd, search_path)
        else:
            base_path = os.path.join(os.getcwd(), search_path)
    else:
        base_path = search_path

    # Handle pattern that may contain directory components
    # e.g., "blog_app/*.py" should search in "blog_app/" with pattern "*.py"
    pattern = input_data.pattern
    if "/" in pattern and "**" not in pattern:
        # Split pattern into directory and file pattern
        parts = pattern.rsplit("/", 1)
        dir_part = parts[0]
        file_pattern = parts[1] if len(parts) > 1 else "*"

        # Update search path to include directory part
        search_path = os.path.join(base_path, dir_part)
        pattern = file_pattern
    else:
        search_path = base_path

    # Search
    result = await glob_files(
        pattern, search_path, limit=input_data.limit, offset=input_data.offset
    )

    return ToolResult(data=result)


async def glob_description(input_data: GlobInput, options: dict[str, Any]) -> str:
    """Get description for glob."""
    return f"Finding files matching '{input_data.pattern}'"


def render_glob_use(input_data: GlobInput, options: dict[str, Any]) -> str:
    """Render glob tool use message."""
    path = input_data.path or "."
    return f"🔍 Glob: {input_data.pattern} in {path}"


# Create the Glob tool
GlobTool = build_tool(
    name="Glob",
    description=glob_description,
    input_schema=GlobInput,
    output_schema=GlobOutput,
    call=glob_call,
    aliases=["glob", "find"],
    search_hint="Find files matching glob patterns",
    max_result_size_chars=50000,
    is_read_only=lambda _: True,
    is_concurrency_safe=lambda _: True,
    render_tool_use_message=render_glob_use,
)

# Register the tool
register_tool(GlobTool)
