"""Persistent agent memory management.

Reference: Claude Code src/tools/AgentTool/agentMemory.ts

Supports three scopes:
- user: Shared across all projects (~/.pilotcode/agent-memory/)
- project: Tied to current project (.pilotcode/agent-memory/)
- local: Project-local but not shared (.pilotcode/agent-memory-local/)
"""

import os
import json
from pathlib import Path
from typing import Callable
from datetime import datetime, timezone


def _get_agent_memory_dir(agent_type: str, scope: str = "project") -> Path:
    """Get the memory directory for an agent type and scope.

    Args:
        agent_type: The agent type (coder, debugger, etc.)
        scope: Memory scope - 'user', 'project', or 'local'

    Returns:
        Path to the agent memory directory
    """
    safe_type = agent_type.replace(":", "-").replace("/", "_")

    if scope == "user":
        base = Path.home() / ".pilotcode" / "agent-memory"
    elif scope == "local":
        base = Path.cwd() / ".pilotcode" / "agent-memory-local"
    else:
        base = Path.cwd() / ".pilotcode" / "agent-memory"

    return base / safe_type


def get_agent_memory_dir(agent_type: str, scope: str = "project") -> Path:
    """Public: get the memory directory for an agent type and scope."""
    return _get_agent_memory_dir(agent_type, scope)


def load_agent_memory_prompt(agent_type: str, scope: str = "project") -> str:
    """Load agent memory as a system prompt section.

    Reads the MEMORY.md file and returns it as a formatted string.
    Returns empty string if no memory file exists.

    Args:
        agent_type: The agent type
        scope: Memory scope

    Returns:
        Memory content as system prompt section, or empty string
    """
    mem_dir = _get_agent_memory_dir(agent_type, scope)
    mem_file = mem_dir / "MEMORY.md"

    if not mem_file.exists():
        return ""

    try:
        content = mem_file.read_text(encoding="utf-8").strip()
        if not content:
            return ""
        return f"\n## Agent Memory ({agent_type})\n{content}\n"
    except Exception:
        return ""


def save_agent_memory(
    agent_type: str,
    content: str,
    scope: str = "project",
    append: bool = False,
) -> bool:
    """Save content to agent memory.

    Args:
        agent_type: The agent type
        content: Memory content to save
        scope: Memory scope
        append: If True, append to existing memory instead of overwriting

    Returns:
        True if saved successfully
    """
    mem_dir = _get_agent_memory_dir(agent_type, scope)
    mem_dir.mkdir(parents=True, exist_ok=True)

    mem_file = mem_dir / "MEMORY.md"

    try:
        if append and mem_file.exists():
            existing = mem_file.read_text(encoding="utf-8").strip()
            timestamp = datetime.now(tz=timezone.utc).isoformat()
            content = f"{existing}\n\n--- [{timestamp}]\n{content}"

        mem_file.write_text(content.strip() + "\n", encoding="utf-8")
        return True
    except Exception:
        return False


def clear_agent_memory(agent_type: str, scope: str = "project") -> bool:
    """Clear agent memory file.

    Args:
        agent_type: The agent type
        scope: Memory scope

    Returns:
        True if cleared successfully
    """
    mem_dir = _get_agent_memory_dir(agent_type, scope)
    mem_file = mem_dir / "MEMORY.md"

    if mem_file.exists():
        try:
            mem_file.unlink()
            return True
        except Exception:
            return False
    return True


def has_agent_memory(agent_type: str, scope: str = "project") -> bool:
    """Check if agent has memory.

    Args:
        agent_type: The agent type
        scope: Memory scope

    Returns:
        True if memory file exists and is non-empty
    """
    mem_dir = _get_agent_memory_dir(agent_type, scope)
    mem_file = mem_dir / "MEMORY.md"
    return mem_file.exists() and mem_file.stat().st_size > 0


def is_agent_memory_path(path: str) -> bool:
    """Check if a path is an agent memory path.

    Used for security validation.

    Args:
        path: File path to check

    Returns:
        True if the path is within an agent memory directory
    """
    p = Path(path).resolve()
    memory_bases = [
        Path.home() / ".pilotcode" / "agent-memory",
        Path.cwd() / ".pilotcode" / "agent-memory",
        Path.cwd() / ".pilotcode" / "agent-memory-local",
    ]
    for base in memory_bases:
        try:
            base_resolved = base.resolve()
            if base_resolved in p.parents or p == base_resolved:
                return True
        except Exception:
            continue
    return False


# =============================================================================
# Memory Snapshot support (project-level memory initialization)
# =============================================================================


def _get_snapshot_dir(agent_type: str) -> Path:
    """Get the snapshot directory for an agent type."""
    safe_type = agent_type.replace(":", "-").replace("/", "_")
    return Path.cwd() / ".pilotcode" / "agent-memory-snapshots" / safe_type


def check_agent_memory_snapshot(agent_type: str) -> bool:
    """Check if a newer memory snapshot exists.

    Args:
        agent_type: The agent type

    Returns:
        True if a snapshot exists that is newer than local memory
    """
    snapshot_dir = _get_snapshot_dir(agent_type)
    if not snapshot_dir.exists():
        return False

    snapshot_files = list(snapshot_dir.glob("*.md"))
    if not snapshot_files:
        return False

    local_dir = _get_agent_memory_dir(agent_type, "local")
    local_file = local_dir / "MEMORY.md"

    if not local_file.exists():
        return True

    latest_snapshot = max(snapshot_files, key=lambda f: f.stat().st_mtime)
    return latest_snapshot.stat().st_mtime > local_file.stat().st_mtime


def initialize_from_snapshot(agent_type: str) -> bool:
    """Initialize local memory from the latest snapshot.

    Args:
        agent_type: The agent type

    Returns:
        True if initialized successfully
    """
    snapshot_dir = _get_snapshot_dir(agent_type)
    if not snapshot_dir.exists():
        return False

    snapshot_files = sorted(snapshot_dir.glob("*.md"), key=lambda f: f.stat().st_mtime)
    if not snapshot_files:
        return False

    latest = snapshot_files[-1]
    content = latest.read_text(encoding="utf-8")
    return save_agent_memory(agent_type, content, scope="local")


# =============================================================================
# Memory-scoped tool wrapper
# =============================================================================


def create_memory_file_can_use_tool(memory_file_path: str) -> Callable[[str], bool]:
    """Create a can_use_tool function that only allows editing the memory file.

    Used for session memory extraction to prevent the LLM from writing elsewhere.

    Args:
        memory_file_path: The exact path the LLM is allowed to edit

    Returns:
        A callable that returns True only for the memory file path
    """
    allowed_path = Path(memory_file_path).resolve()

    def can_use_tool(tool_name: str, tool_input: dict) -> bool:
        if tool_name in ("FileWrite", "FileEdit"):
            file_path = tool_input.get("path", "")
            resolved = Path(file_path).resolve()
            return resolved == allowed_path
        if tool_name in ("FileRead",):
            file_path = tool_input.get("path", "")
            resolved = Path(file_path).resolve()
            return is_agent_memory_path(str(resolved)) or resolved == allowed_path
        return False

    return can_use_tool
