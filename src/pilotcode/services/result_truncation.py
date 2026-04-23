"""Smart result truncation to prevent context overflow.

Following Claude Code's approach of intelligently truncating large results
while providing clear feedback about what was truncated.
"""

from dataclasses import dataclass
from typing import Any, TypeVar, Generic, Callable

T = TypeVar("T")


@dataclass
class TruncatedResult(Generic[T]):
    """Result with truncation information."""

    data: T
    original_count: int
    truncated_count: int
    is_truncated: bool
    truncation_message: str | None = None


class TruncationConfig:
    """Configuration for result truncation."""

    # Default limits
    DEFAULT_MAX_FILES = 1000
    DEFAULT_MAX_LINES = 10000
    DEFAULT_MAX_CHARS = 100000
    DEFAULT_MAX_ITEMS = 1000

    # File search limits
    MAX_GLOB_FILES = 100
    MAX_GREP_RESULTS = 1000
    MAX_LS_ENTRIES = 1000

    def __init__(
        self,
        max_files: int | None = None,
        max_lines: int | None = None,
        max_chars: int | None = None,
        max_items: int | None = None,
    ):
        self.max_files = max_files or self.DEFAULT_MAX_FILES
        self.max_lines = max_lines or self.DEFAULT_MAX_LINES
        self.max_chars = max_chars or self.DEFAULT_MAX_CHARS
        self.max_items = max_items or self.DEFAULT_MAX_ITEMS


def truncate_file_list(
    files: list[str], max_files: int | None = None, show_sample: bool = True
) -> TruncatedResult[list[str]]:
    """Truncate a list of files with informative message.

    Args:
        files: List of file paths
        max_files: Maximum number of files to return
        show_sample: Whether to include sample of truncated files

    Returns:
        TruncatedResult with files and truncation info
    """
    config = TruncationConfig()
    limit = max_files or config.max_files

    if len(files) <= limit:
        return TruncatedResult(
            data=files, original_count=len(files), truncated_count=0, is_truncated=False
        )

    truncated_files = files[:limit]
    truncated_count = len(files) - limit

    message = _build_truncation_message(
        item_type="files",
        total=len(files),
        shown=limit,
        truncated=truncated_count,
        suggestion="Use more specific patterns or explore directories individually.",
        show_sample=show_sample,
        sample=files[limit : limit + 5] if show_sample else None,
    )

    return TruncatedResult(
        data=truncated_files,
        original_count=len(files),
        truncated_count=truncated_count,
        is_truncated=True,
        truncation_message=message,
    )


def truncate_text_content(
    content: str,
    max_chars: int | None = None,
    max_lines: int | None = None,
    from_start: bool = True,
) -> TruncatedResult[str]:
    """Truncate text content by characters and/or lines.

    Args:
        content: Text content to truncate
        max_chars: Maximum characters (None for no limit)
        max_lines: Maximum lines (None for no limit)
        from_start: If True, truncate from end; if False, truncate from start

    Returns:
        TruncatedResult with content and truncation info
    """
    config = TruncationConfig()
    char_limit = max_chars or config.max_chars
    line_limit = max_lines or config.max_lines

    original_lines = content.split("\n")
    original_char_count = len(content)

    # Apply line limit first
    if len(original_lines) > line_limit:
        if from_start:
            truncated_lines = original_lines[:line_limit]
        else:
            truncated_lines = original_lines[-line_limit:]
        content = "\n".join(truncated_lines)
    else:
        truncated_lines = original_lines

    # Then apply character limit
    if len(content) > char_limit:
        if from_start:
            content = content[:char_limit]
        else:
            content = content[-char_limit:]

    is_truncated = len(truncated_lines) < len(original_lines) or len(content) < original_char_count

    if not is_truncated:
        return TruncatedResult(
            data=content, original_count=len(original_lines), truncated_count=0, is_truncated=False
        )

    truncated_line_count = len(original_lines) - len(truncated_lines)

    message_parts = []
    if truncated_line_count > 0:
        message_parts.append(f"{truncated_line_count} lines")
    if len(content) < original_char_count:
        message_parts.append(f"{original_char_count - len(content)} characters")

    message = f"Content truncated: {' and '.join(message_parts)} omitted."

    return TruncatedResult(
        data=content,
        original_count=len(original_lines),
        truncated_count=truncated_line_count,
        is_truncated=True,
        truncation_message=message,
    )


def truncate_search_results(
    results: list[dict[str, Any]], max_results: int | None = None, result_type: str = "matches"
) -> TruncatedResult[list[dict[str, Any]]]:
    """Truncate search results (grep, find, etc.).

    Args:
        results: List of search result items
        max_results: Maximum results to return
        result_type: Type of results for message (e.g., "matches", "files")

    Returns:
        TruncatedResult with results and truncation info
    """
    config = TruncationConfig()
    limit = max_results or config.DEFAULT_MAX_ITEMS

    if len(results) <= limit:
        return TruncatedResult(
            data=results, original_count=len(results), truncated_count=0, is_truncated=False
        )

    truncated_results = results[:limit]
    truncated_count = len(results) - limit

    message = _build_truncation_message(
        item_type=result_type,
        total=len(results),
        shown=limit,
        truncated=truncated_count,
        suggestion="Use more specific search patterns to narrow results.",
    )

    return TruncatedResult(
        data=truncated_results,
        original_count=len(results),
        truncated_count=truncated_count,
        is_truncated=True,
        truncation_message=message,
    )


def truncate_directory_listing(
    entries: list[dict[str, Any]], max_entries: int | None = None, directory_path: str = ""
) -> TruncatedResult[list[dict[str, Any]]]:
    """Truncate directory listing results.

    Args:
        entries: List of directory entries
        max_entries: Maximum entries to show
        directory_path: Path of directory being listed

    Returns:
        TruncatedResult with entries and truncation info
    """
    config = TruncationConfig()
    limit = max_entries or config.MAX_LS_ENTRIES

    if len(entries) <= limit:
        return TruncatedResult(
            data=entries, original_count=len(entries), truncated_count=0, is_truncated=False
        )

    truncated_entries = entries[:limit]
    truncated_count = len(entries) - limit

    path_info = f" in {directory_path}" if directory_path else ""
    message = _build_truncation_message(
        item_type="entries",
        total=len(entries),
        shown=limit,
        truncated=truncated_count,
        suggestion=f"Use Bash or Ls tool with specific subdirectories{path_info}.",
    )

    return TruncatedResult(
        data=truncated_entries,
        original_count=len(entries),
        truncated_count=truncated_count,
        is_truncated=True,
        truncation_message=message,
    )


def _build_truncation_message(
    item_type: str,
    total: int,
    shown: int,
    truncated: int,
    suggestion: str | None = None,
    show_sample: bool = False,
    sample: list[str] | None = None,
) -> str:
    """Build an informative truncation message.

    Following Claude Code's format for truncation messages.
    """
    lines = [
        f"There are more than {total} {item_type}.",
        f"Showing first {shown} {item_type}.",
    ]

    if show_sample and sample:
        lines.append(f"Examples of additional {item_type}: {', '.join(sample[:3])}")

    lines.append(f"{truncated} {item_type} were truncated.")

    if suggestion:
        lines.append(suggestion)

    return " ".join(lines)


def format_truncated_output(
    result: TruncatedResult[T], format_fn: Callable[[T], Any] | None = None
) -> dict[str, Any]:
    """Format a truncated result for output.

    Args:
        result: TruncatedResult to format
        format_fn: Optional function to format the data

    Returns:
        Dictionary with formatted output and metadata
    """
    output = {
        "data": format_fn(result.data) if format_fn else result.data,
        "truncated": result.is_truncated,
        "total": result.original_count,
        "shown": result.original_count - result.truncated_count,
    }

    if result.is_truncated:
        output["truncated_count"] = result.truncated_count
        output["message"] = result.truncation_message

    return output


# Claude Code-style truncation messages for specific tools
TRUNCATION_MESSAGES = {
    "glob": (
        "There are more than {total} files in the repository. "
        "Use the LS tool (passing a specific path), Bash tool, "
        "and other tools to explore nested directories. "
        "The first {limit} files and directories are included below."
    ),
    "ls": (
        "Directory contains more than {total} entries. "
        "Showing first {limit}. Use Bash tool to explore subdirectories."
    ),
    "grep": (
        "Search found more than {total} matches. "
        "Showing first {limit}. Use more specific patterns to narrow results."
    ),
    "git_status": ("Repository has many changes. Showing first {limit} modified files."),
}


def get_truncation_message(tool_name: str, total: int, limit: int) -> str | None:
    """Get a Claude Code-style truncation message for a tool."""
    template = TRUNCATION_MESSAGES.get(tool_name)
    if template:
        return template.format(total=total, limit=limit)
    return None
