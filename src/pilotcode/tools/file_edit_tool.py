"""File edit tool for editing file contents with search/replace."""

import difflib
import os
import shutil
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
        # Resolve to absolute path
        path = Path(file_path).expanduser().resolve()

        # Get workspace directory
        workspace = Path(cwd or os.getcwd()).expanduser().resolve()

        # Check if path is within workspace
        # Use str.startswith for case-insensitive comparison on Windows
        try:
            path.relative_to(workspace)
            return True, ""
        except ValueError:
            return (
                False,
                f"Access denied: Path '{path}' is outside workspace '{workspace}'. Only files within the workspace can be edited.",
            )
    except Exception as e:
        return False, f"Path validation error: {e}"


class FileEditInput(BaseModel):
    """Input for FileEdit tool."""

    file_path: str = Field(description="Path to the file to edit")
    old_string: str = Field(description="The string to search for and replace")
    new_string: str = Field(description="The replacement string")
    expected_replacements: int | None = Field(
        default=None, description="Expected number of replacements (default: 1)"
    )


class FileEditOutput(BaseModel):
    """Output from FileEdit tool."""

    file_path: str
    replacements_made: int
    original_content: str | None = None
    new_content: str | None = None
    diff: str | None = None  # Unified diff format
    error: str | None = None


def _generate_unified_diff(
    old_content: str,
    new_content: str,
    filename: str,
    context_lines: int = 3,
    max_diff_size: int = 3000,
) -> str:
    """Generate a unified diff between old and new content.

    Args:
        old_content: Original file content
        new_content: Modified file content
        filename: Name of the file for diff headers
        context_lines: Number of context lines around changes
        max_diff_size: Maximum diff size before truncation

    Returns:
        Unified diff string (possibly truncated)
    """
    old_lines = old_content.splitlines(keepends=True)
    new_lines = new_content.splitlines(keepends=True)

    # Ensure lines end with newline for proper diff
    if old_lines and not old_lines[-1].endswith("\n"):
        old_lines[-1] += "\n"
    if new_lines and not new_lines[-1].endswith("\n"):
        new_lines[-1] += "\n"

    diff = difflib.unified_diff(
        old_lines, new_lines, fromfile=f"a/{filename}", tofile=f"b/{filename}", n=context_lines
    )

    result = "".join(diff)

    # Truncate enormous diffs
    if len(result) > max_diff_size:
        result = result[: max_diff_size - 50] + "\n... (diff truncated)\n"

    return result


def _normalize_path(file_path: str, cwd: str | None = None) -> str:
    """Normalize a file path for consistent comparison.

    Converts to absolute path and normalizes separators and case on Windows.
    """
    if cwd and not os.path.isabs(file_path):
        file_path = os.path.join(cwd, file_path)
    return os.path.normcase(os.path.normpath(os.path.abspath(file_path)))


async def edit_file_content(
    file_path: str,
    old_string: str,
    new_string: str,
    expected_replacements: int | None = None,
    cwd: str | None = None,
) -> FileEditOutput:
    """Edit file content with search/replace.

    Supports fuzzy matching: if the exact old_string is not found,
    attempts to find the closest match using sequence similarity.
    """
    # Security check: validate path is within workspace
    is_valid, error_msg = _is_path_within_workspace(file_path, cwd)
    if not is_valid:
        return FileEditOutput(file_path=file_path, replacements_made=0, error=error_msg)

    path = Path(file_path).expanduser().resolve()

    if not path.exists():
        return FileEditOutput(
            file_path=str(path), replacements_made=0, error=f"File not found: {file_path}"
        )

    # Create backup before editing
    backup_path = None
    try:
        backup_path = path.with_suffix(path.suffix + ".pilotcode.bak")
        shutil.copy2(path, backup_path)
    except Exception as e:
        return FileEditOutput(
            file_path=str(path),
            replacements_made=0,
            error=f"Failed to create backup before editing: {e}",
        )

    try:
        # Read original content
        original_content = path.read_text(encoding="utf-8", errors="replace")

        # Normalize line endings for Windows compatibility
        # If file uses CRLF but old_string uses LF, convert old_string/new_string to CRLF
        file_has_crlf = "\r\n" in original_content
        old_string_normalized = old_string
        new_string_normalized = new_string
        if file_has_crlf and "\r\n" not in old_string:
            old_string_normalized = old_string.replace("\n", "\r\n")
            new_string_normalized = new_string.replace("\n", "\r\n")

        # Count occurrences
        occurrences = original_content.count(old_string_normalized)

        if occurrences == 0:
            # Try fuzzy matching before giving up
            from difflib import SequenceMatcher

            def _find_best_match(content: str, target: str) -> tuple[str, float]:
                """Find the substring in content most similar to target."""
                target_len = len(target)
                if target_len == 0:
                    return "", 0.0
                best_ratio = 0.0
                best_match = ""
                # Slide a window of target_len across the content
                # Use a step size to avoid O(n^2) on huge files
                step = max(1, target_len // 20)
                for i in range(0, len(content) - target_len + 1, step):
                    candidate = content[i : i + target_len]
                    ratio = SequenceMatcher(None, target, candidate).ratio()
                    if ratio > best_ratio:
                        best_ratio = ratio
                        best_match = candidate
                        if ratio >= 0.99:
                            break
                # Also check a few line-aligned positions for better accuracy
                lines = content.splitlines(keepends=True)
                pos = 0
                for line in lines:
                    for offset in (0, len(line) // 4, len(line) // 2):
                        start = pos + offset
                        if start + target_len <= len(content):
                            candidate = content[start : start + target_len]
                            ratio = SequenceMatcher(None, target, candidate).ratio()
                            if ratio > best_ratio:
                                best_ratio = ratio
                                best_match = candidate
                    pos += len(line)
                return best_match, best_ratio

            best_match, ratio = _find_best_match(original_content, old_string_normalized)

            if ratio >= 0.75:
                # Use fuzzy match
                fuzzy_note = f"[FUZZY MATCH] Exact string not found. Used closest match (similarity {ratio:.2f})."
                new_content = original_content.replace(best_match, new_string_normalized, 1)
                # Generate unified diff using the actual matched text
                diff = _generate_unified_diff(original_content, new_content, path.name)
                path.write_text(new_content, encoding="utf-8")

                # Verify write succeeded
                try:
                    verify_content = path.read_text(encoding="utf-8")
                    if verify_content != new_content:
                        path.write_text(original_content, encoding="utf-8")
                        return FileEditOutput(
                            file_path=str(path),
                            replacements_made=0,
                            error=f"{fuzzy_note} Write verification failed, rolled back.",
                        )
                except Exception:
                    pass

                # Validate Python syntax and rollback if invalid
                if path.suffix == ".py":
                    import py_compile

                    try:
                        py_compile.compile(str(path), doraise=True)
                    except py_compile.PyCompileError as e:
                        path.write_text(original_content, encoding="utf-8")
                        return FileEditOutput(
                            file_path=str(path),
                            replacements_made=0,
                            original_content=original_content,
                            error=f"{fuzzy_note} Fuzzy match introduced Python syntax error, rolled back: {e}",
                        )

                return FileEditOutput(
                    file_path=str(path),
                    replacements_made=1,
                    original_content=original_content,
                    new_content=new_content,
                    diff=f"{fuzzy_note}\n{diff}",
                )

            # Show surrounding context to help the model fix its query
            context_snippet = ""
            if len(old_string) > 10:
                # Try to find a line containing part of old_string
                search_term = old_string.strip().splitlines()[0][:40]
                idx = original_content.find(search_term)
                if idx != -1:
                    start = max(0, idx - 200)
                    end = min(len(original_content), idx + 200)
                    context_snippet = (
                        f"\n\nNearby content:\n```\n{original_content[start:end]}\n```"
                    )
                else:
                    # Show first 500 chars of file as reference
                    context_snippet = f"\n\nFile starts with:\n```\n{original_content[:500]}\n```"

            return FileEditOutput(
                file_path=str(path),
                replacements_made=0,
                original_content=original_content,
                error=f"String not found in file.{context_snippet}\n\nTIP: Make sure old_string matches the file content EXACTLY (including indentation and newlines). If the file was recently modified, re-read it first.",
            )

        if expected_replacements is not None:
            if occurrences != expected_replacements:
                return FileEditOutput(
                    file_path=str(path),
                    replacements_made=0,
                    original_content=original_content,
                    error=f"Expected {expected_replacements} occurrences, found {occurrences}",
                )

        # Replace
        new_content = original_content.replace(old_string_normalized, new_string_normalized)
        replacements_made = occurrences

        # Generate unified diff
        filename = path.name
        diff = _generate_unified_diff(original_content, new_content, filename)

        # Write back
        path.write_text(new_content, encoding="utf-8")

        # Verify write succeeded
        try:
            verify_content = path.read_text(encoding="utf-8")
            if verify_content != new_content:
                path.write_text(original_content, encoding="utf-8")
                return FileEditOutput(
                    file_path=str(path),
                    replacements_made=0,
                    error="Write verification failed (disk readback mismatch), rolled back.",
                )
        except Exception as verify_err:
            path.write_text(original_content, encoding="utf-8")
            return FileEditOutput(
                file_path=str(path),
                replacements_made=0,
                error=f"Write verification failed: {verify_err}, rolled back.",
            )

        # Validate Python syntax and rollback if invalid
        if path.suffix == ".py":
            import py_compile

            try:
                py_compile.compile(str(path), doraise=True)
            except py_compile.PyCompileError as e:
                # Rollback to original content
                path.write_text(original_content, encoding="utf-8")
                return FileEditOutput(
                    file_path=str(path),
                    replacements_made=0,
                    original_content=original_content,
                    error=f"Edit introduced Python syntax error, change rolled back: {e}",
                )

        return FileEditOutput(
            file_path=str(path),
            replacements_made=replacements_made,
            original_content=original_content if replacements_made == 1 else None,
            new_content=new_content if replacements_made == 1 else None,
            diff=diff,
        )
    except Exception as e:
        # Try to restore from backup on unexpected error
        if backup_path and backup_path.exists():
            try:
                shutil.copy2(backup_path, path)
            except:
                pass
        return FileEditOutput(file_path=str(path), replacements_made=0, error=str(e))
    finally:
        # Clean up backup on success, keep on failure for manual recovery
        if backup_path and backup_path.exists():
            try:
                backup_path.unlink()
            except:
                pass


async def file_edit_validate(
    input_data: FileEditInput, context: ToolUseContext
) -> tuple[bool, str | None]:
    """Validate file edit input."""
    cwd = None
    if context.get_app_state:
        app_state = context.get_app_state()
        cwd = getattr(app_state, "cwd", os.getcwd())

    normalized_path = _normalize_path(input_data.file_path, cwd)

    # Check if file has been read (conflict detection)
    # Use normalized path comparison to handle Windows path variations
    matched_key = None
    read_info = None
    if context.read_file_state:
        for key, info in context.read_file_state.items():
            if _normalize_path(key, None) == normalized_path:
                matched_key = key
                read_info = info
                break

    if read_info is not None:
        read_timestamp = read_info.get("timestamp", 0)
        if os.path.exists(normalized_path):
            mtime = os.path.getmtime(normalized_path)
            if mtime > read_timestamp:
                return False, "File has been modified since it was read"
    else:
        if os.path.exists(normalized_path):
            # Allow editing with a warning rather than blocking entirely
            # This is important for headless/simple mode where read_file_state
            # may not be perfectly maintained
            return True, None

    return True, None


async def file_edit_call(
    input_data: FileEditInput,
    context: ToolUseContext,
    can_use_tool: Any,
    parent_message: Any,
    on_progress: Any,
) -> ToolResult[FileEditOutput]:
    """Execute file edit."""
    # Resolve path
    file_path = input_data.file_path
    cwd = os.getcwd()
    if not os.path.isabs(file_path) and context.get_app_state:
        app_state = context.get_app_state()
        cwd = getattr(app_state, "cwd", os.getcwd())
        file_path = os.path.join(cwd, file_path)

    # Edit file with workspace restriction
    result = await edit_file_content(
        file_path,
        input_data.old_string,
        input_data.new_string,
        input_data.expected_replacements,
        cwd,
    )

    return ToolResult(data=result)


async def file_edit_description(input_data: FileEditInput, options: dict[str, Any]) -> str:
    """Get description for file edit."""
    path = Path(input_data.file_path)
    return f"Editing {path.name}"


def render_file_edit_use(input_data: FileEditInput, options: dict[str, Any]) -> str:
    """Render file edit tool use message."""
    path = Path(input_data.file_path)
    old_preview = input_data.old_string[:30].replace("\n", " ")
    new_preview = input_data.new_string[:30].replace("\n", " ")
    return f"✏️  Editing {path.name}: '{old_preview}...' → '{new_preview}...'"


def render_file_edit_result(
    result: FileEditOutput, messages: list[Any], options: dict[str, Any]
) -> str:
    """Render file edit result for display.

    Shows the unified diff if available, otherwise a simple success message.
    """
    if result.error:
        return f"❌ Error editing {Path(result.file_path).name}: {result.error}"

    if result.diff:
        return f"✅ Edited {Path(result.file_path).name} ({result.replacements_made} replacement(s))\n\n{result.diff}"

    return f"✅ Edited {Path(result.file_path).name} ({result.replacements_made} replacement(s))"


# Create the FileEdit tool
FileEditTool = build_tool(
    name="FileEdit",
    description=file_edit_description,
    input_schema=FileEditInput,
    output_schema=FileEditOutput,
    call=file_edit_call,
    validate_input=file_edit_validate,
    aliases=["edit", "replace"],
    search_hint="Edit file with search/replace",
    max_result_size_chars=50000,
    is_read_only=lambda _: False,
    is_destructive=lambda _: True,
    is_concurrency_safe=lambda _: False,
    render_tool_use_message=render_file_edit_use,
    render_tool_result_message=render_file_edit_result,
)

# Register the tool
register_tool(FileEditTool)
