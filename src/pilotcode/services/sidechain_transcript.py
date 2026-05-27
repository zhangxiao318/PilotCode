"""Sidechain transcript storage for sub-agent conversations.

When a sub-agent runs, its full conversation (system prompt, user prompt,
all assistant turns, tool calls, and tool results) is stored in a separate
sidechain file rather than being inlined into the parent context. The parent
only receives a concise summary, preventing sub-agent content from inflating
the parent context window.

This mirrors Claude Code's sidechain transcript design (sessionStorage.ts:247).
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..utils.paths import get_data_dir


@dataclass
class SidechainMetadata:
    """Metadata for a sidechain transcript."""

    agent_id: str
    agent_type: str
    parent_session_id: str
    created_at: float
    summary: str
    turns: int
    tools_used: list[str]
    worktree_path: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "agent_type": self.agent_type,
            "parent_session_id": self.parent_session_id,
            "created_at": self.created_at,
            "summary": self.summary,
            "turns": self.turns,
            "tools_used": self.tools_used,
            "worktree_path": self.worktree_path,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SidechainMetadata:
        return cls(
            agent_id=data.get("agent_id", ""),
            agent_type=data.get("agent_type", ""),
            parent_session_id=data.get("parent_session_id", ""),
            created_at=data.get("created_at", 0.0),
            summary=data.get("summary", ""),
            turns=data.get("turns", 0),
            tools_used=data.get("tools_used", []),
            worktree_path=data.get("worktree_path"),
        )


class SidechainTranscript:
    """Manages sidechain transcript files for sub-agent conversations.

    File layout:
      sidechains/{parent_session_id}/{agent_id}_{timestamp}.jsonl
      sidechains/{parent_session_id}/{agent_id}_{timestamp}.meta.json
    """

    SUBDIR = "sidechains"

    def __init__(self, parent_session_id: str | None = None):
        self.parent_session_id = parent_session_id or "global"
        self._base_dir = get_data_dir() / self.SUBDIR / self.parent_session_id
        self._ensure_dir()

    def _ensure_dir(self) -> None:
        self._base_dir.mkdir(parents=True, exist_ok=True)

    def _transcript_path(self, agent_id: str, timestamp: float | None = None) -> Path:
        ts = timestamp or time.time()
        return self._base_dir / f"{agent_id}_{int(ts)}.jsonl"

    def _meta_path(self, transcript_path: Path) -> Path:
        return transcript_path.with_suffix(".meta.json")

    def save_transcript(
        self,
        agent_id: str,
        messages: list[Any],
        summary: str,
        agent_type: str = "",
        tools_used: list[str] | None = None,
        worktree_path: str | None = None,
    ) -> str:
        """Save a sub-agent conversation to a sidechain file.

        Args:
            agent_id: Unique identifier for the sub-agent.
            messages: Full conversation messages (any format with role/content).
            summary: Concise summary returned to the parent.
            agent_type: Type of sub-agent (coder, debugger, etc.).
            tools_used: List of tool names used by the sub-agent.
            worktree_path: Optional worktree isolation path.

        Returns:
            Path to the saved transcript file.
        """
        ts = time.time()
        transcript_path = self._transcript_path(agent_id, ts)
        meta_path = self._meta_path(transcript_path)

        # Serialize messages to JSONL
        with transcript_path.open("w", encoding="utf-8") as f:
            for msg in messages:
                record = self._serialize_message(msg)
                f.write(json.dumps(record, ensure_ascii=False) + "\n")

        # Write metadata
        metadata = SidechainMetadata(
            agent_id=agent_id,
            agent_type=agent_type,
            parent_session_id=self.parent_session_id,
            created_at=ts,
            summary=summary,
            turns=len([m for m in messages if self._get_role(m) == "assistant"]),
            tools_used=tools_used or [],
            worktree_path=worktree_path,
        )
        with meta_path.open("w", encoding="utf-8") as f:
            json.dump(metadata.to_dict(), f, indent=2, ensure_ascii=False)

        return str(transcript_path)

    def load_transcript(
        self, transcript_path: str
    ) -> tuple[list[dict[str, Any]], SidechainMetadata] | None:
        """Load a transcript and its metadata."""
        tpath = Path(transcript_path)
        mpath = self._meta_path(tpath)

        if not tpath.exists():
            return None

        messages: list[dict[str, Any]] = []
        with tpath.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    messages.append(json.loads(line))
                except json.JSONDecodeError:
                    continue

        metadata = SidechainMetadata(
            agent_id="", agent_type="", parent_session_id="", created_at=0.0, summary="", turns=0
        )
        if mpath.exists():
            with mpath.open("r", encoding="utf-8") as f:
                metadata = SidechainMetadata.from_dict(json.load(f))

        return messages, metadata

    def list_transcripts(self) -> list[tuple[str, SidechainMetadata]]:
        """List all transcripts for this parent session."""
        results: list[tuple[str, SidechainMetadata]] = []
        if not self._base_dir.exists():
            return results

        for meta_file in self._base_dir.glob("*.meta.json"):
            try:
                with meta_file.open("r", encoding="utf-8") as f:
                    metadata = SidechainMetadata.from_dict(json.load(f))
                # meta.json -> .jsonl (strip .json suffix first)
                transcript_file = meta_file.with_suffix("").with_suffix(".jsonl")
                if transcript_file.exists():
                    results.append((str(transcript_file), metadata))
            except Exception:
                continue

        results.sort(key=lambda x: x[1].created_at, reverse=True)
        return results

    def get_latest_transcript(self, agent_id: str) -> str | None:
        """Get the path to the most recent transcript for an agent."""
        candidates = []
        for transcript_path, metadata in self.list_transcripts():
            if metadata.agent_id == agent_id:
                candidates.append((transcript_path, metadata.created_at))
        if not candidates:
            return None
        candidates.sort(key=lambda x: x[1], reverse=True)
        return candidates[0][0]

    def delete_old_transcripts(self, max_age_days: int = 7) -> int:
        """Delete transcripts older than max_age_days."""
        cutoff = time.time() - (max_age_days * 24 * 3600)
        deleted = 0
        for transcript_path, metadata in self.list_transcripts():
            if metadata.created_at < cutoff:
                try:
                    Path(transcript_path).unlink(missing_ok=True)
                    self._meta_path(Path(transcript_path)).unlink(missing_ok=True)
                    deleted += 1
                except Exception:
                    pass
        return deleted

    # ------------------------------------------------------------------
    # Serialization helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _get_role(msg: Any) -> str:
        """Extract role from a message object."""
        if hasattr(msg, "role"):
            return msg.role
        if hasattr(msg, "type"):
            return msg.type
        return "unknown"

    @staticmethod
    def _get_content(msg: Any) -> str:
        """Extract content from a message object."""
        if hasattr(msg, "content"):
            return str(msg.content or "")
        if hasattr(msg, "text"):
            return str(msg.text or "")
        return ""

    @staticmethod
    def _serialize_message(msg: Any) -> dict[str, Any]:
        """Serialize a message to a plain dict for JSONL storage."""
        record: dict[str, Any] = {
            "role": SidechainTranscript._get_role(msg),
            "content": SidechainTranscript._get_content(msg),
        }

        # Capture tool calls
        tool_calls = getattr(msg, "tool_calls", None)
        if tool_calls:
            record["tool_calls"] = [
                {
                    "id": getattr(tc, "id", ""),
                    "name": getattr(tc, "name", ""),
                    "arguments": getattr(tc, "arguments", {}),
                }
                for tc in tool_calls
            ]

        # Capture tool call id (for tool results)
        tool_call_id = getattr(msg, "tool_call_id", None)
        if tool_call_id:
            record["tool_call_id"] = tool_call_id

        name = getattr(msg, "name", None)
        if name:
            record["name"] = name

        # Timestamp if available
        timestamp = getattr(msg, "timestamp", None)
        if timestamp:
            record["timestamp"] = (
                timestamp.isoformat() if hasattr(timestamp, "isoformat") else str(timestamp)
            )

        return record


# Global cache keyed by parent session ID
_transcript_instances: dict[str, SidechainTranscript] = {}


def get_sidechain_transcript(parent_session_id: str | None = None) -> SidechainTranscript:
    """Get or create a SidechainTranscript for a parent session."""
    sid = parent_session_id or "global"
    if sid not in _transcript_instances:
        _transcript_instances[sid] = SidechainTranscript(sid)
    return _transcript_instances[sid]


def save_sidechain_transcript(
    agent_id: str,
    messages: list[Any],
    summary: str,
    parent_session_id: str | None = None,
    agent_type: str = "",
    tools_used: list[str] | None = None,
    worktree_path: str | None = None,
) -> str:
    """Convenience function to save a sub-agent transcript."""
    st = get_sidechain_transcript(parent_session_id)
    return st.save_transcript(
        agent_id=agent_id,
        messages=messages,
        summary=summary,
        agent_type=agent_type,
        tools_used=tools_used,
        worktree_path=worktree_path,
    )
