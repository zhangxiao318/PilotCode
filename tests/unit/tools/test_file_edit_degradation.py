"""Tests for FileEdit auto-degradation (line-level and block-level matching)."""

from pilotcode.tools.file_edit_tool import (
    _try_line_level_match,
    _try_block_level_match,
    _extract_anchor_lines,
)


class TestExtractAnchorLines:
    def test_extracts_meaningful_lines(self):
        text = "\n  def foo():\n    pass\n\n"
        anchors = _extract_anchor_lines(text)
        assert anchors == ["def foo():", "pass"]

    def test_ignores_short_lines(self):
        text = "a\nlonger line here\n"
        anchors = _extract_anchor_lines(text)
        assert anchors == ["longer line here"]


class TestLineLevelMatch:
    def test_basic_match(self):
        content = "line1\ndef foo():\n    pass\nline4\n"
        old = "def foo():\n    pass"
        new = "def bar():\n    return"
        matched, replacement = _try_line_level_match(content, old, new)
        assert matched is not None
        assert "def foo():\n    pass" in matched
        assert replacement == new

    def test_indented_mismatch(self):
        """Model uses wrong indentation in old_string."""
        content = "    def foo():\n        pass\n"
        old = "def foo():\n    pass"  # missing outer indent
        new = "def bar():\n    return"
        matched, replacement = _try_line_level_match(content, old, new)
        assert matched is not None  # anchor lines match ignoring whitespace
        assert "def foo():" in matched

    def test_no_match_returns_none(self):
        content = "line1\nline2\n"
        old = "def nonexistent():\n    pass"
        new = "def x():\n    pass"
        matched, _ = _try_line_level_match(content, old, new)
        assert matched is None


class TestBlockLevelMatch:
    def test_function_block_match(self):
        content = (
            "class MyClass:\n"
            "    def method(self):\n"
            "        a = 1\n"
            "        return a\n"
            "\n"
            "    def other(self):\n"
            "        pass\n"
        )
        old = "    def method(self):\n" "        a = 1\n" "        return a\n"
        new = "    def method(self):\n" "        b = 2\n" "        return b\n"
        matched, replacement = _try_block_level_match(content, old, new)
        assert matched is not None
        assert "def method(self):" in matched
        assert "return a" in matched
        assert replacement == new

    def test_no_definition_returns_none(self):
        content = "x = 1\ny = 2\n"
        old = "x = 1\ny = 2"
        new = "x = 3\ny = 4"
        matched, _ = _try_block_level_match(content, old, new)
        assert matched is None

    def test_class_block_match(self):
        content = "class A:\n" "    x = 1\n" "\n" "class B:\n" "    y = 2\n"
        old = "class A:\n" "    x = 1\n"
        new = "class A:\n" "    z = 3\n"
        matched, replacement = _try_block_level_match(content, old, new)
        assert matched is not None
        assert "class A:" in matched
        assert replacement == new
