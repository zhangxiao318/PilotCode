"""Tests for SmartEditPlanner tool."""

import tempfile
from pathlib import Path

from pilotcode.tools.smart_edit_planner import (
    plan_edits,
)


class TestPlanEdits:
    """Test the core edit planning logic."""

    async def test_finds_all_occurrences(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            p1 = Path(tmpdir) / "a.py"
            p1.write_text("foo()\nbar()\nfoo()\n")
            p2 = Path(tmpdir) / "b.py"
            p2.write_text("baz()\nfoo()\n")

            result = await plan_edits(
                pattern="foo()",
                replacement_hint="new_foo()",
                scope=tmpdir,
                glob=None,
                max_results=50,
            )

            assert result.total_occurrences == 3
            assert len(result.checklist) == 3
            assert sorted(result.files_affected) == ["a.py", "b.py"]
            assert result.pattern == "foo()"
            assert not result.truncated

    async def test_respects_glob_filter(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            p1 = Path(tmpdir) / "a.py"
            p1.write_text("foo()\n")
            p2 = Path(tmpdir) / "a.txt"
            p2.write_text("foo()\n")

            result = await plan_edits(
                pattern="foo()",
                replacement_hint="new_foo()",
                scope=tmpdir,
                glob="*.py",
                max_results=50,
            )

            assert result.total_occurrences == 1
            assert len(result.checklist) == 1
            assert result.files_affected == ["a.py"]

    async def test_respects_max_results(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            p = Path(tmpdir) / "a.py"
            p.write_text("\n".join(["foo()"] * 10))

            result = await plan_edits(
                pattern="foo()",
                replacement_hint="new_foo()",
                scope=tmpdir,
                glob=None,
                max_results=5,
            )

            assert result.total_occurrences == 10
            assert len(result.checklist) == 5
            assert result.truncated is True
            assert "truncated" in result.note.lower()

    async def test_no_matches(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            p = Path(tmpdir) / "a.py"
            p.write_text("bar()\n")

            result = await plan_edits(
                pattern="foo()",
                replacement_hint="new_foo()",
                scope=tmpdir,
                glob=None,
                max_results=50,
            )

            assert result.total_occurrences == 0
            assert len(result.checklist) == 0
            assert "no occurrences found" in result.note.lower()

    async def test_single_file_scope(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            p = Path(tmpdir) / "a.py"
            p.write_text("foo()\nbar()\n")

            result = await plan_edits(
                pattern="foo()",
                replacement_hint="new_foo()",
                scope=str(p),
                glob=None,
                max_results=50,
            )

            assert result.total_occurrences == 1
            assert len(result.checklist) == 1

    async def test_checklist_item_has_context(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            p = Path(tmpdir) / "a.py"
            p.write_text("line1\nline2\nfoo()\nline4\nline5\n")

            result = await plan_edits(
                pattern="foo()",
                replacement_hint="new_foo()",
                scope=tmpdir,
                glob=None,
                max_results=50,
            )

            item = result.checklist[0]
            assert item.file_path == "a.py"
            assert item.line_number == 3
            assert "line2" in item.context_before
            assert "line4" in item.context_after
            assert item.matched_line == "foo()"
            assert item.suggested_edit == "new_foo()"

    async def test_ignores_hidden_dirs(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            p = Path(tmpdir) / "a.py"
            p.write_text("foo()\n")
            hidden = Path(tmpdir) / ".git"
            hidden.mkdir()
            (hidden / "b.py").write_text("foo()\n")

            result = await plan_edits(
                pattern="foo()",
                replacement_hint="new_foo()",
                scope=tmpdir,
                glob=None,
                max_results=50,
            )

            assert result.total_occurrences == 1
            assert result.files_affected == ["a.py"]

    async def test_ignores_pycache(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            p = Path(tmpdir) / "a.py"
            p.write_text("foo()\n")
            cache = Path(tmpdir) / "__pycache__"
            cache.mkdir()
            (cache / "b.cpython-310.pyc").write_text("foo()\n")

            result = await plan_edits(
                pattern="foo()",
                replacement_hint="new_foo()",
                scope=tmpdir,
                glob=None,
                max_results=50,
            )

            assert result.total_occurrences == 1

    async def test_missing_scope_path(self):
        result = await plan_edits(
            pattern="foo()",
            replacement_hint="new_foo()",
            scope="/nonexistent/path",
            glob=None,
            max_results=50,
        )
        assert result.total_occurrences == 0
        assert "not found" in result.note.lower()
