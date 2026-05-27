"""Session persistence for QueryEngine.

Encapsulates save/load for both legacy JSON format and unified
incremental storage.
"""

from __future__ import annotations

import json
import os
from typing import Any

from ..types.message import serialize_messages, deserialize_messages


class SessionManager:
    """Manages conversation session persistence."""

    def __init__(
        self,
        session_id: str,
        config: Any,
        messages_ref: list[Any],
    ):
        self.session_id = session_id
        self.config = config
        self.messages = messages_ref

    def save_session(self, path: str) -> None:
        """Save conversation session to a single JSON file (legacy format)."""
        os.makedirs(os.path.dirname(path) if os.path.dirname(path) else ".", exist_ok=True)
        data = {
            "version": 1,
            "cwd": self.config.cwd,
            "custom_system_prompt": self.config.custom_system_prompt,
            "max_turns": self.config.max_turns,
            "messages": serialize_messages(self.messages),
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    def load_session(self, path: str) -> bool:
        """Load conversation session from a single JSON file (legacy format).

        Returns True if loaded successfully.
        """
        if not os.path.exists(path):
            return False
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        self.messages[:] = deserialize_messages(data.get("messages", []))
        self.config.cwd = data.get("cwd", self.config.cwd)
        if data.get("custom_system_prompt"):
            self.config.custom_system_prompt = data["custom_system_prompt"]
        self.config.max_turns = data.get("max_turns", self.config.max_turns)
        return True

    def save_to_storage(self, name: str | None = None) -> bool:
        """Save session to unified incremental storage (session_persistence)."""
        from ..services.session_persistence import save_session

        return save_session(
            session_id=self.session_id,
            messages=self.messages,
            name=name or f"Session {self.session_id[:8]}",
            project_path=self.config.cwd,
            cwd=self.config.cwd,
            custom_system_prompt=self.config.custom_system_prompt,
            max_turns=self.config.max_turns,
        )

    def load_from_storage(self, session_id: str | None = None) -> tuple[bool, str, list[Any]]:
        """Load session from unified incremental storage.

        Returns (success, loaded_session_id, loaded_messages).
        The caller is responsible for updating its own session_id and messages
        references because simple assignment would break the shared list ref.
        """
        from ..services.session_persistence import load_session

        sid = session_id or self.session_id
        result = load_session(sid)
        if not result:
            return False, sid, []
        messages, metadata = result
        self.config.cwd = metadata.get("cwd", self.config.cwd)
        if metadata.get("custom_system_prompt"):
            self.config.custom_system_prompt = metadata["custom_system_prompt"]
        if metadata.get("max_turns") is not None:
            self.config.max_turns = metadata["max_turns"]
        return True, sid, messages
