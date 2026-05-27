"""Tests for memory_dir (memdir) file-based memory system."""

import tempfile

from pilotcode.services.memory_dir import (
    build_memory_prompt,
    ensure_memory_dir,
    load_memory_index,
    parse_frontmatter,
    scan_memory_files,
    truncate_entrypoint,
    update_memory_index,
    write_memory_file,
)


class TestTruncateEntrypoint:
    def test_no_truncation_needed(self):
        raw = "# Memory Index\n- [a](a.md) — hook\n"
        content, truncated = truncate_entrypoint(raw)
        assert not truncated
        assert "Memory Index" in content

    def test_line_truncation(self):
        raw = "\n".join([f"line {i}" for i in range(250)])
        content, truncated = truncate_entrypoint(raw)
        assert truncated
        assert "truncated" in content.lower()
        assert content.count("\n") < 210

    def test_byte_truncation(self):
        raw = "x" * 30_000
        content, truncated = truncate_entrypoint(raw)
        assert truncated
        assert len(content) < 26_000


class TestParseFrontmatter:
    def test_valid_frontmatter(self):
        text = "---\ndescription: Test\ntype: user\n---\n\nBody content"
        fm, body = parse_frontmatter(text)
        assert fm["description"] == "Test"
        assert fm["type"] == "user"
        assert body == "Body content"

    def test_no_frontmatter(self):
        text = "Just body content"
        fm, body = parse_frontmatter(text)
        assert fm == {}
        assert body == text


class TestMemoryDirLifecycle:
    def test_ensure_memory_dir(self):
        with tempfile.TemporaryDirectory() as td:
            d = ensure_memory_dir(td)
            assert d.exists()
            assert d.name == "memory"

    def test_load_memory_index_missing(self):
        with tempfile.TemporaryDirectory() as td:
            assert load_memory_index(td) is None

    def test_load_memory_index_existing(self):
        with tempfile.TemporaryDirectory() as td:
            d = ensure_memory_dir(td)
            (d / "MEMORY.md").write_text("# Index\n- [a](a.md)\n")
            content = load_memory_index(td)
            assert "# Index" in content

    def test_scan_memory_files(self):
        with tempfile.TemporaryDirectory() as td:
            d = ensure_memory_dir(td)
            (d / "user_pref.md").write_text(
                "---\ndescription: User likes Python\ntype: user\n---\n\nDetails"
            )
            (d / "MEMORY.md").write_text("# Index\n")
            files = scan_memory_files(td)
            assert len(files) == 1
            assert files[0]["filename"] == "user_pref.md"
            assert files[0]["description"] == "User likes Python"
            assert files[0]["type"] == "user"

    def test_build_memory_prompt_with_index(self):
        with tempfile.TemporaryDirectory() as td:
            d = ensure_memory_dir(td)
            (d / "MEMORY.md").write_text("# Index\n- [a](a.md) — hook\n", encoding="utf-8")
            prompt = build_memory_prompt(td)
            assert "# Memory" in prompt
            assert "MEMORY.md" in prompt
            assert "- [a](a.md) — hook" in prompt

    def test_build_memory_prompt_empty(self):
        with tempfile.TemporaryDirectory() as td:
            prompt = build_memory_prompt(td)
            assert "currently empty" in prompt

    def test_write_and_update(self):
        with tempfile.TemporaryDirectory() as td:
            write_memory_file(
                td,
                "test.md",
                {"description": "Desc", "type": "project"},
                "Content here",
            )
            update_memory_index(td, "Title", "test.md", "one-line hook")
            d = ensure_memory_dir(td)
            index = (d / "MEMORY.md").read_text(encoding="utf-8")
            assert "[Title](test.md) — one-line hook" in index
            topic = (d / "test.md").read_text(encoding="utf-8")
            assert "Content here" in topic


class TestMemoryDirDedup:
    def test_index_dedup(self):
        with tempfile.TemporaryDirectory() as td:
            update_memory_index(td, "Old", "x.md", "old hook")
            update_memory_index(td, "New", "x.md", "new hook")
            d = ensure_memory_dir(td)
            index = (d / "MEMORY.md").read_text(encoding="utf-8")
            assert index.count("x.md") == 1
            assert "new hook" in index
