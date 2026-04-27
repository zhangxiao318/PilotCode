"""Project-level knowledge base (memory) system.

A lightweight, project-local knowledge base stored in ``.pilotcode/memory/``
directory (relative to project root). Format is JSONL (one JSON object per
line, append-friendly).
"""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class MemoryEntry:
    """A single entry in the project memory knowledge base."""

    id: str
    category: str
    timestamp: float
    tags: list[str]
    content: str
    source: str
    metadata: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "category": self.category,
            "timestamp": self.timestamp,
            "tags": self.tags,
            "content": self.content,
            "source": self.source,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MemoryEntry:
        return cls(
            id=data["id"],
            category=data["category"],
            timestamp=data["timestamp"],
            tags=data.get("tags", []),
            content=data["content"],
            source=data.get("source", "manual"),
            metadata=data.get("metadata", {}),
        )


class ProjectMemoryKB:
    """Manages a project-local knowledge base stored in ``.pilotcode/memory/``."""

    CATEGORIES = {"fact", "bug", "decision", "qa"}

    def __init__(self, root_path: str | Path) -> None:
        self.root = Path(root_path).resolve()
        self.memory_dir = self.root / ".pilotcode" / "memory"
        self._file_map = {
            "fact": self.memory_dir / "facts.jsonl",
            "bug": self.memory_dir / "bugs.jsonl",
            "decision": self.memory_dir / "decisions.jsonl",
            "qa": self.memory_dir / "qa.jsonl",
        }
        self._index_path = self.memory_dir / "index.json"

    def _ensure_dir(self) -> None:
        """Ensure the memory directory exists."""
        self.memory_dir.mkdir(parents=True, exist_ok=True)

    def _load_entries(self, category: str | None = None) -> list[MemoryEntry]:
        """Load entries from JSONL files, skipping malformed lines gracefully."""
        entries: list[MemoryEntry] = []
        categories = [category] if category else list(self.CATEGORIES)
        for cat in categories:
            path = self._file_map.get(cat)
            if not path or not path.exists():
                continue
            with path.open("r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        data = json.loads(line)
                        entries.append(MemoryEntry.from_dict(data))
                    except (json.JSONDecodeError, KeyError):
                        continue
        return entries

    def _write_entry(self, entry: MemoryEntry) -> None:
        """Append a single entry to the appropriate JSONL file."""
        self._ensure_dir()
        path = self._file_map[entry.category]
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry.to_dict(), ensure_ascii=False) + "\n")

    def _update_index(self) -> None:
        """Update optional index metadata with current stats."""
        try:
            with self._index_path.open("w", encoding="utf-8") as f:
                json.dump(
                    {"stats": self.get_stats(), "updated_at": time.time()},
                    f,
                    indent=2,
                )
        except (OSError, IOError):
            pass

    def _entry_text(self, entry: MemoryEntry) -> str:
        """Return a lowercase text representation of an entry for searching."""
        parts = [entry.content]
        parts.extend(entry.tags)
        for value in entry.metadata.values():
            if isinstance(value, list):
                for item in value:
                    parts.append(str(item))
            else:
                parts.append(str(value))
        return " ".join(parts).lower()

    def add(self, entry: MemoryEntry) -> None:
        """Add a memory entry to the knowledge base.

        Args:
            entry: The memory entry to store.

        Raises:
            ValueError: If the entry category is not recognised.
        """
        if entry.category not in self.CATEGORIES:
            raise ValueError(f"Unknown category: {entry.category}")
        if not entry.id:
            entry.id = str(uuid.uuid4())
        if not entry.timestamp:
            entry.timestamp = time.time()
        self._write_entry(entry)
        self._update_index()

    def add_fact(
        self,
        content: str,
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        """Add a fact entry.

        Returns:
            The generated entry ID.
        """
        entry = MemoryEntry(
            id=str(uuid.uuid4()),
            category="fact",
            timestamp=time.time(),
            tags=tags or [],
            content=content,
            source="manual",
            metadata=metadata or {},
        )
        self.add(entry)
        return entry.id

    def add_bug(
        self,
        symptom: str,
        root_cause: str,
        fix: str,
        files_involved: list[str] | None = None,
        status: str = "fixed",
        tags: list[str] | None = None,
    ) -> str:
        """Add a bug entry.

        Returns:
            The generated entry ID.
        """
        metadata: dict[str, Any] = {
            "symptom": symptom,
            "root_cause": root_cause,
            "fix": fix,
            "files_involved": files_involved or [],
            "status": status,
        }
        parts = [f"Bug: {symptom}", f"Root cause: {root_cause}", f"Fix: {fix}"]
        if files_involved:
            parts.append(f"Files involved: {', '.join(files_involved)}")
        entry = MemoryEntry(
            id=str(uuid.uuid4()),
            category="bug",
            timestamp=time.time(),
            tags=tags or [],
            content="\n".join(parts),
            source="manual",
            metadata=metadata,
        )
        self.add(entry)
        return entry.id

    def add_decision(
        self,
        content: str,
        context: str,
        options_considered: list[str],
        consequences: str,
        tags: list[str] | None = None,
    ) -> str:
        """Add a decision entry.

        Returns:
            The generated entry ID.
        """
        metadata: dict[str, Any] = {
            "context": context,
            "options_considered": options_considered,
            "consequences": consequences,
        }
        entry = MemoryEntry(
            id=str(uuid.uuid4()),
            category="decision",
            timestamp=time.time(),
            tags=tags or [],
            content=content,
            source="manual",
            metadata=metadata,
        )
        self.add(entry)
        return entry.id

    def add_qa(
        self,
        question: str,
        answer: str,
        related_files: list[str] | None = None,
        tags: list[str] | None = None,
    ) -> str:
        """Add a Q&A entry.

        Returns:
            The generated entry ID.
        """
        metadata: dict[str, Any] = {
            "question": question,
            "answer": answer,
            "related_files": related_files or [],
        }
        parts = [f"Q: {question}", f"A: {answer}"]
        if related_files:
            parts.append(f"Related files: {', '.join(related_files)}")
        entry = MemoryEntry(
            id=str(uuid.uuid4()),
            category="qa",
            timestamp=time.time(),
            tags=tags or [],
            content="\n".join(parts),
            source="manual",
            metadata=metadata,
        )
        self.add(entry)
        return entry.id

    def search(
        self,
        query: str,
        categories: list[str] | None = None,
        top_k: int = 5,
    ) -> list[MemoryEntry]:
        """Search entries using simple keyword scoring.

        Words in *query* are matched case-insensitively against the
        entry's content, tags, and metadata values.

        Args:
            query: Space-separated keywords.
            categories: Optional list of categories to restrict the search.
            top_k: Maximum number of results to return.

        Returns:
            Matching entries sorted by relevance (score desc, then recency).
        """
        query_words = [w.lower() for w in query.split() if w]
        if not query_words:
            return []

        entries = self._load_entries()
        if categories:
            entries = [e for e in entries if e.category in categories]

        scored: list[tuple[int, MemoryEntry]] = []
        for entry in entries:
            text = self._entry_text(entry)
            score = sum(1 for w in query_words if w in text)
            if score:
                scored.append((score, entry))

        scored.sort(key=lambda x: (-x[0], -x[1].timestamp))
        return [entry for _, entry in scored[:top_k]]

    def search_by_tags(
        self,
        tags: list[str],
        categories: list[str] | None = None,
    ) -> list[MemoryEntry]:
        """Search entries by exact tag matching (all supplied tags must match).

        Args:
            tags: Tags that must all be present on an entry.
            categories: Optional list of categories to restrict the search.

        Returns:
            Matching entries sorted by recency.
        """
        if not tags:
            return []

        tag_set = {t.lower() for t in tags}
        entries = self._load_entries()
        if categories:
            entries = [e for e in entries if e.category in categories]

        results: list[MemoryEntry] = []
        for entry in entries:
            entry_tags = {t.lower() for t in entry.tags}
            if tag_set.issubset(entry_tags):
                results.append(entry)

        results.sort(key=lambda e: -e.timestamp)
        return results

    def get_recent(
        self,
        limit: int = 10,
        categories: list[str] | None = None,
    ) -> list[MemoryEntry]:
        """Get the most recent entries.

        Args:
            limit: Maximum number of entries to return.
            categories: Optional list of categories to filter by.

        Returns:
            The most recent entries sorted by timestamp descending.
        """
        entries = self._load_entries()
        if categories:
            entries = [e for e in entries if e.category in categories]
        entries.sort(key=lambda e: -e.timestamp)
        return entries[:limit]

    def get_stats(self) -> dict[str, Any]:
        """Return statistics about the knowledge base.

        Returns:
            A dictionary with ``total`` and ``by_category`` counts.
        """
        stats: dict[str, Any] = {"total": 0, "by_category": {}}
        for cat in self.CATEGORIES:
            count = 0
            path = self._file_map[cat]
            if path.exists():
                with path.open("r", encoding="utf-8") as f:
                    for line in f:
                        if line.strip():
                            count += 1
            stats["by_category"][cat] = count
            stats["total"] += count
        return stats

    def export(self, path: str | Path) -> None:
        """Export all entries to a single JSON file.

        Args:
            path: Destination file path.
        """
        entries = self._load_entries()
        data = {
            "exported_at": time.time(),
            "count": len(entries),
            "entries": [e.to_dict() for e in entries],
        }
        export_path = Path(path)
        export_path.parent.mkdir(parents=True, exist_ok=True)
        with export_path.open("w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)


# Global instance cache keyed by resolved root path.
_memory_kb_instances: dict[str, ProjectMemoryKB] = {}


def get_memory_kb(root_path: str | Path | None = None) -> ProjectMemoryKB:
    """Get or create a :class:`ProjectMemoryKB` instance for the given root path.

    Instances are cached so repeated calls with the same path return the
    same object.

    Args:
        root_path: Project root directory. Defaults to the current working
            directory when ``None``.

    Returns:
        A ``ProjectMemoryKB`` instance bound to *root_path*.
    """
    if root_path is None:
        root_path = Path.cwd()
    resolved = str(Path(root_path).resolve())
    if resolved not in _memory_kb_instances:
        _memory_kb_instances[resolved] = ProjectMemoryKB(resolved)
    return _memory_kb_instances[resolved]
