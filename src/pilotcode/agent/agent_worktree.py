"""Agent worktree isolation.

Reference: Claude Code src/utils/worktree.ts

Provides isolated git worktrees for agent execution so agents can
safely modify files without affecting the main working tree.
"""

import os
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Any
from datetime import datetime, timezone, timedelta

# Validation: only allow safe characters in worktree slugs
_WORKTREE_SLUG_RE = re.compile(r"^[a-zA-Z0-9._-]+$")


def find_canonical_git_root(path: str | None = None) -> str | None:
    """Find the canonical git root directory.

    This ensures agent worktrees are always created in the main repo root,
    not in nested worktrees.

    Args:
        path: Starting path, defaults to cwd

    Returns:
        Canonical git root path, or None if not in a git repo
    """
    target = path or os.getcwd()
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-superproject-working-tree"],
            capture_output=True,
            text=True,
            cwd=target,
            timeout=10,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()

        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            cwd=target,
            timeout=10,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass
    return None


def is_git_repo(path: str | None = None) -> bool:
    """Check if path is in a git repository."""
    return find_canonical_git_root(path) is not None


def validate_slug(slug: str) -> bool:
    """Validate a worktree slug.

    Args:
        slug: The slug to validate

    Returns:
        True if the slug is valid
    """
    if not slug:
        return False
    if len(slug) > 100:
        return False
    if ".." in slug:
        return False
    return bool(_WORKTREE_SLUG_RE.match(slug))


def get_worktrees_dir() -> Path:
    """Get the worktrees directory."""
    return Path.cwd() / ".pilotcode" / "worktrees"


def create_agent_worktree(slug: str) -> dict[str, Any] | None:
    """Create a git worktree for an agent.

    Args:
        slug: Unique worktree slug (e.g., "agent-a1b2c3d4")

    Returns:
        Dict with worktree info, or None on failure:
        {
            "worktree_path": str,
            "branch": str,
            "head_commit": str,
            "git_root": str,
        }
    """
    if not validate_slug(slug):
        return None

    git_root = find_canonical_git_root()
    if not git_root:
        return None

    worktrees_dir = get_worktrees_dir()
    worktree_path = worktrees_dir / slug
    branch_name = f"worktree-{slug}"

    try:
        worktrees_dir.mkdir(parents=True, exist_ok=True)

        subprocess.run(
            ["git", "worktree", "add", "-b", branch_name, str(worktree_path), "HEAD"],
            capture_output=True,
            text=True,
            cwd=git_root,
            timeout=30,
            check=True,
        )

        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            cwd=git_root,
            timeout=10,
            check=True,
        )
        head_commit = result.stdout.strip()

        return {
            "worktree_path": str(worktree_path),
            "branch": branch_name,
            "head_commit": head_commit,
            "git_root": git_root,
        }
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError):
        return None


def remove_agent_worktree(slug: str) -> bool:
    """Remove an agent worktree.

    Args:
        slug: Worktree slug

    Returns:
        True if removed successfully
    """
    if not validate_slug(slug):
        return False

    git_root = find_canonical_git_root()
    if not git_root:
        return False

    worktrees_dir = get_worktrees_dir()
    worktree_path = worktrees_dir / slug
    branch_name = f"worktree-{slug}"

    if not worktree_path.exists():
        return True

    try:
        # Remove worktree
        subprocess.run(
            ["git", "worktree", "remove", "--force", str(worktree_path)],
            capture_output=True,
            text=True,
            cwd=git_root,
            timeout=30,
        )

        # Delete branch
        subprocess.run(
            ["git", "branch", "-D", branch_name],
            capture_output=True,
            text=True,
            cwd=git_root,
            timeout=10,
        )

        # Prune worktree metadata
        subprocess.run(
            ["git", "worktree", "prune"],
            capture_output=True,
            text=True,
            cwd=git_root,
            timeout=10,
        )

        return True
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False


def has_worktree_changes(slug: str) -> bool:
    """Check if an agent worktree has changes.

    Args:
        slug: Worktree slug

    Returns:
        True if there are uncommitted changes or new commits
    """
    if not validate_slug(slug):
        return False

    worktrees_dir = get_worktrees_dir()
    worktree_path = worktrees_dir / slug

    if not worktree_path.exists():
        return False

    try:
        # Check for uncommitted changes
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            capture_output=True,
            text=True,
            cwd=str(worktree_path),
            timeout=10,
        )
        if result.stdout.strip():
            return True

        # Check for new commits ahead of base branch
        result = subprocess.run(
            ["git", "rev-list", "HEAD..@", "--count"],
            capture_output=True,
            text=True,
            cwd=str(worktree_path),
            timeout=10,
        )
        commits_ahead = result.stdout.strip()
        return commits_ahead and int(commits_ahead) > 0
    except (subprocess.TimeoutExpired, FileNotFoundError, ValueError):
        return True  # Fail closed: assume changes on error


def cleanup_stale_agent_worktrees(max_age_days: int = 30) -> int:
    """Clean up stale agent worktrees.

    Removes worktrees older than max_age_days matching ephemeral patterns.

    Args:
        max_age_days: Maximum age in days before cleanup

    Returns:
        Number of worktrees cleaned up
    """
    worktrees_dir = get_worktrees_dir()
    if not worktrees_dir.exists():
        return 0

    cutoff = datetime.now(tz=timezone.utc) - timedelta(days=max_age_days)
    cleaned = 0

    for entry in worktrees_dir.iterdir():
        if not entry.is_dir():
            continue
        # Match ephemeral worktree patterns
        if not entry.name.startswith(("agent-", "wf_", "task-")):
            continue

        try:
            mtime = datetime.fromtimestamp(entry.stat().st_mtime, tz=timezone.utc)
            if mtime < cutoff:
                if remove_agent_worktree(entry.name):
                    cleaned += 1
        except Exception:
            continue

    return cleaned


def read_worktree_head_sha(slug: str) -> str | None:
    """Read the current HEAD SHA of an agent worktree.

    Reads .git pointer file directly for fast access.

    Args:
        slug: Worktree slug

    Returns:
        HEAD commit SHA, or None
    """
    if not validate_slug(slug):
        return None

    worktrees_dir = get_worktrees_dir()
    worktree_path = worktrees_dir / slug
    head_file = worktree_path / ".git" / "HEAD"

    if not head_file.exists():
        return None

    try:
        content = head_file.read_text().strip()
        if content.startswith("ref: "):
            ref = content[5:]
            ref_file = worktree_path / ".git" / ref
            if ref_file.exists():
                return ref_file.read_text().strip()
        return content
    except Exception:
        return None


def build_worktree_notice(worktree_path: str, branch: str) -> str:
    """Build a notice for fork children about worktree paths.

    Args:
        worktree_path: The worktree path
        branch: The branch name

    Returns:
        Notice string to include in prompt
    """
    return (
        f"\n<worktree-notice>\n"
        f"You are running in an isolated git worktree.\n"
        f"Worktree path: {worktree_path}\n"
        f"Branch: {branch}\n"
        f"Use absolute paths from the worktree root.\n"
        f"</worktree-notice>"
    )
