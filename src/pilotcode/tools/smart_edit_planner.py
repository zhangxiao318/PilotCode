"""SmartEditPlanner — framework-side pre-analysis for weak models.

When a model needs to change a pattern across multiple files, it calls
SmartEditPlanner instead of searching manually. The framework returns a
structured checklist that the model can execute one item at a time.

This reduces the cognitive load on weak models and prevents the
"I changed 2 out of 5 occurrences" problem.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any
from pydantic import BaseModel, Field

from .base import ToolResult, ToolUseContext, build_tool, resolve_cwd
from .registry import register_tool


class SmartEditPlannerInput(BaseModel):
    """Input for SmartEditPlanner tool."""

    pattern: str = Field(
        description="The exact string or regex pattern to search for across the codebase"
    )
    replacement_hint: str = Field(
        default="",
        description="Description of what the pattern should be replaced with (for context)",
    )
    scope: str = Field(
        default=".",
        description="Directory to search in (default: current working directory)",
    )
    glob: str | None = Field(
        default=None,
        description="Optional glob filter, e.g. '*.py' to search only Python files",
    )
    max_results: int = Field(
        default=50,
        description="Maximum number of matches to return",
    )


class EditChecklistItem(BaseModel):
    """A single item in the edit checklist."""

    file_path: str
    line_number: int
    context_before: str
    matched_line: str
    context_after: str
    suggested_edit: str = ""


class SmartEditPlannerOutput(BaseModel):
    """Output from SmartEditPlanner tool."""

    pattern: str
    replacement_hint: str
    total_occurrences: int
    files_affected: list[str]
    checklist: list[EditChecklistItem]
    truncated: bool = False
    note: str = ""


# ---------------------------------------------------------------------------
# Ignore patterns (sync with grep_tool.py)
# ---------------------------------------------------------------------------

_IGNORE_PATTERNS = {
    "node_modules",
    "__pycache__",
    ".git",
    ".svn",
    ".hg",
    "venv",
    ".venv",
    "env",
    "dist",
    "build",
    "target",
}


def _should_ignore(path: Path) -> bool:
    name = path.name
    if name.startswith("."):
        return True
    for pat in _IGNORE_PATTERNS:
        if pat in str(path):
            return True
    return False


# ---------------------------------------------------------------------------
# Core logic
# ---------------------------------------------------------------------------


async def plan_edits(
    pattern: str,
    replacement_hint: str,
    scope: str,
    glob: str | None,
    max_results: int,
) -> SmartEditPlannerOutput:
    """Search for pattern and build a structured edit checklist."""
    search_path = Path(scope).expanduser().resolve()

    if not search_path.exists():
        return SmartEditPlannerOutput(
            pattern=pattern,
            replacement_hint=replacement_hint,
            total_occurrences=0,
            files_affected=[],
            checklist=[],
            note=f"Scope path not found: {scope}",
        )

    checklist: list[EditChecklistItem] = []
    files_affected: set[str] = set()
    total_occurrences = 0
    truncated = False

    # Collect files
    files_to_search: list[Path] = []
    if search_path.is_file():
        files_to_search = [search_path]
    else:
        for root, dirs, filenames in os.walk(search_path):
            dirs[:] = [d for d in dirs if not _should_ignore(Path(root) / d)]
            for filename in filenames:
                if _should_ignore(Path(filename)):
                    continue
                if glob and not Path(filename).match(glob):
                    continue
                files_to_search.append(Path(root) / filename)

    # Search each file
    for file_path in files_to_search:
        try:
            if file_path.stat().st_size > 5 * 1024 * 1024:  # Skip > 5MB
                continue
            content = file_path.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue

        lines = content.split("\n")
        rel_path = (
            str(file_path.relative_to(search_path))
            if search_path in file_path.parents
            else file_path.name
        )

        for line_num, line in enumerate(lines, start=1):
            if pattern in line:
                total_occurrences += 1
                if not truncated:
                    if len(checklist) < max_results:
                        files_affected.add(rel_path)

                        # Context: 2 lines before, 2 lines after
                        ctx_before = "\n".join(lines[max(0, line_num - 3) : line_num - 1])
                        ctx_after = "\n".join(lines[line_num : min(len(lines), line_num + 2)])

                        # Build suggested edit
                        suggested = (
                            line.replace(pattern, replacement_hint, 1) if replacement_hint else ""
                        )

                        checklist.append(
                            EditChecklistItem(
                                file_path=rel_path,
                                line_number=line_num,
                                context_before=ctx_before,
                                matched_line=line,
                                context_after=ctx_after,
                                suggested_edit=suggested,
                            )
                        )
                    else:
                        truncated = True

        if truncated:
            break

    # Build guidance note
    note_parts: list[str] = []
    if total_occurrences == 0:
        note_parts.append("No occurrences found. The pattern may not exist in the search scope.")
    elif truncated:
        note_parts.append(
            f"Results truncated to {max_results} items. " f"Total occurrences: {total_occurrences}."
        )
    else:
        note_parts.append(
            f"Found {total_occurrences} occurrence(s) across {len(files_affected)} file(s). "
            "Process checklist items one at a time using FileEdit."
        )

    return SmartEditPlannerOutput(
        pattern=pattern,
        replacement_hint=replacement_hint,
        total_occurrences=total_occurrences,
        files_affected=sorted(files_affected),
        checklist=checklist,
        truncated=truncated,
        note=" ".join(note_parts),
    )


# ---------------------------------------------------------------------------
# Tool wrapper
# ---------------------------------------------------------------------------


async def smart_edit_planner_call(
    input_data: SmartEditPlannerInput,
    context: ToolUseContext,
    can_use_tool: Any,
    parent_message: Any,
    on_progress: Any,
) -> ToolResult[SmartEditPlannerOutput]:
    """Execute SmartEditPlanner."""
    scope = input_data.scope
    if not os.path.isabs(scope):
        scope = os.path.join(resolve_cwd(context), scope)

    result = await plan_edits(
        pattern=input_data.pattern,
        replacement_hint=input_data.replacement_hint,
        scope=scope,
        glob=input_data.glob,
        max_results=input_data.max_results,
    )
    return ToolResult(data=result)


async def smart_edit_planner_description(
    input_data: SmartEditPlannerInput, options: dict[str, Any]
) -> str:
    return f"Planning edits for '{input_data.pattern}'"


def render_smart_edit_planner_use(
    input_data: SmartEditPlannerInput, options: dict[str, Any]
) -> str:
    return f"📋 SmartEditPlanner: '{input_data.pattern}'"


SmartEditPlanner = build_tool(
    name="SmartEditPlanner",
    description=smart_edit_planner_description,
    input_schema=SmartEditPlannerInput,
    output_schema=SmartEditPlannerOutput,
    call=smart_edit_planner_call,
    aliases=["edit_planner", "plan_edits"],
    search_hint="Generate a checklist of all files/lines that need editing for a given pattern",
    max_result_size_chars=100000,
    is_read_only=lambda _: True,
    is_concurrency_safe=lambda _: True,
    render_tool_use_message=render_smart_edit_planner_use,
)

register_tool(SmartEditPlanner)
