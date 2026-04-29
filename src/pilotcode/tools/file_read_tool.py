"""File read tool for reading file contents."""

import os
import asyncio
from pathlib import Path
from typing import Any
from pydantic import BaseModel, Field

from .base import ToolResult, ToolUseContext, build_tool, resolve_cwd
from .registry import register_tool


class FileReadInput(BaseModel):
    """Input for FileRead tool."""

    file_path: str = Field(description="Path to the file to read")
    offset: int | None = Field(
        default=None, description="Line offset to start reading from (1-indexed)"
    )
    limit: int | None = Field(default=None, description="Maximum number of lines to read")


class FileReadOutput(BaseModel):
    """Output from FileRead tool."""

    content: str
    file_path: str
    total_lines: int | None = None
    lines_read: int | None = None
    truncated: bool = False
    encoding: str | None = None


async def read_file_content(
    file_path: str, offset: int | None = None, limit: int | None = None
) -> FileReadOutput:
    """Read file content with optional offset and limit."""
    path = Path(file_path).expanduser().resolve()

    if not path.exists():
        return FileReadOutput(content="", file_path=str(path), error=f"File not found: {file_path}")

    if not path.is_file():
        return FileReadOutput(
            content="", file_path=str(path), error=f"Path is not a file: {file_path}"
        )

    try:
        # Read file content with encoding fallback:
        # 1. UTF-8 (default)
        # 2. System default (cp936/gbk on Chinese Windows)
        # 3. latin-1 as last resort (never fails, preserves all bytes)
        def _read_with_fallback(p: Path) -> tuple[str, str]:
            for enc in ("utf-8", sys.getdefaultencoding(), "cp936", "gbk", "gb18030", "latin-1"):
                try:
                    return p.read_text(encoding=enc), enc
                except UnicodeDecodeError:
                    continue
            # Should never reach here because latin-1 always succeeds
            return p.read_text(encoding="utf-8", errors="replace"), "utf-8"

        import sys
        content, detected_encoding = await asyncio.to_thread(_read_with_fallback, path)

        # Split into lines for offset/limit handling
        lines = content.split("\n")
        total_lines = len(lines)

        # Apply offset (1-indexed)
        if offset is not None and offset > 0:
            start_idx = offset - 1
            lines = lines[start_idx:]

        # Apply limit
        truncated = False
        if limit is not None and limit > 0:
            if len(lines) > limit:
                lines = lines[:limit]
                truncated = True

        result_content = "\n".join(lines)

        # Hard safety cap on total characters (independent of line limit)
        MAX_READ_CHARS = 100_000
        if len(result_content) > MAX_READ_CHARS:
            result_content = result_content[:MAX_READ_CHARS]
            truncated = True

        return FileReadOutput(
            content=result_content,
            file_path=str(path),
            total_lines=total_lines,
            lines_read=len(lines),
            truncated=truncated,
            encoding=detected_encoding,
        )
    except Exception as e:
        return FileReadOutput(content="", file_path=str(path), error=str(e))


async def file_read_call(
    input_data: FileReadInput,
    context: ToolUseContext,
    can_use_tool: Any,
    parent_message: Any,
    on_progress: Any,
) -> ToolResult[FileReadOutput]:
    """Execute file read."""
    # Resolve path
    file_path = input_data.file_path
    if not os.path.isabs(file_path):
        cwd = resolve_cwd(context)
        file_path = os.path.join(cwd, file_path)

    # Read file
    result = await read_file_content(file_path, offset=input_data.offset, limit=input_data.limit)

    # Update read file state for conflict detection and encoding tracking
    if context.read_file_state is not None:
        import time

        # Use normalized absolute path as key to ensure consistent matching with FileEdit
        normalized_key = os.path.normcase(os.path.normpath(os.path.abspath(file_path)))
        context.read_file_state[normalized_key] = {
            "timestamp": time.time(),
            "mtime": os.path.getmtime(file_path) if os.path.exists(file_path) else None,
            "encoding": result.encoding,
        }

    return ToolResult(data=result)


async def file_read_description(input_data: FileReadInput, options: dict[str, Any]) -> str:
    """Get description for file read."""
    return f"Reading {Path(input_data.file_path).name}"


def render_file_read_use(input_data: FileReadInput, options: dict[str, Any]) -> str:
    """Render file read tool use message."""
    path = Path(input_data.file_path)
    if input_data.offset or input_data.limit:
        range_str = ""
        if input_data.offset:
            range_str += f" from line {input_data.offset}"
        if input_data.limit:
            range_str += f" ({input_data.limit} lines)"
        return f"📄 Reading {path.name}{range_str}"
    return f"📄 Reading {path.name}"


# Create the FileRead tool
FileReadTool = build_tool(
    name="FileRead",
    description=file_read_description,
    input_schema=FileReadInput,
    output_schema=FileReadOutput,
    call=file_read_call,
    aliases=["read", "cat", "view"],
    search_hint="Read file contents",
    max_result_size_chars=float("inf"),  # Never persist to disk
    is_read_only=lambda _: True,
    is_concurrency_safe=lambda _: True,
    render_tool_use_message=render_file_read_use,
)

# Register the tool
register_tool(FileReadTool)
