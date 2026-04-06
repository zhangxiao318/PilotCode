"""Git tools for version control operations."""

import subprocess
from typing import Any
from pydantic import BaseModel, Field

from .base import Tool, ToolResult, ToolUseContext, build_tool
from .registry import register_tool


class GitStatusInput(BaseModel):
    """Input for GitStatus tool."""

    path: str = Field(default=".", description="Repository path")


class GitStatusOutput(BaseModel):
    """Output from GitStatus tool."""

    branch: str
    is_clean: bool
    modified: list[str]
    staged: list[str]
    untracked: list[str]
    ahead: int = 0
    behind: int = 0


def run_git_command(args: list[str], cwd: str = ".") -> tuple[int, str, str]:
    """Run a git command."""
    try:
        result = subprocess.run(["git"] + args, capture_output=True, cwd=cwd)
        # Try UTF-8 first, then fallback to system encoding (for Windows compatibility)
        try:
            stdout = result.stdout.decode("utf-8")
            stderr = result.stderr.decode("utf-8")
        except UnicodeDecodeError:
            import sys

            # Fallback to system default encoding with error handling
            stdout = result.stdout.decode(sys.getdefaultencoding(), errors="replace")
            stderr = result.stderr.decode(sys.getdefaultencoding(), errors="replace")
        return result.returncode, stdout, stderr
    except Exception as e:
        return -1, "", str(e)


async def git_status_call(
    input_data: GitStatusInput,
    context: ToolUseContext,
    can_use_tool: Any,
    parent_message: Any,
    on_progress: Any,
) -> ToolResult[GitStatusOutput]:
    """Get git status."""
    # Get branch
    rc, stdout, stderr = run_git_command(["branch", "--show-current"], input_data.path)
    branch = stdout.strip() if rc == 0 else "unknown"

    # Get status
    rc, stdout, stderr = run_git_command(["status", "--porcelain"], input_data.path)

    modified = []
    staged = []
    untracked = []

    if rc == 0:
        for line in stdout.split("\n"):
            if not line:
                continue
            status = line[:2]
            filename = line[3:]

            if status[0] in "MADRC":
                staged.append(filename)
            if status[1] in "MD":
                modified.append(filename)
            if status == "??":
                untracked.append(filename)

    # Check ahead/behind
    rc, stdout, stderr = run_git_command(
        ["rev-list", "--left-right", "--count", f"HEAD...{branch}@{{u}}"], input_data.path
    )
    ahead = behind = 0
    if rc == 0:
        parts = stdout.strip().split()
        if len(parts) == 2:
            ahead = int(parts[0])
            behind = int(parts[1])

    return ToolResult(
        data=GitStatusOutput(
            branch=branch,
            is_clean=len(modified) == 0 and len(staged) == 0 and len(untracked) == 0,
            modified=modified,
            staged=staged,
            untracked=untracked,
            ahead=ahead,
            behind=behind,
        )
    )


class GitDiffInput(BaseModel):
    """Input for GitDiff tool."""

    path: str = Field(default=".", description="Repository path")
    file: str | None = Field(default=None, description="Specific file to diff")
    staged: bool = Field(default=False, description="Show staged changes")


class GitDiffOutput(BaseModel):
    """Output from GitDiff tool."""

    diff: str
    file_count: int


async def git_diff_call(
    input_data: GitDiffInput,
    context: ToolUseContext,
    can_use_tool: Any,
    parent_message: Any,
    on_progress: Any,
) -> ToolResult[GitDiffOutput]:
    """Get git diff."""
    args = ["diff"]
    if input_data.staged:
        args.append("--staged")
    if input_data.file:
        args.append(input_data.file)

    rc, stdout, stderr = run_git_command(args, input_data.path)

    if rc != 0:
        return ToolResult(data=GitDiffOutput(diff="", file_count=0), error=stderr)

    # Count files in diff
    file_count = stdout.count("diff --git")

    # Truncate if too long
    diff = stdout
    if len(diff) > 10000:
        diff = diff[:10000] + "\n... (diff truncated)"

    return ToolResult(data=GitDiffOutput(diff=diff, file_count=file_count))


class GitLogInput(BaseModel):
    """Input for GitLog tool."""

    path: str = Field(default=".", description="Repository path")
    max_count: int = Field(default=10, description="Maximum commits to show")
    file: str | None = Field(default=None, description="Filter by file")


class GitCommit(BaseModel):
    """Git commit info."""

    hash: str
    short_hash: str
    author: str
    date: str
    message: str


class GitLogOutput(BaseModel):
    """Output from GitLog tool."""

    commits: list[GitCommit]
    total: int


async def git_log_call(
    input_data: GitLogInput,
    context: ToolUseContext,
    can_use_tool: Any,
    parent_message: Any,
    on_progress: Any,
) -> ToolResult[GitLogOutput]:
    """Get git log."""
    args = [
        "log",
        f"--max-count={input_data.max_count}",
        "--pretty=format:%H|%h|%an|%ad|%s",
        "--date=short",
    ]

    if input_data.file:
        args.append("--")
        args.append(input_data.file)

    rc, stdout, stderr = run_git_command(args, input_data.path)

    if rc != 0:
        return ToolResult(data=GitLogOutput(commits=[], total=0), error=stderr)

    commits = []
    for line in stdout.strip().split("\n"):
        if not line:
            continue
        parts = line.split("|", 4)
        if len(parts) >= 5:
            commits.append(
                GitCommit(
                    hash=parts[0],
                    short_hash=parts[1],
                    author=parts[2],
                    date=parts[3],
                    message=parts[4],
                )
            )

    return ToolResult(data=GitLogOutput(commits=commits, total=len(commits)))


class GitBranchInput(BaseModel):
    """Input for GitBranch tool."""

    path: str = Field(default=".", description="Repository path")
    action: str = Field(default="list", description="Action: list, create, delete, switch")
    branch_name: str | None = Field(
        default=None, description="Branch name for create/delete/switch"
    )


class GitBranchOutput(BaseModel):
    """Output from GitBranch tool."""

    action: str
    branches: list[str] | None = None
    current: str | None = None
    message: str


async def git_branch_call(
    input_data: GitBranchInput,
    context: ToolUseContext,
    can_use_tool: Any,
    parent_message: Any,
    on_progress: Any,
) -> ToolResult[GitBranchOutput]:
    """Manage git branches."""
    if input_data.action == "list":
        rc, stdout, stderr = run_git_command(["branch", "-a"], input_data.path)

        if rc != 0:
            return ToolResult(data=GitBranchOutput(action="list", message=""), error=stderr)

        branches = []
        current = None
        for line in stdout.split("\n"):
            line = line.strip()
            if not line:
                continue
            if line.startswith("*"):
                current = line[2:]
                branches.append(current)
            else:
                branches.append(line)

        return ToolResult(
            data=GitBranchOutput(
                action="list",
                branches=branches,
                current=current,
                message=f"Found {len(branches)} branches",
            )
        )

    elif input_data.action == "create":
        if not input_data.branch_name:
            return ToolResult(
                data=GitBranchOutput(action="create", message=""), error="Branch name required"
            )

        rc, stdout, stderr = run_git_command(["branch", input_data.branch_name], input_data.path)

        return ToolResult(
            data=GitBranchOutput(
                action="create",
                message=f"Created branch: {input_data.branch_name}" if rc == 0 else stderr,
            )
        )

    elif input_data.action == "switch":
        if not input_data.branch_name:
            return ToolResult(
                data=GitBranchOutput(action="switch", message=""), error="Branch name required"
            )

        rc, stdout, stderr = run_git_command(["switch", input_data.branch_name], input_data.path)

        return ToolResult(
            data=GitBranchOutput(
                action="switch",
                message=f"Switched to: {input_data.branch_name}" if rc == 0 else stderr,
            )
        )

    else:
        return ToolResult(
            data=GitBranchOutput(action=input_data.action, message=""),
            error=f"Unknown action: {input_data.action}",
        )


# Register Git tools
GitStatusTool = build_tool(
    name="GitStatus",
    description=lambda x, o: f"Git status for {x.path}",
    input_schema=GitStatusInput,
    output_schema=GitStatusOutput,
    call=git_status_call,
    aliases=["git_status", "gst"],
    is_read_only=lambda _: True,
    is_concurrency_safe=lambda _: True,
)

GitDiffTool = build_tool(
    name="GitDiff",
    description=lambda x, o: f"Git diff{' --staged' if x.staged else ''}",
    input_schema=GitDiffInput,
    output_schema=GitDiffOutput,
    call=git_diff_call,
    aliases=["git_diff", "gd"],
    is_read_only=lambda _: True,
    is_concurrency_safe=lambda _: True,
)

GitLogTool = build_tool(
    name="GitLog",
    description=lambda x, o: f"Git log ({x.max_count} commits)",
    input_schema=GitLogInput,
    output_schema=GitLogOutput,
    call=git_log_call,
    aliases=["git_log", "gl"],
    is_read_only=lambda _: True,
    is_concurrency_safe=lambda _: True,
)

GitBranchTool = build_tool(
    name="GitBranch",
    description=lambda x, o: f"Git branch {x.action}",
    input_schema=GitBranchInput,
    output_schema=GitBranchOutput,
    call=git_branch_call,
    aliases=["git_branch", "gb"],
    is_read_only=lambda x: x.action == "list" if x else True,
    is_concurrency_safe=lambda x: x.action == "list" if x else True,
)

register_tool(GitStatusTool)
register_tool(GitDiffTool)
register_tool(GitLogTool)
register_tool(GitBranchTool)
