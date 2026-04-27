"""Session persistence - incremental JSON Lines storage with rolling segments.

File layout for session "sess_123":
  sess_123.index.json   – segment index + store metadata
  sess_123.meta.json    – human-readable metadata (name, project_path, ...)
  sess_123.data.0.jsonl – JSON Lines segment 0
  sess_123.data.1.jsonl – JSON Lines segment 1 (created when 0 is full)

Only the two most recent segments are kept.  After auto_compact a rollover
rewrites the full in-memory state into a fresh segment and old ones are purged.
"""

import json
from datetime import datetime
from pathlib import Path
from dataclasses import dataclass, asdict
from platformdirs import user_data_dir

from ..types.message import (
    Message,
    UserMessage,
    AssistantMessage,
    SystemMessage,
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
    archived: bool = False

    def __post_init__(self):
        if self.tags is None:
            self.tags = []


class SessionPersistence:
    """Manages session persistence with incremental JSON Lines storage."""

    DATA_DIR = Path(user_data_dir("pilotcode", "pilotcode")) / "sessions"

    # Segment thresholds
    SEGMENT_MAX_MESSAGES = 50
    MAX_SEGMENTS = 2

    def __init__(self):
        self._ensure_data_dir()
        # Tracks how many messages were persisted per session so we can append
        # only the delta on the next save.  Restored from index on load.
        self._last_saved_counts: dict[str, int] = {}

    def _ensure_data_dir(self) -> None:
        self.DATA_DIR.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Paths
    # ------------------------------------------------------------------
    def _index_path(self, session_id: str) -> Path:
        return self.DATA_DIR / f"{session_id}.index.json"

    def _meta_path(self, session_id: str) -> Path:
        return self.DATA_DIR / f"{session_id}.meta.json"

    def _data_path(self, session_id: str, segment_idx: int) -> Path:
        return self.DATA_DIR / f"{session_id}.data.{segment_idx}.jsonl"

    def _list_segments(self, session_id: str) -> list[Path]:
        pattern = f"{session_id}.data.*.jsonl"
        files = sorted(
            self.DATA_DIR.glob(pattern),
            key=lambda p: int(p.stem.rsplit(".", 1)[-1]),
        )
        return files

    # ------------------------------------------------------------------
    # Index I/O
    # ------------------------------------------------------------------
    def _read_index(self, session_id: str) -> dict | None:
        path = self._index_path(session_id)
        if not path.exists():
            return None
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return None

    def _write_index(self, session_id: str, index: dict) -> None:
        with open(self._index_path(session_id), "w", encoding="utf-8") as f:
            json.dump(index, f, indent=2)

    # ------------------------------------------------------------------
    # Message serialization
    # ------------------------------------------------------------------
    def _message_to_dict(self, message: Message) -> dict:
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
                tool_use_id = data.get("tool_use_id") or data.get("id", "")
                name = data.get("name") or data.get("tool_name", "")
                return ToolUseMessage(
                    tool_use_id=tool_use_id,
                    name=name,
                    input=data.get("input") or data.get("tool_input", {}),
                )
            elif msg_type == "tool_result":
                tool_use_id = data.get("tool_use_id") or data.get("id", "")
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

    # ------------------------------------------------------------------
    # Core incremental operations
    # ------------------------------------------------------------------
    def _rollover(self, session_id: str, messages: list[Message]) -> bool:
        """Create a fresh segment containing all current messages.

        Used after auto_compact (message deletion) or on first save.
        """
        try:
            for seg in self._list_segments(session_id):
                seg.unlink(missing_ok=True)

            data_path = self._data_path(session_id, 0)
            with open(data_path, "w", encoding="utf-8") as f:
                for msg in messages:
                    f.write(json.dumps(self._message_to_dict(msg), ensure_ascii=False) + "\n")

            index = {
                "version": "2.0",
                "session_id": session_id,
                "data_files": [{"file": data_path.name, "start_idx": 0, "count": len(messages)}],
                "total_messages": len(messages),
            }
            self._write_index(session_id, index)
            self._last_saved_counts[session_id] = len(messages)
            return True
        except Exception as e:
            print(f"[Session] Rollover failed: {e}")
            return False

    def _append_messages(self, session_id: str, messages: list[Message], start_idx: int) -> bool:
        """Append new messages to the current segment."""
        try:
            index = self._read_index(session_id) or {}
            data_files = index.get("data_files", [])

            if not data_files:
                seg_idx = 0
                seg_count = 0
            else:
                last = data_files[-1]
                seg_idx = int(last["file"].rsplit(".", 2)[-2])
                seg_count = last["count"]

            # Roll to next segment if current is full
            if seg_count >= self.SEGMENT_MAX_MESSAGES:
                seg_idx += 1
                seg_count = 0

            data_path = self._data_path(session_id, seg_idx)
            new_messages = messages[start_idx:]

            mode = "a" if data_path.exists() else "w"
            with open(data_path, mode, encoding="utf-8") as f:
                for msg in new_messages:
                    f.write(json.dumps(self._message_to_dict(msg), ensure_ascii=False) + "\n")

            if not data_files or seg_count >= self.SEGMENT_MAX_MESSAGES:
                data_files.append(
                    {"file": data_path.name, "start_idx": start_idx, "count": len(new_messages)}
                )
            else:
                data_files[-1]["count"] = seg_count + len(new_messages)

            index.update(
                {
                    "version": "2.0",
                    "session_id": session_id,
                    "data_files": data_files,
                    "total_messages": len(messages),
                }
            )
            self._write_index(session_id, index)

            self._prune_segments(session_id)
            self._last_saved_counts[session_id] = len(messages)
            return True
        except Exception as e:
            print(f"[Session] Append failed: {e}")
            return False

    def _prune_segments(self, session_id: str) -> None:
        """Delete oldest segments when count exceeds MAX_SEGMENTS."""
        index = self._read_index(session_id)
        if not index:
            return

        data_files = index.get("data_files", [])
        while len(data_files) > self.MAX_SEGMENTS:
            oldest = data_files.pop(0)
            seg_path = self.DATA_DIR / oldest["file"]
            seg_path.unlink(missing_ok=True)
            if data_files:
                data_files[0]["start_idx"] = 0

        index["data_files"] = data_files
        self._write_index(session_id, index)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def save_session(
        self,
        session_id: str,
        messages: list[Message],
        name: str | None = None,
        project_path: str | None = None,
        tags: list[str] | None = None,
    ) -> bool:
        """Save a session incrementally.

        Only new messages (delta since last save) are appended.  If the
        in-memory message count has shrunk (e.g. auto_compact deleted old
        messages) a rollover is performed instead.
        """
        try:
            last_count = self._last_saved_counts.get(session_id, 0)
            current_count = len(messages)

            index = self._read_index(session_id)
            store_exists = index is not None

            if current_count < last_count or not store_exists:
                ok = self._rollover(session_id, messages)
            else:
                ok = self._append_messages(session_id, messages, last_count)

            if not ok:
                return False

            # Update human-readable metadata
            metadata = SessionMetadata(
                session_id=session_id,
                name=name or f"Session {session_id[:8]}",
                created_at=datetime.now().isoformat(),
                updated_at=datetime.now().isoformat(),
                message_count=current_count,
                project_path=project_path,
                summary=self._generate_summary(messages),
                tags=tags or [],
            )
            with open(self._meta_path(session_id), "w", encoding="utf-8") as f:
                json.dump(asdict(metadata), f, indent=2)

            return True
        except Exception as e:
            print(f"Error saving session: {e}")
            return False

    def load_session(self, session_id: str) -> tuple[list[Message], dict] | None:
        """Load a session from incremental store."""
        index = self._read_index(session_id)
        if not index:
            return None

        messages: list[Message] = []
        for seg_info in index.get("data_files", []):
            seg_path = self.DATA_DIR / seg_info["file"]
            if not seg_path.exists():
                continue
            with open(seg_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        msg = self._dict_to_message(json.loads(line))
                        if msg:
                            messages.append(msg)
                    except Exception:
                        continue

        metadata = {
            "session_id": session_id,
            "saved_at": index.get("saved_at"),
            "version": index.get("version"),
        }
        meta_path = self._meta_path(session_id)
        if meta_path.exists():
            with open(meta_path, "r", encoding="utf-8") as f:
                metadata.update(json.load(f))

        # Restore last-saved count so subsequent saves are incremental
        self._last_saved_counts[session_id] = len(messages)
        return messages, metadata

    def list_sessions(self, project_path: str | None = None) -> list[SessionMetadata]:
        """List available sessions."""
        sessions = []
        try:
            for meta_path in self.DATA_DIR.glob("*.meta.json"):
                try:
                    with open(meta_path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    metadata = SessionMetadata(**data)
                    if project_path and metadata.project_path != project_path:
                        continue
                    sessions.append(metadata)
                except Exception:
                    continue
            sessions.sort(key=lambda s: s.updated_at, reverse=True)
        except Exception as e:
            print(f"Error listing sessions: {e}")
        return sessions

    def delete_session(self, session_id: str) -> bool:
        """Delete a session and all its segments."""
        try:
            for p in [
                self._index_path(session_id),
                self._meta_path(session_id),
            ]:
                if p.exists():
                    p.unlink()
            for seg in self._list_segments(session_id):
                seg.unlink(missing_ok=True)
            self._last_saved_counts.pop(session_id, None)
            return True
        except Exception as e:
            print(f"Error deleting session: {e}")
            return False

    def rename_session(self, session_id: str, new_name: str) -> bool:
        """Rename a session."""
        try:
            meta = self._meta_path(session_id)
            if not meta.exists():
                return False
            with open(meta, "r", encoding="utf-8") as f:
                data = json.load(f)
            data["name"] = new_name
            data["updated_at"] = datetime.now().isoformat()
            with open(meta, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            return True
        except Exception as e:
            print(f"Error renaming session: {e}")
            return False

    def archive_session(self, session_id: str, archived: bool = True) -> bool:
        """Archive or unarchive a session."""
        try:
            meta = self._meta_path(session_id)
            if not meta.exists():
                return False
            with open(meta, "r", encoding="utf-8") as f:
                data = json.load(f)
            data["archived"] = archived
            data["updated_at"] = datetime.now().isoformat()
            with open(meta, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            return True
        except Exception as e:
            print(f"Error archiving session: {e}")
            return False

    def _generate_summary(self, messages: list[Message], max_length: int = 200) -> str:
        if not messages:
            return "Empty session"
        for msg in messages:
            if isinstance(msg, UserMessage):
                content = msg.content
                if len(content) > max_length:
                    content = content[:max_length] + "..."
                return content
        return f"Session with {len(messages)} messages"

    def export_session(self, session_id: str, export_path: Path, format: str = "json") -> bool:
        """Export session to a file."""
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
                with open(export_path, "w", encoding="utf-8") as f:
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
                        lines.append(
                            f"### Tool result ({msg.tool_use_id})\n\n```\n{msg.content}\n```\n"
                        )
                with open(export_path, "w", encoding="utf-8") as f:
                    f.write("\n".join(lines))
            return True
        except Exception as e:
            print(f"Error exporting session: {e}")
            return False

    def get_last_session(self, project_path: str | None = None) -> SessionMetadata | None:
        sessions = self.list_sessions(project_path=project_path)
        return sessions[0] if sessions else None


# Global instance
_persistence: SessionPersistence | None = None


def get_session_persistence() -> SessionPersistence:
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
    return get_session_persistence().save_session(session_id, messages, name, project_path)


def load_session(session_id: str) -> tuple[list[Message], dict] | None:
    return get_session_persistence().load_session(session_id)


def list_sessions(project_path: str | None = None) -> list[SessionMetadata]:
    return get_session_persistence().list_sessions(project_path)


def get_last_session(project_path: str | None = None) -> SessionMetadata | None:
    return get_session_persistence().get_last_session(project_path)
