"""Tests for ProjectMemoryKB (project-level knowledge base)."""

import json
import time
from pathlib import Path

import pytest

from pilotcode.services.memory_kb import (
    MemoryEntry,
    ProjectMemoryKB,
    get_memory_kb,
    _memory_kb_instances,
)


class TestMemoryEntry:
    """Tests for MemoryEntry dataclass."""

    def test_creation(self):
        entry = MemoryEntry(
            id="e1",
            category="fact",
            timestamp=time.time(),
            tags=["python"],
            content="Python 3.12 has better error messages",
            source="manual",
            metadata={},
        )
        assert entry.id == "e1"
        assert entry.category == "fact"

    def test_to_dict_roundtrip(self):
        entry = MemoryEntry(
            id="e1",
            category="bug",
            timestamp=1234.0,
            tags=["critical"],
            content="Race condition in cache",
            source="auto",
            metadata={"file": "cache.py"},
        )
        data = entry.to_dict()
        restored = MemoryEntry.from_dict(data)
        assert restored.id == entry.id
        assert restored.category == entry.category
        assert restored.tags == entry.tags
        assert restored.content == entry.content
        assert restored.metadata == entry.metadata

    def test_from_dict_defaults(self):
        data = {"id": "e1", "category": "fact", "timestamp": 0.0, "tags": [], "content": "x"}
        entry = MemoryEntry.from_dict(data)
        assert entry.source == "manual"
        assert entry.metadata == {}


class TestProjectMemoryKB:
    """Tests for ProjectMemoryKB."""

    @pytest.fixture
    def kb(self, temp_dir):
        return ProjectMemoryKB(temp_dir)

    def test_ensure_dir(self, kb):
        assert not kb.memory_dir.exists()
        kb._ensure_dir()
        assert kb.memory_dir.exists()

    def test_add_fact(self, kb):
        eid = kb.add_fact("Python supports match-case", tags=["python", "syntax"])
        assert isinstance(eid, str)
        assert len(eid) > 0

        entries = kb._load_entries("fact")
        assert len(entries) == 1
        assert entries[0].content == "Python supports match-case"
        assert "python" in entries[0].tags

    def test_add_bug(self, kb):
        eid = kb.add_bug(
            symptom="Crash on startup",
            root_cause="Null pointer",
            fix="Add null check",
            files_involved=["main.py"],
            status="fixed",
            tags=["crash"],
        )
        entries = kb._load_entries("bug")
        assert len(entries) == 1
        assert "Crash on startup" in entries[0].content
        assert entries[0].metadata["status"] == "fixed"
        assert entries[0].metadata["files_involved"] == ["main.py"]

    def test_add_decision(self, kb):
        eid = kb.add_decision(
            content="Use PostgreSQL over MySQL",
            context="Database selection",
            options_considered=["MySQL", "SQLite", "PostgreSQL"],
            consequences="Better JSON support",
            tags=["database"],
        )
        entries = kb._load_entries("decision")
        assert len(entries) == 1
        assert entries[0].metadata["options_considered"] == ["MySQL", "SQLite", "PostgreSQL"]

    def test_add_qa(self, kb):
        eid = kb.add_qa(
            question="How to run tests?",
            answer="pytest tests/",
            related_files=["README.md"],
            tags=["testing"],
        )
        entries = kb._load_entries("qa")
        assert len(entries) == 1
        assert "How to run tests?" in entries[0].content
        assert entries[0].metadata["answer"] == "pytest tests/"

    def test_add_invalid_category(self, kb):
        entry = MemoryEntry(
            id="x",
            category="invalid",
            timestamp=time.time(),
            tags=[],
            content="bad",
            source="manual",
            metadata={},
        )
        with pytest.raises(ValueError, match="Unknown category"):
            kb.add(entry)

    def test_search_basic(self, kb):
        kb.add_fact("Python is great", tags=["python"])
        kb.add_fact("JavaScript is versatile", tags=["js"])
        kb.add_bug(symptom="Python segfault", root_cause="C extension", fix="update", tags=["python"])

        results = kb.search("python")
        assert len(results) == 2
        assert all("python" in e.content.lower() for e in results)

    def test_search_by_category(self, kb):
        kb.add_fact("Python fact", tags=[])
        kb.add_bug(symptom="Python bug", root_cause="x", fix="y", tags=[])

        results = kb.search("python", categories=["fact"])
        assert len(results) == 1
        assert results[0].category == "fact"

    def test_search_top_k(self, kb):
        for i in range(10):
            kb.add_fact(f"Fact number {i}", tags=[])

        results = kb.search("fact", top_k=3)
        assert len(results) == 3

    def test_search_empty_query(self, kb):
        kb.add_fact("something", tags=[])
        assert kb.search("") == []
        assert kb.search("   ") == []

    def test_search_by_tags(self, kb):
        kb.add_fact("Fact A", tags=["important", "review"])
        kb.add_fact("Fact B", tags=["important"])
        kb.add_fact("Fact C", tags=["review"])

        results = kb.search_by_tags(["important", "review"])
        assert len(results) == 1
        assert results[0].content == "Fact A"

    def test_search_by_tags_empty(self, kb):
        assert kb.search_by_tags([]) == []

    def test_get_recent(self, kb):
        kb.add_fact("Old fact", tags=[])
        time.sleep(0.01)
        kb.add_fact("New fact", tags=[])

        results = kb.get_recent(limit=1)
        assert len(results) == 1
        assert results[0].content == "New fact"

    def test_get_recent_by_category(self, kb):
        kb.add_fact("Fact", tags=[])
        kb.add_bug(symptom="Bug", root_cause="x", fix="y", tags=[])

        results = kb.get_recent(categories=["bug"])
        assert len(results) == 1
        assert results[0].category == "bug"

    def test_get_stats(self, kb):
        kb.add_fact("F1", tags=[])
        kb.add_fact("F2", tags=[])
        kb.add_bug(symptom="B1", root_cause="x", fix="y", tags=[])

        stats = kb.get_stats()
        assert stats["total"] == 3
        assert stats["by_category"]["fact"] == 2
        assert stats["by_category"]["bug"] == 1
        assert stats["by_category"]["decision"] == 0

    def test_get_stats_empty(self, kb):
        stats = kb.get_stats()
        assert stats["total"] == 0

    def test_export(self, kb, temp_dir):
        kb.add_fact("Export me", tags=["test"])
        export_path = temp_dir / "export.json"
        kb.export(export_path)

        assert export_path.exists()
        data = json.loads(export_path.read_text())
        assert data["count"] == 1
        assert len(data["entries"]) == 1
        assert data["entries"][0]["content"] == "Export me"

    def test_load_entries_skips_malformed(self, kb):
        kb._ensure_dir()
        path = kb._file_map["fact"]
        with path.open("w", encoding="utf-8") as f:
            f.write('{"id": "good", "category": "fact", "timestamp": 0, "tags": [], "content": "ok"}\n')
            f.write('bad json line\n')
            f.write('{"id": "good2", "category": "fact", "timestamp": 0, "tags": [], "content": "ok2"}\n')

        entries = kb._load_entries("fact")
        assert len(entries) == 2
        assert {e.id for e in entries} == {"good", "good2"}

    def test_entry_text_includes_metadata(self, kb):
        entry = MemoryEntry(
            id="e1",
            category="fact",
            timestamp=0,
            tags=["tag1"],
            content="content",
            source="manual",
            metadata={"author": "alice", "labels": ["l1", "l2"]},
        )
        text = kb._entry_text(entry)
        assert "content" in text
        assert "tag1" in text
        assert "alice" in text
        assert "l1" in text
        assert "l2" in text


class TestGlobalInstance:
    """Tests for get_memory_kb singleton."""

    def test_singleton_per_path(self, temp_dir):
        # Clear cache for this path
        resolved = str(temp_dir.resolve())
        _memory_kb_instances.pop(resolved, None)

        kb1 = get_memory_kb(temp_dir)
        kb2 = get_memory_kb(temp_dir)
        assert kb1 is kb2

    def test_different_paths(self, temp_dir):
        dir1 = temp_dir / "a"
        dir2 = temp_dir / "b"
        dir1.mkdir()
        dir2.mkdir()

        _memory_kb_instances.pop(str(dir1.resolve()), None)
        _memory_kb_instances.pop(str(dir2.resolve()), None)

        kb1 = get_memory_kb(dir1)
        kb2 = get_memory_kb(dir2)
        assert kb1 is not kb2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
