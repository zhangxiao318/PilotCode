"""Tests for memory_recall query-time retrieval."""

import tempfile

from pilotcode.services.memory_recall import (
    find_relevant_memories,
    format_memory_attachment,
    load_memory_content,
)
from pilotcode.services.memory_dir import write_memory_file, ensure_memory_dir


class TestFindRelevantMemories:
    def test_empty_dir(self):
        with tempfile.TemporaryDirectory() as td:
            assert find_relevant_memories("hello", td) == []

    def test_keyword_match(self):
        with tempfile.TemporaryDirectory() as td:
            write_memory_file(
                td,
                "python_style.md",
                {"description": "Python coding style preferences", "type": "user"},
                "Use black and ruff",
            )
            write_memory_file(
                td,
                "java_notes.md",
                {"description": "Java project notes", "type": "project"},
                "Spring boot setup",
            )
            results = find_relevant_memories("python formatting", td, top_k=3)
            assert len(results) == 1
            assert "python_style" in results[0]["filename"]

    def test_no_match(self):
        with tempfile.TemporaryDirectory() as td:
            write_memory_file(
                td,
                "rust.md",
                {"description": "Rust notes", "type": "reference"},
                "Cargo.toml",
            )
            results = find_relevant_memories("kubernetes deployment", td)
            assert results == []

    def test_top_k_limit(self):
        with tempfile.TemporaryDirectory() as td:
            for i in range(5):
                write_memory_file(
                    td,
                    f"file{i}.md",
                    {"description": f"python topic {i}", "type": "reference"},
                    "content",
                )
            results = find_relevant_memories("python", td, top_k=2)
            assert len(results) == 2


class TestLoadMemoryContent:
    def test_read_and_truncate(self):
        with tempfile.TemporaryDirectory() as td:
            write_memory_file(
                td,
                "long.md",
                {"description": "Long", "type": "reference"},
                "\n".join([f"line {i}" for i in range(150)]),
            )
            from pilotcode.services.memory_dir import ensure_memory_dir

            d = ensure_memory_dir(td)
            content = load_memory_content(str(d / "long.md"))
            assert "truncated" in content.lower()
            assert content.count("\n") < 110

    def test_missing_file(self):
        assert load_memory_content("/nonexistent/path.md") is None


class TestFormatMemoryAttachment:
    def test_format(self):
        with tempfile.TemporaryDirectory() as td:
            write_memory_file(
                td,
                "pref.md",
                {"description": "Pref", "type": "user"},
                "Use FastAPI",
            )
            d = ensure_memory_dir(td)
            memories = [{"filename": "pref.md", "path": str(d / "pref.md")}]
            text = format_memory_attachment(memories)
            assert "## Relevant Memories" in text
            assert "Use FastAPI" in text

    def test_empty(self):
        assert format_memory_attachment([]) == ""
