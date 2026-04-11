"""Git worktree tools for managing multiple working directories."""

import subprocess
import os
from typing import Any
from pydantic import BaseModel, Field

from .base import ToolResult, ToolUseContext, build_tool
from .registry import register_tool


class EnterWorktreeInput(BaseModel):
    """Input for EnterWorktree tool."""

    path: str = Field(description="Path to the worktree directory")


class EnterWorktreeOutput(BaseModel):
    """Output from EnterWorktree tool."""

    path: str
    branch: str
    message: str


def run_git(args: list[str], cwd: str = ".") -> tuple[int, str, str]:
    """Run git command."""
    try:
        result = subprocess.run(["git"] + args, capture_output=True, text=True, cwd=cwd)
        return result.returncode, result.stdout, result.stderr
    except Exception as e:
        return -1, "", str(e)


async def enter_worktree_call(
    input_data: EnterWorktreeInput,
    context: ToolUseContext,
    can_use_tool: Any,
    parent_message: Any,
    on_progress: Any,
) -> ToolResult[EnterWorktreeOutput]:
    """Enter a git worktree."""
    path = os.path.expanduser(input_data.path)

    # Check if it's a valid worktree
    rc, stdout, stderr = run_git(["worktree", "list", "--porcelain"])

    if rc != 0:
        return ToolResult(
            data=EnterWorktreeOutput(path=path, branch="", message=""),
            error=f"Failed to list worktrees: {stderr}",
        )

    # Find the worktree
    worktrees = stdout.strip().split("\n\n")
    target_worktree = None

    for wt in worktrees:
        lines = wt.split("\n")
        worktree_path = None
        worktree_branch = None

        for line in lines:
            if line.startswith("worktree "):
                worktree_path = line[9:]
            elif line.startswith("branch "):
                worktree_branch = line[7:]

        if worktree_path and os.path.samefile(worktree_path, path):
            target_worktree = {"path": worktree_path, "branch": worktree_branch or "detached"}
            break

    if not target_worktree:
        return ToolResult(
            data=EnterWorktreeOutput(path=path, branch="", message=""),
            error=f"Not a valid worktree: {path}",
        )

    # Change to the worktree directory
    if context.get_app_state:
        context.get_app_state()
        # Update cwd in state
        if context.set_app_state:
            context.set_app_state(lambda s: s)  # Trigger update

    return ToolResult(
        data=EnterWorktreeOutput(
            path=target_worktree["path"],
            branch=target_worktree["branch"],
            message=f"Entered worktree: {target_worktree['path']} ({target_worktree['branch']})",
        )
    )


class ExitWorktreeInput(BaseModel):
    """Input for ExitWorktree tool."""

    pass


class ExitWorktreeOutput(BaseModel):
    """Output from ExitWorktree tool."""

    previous_path: str
    main_path: str
    message: str


async def exit_worktree_call(
    input_data: ExitWorktreeInput,
    context: ToolUseContext,
    can_use_tool: Any,
    parent_message: Any,
    on_progress: Any,
) -> ToolResult[ExitWorktreeOutput]:
    """Exit worktree and return to main repository."""
    # Find main repository by looking for .git directory
    current_dir = context.get_app_state().cwd if context.get_app_state else "."

    # Go up until we find the main repo
    main_path = current_dir
    while main_path != "/":
        parent = os.path.dirname(main_path)
        if os.path.isdir(os.path.join(parent, ".git")):
            main_path = parent
            break
        main_path = parent

    return ToolResult(
        data=ExitWorktreeOutput(
            previous_path=current_dir,
            main_path=main_path,
            message=f"Returned to main repository: {main_path}",
        )
    )


class ListWorktreesInput(BaseModel):
    """Input for ListWorktrees tool."""

    pass


class WorktreeInfo(BaseModel):
    """Worktree information."""

    path: str
    branch: str
    detached: bool


class ListWorktreesOutput(BaseModel):
    """Output from ListWorktrees tool."""

    worktrees: list[WorktreeInfo]
    current: str


async def list_worktrees_call(
    input_data: ListWorktreesInput,
    context: ToolUseContext,
    can_use_tool: Any,
    parent_message: Any,
    on_progress: Any,
) -> ToolResult[ListWorktreesOutput]:
    """List all git worktrees."""
    rc, stdout, stderr = run_git(["worktree", "list", "--porcelain"])

    if rc != 0:
        return ToolResult(
            data=ListWorktreesOutput(worktrees=[], current=""),
            error=f"Failed to list worktrees: {stderr}",
        )

    worktrees = []
    current = ""

    blocks = stdout.strip().split("\n\n")
    for block in blocks:
        lines = block.split("\n")
        path = ""
        branch = ""
        detached = False

        for line in lines:
            if line.startswith("worktree "):
                path = line[9:]
            elif line.startswith("branch "):
                branch = line[7:].replace("refs/heads/", "")
            elif line == "detached":
                detached = True

        if path:
            worktrees.append(
                WorktreeInfo(path=path, branch=branch or "detached", detached=detached)
            )
            # Assume first is main/current
            if not current:
                current = path

    return ToolResult(data=ListWorktreesOutput(worktrees=worktrees, current=current))


# Register worktree tools
EnterWorktreeTool = build_tool(
    name="EnterWorktree",
    description=lambda x, o: f"Enter worktree: {x.path}",
    input_schema=EnterWorktreeInput,
    output_schema=EnterWorktreeOutput,
    call=enter_worktree_call,
    aliases=["enter_worktree", "worktree_enter"],
    is_read_only=lambda _: False,
    is_concurrency_safe=lambda _: False,
)

ExitWorktreeTool = build_tool(
    name="ExitWorktree",
    description=lambda x, o: "Exit worktree and return to main repo",
    input_schema=ExitWorktreeInput,
    output_schema=ExitWorktreeOutput,
    call=exit_worktree_call,
    aliases=["exit_worktree", "worktree_exit"],
    is_read_only=lambda _: True,
    is_concurrency_safe=lambda _: True,
)

ListWorktreesTool = build_tool(
    name="ListWorktrees",
    description=lambda x, o: "List all git worktrees",
    input_schema=ListWorktreesInput,
    output_schema=ListWorktreesOutput,
    call=list_worktrees_call,
    aliases=["worktrees", "list_worktrees"],
    is_read_only=lambda _: True,
    is_concurrency_safe=lambda _: True,
)

register_tool(EnterWorktreeTool)
register_tool(ExitWorktreeTool)
register_tool(ListWorktreesTool)
