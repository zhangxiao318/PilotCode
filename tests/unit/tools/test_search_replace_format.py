"""Tests for Claude-style search/replace edit format parsing."""

from __future__ import annotations


from pilotcode.tools.file_edit_tool import (
    _parse_search_replace_blocks,
    edit_file_content,
)


class TestParseSearchReplaceBlocks:
    def test_no_blocks_returns_none(self):
        assert _parse_search_replace_blocks("plain old string") is None

    def test_single_block(self):
        text = """<<<<<<< SEARCH
old content
=======
new content
>>>>>>> REPLACE"""
        blocks = _parse_search_replace_blocks(text)
        assert blocks is not None
        assert len(blocks) == 1
        assert blocks[0] == ("old content", "new content")

    def test_multiple_blocks(self):
        text = """<<<<<<< SEARCH
old1
=======
new1
>>>>>>> REPLACE

<<<<<<< SEARCH
old2
=======
new2
>>>>>>> REPLACE"""
        blocks = _parse_search_replace_blocks(text)
        assert blocks is not None
        assert len(blocks) == 2
        assert blocks[0] == ("old1", "new1")
        assert blocks[1] == ("old2", "new2")

    def test_block_with_leading_trailing_newlines(self):
        text = """<<<<<<< SEARCH

old content

=======

new content

>>>>>>> REPLACE"""
        blocks = _parse_search_replace_blocks(text)
        assert blocks is not None
        assert blocks[0] == ("old content", "new content")

    def test_multiline_block(self):
        text = """<<<<<<< SEARCH
line1
line2
line3
=======
lineA
lineB
lineC
>>>>>>> REPLACE"""
        blocks = _parse_search_replace_blocks(text)
        assert blocks is not None
        assert blocks[0] == ("line1\nline2\nline3", "lineA\nlineB\nlineC")

    def test_incomplete_block_returns_none(self):
        text = """<<<<<<< SEARCH
old content
=======
new content"""
        assert _parse_search_replace_blocks(text) is None


class TestSearchReplaceEditExecution:
    async def test_single_block_edit(self, tmp_path):
        f = tmp_path / "test.py"
        f.write_text("def foo():\n    return 1\n")

        blocks = _parse_search_replace_blocks(
            "<<<<<<< SEARCH\ndef foo():\n    return 1\n=======\ndef foo():\n    return 2\n>>>>>>> REPLACE"
        )
        assert blocks is not None

        for old, new in blocks:
            result = await edit_file_content(str(f), old, new, None, str(tmp_path))
            assert result.error is None
            assert result.replacements_made == 1

        assert "return 2" in f.read_text()

    async def test_multiple_blocks_sequential(self, tmp_path):
        f = tmp_path / "test.py"
        f.write_text("a\nb\nc\n")

        blocks = _parse_search_replace_blocks(
            "<<<<<<< SEARCH\na\n=======\nx\n>>>>>>> REPLACE\n"
            "<<<<<<< SEARCH\nc\n=======\nz\n>>>>>>> REPLACE"
        )
        assert blocks is not None
        assert len(blocks) == 2

        for old, new in blocks:
            result = await edit_file_content(str(f), old, new, None, str(tmp_path))
            assert result.error is None

        content = f.read_text()
        assert "x\n" in content
        assert "z\n" in content
        assert "a\n" not in content
        assert "c\n" not in content
