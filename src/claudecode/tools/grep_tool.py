"""Grep tool for searching text in files using ripgrep-like functionality."""

import os
import re
import subprocess
from pathlib import Path
from typing import Any, Literal
from enum import Enum
from pydantic import BaseModel, Field

from .base import Tool, ToolResult, ToolUseContext, build_tool
from .registry import register_tool


class OutputMode(str, Enum):
    """Output mode for grep results."""
    CONTENT = "content"
    FILES_WITH_MATCHES = "files_with_matches"
    COUNT_MATCHES = "count_matches"


class GrepInput(BaseModel):
    """Input for Grep tool."""
    pattern: str = Field(description="Regex pattern to search for")
    path: str = Field(default=".", description="Path to search in")
    glob: str | None = Field(default=None, description="Glob pattern to filter files")
    output_mode: OutputMode = Field(default=OutputMode.CONTENT, description="Output format")
    head_limit: int | None = Field(default=250, description="Max lines in content mode")
    offset: int = Field(default=0, description="Lines to skip")
    case_sensitive: bool = Field(default=True, description="Case sensitive search")
    multiline: bool = Field(default=False, description="Enable multiline matching")


class GrepMatch(BaseModel):
    """A single grep match."""
    file: str
    line_number: int
    content: str
    match_start: int
    match_end: int


class GrepOutput(BaseModel):
    """Output from Grep tool."""
    content: str | None = None
    filenames: list[str] | None = None
    num_matches: int
    truncated: bool = False


def should_ignore_path(path: Path) -> bool:
    """Check if path should be ignored."""
    name = path.name
    if name.startswith('.'):
        return True
    ignore_patterns = [
        'node_modules', '__pycache__', '.git', '.svn', '.hg',
        'venv', '.venv', 'env', 'dist', 'build', 'target',
        '*.min.js', '*.min.css', '*.bundle.js'
    ]
    for pattern in ignore_patterns:
        if pattern in str(path):
            return True
    return False


async def grep_files(
    pattern: str,
    search_path: str,
    glob_pattern: str | None = None,
    output_mode: OutputMode = OutputMode.CONTENT,
    head_limit: int | None = 250,
    offset: int = 0,
    case_sensitive: bool = True,
    multiline: bool = False
) -> GrepOutput:
    """Search for pattern in files."""
    path = Path(search_path).expanduser().resolve()
    
    if not path.exists():
        return GrepOutput(
            num_matches=0,
            content=None,
            filenames=None,
            error=f"Path not found: {search_path}"
        )
    
    try:
        matches = []
        files_with_matches = set()
        
        flags = 0 if case_sensitive else re.IGNORECASE
        if multiline:
            flags |= re.MULTILINE | re.DOTALL
        
        try:
            regex = re.compile(pattern, flags)
        except re.error as e:
            return GrepOutput(
                num_matches=0,
                content=None,
                filenames=None,
                error=f"Invalid regex pattern: {e}"
            )
        
        # Determine files to search
        if path.is_file():
            files = [path]
        else:
            files = []
            for root, dirs, filenames in os.walk(path):
                # Filter directories
                dirs[:] = [d for d in dirs if not should_ignore_path(Path(root) / d)]
                
                for filename in filenames:
                    if should_ignore_path(Path(filename)):
                        continue
                    
                    # Apply glob filter
                    if glob_pattern and not Path(filename).match(glob_pattern):
                        continue
                    
                    file_path = Path(root) / filename
                    files.append(file_path)
        
        # Search files
        for file_path in files:
            try:
                # Skip binary files
                if os.path.getsize(file_path) > 10 * 1024 * 1024:  # Skip files > 10MB
                    continue
                
                content = file_path.read_text(encoding='utf-8', errors='replace')
                lines = content.split('\n')
                
                rel_path = file_path.relative_to(path) if path in file_path.parents else file_path.name
                
                for line_num, line in enumerate(lines, 1):
                    for match in regex.finditer(line):
                        match_obj = GrepMatch(
                            file=str(rel_path),
                            line_number=line_num,
                            content=line,
                            match_start=match.start(),
                            match_end=match.end()
                        )
                        matches.append(match_obj)
                        files_with_matches.add(str(rel_path))
                        
                        if output_mode == OutputMode.FILES_WITH_MATCHES:
                            break
                    
                    if output_mode == OutputMode.FILES_WITH_MATCHES and str(rel_path) in files_with_matches:
                        break
            except Exception:
                continue
        
        # Format output
        if output_mode == OutputMode.FILES_WITH_MATCHES:
            filenames = sorted(files_with_matches)
            if offset > 0:
                filenames = filenames[offset:]
            return GrepOutput(
                num_matches=len(matches),
                filenames=filenames
            )
        
        elif output_mode == OutputMode.COUNT_MATCHES:
            return GrepOutput(
                num_matches=len(matches)
            )
        
        else:  # CONTENT mode
            # Apply offset
            if offset > 0:
                matches = matches[offset:]
            
            # Apply head limit
            truncated = False
            if head_limit is not None and len(matches) > head_limit:
                matches = matches[:head_limit]
                truncated = True
            
            # Format content
            lines = []
            for m in matches:
                lines.append(f"{m.file}:{m.line_number}:{m.content}")
            
            return GrepOutput(
                num_matches=len(matches),
                content='\n'.join(lines),
                truncated=truncated
            )
    
    except Exception as e:
        return GrepOutput(
            num_matches=0,
            content=None,
            filenames=None,
            error=str(e)
        )


async def grep_call(
    input_data: GrepInput,
    context: ToolUseContext,
    can_use_tool: Any,
    parent_message: Any,
    on_progress: Any
) -> ToolResult[GrepOutput]:
    """Execute grep search."""
    # Resolve path
    search_path = input_data.path
    if not os.path.isabs(search_path) and context.get_app_state:
        app_state = context.get_app_state()
        cwd = getattr(app_state, 'cwd', os.getcwd())
        search_path = os.path.join(cwd, search_path)
    
    # Search
    result = await grep_files(
        pattern=input_data.pattern,
        search_path=search_path,
        glob_pattern=input_data.glob,
        output_mode=input_data.output_mode,
        head_limit=input_data.head_limit,
        offset=input_data.offset,
        case_sensitive=input_data.case_sensitive,
        multiline=input_data.multiline
    )
    
    return ToolResult(data=result)


async def grep_description(input_data: GrepInput, options: dict[str, Any]) -> str:
    """Get description for grep."""
    return f"Searching for '{input_data.pattern}'"


def render_grep_use(input_data: GrepInput, options: dict[str, Any]) -> str:
    """Render grep tool use message."""
    path = input_data.path or "."
    return f"🔎 Grep: '{input_data.pattern}' in {path}"


# Create the Grep tool
GrepTool = build_tool(
    name="Grep",
    description=grep_description,
    input_schema=GrepInput,
    output_schema=GrepOutput,
    call=grep_call,
    aliases=["grep", "search", "rg"],
    search_hint="Search text using regex patterns",
    max_result_size_chars=50000,
    is_read_only=lambda _: True,
    is_concurrency_safe=lambda _: True,
    render_tool_use_message=render_grep_use,
)

# Register the tool
register_tool(GrepTool)
