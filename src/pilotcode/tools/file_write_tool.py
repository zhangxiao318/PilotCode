"""File write tool for writing file contents."""

import os
import sys
import tempfile
import shutil
import time
import hashlib
from pathlib import Path
from typing import Any
from pydantic import BaseModel, Field

from .base import ToolResult, ToolUseContext, build_tool
from .registry import register_tool


def _is_path_within_workspace(file_path: str, cwd: str | None = None) -> tuple[bool, str]:
    """Check if a file path is within the workspace directory.

    Returns:
        (is_valid, error_message): True if path is safe, False with error message if outside workspace
    """
    try:
        # Reject obvious path traversal
        if ".." in file_path:
            return False, f"Access denied: Path traversal detected in '{file_path}'."

        raw_path = Path(file_path).expanduser()

        # On non-Windows, a path like C:/Windows/... is NOT absolute but looks
        # like a Windows absolute path.  Resolve() would prepend cwd, making it
        # appear inside the workspace.  Reject it outright on non-Windows only.
        if sys.platform != "win32" and ":" in file_path and not file_path.startswith("~/"):
            return False, f"Access denied: Invalid absolute path '{file_path}'."

        # Resolve to absolute path
        path = raw_path.resolve()

        # Get workspace directory
        workspace = Path(cwd or os.getcwd()).expanduser().resolve()

        # Check if path is within workspace
        try:
            path.relative_to(workspace)
            return True, ""
        except ValueError:
            return (
                False,
                f"Access denied: Path '{path}' is outside workspace '{workspace}'. Only files within the workspace can be written.",
            )
    except Exception as e:
        return False, f"Path validation error: {e}"


class FileWriteInput(BaseModel):
    """Input for FileWrite tool."""

    file_path: str = Field(description="Path to the file to write")
    content: str = Field(description="Content to write to the file")
    append: bool = Field(
        default=False,
        description="Append to existing file. Use this to merge/combine files by appending content to an existing file.",
    )


class FileWriteOutput(BaseModel):
    """Output from FileWrite tool."""

    file_path: str
    bytes_written: int
    created: bool = False
    previous_size: int | None = None
    error: str | None = None


async def write_file_atomic(
    file_path: str, content: str, append: bool = False, cwd: str | None = None
) -> FileWriteOutput:
    """Write file atomically using temp file and rename."""
    # Security check: validate path is within workspace
    is_valid, error_msg = _is_path_within_workspace(file_path, cwd)
    if not is_valid:
        return FileWriteOutput(file_path=file_path, bytes_written=0, created=False, error=error_msg)

    path = Path(file_path).expanduser().resolve()

    # Ensure parent directory exists (but check it's within workspace)
    parent = path.parent
    try:
        parent.relative_to(Path(cwd or os.getcwd()).expanduser().resolve())
        parent.mkdir(parents=True, exist_ok=True)
    except ValueError:
        return FileWriteOutput(
            file_path=str(path),
            bytes_written=0,
            created=False,
            error=f"Access denied: Parent directory '{parent}' is outside workspace.",
        )

    created = not path.exists()
    previous_size = path.stat().st_size if path.exists() else None

    try:
        if append and path.exists():
            # Append mode: read existing content, append, then write
            existing = path.read_text(encoding="utf-8", errors="replace")
            content = existing + content

        # Write to temp file then rename (atomic operation)
        temp_fd, temp_path = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
        try:
            os.write(temp_fd, content.encode("utf-8"))
            os.close(temp_fd)

            # Atomic rename
            shutil.move(temp_path, path)
        except:
            # Clean up temp file on error
            try:
                os.close(temp_fd)
                os.unlink(temp_path)
            except Exception:
                pass
            raise

        return FileWriteOutput(
            file_path=str(path),
            bytes_written=len(content.encode("utf-8")),
            created=created,
            previous_size=previous_size,
        )
    except Exception as e:
        return FileWriteOutput(
            file_path=str(path),
            bytes_written=0,
            created=created,
            previous_size=previous_size,
            error=str(e),
        )


async def file_write_validate(
    input_data: FileWriteInput, context: ToolUseContext
) -> tuple[bool, str | None]:
    """Validate file write input."""
    file_path = input_data.file_path

    if not os.path.isabs(file_path) and context.get_app_state:
        app_state = context.get_app_state()
        cwd = getattr(app_state, "cwd", os.getcwd())
        file_path = os.path.join(cwd, file_path)

    # Normalize key to match FileRead (uses normcase + normpath + abspath)
    normalized_key = os.path.normcase(os.path.normpath(os.path.abspath(file_path)))

    # Check if file has been read (conflict detection)
    if context.read_file_state and normalized_key in context.read_file_state:
        read_info = context.read_file_state[normalized_key]
        read_timestamp = read_info.get("timestamp", 0)

        # Check if file has been modified since read
        if os.path.exists(file_path):
            mtime = os.path.getmtime(file_path)
            if mtime > read_timestamp:
                return (
                    False,
                    f"File has been modified since it was read (mtime: {mtime} > read_time: {read_timestamp})",
                )
    else:
        # File hasn't been read before - warn but allow if file doesn't exist
        if os.path.exists(file_path):
            return False, "File must be read before writing (to enable conflict detection)"

    return True, None


async def file_write_call(
    input_data: FileWriteInput,
    context: ToolUseContext,
    can_use_tool: Any,
    parent_message: Any,
    on_progress: Any,
) -> ToolResult[FileWriteOutput]:
    """Execute file write."""
    # Handle field name mapping - LLM might use 'path' instead of 'file_path'
    file_path = getattr(input_data, "file_path", None)
    if not file_path:
        # Try 'path' as fallback
        file_path = getattr(input_data, "path", None)

    if not file_path:
        return ToolResult(
            data=FileWriteOutput(
                file_path="", bytes_written=0, error="Missing required field: file_path (or path)"
            )
        )

    # Get workspace directory for security check
    cwd = os.getcwd()
    if context.get_app_state:
        app_state = context.get_app_state()
        cwd = getattr(app_state, "cwd", os.getcwd())
    if not os.path.isabs(file_path):
        file_path = os.path.join(cwd, file_path)

    # Write file with workspace restriction
    result = await write_file_atomic(
        file_path, input_data.content, append=input_data.append, cwd=cwd
    )

    # Add file to read_file_state so it can be edited immediately
    # This allows the AI to edit files it just created
    if not result.error and context.read_file_state is not None:
        context.read_file_state[file_path] = {
            "timestamp": time.time(),
            "hash": hashlib.md5(input_data.content.encode()).hexdigest()[:8],
        }

    if result.error:
        return ToolResult(data=result, error=result.error)
    return ToolResult(data=result)


async def file_write_description(input_data: FileWriteInput, options: dict[str, Any]) -> str:
    """Get description for file write."""
    path = Path(input_data.file_path)
    action = "Appending to" if input_data.append else "Writing"
    return f"{action} {path.name}"


def render_file_write_use(input_data: FileWriteInput, options: dict[str, Any]) -> str:
    """Render file write tool use message."""
    path = Path(input_data.file_path)
    action = "➕ Appending to" if input_data.append else "✏️  Writing"
    return f"{action} {path.name}"


# Create the FileWrite tool
FileWriteTool = build_tool(
    name="FileWrite",
    description=file_write_description,
    input_schema=FileWriteInput,
    output_schema=FileWriteOutput,
    call=file_write_call,
    validate_input=file_write_validate,
    aliases=["write", "create"],
    search_hint="Write content to a file",
    is_read_only=lambda _: False,
    is_destructive=lambda _: True,
    is_concurrency_safe=lambda _: False,
    render_tool_use_message=render_file_write_use,
)

# Register the tool
register_tool(FileWriteTool)
