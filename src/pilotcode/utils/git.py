"""Git utility functions."""

from __future__ import annotations

import asyncio
import subprocess
from dataclasses import dataclass
from typing import Optional


@dataclass
class GitExecResult:
    """Result of a git command execution."""

    returncode: int
    stdout: str
    stderr: str


@dataclass
class RepoInfo:
    """Repository information."""

    is_git_repo: bool
    root_path: Optional[str] = None
    current_branch: Optional[str] = None
    default_branch: str = "main"
    remote_url: Optional[str] = None
    github_owner: Optional[str] = None
    github_repo: Optional[str] = None


async def git_exec(args: list[str], cwd: Optional[str] = None) -> GitExecResult:
    """Execute a git command asynchronously.

    Args:
        args: Git command arguments (without 'git' prefix)
        cwd: Working directory (default: current directory)

    Returns:
        GitExecResult with returncode, stdout, and stderr
    """
    cmd = ["git"] + args

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=cwd,
        )

        stdout, stderr = await proc.communicate()

        return GitExecResult(
            returncode=proc.returncode,
            stdout=stdout.decode("utf-8", errors="replace").strip(),
            stderr=stderr.decode("utf-8", errors="replace").strip(),
        )

    except Exception as e:
        return GitExecResult(
            returncode=1,
            stdout="",
            stderr=str(e),
        )


def git_exec_sync(args: list[str], cwd: Optional[str] = None) -> GitExecResult:
    """Execute a git command synchronously.

    Args:
        args: Git command arguments (without 'git' prefix)
        cwd: Working directory (default: current directory)

    Returns:
        GitExecResult with returncode, stdout, and stderr
    """
    cmd = ["git"] + args

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=cwd,
        )

        return GitExecResult(
            returncode=result.returncode,
            stdout=result.stdout.strip(),
            stderr=result.stderr.strip(),
        )

    except Exception as e:
        return GitExecResult(
            returncode=1,
            stdout="",
            stderr=str(e),
        )


async def get_current_branch(cwd: Optional[str] = None) -> str:
    """Get the current git branch name.

    Args:
        cwd: Working directory

    Returns:
        Branch name or "HEAD" if detached
    """
    result = await git_exec(["rev-parse", "--abbrev-ref", "HEAD"], cwd=cwd)

    if result.returncode == 0:
        return result.stdout or "HEAD"

    return "HEAD"


def get_current_branch_sync(cwd: Optional[str] = None) -> str:
    """Get the current git branch name synchronously.

    Args:
        cwd: Working directory

    Returns:
        Branch name or "HEAD" if detached
    """
    result = git_exec_sync(["rev-parse", "--abbrev-ref", "HEAD"], cwd=cwd)

    if result.returncode == 0:
        return result.stdout or "HEAD"

    return "HEAD"


async def is_git_repository(cwd: Optional[str] = None) -> bool:
    """Check if the directory is a git repository.

    Args:
        cwd: Working directory

    Returns:
        True if directory is a git repository
    """
    result = await git_exec(["rev-parse", "--git-dir"], cwd=cwd)
    return result.returncode == 0


def is_git_repository_sync(cwd: Optional[str] = None) -> bool:
    """Check if the directory is a git repository synchronously.

    Args:
        cwd: Working directory

    Returns:
        True if directory is a git repository
    """
    result = git_exec_sync(["rev-parse", "--git-dir"], cwd=cwd)
    return result.returncode == 0


async def get_repo_root(cwd: Optional[str] = None) -> Optional[str]:
    """Get the root path of the git repository.

    Args:
        cwd: Working directory

    Returns:
        Repository root path or None if not a git repo
    """
    result = await git_exec(["rev-parse", "--show-toplevel"], cwd=cwd)

    if result.returncode == 0:
        return result.stdout

    return None


def get_repo_root_sync(cwd: Optional[str] = None) -> Optional[str]:
    """Get the root path of the git repository synchronously.

    Args:
        cwd: Working directory

    Returns:
        Repository root path or None if not a git repo
    """
    result = git_exec_sync(["rev-parse", "--show-toplevel"], cwd=cwd)

    if result.returncode == 0:
        return result.stdout

    return None


async def get_remote_url(remote: str = "origin", cwd: Optional[str] = None) -> Optional[str]:
    """Get the URL of a remote.

    Args:
        remote: Remote name (default: origin)
        cwd: Working directory

    Returns:
        Remote URL or None
    """
    result = await git_exec(["remote", "get-url", remote], cwd=cwd)

    if result.returncode == 0:
        return result.stdout

    return None


def get_remote_url_sync(remote: str = "origin", cwd: Optional[str] = None) -> Optional[str]:
    """Get the URL of a remote synchronously.

    Args:
        remote: Remote name (default: origin)
        cwd: Working directory

    Returns:
        Remote URL or None
    """
    result = git_exec_sync(["remote", "get-url", remote], cwd=cwd)

    if result.returncode == 0:
        return result.stdout

    return None


def parse_github_remote(url: Optional[str]) -> tuple[Optional[str], Optional[str]]:
    """Parse GitHub owner and repo from remote URL.

    Args:
        url: Git remote URL

    Returns:
        Tuple of (owner, repo) or (None, None)
    """
    if not url:
        return None, None

    # Handle HTTPS: https://github.com/owner/repo.git
    # Handle SSH: git@github.com:owner/repo.git

    import re

    # HTTPS format
    https_match = re.match(r"https?://github\.com/([^/]+)/([^/]+?)(?:\.git)?$", url)
    if https_match:
        return https_match.group(1), https_match.group(2)

    # SSH format
    ssh_match = re.match(r"git@github\.com:([^/]+)/([^/]+?)(?:\.git)?$", url)
    if ssh_match:
        return ssh_match.group(1), ssh_match.group(2)

    return None, None


async def get_default_branch(cwd: Optional[str] = None) -> str:
    """Get the default branch name (main or master).

    Args:
        cwd: Working directory

    Returns:
        Default branch name
    """
    # Try to get from remote
    result = await git_exec(["symbolic-ref", "refs/remotes/origin/HEAD"], cwd=cwd)

    if result.returncode == 0:
        # refs/remotes/origin/main -> main
        return result.stdout.split("/")[-1]

    # Check if main exists
    result = await git_exec(["show-ref", "--verify", "refs/heads/main"], cwd=cwd)
    if result.returncode == 0:
        return "main"

    # Check if master exists
    result = await git_exec(["show-ref", "--verify", "refs/heads/master"], cwd=cwd)
    if result.returncode == 0:
        return "master"

    return "main"  # Default to main


async def get_repo_info(cwd: Optional[str] = None) -> RepoInfo:
    """Get comprehensive repository information.

    Args:
        cwd: Working directory

    Returns:
        RepoInfo with repository details
    """
    # Check if git repo
    root = await get_repo_root(cwd)
    if not root:
        return RepoInfo(is_git_repo=False)

    # Get basic info
    current_branch = await get_current_branch(root)
    default_branch = await get_default_branch(root)
    remote_url = await get_remote_url("origin", root)
    github_owner, github_repo = parse_github_remote(remote_url)

    return RepoInfo(
        is_git_repo=True,
        root_path=root,
        current_branch=current_branch,
        default_branch=default_branch,
        remote_url=remote_url,
        github_owner=github_owner,
        github_repo=github_repo,
    )


def get_repo_info_sync(cwd: Optional[str] = None) -> RepoInfo:
    """Get comprehensive repository information synchronously.

    Args:
        cwd: Working directory

    Returns:
        RepoInfo with repository details
    """
    # Check if git repo
    root = get_repo_root_sync(cwd)
    if not root:
        return RepoInfo(is_git_repo=False)

    # Get basic info
    current_branch = get_current_branch_sync(root)
    remote_url = get_remote_url_sync("origin", root)
    github_owner, github_repo = parse_github_remote(remote_url)

    # Try to determine default branch
    result = git_exec_sync(["symbolic-ref", "refs/remotes/origin/HEAD"], cwd=root)
    if result.returncode == 0:
        default_branch = result.stdout.split("/")[-1]
    else:
        # Check if main exists
        result = git_exec_sync(["show-ref", "--verify", "refs/heads/main"], cwd=root)
        default_branch = "main" if result.returncode == 0 else "master"

    return RepoInfo(
        is_git_repo=True,
        root_path=root,
        current_branch=current_branch,
        default_branch=default_branch,
        remote_url=remote_url,
        github_owner=github_owner,
        github_repo=github_repo,
    )


async def has_uncommitted_changes(cwd: Optional[str] = None) -> bool:
    """Check if there are uncommitted changes.

    Args:
        cwd: Working directory

    Returns:
        True if there are uncommitted changes
    """
    result = await git_exec(["status", "--porcelain"], cwd=cwd)
    return bool(result.stdout.strip())


def has_uncommitted_changes_sync(cwd: Optional[str] = None) -> bool:
    """Check if there are uncommitted changes synchronously.

    Args:
        cwd: Working directory

    Returns:
        True if there are uncommitted changes
    """
    result = git_exec_sync(["status", "--porcelain"], cwd=cwd)
    return bool(result.stdout.strip())


async def get_last_commit_message(cwd: Optional[str] = None) -> Optional[str]:
    """Get the last commit message.

    Args:
        cwd: Working directory

    Returns:
        Last commit message or None
    """
    result = await git_exec(["log", "-1", "--pretty=%B"], cwd=cwd)

    if result.returncode == 0:
        return result.stdout

    return None


def get_last_commit_message_sync(cwd: Optional[str] = None) -> Optional[str]:
    """Get the last commit message synchronously.

    Args:
        cwd: Working directory

    Returns:
        Last commit message or None
    """
    result = git_exec_sync(["log", "-1", "--pretty=%B"], cwd=cwd)

    if result.returncode == 0:
        return result.stdout

    return None
