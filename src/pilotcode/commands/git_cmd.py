"""Git command router - all git operations under /git."""

import subprocess

from .base import CommandHandler, register_command, CommandContext

# Import all git sub-command handlers (modules no longer self-register)
from .branch_cmd import branch_command
from .commit_cmd import commit_command
from .diff_cmd import diff_command
from .switch_cmd import switch_command
from .blame_cmd import blame_command
from .cherrypick_cmd import cherrypick_command
from .bisect_cmd import bisect_command
from .revert_cmd import revert_command
from .reset_cmd import reset_command
from .clean_cmd import clean_command
from .history_cmd import history_command
from .git_commands import (
    merge_command,
    rebase_command,
    stash_command,
    tag_command,
    pr_command,
    issue_command,
    fetch_command,
    pull_command,
    push_command,
)
from .remote_cmd import remote_command


async def git_command(args: list[str], context: CommandContext) -> str:
    """Handle /git <subcommand> [...].

    Examples:
      /git                → git status
      /git branch         → list branches
      /git branch feat    → create branch
      /git commit "msg"   → commit
      /git diff           → show diff
      /git stash list     → list stashes
      /git pr list        → list pull requests
    """
    if not args:
        return await _git_status(context)

    sub = args[0]
    sub_args = args[1:]

    if sub in ("help", "-h", "--help"):
        return _git_help()

    handlers = {
        "status": _git_status,
        "st": _git_status,
        "branch": branch_command,
        "br": branch_command,
        "commit": commit_command,
        "ci": commit_command,
        "diff": diff_command,
        "switch": switch_command,
        "sw": switch_command,
        "merge": merge_command,
        "rebase": rebase_command,
        "stash": stash_command,
        "tag": tag_command,
        "remote": remote_command,
        "blame": blame_command,
        "cherrypick": cherrypick_command,
        "cherry-pick": cherrypick_command,
        "bisect": bisect_command,
        "revert": revert_command,
        "reset": reset_command,
        "clean": clean_command,
        "history": history_command,
        "hist": history_command,
        "log": history_command,
        "pr": pr_command,
        "issue": issue_command,
        "fetch": fetch_command,
        "pull": pull_command,
        "push": push_command,
    }

    handler = handlers.get(sub)
    if handler:
        return await handler(sub_args, context)

    # Fallback: run as raw git command
    try:
        result = subprocess.run(
            ["git", sub] + sub_args,
            capture_output=True,
            text=True,
            errors="replace",
            cwd=context.cwd,
        )
        if result.returncode == 0:
            return result.stdout or f"git {sub} completed."
        return f"git {sub} failed: {result.stderr}"
    except Exception as e:
        return f"Error running git {sub}: {e}"


async def _git_status(context: CommandContext) -> str:
    """Show git status."""
    try:
        result = subprocess.run(
            ["git", "status", "-sb"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            cwd=context.cwd,
        )
        if result.returncode == 0:
            return f"Git status:\n{result.stdout}"
        return f"Not a git repository or error: {result.stderr}"
    except Exception as e:
        return f"Error: {e}"


def _git_help() -> str:
    """Return help text for /git subcommands."""
    return """Git operations - available subcommands:

  status (st)      - Show working tree status
  branch (br)      - List or create branches
  commit (ci)      - Commit changes
  diff             - Show changes
  switch (sw)      - Switch branches
  merge            - Merge a branch
  rebase           - Rebase current branch
  stash            - Stash changes
  tag              - Manage tags
  remote           - Manage remotes
  blame            - Show line annotations
  cherrypick       - Apply commits
  bisect           - Binary search for bugs
  revert           - Revert commits
  reset            - Reset state
  clean            - Remove untracked files
  history (hist)   - Show commit history
  log              - Alias for history
  pr               - Pull request operations
  issue            - Issue operations
  fetch            - Download from remote
  pull             - Fetch and merge
  push             - Upload to remote

Usage: /git <subcommand> [options]
Example: /git branch -a"""


register_command(
    CommandHandler(
        name="git",
        description="Git operations",
        handler=git_command,
        aliases=["g"],
    )
)
