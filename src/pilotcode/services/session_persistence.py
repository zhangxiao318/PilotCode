"""Session persistence - save and restore conversations.

This module provides:
1. Save sessions to disk
2. Load sessions from disk
3. List available sessions
4. Auto-save functionality
5. Session compression
"""

import json
import gzip
from datetime import datetime
from pathlib import Path
from dataclasses import dataclass, asdict
from platformdirs import user_data_dir

from ..types.message import (
    Message,
    UserMessage,
    AssistantMessage,
    ToolResultMessage,
    ToolUseMessage,
)


@dataclass
class SessionMetadata:
    """Session metadata."""

    session_id: str
    name: str
    created_at: str
    updated_at: str
    message_count: int
    project_path: str | None = None
    summary: str = ""
    tags: list[str] = None

    def __post_init__(self):
        if self.tags is None:
            self.tags = []


class SessionPersistence:
    """Manages session persistence."""

    DATA_DIR = Path(user_data_dir("pilotcode", "pilotcode")) / "sessions"
    MAX_MESSAGES_BEFORE_COMPRESSION = 50

    def __init__(self):
        self._ensure_data_dir()

    def _ensure_data_dir(self) -> None:
        """Ensure data directory exists."""
        self.DATA_DIR.mkdir(parents=True, exist_ok=True)

    def _get_session_path(self, session_id: str) -> Path:
        """Get path to session file."""
        return self.DATA_DIR / f"{session_id}.json.gz"

    def _get_metadata_path(self, session_id: str) -> Path:
        """Get path to metadata file."""
        return self.DATA_DIR / f"{session_id}.meta.json"

    def _message_to_dict(self, message: Message) -> dict:
        """Convert message to dictionary."""
        # Handle timestamp serialization
        timestamp = getattr(message, "timestamp", None)
        if isinstance(timestamp, datetime):
            timestamp = timestamp.isoformat()

        if isinstance(message, UserMessage):
            return {"type": "user", "content": message.content, "timestamp": timestamp}
        elif isinstance(message, AssistantMessage):
            return {
                "type": "assistant",
                "content": message.content,
                "reasoning_content": message.reasoning_content,
                "timestamp": timestamp,
            }
        elif isinstance(message, SystemMessage):
            return {"type": "system", "content": message.content, "timestamp": timestamp}
        elif isinstance(message, ToolUseMessage):
            return {
                "type": "tool_use",
                "tool_use_id": message.tool_use_id,
                "name": message.name,
                "input": message.input,
                "timestamp": timestamp,
            }
        elif isinstance(message, ToolResultMessage):
            return {
                "type": "tool_result",
                "tool_use_id": message.tool_use_id,
                "content": message.content,
                "is_error": message.is_error,
                "timestamp": timestamp,
            }
        else:
            return {"type": "unknown", "content": str(message)}

    def _dict_to_message(self, data: dict) -> Message | None:
        """Convert dictionary to message.

        Supports both current and legacy (pre-fix) field names for backward
        compatibility with old session files.
        """
        msg_type = data.get("type")

        try:
            if msg_type == "user":
                return UserMessage(content=data.get("content", ""))
            elif msg_type == "assistant":
                return AssistantMessage(
                    content=data.get("content", ""),
                    reasoning_content=data.get("reasoning_content"),
                )
            elif msg_type == "system":
                return SystemMessage(content=data.get("content", ""))
            elif msg_type == "tool_use":
                # Prefer new field names; fallback to legacy names
                tool_use_id = data.get("tool_use_id") or data.get("id", "")
                name = data.get("name") or data.get("tool_name", "")
                return ToolUseMessage(
                    tool_use_id=tool_use_id,
                    name=name,
                    input=data.get("input") or data.get("tool_input", {}),
                )
            elif msg_type == "tool_result":
                # Prefer new field names; fallback to legacy names
                tool_use_id = data.get("tool_use_id") or data.get("id", "")
                # Legacy files stored truncated previews in 'tool_result'; use it as content
                content = data.get("content")
                if content is None:
                    content = data.get("tool_result", "")
                is_error = data.get("is_error", False)
                if is_error is False and data.get("tool_error"):
                    is_error = True
                return ToolResultMessage(
                    tool_use_id=tool_use_id,
                    content=content,
                    is_error=is_error,
                )
        except Exception:
            pass

        return None

    def save_session(
        self,
        session_id: str,
        messages: list[Message],
        name: str | None = None,
        project_path: str | None = None,
        tags: list[str] | None = None,
    ) -> bool:
        """Save a session to disk.

        Args:
            session_id: Unique session identifier
            messages: List of messages to save
            name: Human-readable name for the session
            project_path: Path to the project directory
            tags: Tags for categorizing the session

        Returns:
            True if saved successfully
        """
        try:
            # Convert messages to dicts
            message_dicts = [self._message_to_dict(m) for m in messages]

            # Create session data
            session_data = {
                "version": "1.0",
                "session_id": session_id,
                "saved_at": datetime.now().isoformat(),
                "messages": message_dicts,
            }

            # Compress and save
            session_path = self._get_session_path(session_id)
            with gzip.open(session_path, "wt", encoding="utf-8") as f:
                json.dump(session_data, f, indent=2)

            # Update metadata
            metadata = SessionMetadata(
                session_id=session_id,
                name=name or f"Session {session_id[:8]}",
                created_at=session_data["saved_at"],
                updated_at=session_data["saved_at"],
                message_count=len(messages),
                project_path=project_path,
                summary=self._generate_summary(messages),
                tags=tags or [],
            )

            metadata_path = self._get_metadata_path(session_id)
            with open(metadata_path, "w") as f:
                json.dump(asdict(metadata), f, indent=2)

            return True

        except Exception as e:
            print(f"Error saving session: {e}")
            return False

    def load_session(self, session_id: str) -> tuple[list[Message], dict] | None:
        """Load a session from disk.

        Args:
            session_id: Session identifier

        Returns:
            Tuple of (messages, metadata) or None if not found
        """
        try:
            session_path = self._get_session_path(session_id)
            if not session_path.exists():
                return None

            # Load and decompress
            with gzip.open(session_path, "rt", encoding="utf-8") as f:
                session_data = json.load(f)

            # Convert dicts back to messages
            messages = []
            for msg_dict in session_data.get("messages", []):
                msg = self._dict_to_message(msg_dict)
                if msg:
                    messages.append(msg)

            # Load metadata
            metadata = {
                "session_id": session_id,
                "saved_at": session_data.get("saved_at"),
                "version": session_data.get("version"),
            }

            metadata_path = self._get_metadata_path(session_id)
            if metadata_path.exists():
                with open(metadata_path, "r") as f:
                    metadata.update(json.load(f))

            return messages, metadata

        except Exception as e:
            print(f"Error loading session: {e}")
            return None

    def list_sessions(self, project_path: str | None = None) -> list[SessionMetadata]:
        """List available sessions.

        Args:
            project_path: Filter by project path

        Returns:
            List of session metadata
        """
        sessions = []

        try:
            for metadata_path in self.DATA_DIR.glob("*.meta.json"):
                try:
                    with open(metadata_path, "r") as f:
                        data = json.load(f)

                    metadata = SessionMetadata(**data)

                    # Filter by project path if specified
                    if project_path and metadata.project_path != project_path:
                        continue

                    sessions.append(metadata)

                except Exception:
                    continue

            # Sort by updated_at (most recent first)
            sessions.sort(key=lambda s: s.updated_at, reverse=True)

        except Exception as e:
            print(f"Error listing sessions: {e}")

        return sessions

    def delete_session(self, session_id: str) -> bool:
        """Delete a session.

        Args:
            session_id: Session to delete

        Returns:
            True if deleted successfully
        """
        try:
            session_path = self._get_session_path(session_id)
            metadata_path = self._get_metadata_path(session_id)

            if session_path.exists():
                session_path.unlink()

            if metadata_path.exists():
                metadata_path.unlink()

            return True

        except Exception as e:
            print(f"Error deleting session: {e}")
            return False

    def rename_session(self, session_id: str, new_name: str) -> bool:
        """Rename a session.

        Args:
            session_id: Session to rename
            new_name: New name for the session

        Returns:
            True if renamed successfully
        """
        try:
            metadata_path = self._get_metadata_path(session_id)

            if not metadata_path.exists():
                return False

            with open(metadata_path, "r") as f:
                data = json.load(f)

            data["name"] = new_name
            data["updated_at"] = datetime.now().isoformat()

            with open(metadata_path, "w") as f:
                json.dump(data, f, indent=2)

            return True

        except Exception as e:
            print(f"Error renaming session: {e}")
            return False

    def _generate_summary(self, messages: list[Message], max_length: int = 200) -> str:
        """Generate a summary of the session."""
        if not messages:
            return "Empty session"

        # Get first user message as summary
        for msg in messages:
            if isinstance(msg, UserMessage):
                content = msg.content
                if len(content) > max_length:
                    content = content[:max_length] + "..."
                return content

        return f"Session with {len(messages)} messages"

    def export_session(self, session_id: str, export_path: Path, format: str = "json") -> bool:
        """Export session to a file.

        Args:
            session_id: Session to export
            export_path: Path for exported file
            format: Export format (json, markdown)

        Returns:
            True if exported successfully
        """
        try:
            result = self.load_session(session_id)
            if not result:
                return False

            messages, metadata = result

            if format == "json":
                export_data = {
                    "metadata": metadata,
                    "messages": [self._message_to_dict(m) for m in messages],
                }

                with open(export_path, "w") as f:
                    json.dump(export_data, f, indent=2)

            elif format == "markdown":
                lines = [
                    f"# {metadata.get('name', 'Session')}",
                    "",
                    f"**Created:** {metadata.get('created_at', 'Unknown')}",
                    f"**Messages:** {len(messages)}",
                    "",
                    "---",
                    "",
                ]

                for msg in messages:
                    if isinstance(msg, UserMessage):
                        lines.append(f"## User\n\n{msg.content}\n")
                    elif isinstance(msg, AssistantMessage):
                        lines.append(f"## Assistant\n\n{msg.content}\n")
                    elif isinstance(msg, ToolResultMessage):
                        lines.append(f"### Tool: {msg.name}\n\n```\n{msg.result}\n```\n")

                with open(export_path, "w") as f:
                    f.write("\n".join(lines))

            return True

        except Exception as e:
            print(f"Error exporting session: {e}")
            return False

    def get_last_session(self, project_path: str | None = None) -> SessionMetadata | None:
        """Get the most recently updated session.

        Args:
            project_path: Optional filter by project path

        Returns:
            Most recent SessionMetadata or None if no sessions exist
        """
        sessions = self.list_sessions(project_path=project_path)
        return sessions[0] if sessions else None


# Global instance
_persistence: SessionPersistence | None = None


def get_session_persistence() -> SessionPersistence:
    """Get global session persistence instance."""
    global _persistence
    if _persistence is None:
        _persistence = SessionPersistence()
    return _persistence


def save_session(
    session_id: str,
    messages: list[Message],
    name: str | None = None,
    project_path: str | None = None,
) -> bool:
    """Convenience function to save a session."""
    return get_session_persistence().save_session(session_id, messages, name, project_path)


def load_session(session_id: str) -> tuple[list[Message], dict] | None:
    """Convenience function to load a session."""
    return get_session_persistence().load_session(session_id)


def list_sessions(project_path: str | None = None) -> list[SessionMetadata]:
    """Convenience function to list sessions."""
    return get_session_persistence().list_sessions(project_path)


def get_last_session(project_path: str | None = None) -> SessionMetadata | None:
    """Convenience function to get the most recent session."""
    return get_session_persistence().get_last_session(project_path)
