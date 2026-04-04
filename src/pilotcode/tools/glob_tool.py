"""Glob tool for finding files matching patterns."""

import os
import fnmatch
from pathlib import Path
from typing import Any, AsyncIterator
from pydantic import BaseModel, Field

from .base import Tool, ToolResult, ToolUseContext, build_tool
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
    if pattern.startswith('**/') or '/**/' in pattern:
        parts = pattern.split('**/')
        if len(parts) == 2:
            suffix = parts[1]
            return fnmatch.fnmatch(file_path.name, suffix)
    
    return fnmatch.fnmatch(file_path.name, pattern) or fnmatch.fnmatch(str(file_path), pattern)


async def glob_files(
    pattern: str,
    search_path: str,
    limit: int = 100,
    offset: int = 0
) -> GlobOutput:
    """Find files matching glob pattern."""
    path = Path(search_path).expanduser().resolve()
    
    if not path.exists():
        return GlobOutput(
            filenames=[],
            total_count=0,
            truncated=False,
            error=f"Path not found: {search_path}"
        )
    
    if not path.is_dir():
        return GlobOutput(
            filenames=[],
            total_count=0,
            truncated=False,
            error=f"Path is not a directory: {search_path}"
        )
    
    try:
        matches = []
        
        # Handle recursive patterns
        if '**' in pattern:
            # Recursive search
            suffix = pattern.replace('**/', '').replace('**\\', '')
            for root, dirs, files in os.walk(path):
                # Skip hidden directories and common ignore patterns
                dirs[:] = [d for d in dirs if not d.startswith('.') and d not in ['node_modules', '__pycache__', '.git']]
                
                for file in files:
                    if file.startswith('.'):
                        continue
                    file_path = Path(root) / file
                    rel_path = file_path.relative_to(path)
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
        
        return GlobOutput(
            filenames=matches,
            total_count=total_count,
            truncated=truncated
        )
    except Exception as e:
        return GlobOutput(
            filenames=[],
            total_count=0,
            truncated=False,
            error=str(e)
        )


async def glob_call(
    input_data: GlobInput,
    context: ToolUseContext,
    can_use_tool: Any,
    parent_message: Any,
    on_progress: Any
) -> ToolResult[GlobOutput]:
    """Execute glob search."""
    # Determine search path
    search_path = input_data.path
    if search_path is None:
        if context.get_app_state:
            app_state = context.get_app_state()
            search_path = getattr(app_state, 'cwd', os.getcwd())
        else:
            search_path = os.getcwd()
    elif not os.path.isabs(search_path):
        if context.get_app_state:
            app_state = context.get_app_state()
            cwd = getattr(app_state, 'cwd', os.getcwd())
            search_path = os.path.join(cwd, search_path)
    
    # Search
    result = await glob_files(
        input_data.pattern,
        search_path,
        limit=input_data.limit,
        offset=input_data.offset
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
