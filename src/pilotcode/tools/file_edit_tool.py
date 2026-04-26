"""File edit tool for editing file contents with search/replace."""

import difflib
import os
import shutil
from pathlib import Path
from typing import Any
from pydantic import BaseModel, Field

from .base import ToolResult, ToolUseContext, build_tool, resolve_cwd
from .registry import register_tool


# ---------------------------------------------------------------------------
# Auto-degradation helpers for weak models (P0)
# ---------------------------------------------------------------------------


def _extract_anchor_lines(text: str) -> list[str]:
    """Extract non-empty, meaningful lines from old_string for line-level matching.

    Ignores purely whitespace lines and very short lines to increase match
    uniqueness.
    """
    lines = text.splitlines()
    anchors = []
    for line in lines:
        stripped = line.strip()
        if stripped and len(stripped) >= 3:
            anchors.append(stripped)
    return anchors


def _try_line_level_match(
    content: str, old_str: str, new_str: str
) -> tuple[str | None, str]:
    """Attempt line-level split matching when exact match fails.

    Strategy:
    1. Extract anchor (non-empty) lines from old_str.
    2. Search content line-by-line for a contiguous block that contains all
       anchors in order (ignoring surrounding whitespace).
    3. If found, replace that block with new_str.

    Returns:
        (matched_block, replacement) if successful, else (None, error_hint)
    """
    anchors = _extract_anchor_lines(old_str)
    if len(anchors) < 1:
        return None, "old_string has no usable anchor lines."

    content_lines = content.splitlines(keepends=True)
    content_stripped = [ln.rstrip("\n\r") for ln in content_lines]

    # Scan for a contiguous window in content that contains all anchors
    for start_idx in range(len(content_stripped)):
        anchor_idx = 0
        matched_end = start_idx
        for ci in range(start_idx, len(content_stripped)):
            if anchor_idx < len(anchors) and content_stripped[ci].strip() == anchors[anchor_idx]:
                anchor_idx += 1
                matched_end = ci
                if anchor_idx == len(anchors):
                    break
        if anchor_idx == len(anchors):
            # Found a block [start_idx, matched_end] that contains all anchors
            # Expand to include leading/trailing context lines present in old_str
            old_lines = old_str.splitlines(keepends=True)
            old_blank_leading = 0
            for ln in old_lines:
                if ln.strip():
                    break
                old_blank_leading += 1
            old_blank_trailing = 0
            for ln in reversed(old_lines):
                if ln.strip():
                    break
                old_blank_trailing += 1

            block_start = max(0, start_idx - old_blank_leading)
            block_end = min(len(content_lines), matched_end + 1 + old_blank_trailing)
            matched_block = "".join(content_lines[block_start:block_end])
            return matched_block, new_str

    return None, f"Line-level match failed: could not find {len(anchors)} anchor lines in order."


def _try_block_level_match(
    content: str, old_str: str, new_str: str
) -> tuple[str | None, str]:
    """Attempt function/class block matching when line-level match fails.

    Strategy:
    1. Find the first function/class definition line in old_str.
    2. Search for that definition in content.
    3. Extract the complete block from content (using Python indentation rules).
    4. Replace the extracted block with new_str.

    Returns:
        (matched_block, replacement) if successful, else (None, error_hint)
    """
    old_lines = old_str.splitlines()
    def_line = ""
    for ln in old_lines:
        stripped = ln.lstrip()
        if stripped.startswith(("def ", "class ", "async def ")):
            # Extract name up to '(' or ':'
            def_line = stripped
            break

    if not def_line:
        return None, "Block-level match: no function/class definition found in old_string."

    # Search in content for the definition line (ignoring leading whitespace)
    content_lines = content.splitlines(keepends=True)
    target_name = def_line.split("(")[0].strip()

    start_idx = -1
    for i, ln in enumerate(content_lines):
        stripped = ln.lstrip()
        if stripped.startswith(target_name):
            start_idx = i
            break

    if start_idx == -1:
        return None, f"Block-level match: definition '{target_name}' not found in file."

    # Determine base indentation of the definition line
    base_indent = len(content_lines[start_idx]) - len(content_lines[start_idx].lstrip())

    # Walk forward until we hit a line at indentation <= base_indent
    # (or end of file / start of another top-level block)
    end_idx = start_idx + 1
    for i in range(start_idx + 1, len(content_lines)):
        line = content_lines[i]
        if not line.strip():
            end_idx = i + 1
            continue
        line_indent = len(line) - len(line.lstrip())
        if line_indent <= base_indent:
            # Could be end of block or decorator/docstring edge case
            # Stop here for safety
            break
        end_idx = i + 1

    matched_block = "".join(content_lines[start_idx:end_idx])
    return matched_block, new_str


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
                        syntax_hint = (
                            f"\n\nSYNTAX ERROR DETAILS: {e}\n"
                            f"TIP: Re-read the file to get the EXACT text. "
                            f"Your old_string may have subtle differences (indentation, quotes, escapes). "
                            f"For large changes, consider FileWrite ONLY for files under 30 lines."
                        )
                        return FileEditOutput(
                            file_path=str(path),
                            replacements_made=0,
                            original_content=original_content,
                            error=f"{fuzzy_note} Fuzzy match introduced Python syntax error, rolled back.{syntax_hint}",
                        )

                return FileEditOutput(
                    file_path=str(path),
                    replacements_made=1,
                    original_content=original_content,
                    new_content=new_content,
                    diff=f"{fuzzy_note}\n{diff}",
                )

            # ------------------------------------------------------------------
            # P0: Auto-degradation — line-level then block-level matching
            # ------------------------------------------------------------------
            degradation_attempted = []

            # Strategy 1: Line-level split match
            matched_block, replacement = _try_line_level_match(
                original_content, old_string_normalized, new_string_normalized
            )
            if matched_block is not None:
                degradation_attempted.append("line-level match")
                new_content = original_content.replace(matched_block, replacement, 1)
            else:
                # Strategy 2: Block-level match (function/class)
                matched_block, replacement = _try_block_level_match(
                    original_content, old_string_normalized, new_string_normalized
                )
                if matched_block is not None:
                    degradation_attempted.append("block-level match")
                    new_content = original_content.replace(matched_block, replacement, 1)

            if degradation_attempted:
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
                            error=f"Auto-degradation ({', '.join(degradation_attempted)}) write verification failed, rolled back.",
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
                            error=f"Auto-degradation ({', '.join(degradation_attempted)}) introduced Python syntax error, rolled back: {e}",
                        )

                return FileEditOutput(
                    file_path=str(path),
                    replacements_made=1,
                    original_content=original_content,
                    new_content=new_content,
                    diff=f"[AUTO-DEGRADATION: used {', '.join(degradation_attempted)}]\n{diff}",
                )

            # ------------------------------------------------------------------
            # All strategies failed — return detailed context to help the model
            # ------------------------------------------------------------------
            context_snippet = ""
            if len(old_string) > 10:
                search_term = old_string.strip().splitlines()[0][:40]
                idx = original_content.find(search_term)
                if idx != -1:
                    start = max(0, idx - 200)
                    end = min(len(original_content), idx + 200)
                    context_snippet = (
                        f"\n\nNearby content:\n```\n{original_content[start:end]}\n```"
                    )
                else:
                    context_snippet = f"\n\nFile starts with:\n```\n{original_content[:500]}\n```"

            mismatch_hint = ""
            if len(old_string) <= 200 and search_term:
                matched_idx = original_content.find(search_term)
                if matched_idx != -1:
                    matched_context = original_content[
                        max(0, matched_idx - 50) : matched_idx + len(search_term) + 50
                    ]
                    mismatch_hint = (
                        f"\n\n[EXPECTED (your old_string)]\n```\n{old_string[:200]}\n```"
                        f"\n[ACTUAL (closest match in file)]\n```\n{matched_context}\n```"
                    )

            return FileEditOutput(
                file_path=str(path),
                replacements_made=0,
                original_content=original_content,
                error=f"String not found in file.{context_snippet}{mismatch_hint}\n\nTIP: Make sure old_string matches the file content EXACTLY (including indentation and newlines). If the file was recently modified, re-read it first.",
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
            except Exception:
                pass
        return FileEditOutput(file_path=str(path), replacements_made=0, error=str(e))
    finally:
        # Clean up backup on success, keep on failure for manual recovery
        if backup_path and backup_path.exists():
            try:
                backup_path.unlink()
            except Exception:
                pass


async def file_edit_validate(
    input_data: FileEditInput, context: ToolUseContext
) -> tuple[bool, str | None]:
    """Validate file edit input."""
    cwd = resolve_cwd(context)

    normalized_path = _normalize_path(input_data.file_path, cwd)

    # Check if file has been read (conflict detection)
    # Use normalized path comparison to handle Windows path variations
    read_info = None
    if context.read_file_state:
        for key, info in context.read_file_state.items():
            if _normalize_path(key, None) == normalized_path:
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
    cwd = resolve_cwd(context)
    if not os.path.isabs(file_path):
        file_path = os.path.join(cwd, file_path)

    # Edit file with workspace restriction
    result = await edit_file_content(
        file_path,
        input_data.old_string,
        input_data.new_string,
        input_data.expected_replacements,
        cwd,
    )

    # Propagate error to ToolResult so LLM sees a clear failure message
    if result.error:
        return ToolResult(
            data=result,
            error=result.error,
            output_for_assistant=render_file_edit_result(result, [], {}),
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
