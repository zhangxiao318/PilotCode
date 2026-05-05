"""Agent-to-agent communication via file-based mailbox protocol.

Reference: Claude Code src/utils/teammateMailbox.ts

Each agent/teammate has an inbox at .pilotcode/teams/{team_name}/inboxes/{agent_name}.json
Messages are written using file locking for safe concurrent access.
"""

import json
import time
import fcntl
from pathlib import Path
from typing import Any
from datetime import datetime, timezone

# Structured message types
MSG_TYPES = {
    "TEXT": "text",
    "SHUTDOWN_REQUEST": "shutdown_request",
    "SHUTDOWN_RESPONSE": "shutdown_response",
    "PLAN_APPROVAL_REQUEST": "plan_approval_request",
    "PLAN_APPROVAL_RESPONSE": "plan_approval_response",
    "PERMISSION_REQUEST": "permission_request",
    "PERMISSION_RESPONSE": "permission_response",
    "TASK_NOTIFICATION": "task_notification",
}


def _get_inbox_dir(team_name: str) -> Path:
    """Get the inbox directory for a team."""
    return Path.cwd() / ".pilotcode" / "teams" / team_name / "inboxes"


def _get_inbox_path(agent_name: str, team_name: str) -> Path:
    """Get the inbox file path for an agent."""
    return _get_inbox_dir(team_name) / f"{agent_name}.json"


def _lock_file(fd: int, exclusive: bool = True):
    """Acquire a file lock.

    Args:
        fd: File descriptor
        exclusive: True for exclusive lock, False for shared

    Raises:
        BlockingIOError if lock cannot be acquired within timeout
    """
    lock_type = fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH
    fcntl.flock(fd, lock_type | fcntl.LOCK_NB)


def _unlock_file(fd: int):
    """Release a file lock."""
    fcntl.flock(fd, fcntl.LOCK_UN)


def write_to_mailbox(
    recipient: str,
    team_name: str,
    message: dict[str, Any],
) -> bool:
    """Write a message to an agent's mailbox.

    Uses file locking for concurrent writer safety.

    Args:
        recipient: Recipient agent name
        team_name: Team name
        message: Message dict with at minimum: from, text

    Returns:
        True if written successfully
    """
    inbox_dir = _get_inbox_dir(team_name)
    inbox_dir.mkdir(parents=True, exist_ok=True)

    inbox_path = _get_inbox_path(recipient, team_name)

    # Read existing messages
    messages: list[dict] = []
    if inbox_path.exists():
        try:
            with open(inbox_path, "r") as f:
                _lock_file(f.fileno(), exclusive=False)
                data = json.load(f)
                messages = data if isinstance(data, list) else []
                _unlock_file(f.fileno())
        except (json.JSONDecodeError, Exception):
            messages = []

    # Add new message
    msg = {
        **message,
        "timestamp": datetime.now(tz=timezone.utc).isoformat(),
    }
    messages.append(msg)

    # Write back with exclusive lock
    try:
        with open(inbox_path, "w") as f:
            _lock_file(f.fileno(), exclusive=True)
            json.dump(messages, f, indent=2)
            _unlock_file(f.fileno())
        return True
    except Exception:
        return False


def read_unread_messages(
    agent_name: str,
    team_name: str,
    clear_after_read: bool = True,
) -> list[dict[str, Any]]:
    """Read all pending messages for an agent.

    Args:
        agent_name: Agent name
        team_name: Team name
        clear_after_read: If True, clear the mailbox after reading

    Returns:
        List of messages
    """
    inbox_path = _get_inbox_path(agent_name, team_name)
    if not inbox_path.exists():
        return []

    messages: list[dict] = []
    try:
        with open(inbox_path, "r") as f:
            _lock_file(f.fileno(), exclusive=False)
            data = json.load(f)
            messages = data if isinstance(data, list) else []
            _unlock_file(f.fileno())
    except (json.JSONDecodeError, Exception):
        return []

    if clear_after_read:
        try:
            with open(inbox_path, "w") as f:
                _lock_file(f.fileno(), exclusive=True)
                json.dump([], f)
                _unlock_file(f.fileno())
        except Exception:
            pass

    return messages


def broadcast_to_team(
    team_name: str,
    exclude: str | None,
    message: dict[str, Any],
) -> int:
    """Broadcast a message to all team members.

    Args:
        team_name: Team name
        exclude: Agent name to exclude (sender)
        message: Message dict

    Returns:
        Number of recipients the message was sent to
    """
    team_file = Path.cwd() / ".pilotcode" / "teams" / f"{team_name}.json"
    if not team_file.exists():
        return 0

    try:
        team_data = json.loads(team_file.read_text())
        members = team_data.get("members", [])
    except Exception:
        return 0

    count = 0
    for member in members:
        if exclude and member == exclude:
            continue
        if write_to_mailbox(member, team_name, message):
            count += 1

    return count


def get_team_info(team_name: str) -> dict[str, Any] | None:
    """Get team information.

    Args:
        team_name: Team name

    Returns:
        Team info dict, or None if not found
    """
    team_file = Path.cwd() / ".pilotcode" / "teams" / f"{team_name}.json"
    if not team_file.exists():
        return None

    try:
        return json.loads(team_file.read_text())
    except Exception:
        return None


def create_team(team_name: str, lead_agent: str, members: list[str]) -> bool:
    """Create a new team.

    Args:
        team_name: Team name
        lead_agent: Lead agent ID
        members: List of member agent names

    Returns:
        True if created successfully
    """
    teams_dir = Path.cwd() / ".pilotcode" / "teams"
    teams_dir.mkdir(parents=True, exist_ok=True)

    team_file = teams_dir / f"{team_name}.json"
    if team_file.exists():
        return False

    team_data = {
        "name": team_name,
        "lead_agent_id": lead_agent,
        "members": members,
        "created_at": datetime.now(tz=timezone.utc).isoformat(),
    }

    try:
        team_file.write_text(json.dumps(team_data, indent=2))
        return True
    except Exception:
        return False


def delete_team(team_name: str) -> bool:
    """Delete a team and its inboxes.

    Args:
        team_name: Team name

    Returns:
        True if deleted successfully
    """
    team_file = Path.cwd() / ".pilotcode" / "teams" / f"{team_name}.json"
    inbox_dir = _get_inbox_dir(team_name)

    try:
        if team_file.exists():
            team_file.unlink()
        if inbox_dir.exists():
            import shutil

            shutil.rmtree(inbox_dir)
        return True
    except Exception:
        return False
