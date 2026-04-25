"""ApplyPatch tool for applying unified diff patches to files."""

import os
import subprocess
from pathlib import Path
from typing import Any
from pydantic import BaseModel, Field

from .base import ToolResult, ToolUseContext, build_tool, resolve_cwd
from .registry import register_tool


class ApplyPatchInput(BaseModel):
    """Input for ApplyPatch tool."""

    patch_text: str = Field(description="Unified diff patch text to apply")
    base_path: str = Field(default=".", description="Base directory to apply the patch from")
    strip: int = Field(
        default=1, description="Number of leading path components to strip (default: 1)"
    )
    dry_run: bool = Field(default=False, description="If True, simulate the patch without applying")


class ApplyPatchOutput(BaseModel):
    """Output from ApplyPatch tool."""

    success: bool
    output: str
    error: str | None = None


def _apply_patch_with_command(
    patch_text: str, base_path: str, strip: int, dry_run: bool
) -> ApplyPatchOutput:
    """Apply patch using the system `patch` command."""
    cwd = Path(base_path).expanduser().resolve()
    if not cwd.exists():
        return ApplyPatchOutput(success=False, output="", error=f"Directory not found: {base_path}")

    cmd = ["patch", f"-p{strip}"]
    if dry_run:
        cmd.append("--dry-run")
    cmd.append("--batch")

    try:
        result = subprocess.run(
            cmd,
            input=patch_text,
            cwd=cwd,
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            return ApplyPatchOutput(
                success=True,
                output=result.stdout.strip(),
            )
        else:
            return ApplyPatchOutput(
                success=False,
                output=result.stdout.strip(),
                error=result.stderr.strip() or "Patch failed",
            )
    except FileNotFoundError:
        return ApplyPatchOutput(
            success=False,
            output="",
            error="`patch` command not found on this system",
        )
    except Exception as e:
        return ApplyPatchOutput(success=False, output="", error=f"Exception during patch: {e}")


async def apply_patch_call(
    input_data: ApplyPatchInput,
    context: ToolUseContext,
    can_use_tool: Any,
    parent_message: Any,
    on_progress: Any,
) -> ToolResult[ApplyPatchOutput]:
    """Apply a unified diff patch."""
    base_path = input_data.base_path
    if not os.path.isabs(base_path):
        cwd = resolve_cwd(context)
        base_path = os.path.join(cwd, base_path)

    result = _apply_patch_with_command(
        input_data.patch_text,
        base_path,
        input_data.strip,
        input_data.dry_run,
    )
    return ToolResult(data=result)


async def apply_patch_description(input_data: ApplyPatchInput, options: dict[str, Any]) -> str:
    """Get description for ApplyPatch."""
    mode = "dry-run" if input_data.dry_run else "apply"
    return f"🩹 {mode.capitalize()} patch ({len(input_data.patch_text)} chars)"


def render_apply_patch_use(input_data: ApplyPatchInput, options: dict[str, Any]) -> str:
    """Render ApplyPatch tool use message."""
    mode = "dry-run" if input_data.dry_run else "apply"
    return f"🩹 {mode.capitalize()}ing patch ({len(input_data.patch_text)} chars)"


def render_apply_patch_result(
    result: ApplyPatchOutput, messages: list[Any], options: dict[str, Any]
) -> str:
    """Render ApplyPatch result message."""
    if result.success:
        return f"✅ Patch applied successfully\n{result.output}"
    else:
        return f"❌ Patch failed: {result.error}"


ApplyPatchTool = build_tool(
    name="ApplyPatch",
    description="Apply a unified diff patch to files in the workspace. Use this when you have a complete diff (e.g., from git diff or a bug report) that needs to be applied atomically. Supports dry-run mode to preview changes.",
    input_schema=ApplyPatchInput,
    output_schema=ApplyPatchOutput,
    call=apply_patch_call,
    user_facing_name=apply_patch_description,
    render_tool_use_message=render_apply_patch_use,
    render_tool_result_message=render_apply_patch_result,
)

register_tool(ApplyPatchTool)
