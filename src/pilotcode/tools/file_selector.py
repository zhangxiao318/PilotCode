"""FileSelector Tool - Interactive file selection with filtering.

This tool provides:
1. Interactive file selection with patterns
2. Multiple file selection support
3. Filtering by extension, size, date
4. Preview of selected files
5. Git-aware file selection (respect .gitignore)

Features:
- Glob pattern matching
- Regular expression filtering
- Size and date filtering
- Preview file contents
- Multi-select support
"""

from __future__ import annotations

import fnmatch
import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Any
from enum import Enum

from pydantic import BaseModel, Field

from pilotcode.tools.base import ToolResult, ToolUseContext, build_tool
from pilotcode.tools.registry import register_tool


class SortBy(str, Enum):
    """Sort order for files."""

    NAME = "name"
    SIZE = "size"
    DATE = "date"
    TYPE = "type"


class SortOrder(str, Enum):
    """Sort direction."""

    ASC = "asc"
    DESC = "desc"


@dataclass
class FileInfo:
    """Information about a file."""

    path: str
    name: str
    size: int
    modified: datetime
    is_dir: bool
    extension: str = ""

    @property
    def size_human(self) -> str:
        """Get human-readable size."""
        size = self.size
        for unit in ["B", "KB", "MB", "GB"]:
            if size < 1024:
                return f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} TB"

    @property
    def modified_str(self) -> str:
        """Get formatted modification time."""
        return self.modified.strftime("%Y-%m-%d %H:%M")


class FileSelectorInput(BaseModel):
    """Input schema for FileSelector tool."""

    directory: str = Field(default=".", description="Directory to search in")
    pattern: str = Field(
        default="*", description="Glob pattern for file matching (e.g., '*.py', '*.md')"
    )
    regex: Optional[str] = Field(
        default=None, description="Regular expression for filtering file names"
    )
    extensions: Optional[list[str]] = Field(
        default=None, description="List of file extensions to include (e.g., ['py', 'js'])"
    )
    exclude_patterns: Optional[list[str]] = Field(
        default=None, description="Glob patterns to exclude"
    )
    min_size: Optional[int] = Field(default=None, description="Minimum file size in bytes")
    max_size: Optional[int] = Field(default=None, description="Maximum file size in bytes")
    modified_within: Optional[int] = Field(
        default=None, description="Only include files modified within N days"
    )
    sort_by: SortBy = Field(
        default=SortBy.NAME, description="Sort files by: name, size, date, type"
    )
    sort_order: SortOrder = Field(default=SortOrder.ASC, description="Sort order: asc or desc")
    recursive: bool = Field(default=True, description="Search recursively in subdirectories")
    include_hidden: bool = Field(
        default=False, description="Include hidden files (starting with .)"
    )
    respect_gitignore: bool = Field(default=True, description="Respect .gitignore patterns")
    max_results: int = Field(default=1000, description="Maximum number of results to return")
    preview: bool = Field(default=False, description="Include preview of file contents")
    preview_lines: int = Field(default=10, description="Number of lines to preview")


class FileSelectorOutput(BaseModel):
    """Output schema for FileSelector tool."""

    files: list[dict] = Field(description="List of selected files with metadata")
    total_count: int = Field(description="Total number of files found")
    total_size: int = Field(description="Total size of all files in bytes")
    directory: str = Field(description="Directory that was searched")


def load_gitignore(directory: Path) -> list[str]:
    """Load .gitignore patterns from directory."""
    gitignore_path = directory / ".gitignore"
    patterns = []

    if gitignore_path.exists():
        try:
            content = gitignore_path.read_text(encoding="utf-8", errors="ignore")
            for line in content.splitlines():
                line = line.strip()
                # Skip empty lines and comments
                if line and not line.startswith("#"):
                    patterns.append(line)
        except Exception:
            pass

    return patterns


def is_gitignored(path: Path, directory: Path, patterns: list[str]) -> bool:
    """Check if path matches gitignore patterns."""
    try:
        rel_path = path.relative_to(directory)
        rel_path_str = str(rel_path)

        for pattern in patterns:
            # Handle directory patterns
            if pattern.endswith("/"):
                if rel_path_str.startswith(pattern.rstrip("/")):
                    return True
            # Handle negation patterns (!)
            elif pattern.startswith("!"):
                neg_pattern = pattern[1:]
                if fnmatch.fnmatch(rel_path_str, neg_pattern):
                    return False
            # Handle regular patterns
            else:
                if fnmatch.fnmatch(rel_path_str, pattern):
                    return True
                # Also check basename for patterns like *.pyc
                if fnmatch.fnmatch(rel_path.name, pattern):
                    return True

        return False
    except Exception:
        return False


def collect_files(
    directory: Path, input_data: FileSelectorInput, gitignore_patterns: list[str]
) -> list[FileInfo]:
    """Collect files matching basic criteria."""
    files = []

    if input_data.recursive:
        iterator = directory.rglob("*")
    else:
        iterator = directory.iterdir()

    for path in iterator:
        try:
            # Skip hidden files unless included
            if not input_data.include_hidden and path.name.startswith("."):
                continue

            # Check gitignore
            if input_data.respect_gitignore and is_gitignored(path, directory, gitignore_patterns):
                continue

            # Get file info
            stat = path.stat()

            files.append(
                FileInfo(
                    path=str(path),
                    name=path.name,
                    size=stat.st_size if not path.is_dir() else 0,
                    modified=datetime.fromtimestamp(stat.st_mtime),
                    is_dir=path.is_dir(),
                    extension=path.suffix.lower(),
                )
            )

        except (OSError, PermissionError):
            # Skip files we can't access
            continue

    return files


def apply_filters(files: list[FileInfo], input_data: FileSelectorInput) -> list[FileInfo]:
    """Apply all filters to file list."""
    filtered = files

    # Pattern filter (glob)
    if input_data.pattern and input_data.pattern != "*":
        filtered = [f for f in filtered if fnmatch.fnmatch(f.name, input_data.pattern)]

    # Regex filter
    if input_data.regex:
        try:
            regex = re.compile(input_data.regex)
            filtered = [f for f in filtered if regex.search(f.name)]
        except re.error:
            # Invalid regex, skip this filter
            pass

    # Extension filter
    if input_data.extensions:
        exts = [
            ext.lower() if ext.startswith(".") else f".{ext.lower()}"
            for ext in input_data.extensions
        ]
        filtered = [f for f in filtered if f.extension in exts or f.is_dir]

    # Exclude patterns
    if input_data.exclude_patterns:
        for exclude in input_data.exclude_patterns:
            filtered = [f for f in filtered if not fnmatch.fnmatch(f.name, exclude)]

    # Size filters
    if input_data.min_size is not None:
        filtered = [f for f in filtered if f.size >= input_data.min_size or f.is_dir]

    if input_data.max_size is not None:
        filtered = [f for f in filtered if f.size <= input_data.max_size or f.is_dir]

    # Date filter
    if input_data.modified_within is not None:
        cutoff = datetime.now() - timedelta(days=input_data.modified_within)
        filtered = [f for f in filtered if f.modified >= cutoff or f.is_dir]

    return filtered


def sort_files(files: list[FileInfo], sort_by: SortBy, order: SortOrder) -> list[FileInfo]:
    """Sort files by specified criteria."""
    reverse = order == SortOrder.DESC

    if sort_by == SortBy.NAME:
        key_func = lambda f: f.name.lower()
    elif sort_by == SortBy.SIZE:
        key_func = lambda f: f.size
    elif sort_by == SortBy.DATE:
        key_func = lambda f: f.modified
    elif sort_by == SortBy.TYPE:
        key_func = lambda f: (not f.is_dir, f.extension.lower(), f.name.lower())
    else:
        key_func = lambda f: f.name.lower()

    # Always put directories first when sorting by name or type
    if sort_by in (SortBy.NAME, SortBy.TYPE):
        files.sort(key=lambda f: (not f.is_dir, key_func(f)), reverse=False)
        if reverse and sort_by != SortBy.TYPE:
            files.reverse()
    else:
        files.sort(key=key_func, reverse=reverse)

    return files


def is_binary(filepath: str, sample_size: int = 8192) -> bool:
    """Check if file is binary."""
    try:
        with open(filepath, "rb") as f:
            chunk = f.read(sample_size)
            if not chunk:
                return False

            # Check for null bytes
            if b"\x00" in chunk:
                return True

            # Check if mostly non-printable
            text_chars = bytearray({7, 8, 9, 10, 12, 13, 27} | set(range(0x20, 0x100)) - {0x7F})
            non_text = chunk.translate(None, text_chars)
            return len(non_text) / len(chunk) > 0.30
    except Exception:
        return True


def get_preview(filepath: str, lines: int) -> Optional[str]:
    """Get preview of file contents."""
    try:
        path = Path(filepath)

        # Skip binary files
        if is_binary(filepath):
            return "[Binary file]"

        # Read first N lines
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            preview_lines = []
            for i, line in enumerate(f):
                if i >= lines:
                    break
                preview_lines.append(line.rstrip())

            return "\n".join(preview_lines)
    except Exception:
        return None


async def file_selector_call(
    input_data: FileSelectorInput,
    context: ToolUseContext,
    can_use_tool: Any,
    parent_message: Any,
    on_progress: Any,
) -> ToolResult[FileSelectorOutput]:
    """Execute file selection."""
    try:
        # Resolve directory
        directory = Path(input_data.directory).resolve()

        if not directory.exists():
            output = FileSelectorOutput(
                files=[], total_count=0, total_size=0, directory=str(input_data.directory)
            )
            return ToolResult(data=output, error=f"Directory not found: {input_data.directory}")

        if not directory.is_dir():
            output = FileSelectorOutput(
                files=[], total_count=0, total_size=0, directory=str(input_data.directory)
            )
            return ToolResult(data=output, error=f"Path is not a directory: {input_data.directory}")

        # Load .gitignore if needed
        gitignore_patterns = []
        if input_data.respect_gitignore:
            gitignore_patterns = load_gitignore(directory)

        # Collect files
        files = collect_files(directory, input_data, gitignore_patterns)

        # Apply filters
        files = apply_filters(files, input_data)

        # Sort files
        files = sort_files(files, input_data.sort_by, input_data.sort_order)

        # Limit results
        total_count = len(files)
        files = files[: input_data.max_results]

        # Calculate total size
        total_size = sum(f.size for f in files)

        # Build output
        file_dicts = []
        for f in files:
            file_dict = {
                "path": f.path,
                "name": f.name,
                "size": f.size,
                "size_human": f.size_human,
                "modified": f.modified_str,
                "is_directory": f.is_dir,
                "extension": f.extension,
            }

            # Add preview if requested and it's a file
            if input_data.preview and not f.is_dir:
                preview_content = get_preview(f.path, input_data.preview_lines)
                if preview_content:
                    file_dict["preview"] = preview_content

            file_dicts.append(file_dict)

        output = FileSelectorOutput(
            files=file_dicts,
            total_count=total_count,
            total_size=total_size,
            directory=str(directory),
        )

        return ToolResult(data=output)

    except Exception as e:
        output = FileSelectorOutput(
            files=[], total_count=0, total_size=0, directory=input_data.directory
        )
        return ToolResult(data=output, error=f"File selection failed: {str(e)}")


async def file_selector_description(input_data: FileSelectorInput, options: dict[str, Any]) -> str:
    """Get description for file selector."""
    return f"Selecting files from {Path(input_data.directory).name or 'current directory'}"


def render_file_selector_use(input_data: FileSelectorInput, options: dict[str, Any]) -> str:
    """Render file selector tool use message."""
    dir_name = Path(input_data.directory).name or "current directory"
    pattern = input_data.pattern
    if pattern != "*":
        return f"📁 Selecting '{pattern}' files from {dir_name}"
    return f"📁 Selecting files from {dir_name}"


# Create the FileSelector tool
FileSelectorTool = build_tool(
    name="FileSelector",
    description=file_selector_description,
    input_schema=FileSelectorInput,
    output_schema=FileSelectorOutput,
    call=file_selector_call,
    aliases=["select", "find", "ls"],
    search_hint="Select files with filtering",
    is_read_only=lambda _: True,
    is_concurrency_safe=lambda _: True,
    render_tool_use_message=render_file_selector_use,
)

# Register the tool
register_tool(FileSelectorTool)


# Convenience function for programmatic use
async def select_files(directory: str = ".", pattern: str = "*", **kwargs) -> dict:
    """Convenience function to select files.

    Args:
        directory: Directory to search
        pattern: Glob pattern for matching
        **kwargs: Additional filter options

    Returns:
        Dictionary with files list and metadata
    """
    from pilotcode.tools.registry import get_tool

    tool = get_tool("FileSelector")
    if not tool:
        raise Exception("FileSelector tool not found")

    input_data = FileSelectorInput(directory=directory, pattern=pattern, **kwargs)

    # Create a minimal context
    context = ToolUseContext()

    result = await tool.call(
        input_data,
        context,
        lambda *args: True,  # can_use_tool
        None,  # parent_message
        lambda *args: None,  # on_progress
    )

    if result.error:
        raise Exception(result.error)

    return result.data.model_dump()
