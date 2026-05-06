"""Context archive — persistent storage and retrieval of compressed context.

Reference: Claude Code src/services/compact/sessionMemoryCompact.ts

Provides:
1. Persistence: save compressed context to .pilotcode/context/ as JSON
2. Retrieval: query archived context by keyword, time range, or message type
3. Session memory: structured summaries that survive compaction
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from datetime import datetime, timezone
from typing import Any
from dataclasses import dataclass, field, asdict

logger = logging.getLogger(__name__)

# =============================================================================
# Data structures
# =============================================================================


@dataclass
class ContextEntry:
    """A single archived context entry."""

    entry_id: str
    timestamp: str
    message_type: str  # 'user', 'assistant', 'tool_result', 'summary'
    content: str
    token_count: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "ContextEntry":
        return cls(**data)


@dataclass
class ArchiveIndex:
    """Index of all archived context entries."""

    entries: list[dict[str, Any]] = field(default_factory=list)
    last_compact_at: str = ""
    total_entries: int = 0
    total_tokens_saved: int = 0


@dataclass
class SessionMemory:
    """Structured session memory — survives compaction.

    Reference: Claude Code .claude/session-memory.md
    """

    primary_request: str = ""
    key_technical_concepts: list[str] = field(default_factory=list)
    files_examined: list[str] = field(default_factory=list)
    files_modified: list[str] = field(default_factory=list)
    errors_encountered: list[str] = field(default_factory=list)
    pending_tasks: list[str] = field(default_factory=list)
    decisions_made: list[str] = field(default_factory=list)
    updated_at: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "SessionMemory":
        return cls(**data)

    def to_prompt_section(self) -> str:
        """Format as a system prompt section for injection."""
        parts = ["## Session Context (archived)"]
        if self.primary_request:
            parts.append(f"\n### Original Request\n{self.primary_request[:500]}")
        if self.key_technical_concepts:
            parts.append("\n### Key Concepts\n- " + "\n- ".join(self.key_technical_concepts[:10]))
        if self.files_examined:
            parts.append("\n### Files Examined\n- " + "\n- ".join(self.files_examined[:15]))
        if self.files_modified:
            parts.append("\n### Files Modified\n- " + "\n- ".join(self.files_modified[:15]))
        if self.errors_encountered:
            parts.append("\n### Errors\n- " + "\n- ".join(self.errors_encountered[:8]))
        if self.decisions_made:
            parts.append("\n### Decisions\n- " + "\n- ".join(self.decisions_made[:8]))
        return "\n".join(parts)


# =============================================================================
# Archive manager
# =============================================================================


class ContextArchive:
    """Persistent context archive.

    Stores compacted context in .pilotcode/context/ as JSON files.
    Each compaction produces an archive file with:
    - The structured summary (SessionMemory)
    - Index of which messages were archived
    - Metadata about what was saved
    """

    def __init__(self, base_dir: str | None = None):
        self.base_dir = Path(base_dir or Path.cwd() / ".pilotcode" / "context")
        self.base_dir.mkdir(parents=True, exist_ok=True)

        # In-memory session memory for current conversation
        self.session_memory = SessionMemory()
        self._session_memory_path = self.base_dir / "session_memory.json"

        # Load existing session memory
        self._load_session_memory()

    # ------------------------------------------------------------------
    # Session Memory (survives compaction)
    # ------------------------------------------------------------------

    def _session_memory_path(self) -> Path:
        return self.base_dir / "session_memory.json"

    def _load_session_memory(self) -> None:
        """Load session memory from disk."""
        path = self.base_dir / "session_memory.json"
        if path.exists():
            try:
                data = json.loads(path.read_text())
                self.session_memory = SessionMemory.from_dict(data)
            except Exception as exc:
                logger.warning("Failed to load session memory: %s", exc)

    def save_session_memory(self) -> None:
        """Save session memory to disk."""
        self.session_memory.updated_at = datetime.now(tz=timezone.utc).isoformat()
        path = self.base_dir / "session_memory.json"
        try:
            path.write_text(json.dumps(self.session_memory.to_dict(), indent=2, ensure_ascii=False))
        except Exception as exc:
            logger.warning("Failed to save session memory: %s", exc)

    def update_session_memory(self, summary: dict[str, Any]) -> None:
        """Update session memory with a structured summary from compaction."""
        mem = self.session_memory
        if summary.get("primary_request") and not mem.primary_request:
            mem.primary_request = summary["primary_request"]
        if summary.get("key_technical_concepts"):
            mem.key_technical_concepts = list(
                set(mem.key_technical_concepts + summary["key_technical_concepts"])
            )
        if summary.get("files_examined"):
            mem.files_examined = list(set(mem.files_examined + summary["files_examined"]))
        if summary.get("files_modified"):
            mem.files_modified = list(set(mem.files_modified + summary["files_modified"]))
        if summary.get("errors_encountered"):
            for err in summary["errors_encountered"]:
                if err not in mem.errors_encountered:
                    mem.errors_encountered.append(err)
        self.save_session_memory()

    # ------------------------------------------------------------------
    # Context archiving (per-compaction)
    # ------------------------------------------------------------------

    def archive_compaction(
        self,
        messages: list[Any],
        summary: dict[str, Any],
        token_saved: int = 0,
    ) -> str:
        """Archive compressed context to disk.

        Args:
            messages: Original messages being archived.
            summary: Structured summary from compaction.
            token_saved: Estimated tokens saved by this compaction.

        Returns:
            Archive entry ID.
        """
        import uuid

        entry_id = uuid.uuid4().hex[:12]
        timestamp = datetime.now(tz=timezone.utc).isoformat()

        # Build archive entry
        entries = []
        for msg in messages:
            content = str(getattr(msg, "content", ""))
            if not content:
                continue
            msg_type = type(msg).__name__.replace("Message", "").lower()
            if not msg_type:
                msg_type = "unknown"
            entries.append(
                ContextEntry(
                    entry_id=f"{entry_id}_{len(entries)}",
                    timestamp=timestamp,
                    message_type=msg_type,
                    content=content[:500],  # Truncated for archive
                    token_count=len(content) // 4,
                    metadata={
                        "is_error": getattr(msg, "is_error", False),
                        "tool_name": getattr(msg, "name", ""),
                    },
                ).to_dict()
            )

        archive = {
            "archive_id": entry_id,
            "timestamp": timestamp,
            "summary": summary,
            "entries": entries,
            "token_saved": token_saved,
            "entry_count": len(entries),
        }

        # Write archive file
        archive_path = self.base_dir / f"compact_{entry_id}.json"
        try:
            archive_path.write_text(json.dumps(archive, indent=2, ensure_ascii=False))
        except Exception as exc:
            logger.warning("Failed to write context archive %s: %s", entry_id, exc)

        # Update session memory
        self.update_session_memory(summary)

        return entry_id

    # ------------------------------------------------------------------
    # Retrieval
    # ------------------------------------------------------------------

    def list_archives(self) -> list[dict[str, Any]]:
        """List all archive entries with metadata."""
        archives = []
        for path in self.base_dir.glob("compact_*.json"):
            try:
                data = json.loads(path.read_text())
                archives.append(
                    (
                        {
                            "archive_id": data.get("archive_id"),
                            "timestamp": data.get("timestamp"),
                            "entry_count": data.get("entry_count", 0),
                            "token_saved": data.get("token_saved", 0),
                            "summary": data.get("summary", {}).get("primary_request", "")[:100],
                        },
                        path.stat().st_mtime,
                    )
                )
            except Exception:
                continue
        archives.sort(key=lambda x: (x[0].get("timestamp", ""), x[1]), reverse=True)
        return [a[0] for a in archives]

    def get_archive(self, archive_id: str) -> dict[str, Any] | None:
        """Get a specific archive by ID."""
        path = self.base_dir / f"compact_{archive_id}.json"
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text())
        except Exception:
            return None

    def query_context(self, keyword: str, max_results: int = 10) -> list[dict[str, Any]]:
        """Search archived context by keyword.

        Args:
            keyword: Search term.
            max_results: Maximum results to return.

        Returns:
            List of matching context entries.
        """
        results = []
        kw_lower = keyword.lower()

        for path in sorted(self.base_dir.glob("compact_*.json"), reverse=True):
            try:
                data = json.loads(path.read_text())
                for entry in data.get("entries", []):
                    if kw_lower in entry.get("content", "").lower():
                        results.append(entry)
                        if len(results) >= max_results:
                            return results
            except Exception:
                continue
        return results

    def get_recent_context(self, count: int = 5) -> list[dict[str, Any]]:
        """Get most recent archived entries.

        Args:
            count: Number of entries to return.

        Returns:
            List of context entries.
        """
        all_entries = []
        for path in sorted(self.base_dir.glob("compact_*.json"), reverse=True):
            try:
                data = json.loads(path.read_text())
                all_entries.extend(data.get("entries", []))
                if len(all_entries) >= count:
                    break
            except Exception:
                continue
        return all_entries[:count]

    def get_session_memory_prompt(self) -> str:
        """Get session memory formatted as a system prompt section."""
        return self.session_memory.to_prompt_section()

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    def cleanup_old_archives(self, max_age_days: int = 30) -> int:
        """Remove archives older than max_age_days."""
        import time

        cutoff = time.time() - (max_age_days * 86400)
        cleaned = 0
        for path in self.base_dir.glob("compact_*.json"):
            try:
                if path.stat().st_mtime < cutoff:
                    path.unlink()
                    cleaned += 1
            except Exception:
                continue
        return cleaned

    def get_total_tokens_saved(self) -> int:
        """Get total tokens saved across all archives."""
        total = 0
        for path in self.base_dir.glob("compact_*.json"):
            try:
                data = json.loads(path.read_text())
                total += data.get("token_saved", 0)
            except Exception:
                continue
        return total
