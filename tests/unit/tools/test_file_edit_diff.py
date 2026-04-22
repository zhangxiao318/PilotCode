"""Tests for FileEdit tool unified diff functionality."""

import pytest
import tempfile
import os
from pathlib import Path

from pilotcode.tools.file_edit_tool import (
    _generate_unified_diff,
    edit_file_content,
    FileEditOutput,
)


@pytest.fixture
def temp_file_in_project(temp_dir):
    """Create a temporary file within the project directory for testing."""
    file_path = temp_dir / "test_edit.txt"
    file_path.write_text("hello world\nsecond line\nthird line\n")
    yield str(file_path)
    # Cleanup handled by temp_dir fixture


class TestUnifiedDiffGeneration:
    """Test unified diff generation."""

    def test_basic_diff(self):
        """Test basic diff generation."""
        old = "line1\nline2\nline3\n"
        new = "line1\nmodified\nline3\n"

        diff = _generate_unified_diff(old, new, "test.txt")

        assert "--- a/test.txt" in diff
        assert "+++ b/test.txt" in diff
        assert "-line2" in diff
        assert "+modified" in diff
        assert "@@" in diff  # Hunk header

    def test_empty_diff(self):
        """Test diff with no changes."""
        old = "line1\nline2\n"
        new = "line1\nline2\n"

        diff = _generate_unified_diff(old, new, "test.txt")

        # No changes means empty diff
        assert diff == ""

    def test_addition_only(self):
        """Test diff with only additions."""
        old = "line1\n"
        new = "line1\nline2\nline3\n"

        diff = _generate_unified_diff(old, new, "test.txt")

        assert "+line2" in diff
        assert "+line3" in diff
        assert "-line2" not in diff

    def test_deletion_only(self):
        """Test diff with only deletions."""
        old = "line1\nline2\nline3\n"
        new = "line1\n"

        diff = _generate_unified_diff(old, new, "test.txt")

        assert "-line2" in diff
        assert "-line3" in diff
        assert "+line2" not in diff

    def test_context_lines(self):
        """Test context lines around changes."""
        old = "a\nb\nc\nd\ne\nf\ng\n"
        new = "a\nb\nMODIFIED\nd\ne\nf\ng\n"

        diff = _generate_unified_diff(old, new, "test.txt", context_lines=2)

        # Should show context lines
        assert "a" in diff
        assert "b" in diff
        assert "d" in diff
        assert "e" in diff

    def test_diff_truncation(self):
        """Test large diff truncation."""
        old = "\n".join([f"line{i}" for i in range(1000)]) + "\n"
        new = "\n".join([f"modified{i}" for i in range(1000)]) + "\n"

        diff = _generate_unified_diff(old, new, "test.txt", max_diff_size=500)

        assert len(diff) <= 500
        assert "... (diff truncated)" in diff

    def test_no_newline_at_end(self):
        """Test files without trailing newline."""
        old = "line1\nline2"
        new = "line1\nmodified"

        diff = _generate_unified_diff(old, new, "test.txt")

        # Should handle missing newline gracefully
        assert "--- a/test.txt" in diff
        assert "+++ b/test.txt" in diff


class TestEditFileContentWithDiff:
    """Test edit_file_content with diff output."""

    async def test_edit_generates_diff(self, temp_file_in_project):
        temp_file = temp_file_in_project
        """Test that editing generates a diff."""
        result = await edit_file_content(
            temp_file, old_string="hello world", new_string="hello Python"
        )

        assert result.replacements_made == 1
        assert result.diff is not None
        assert "--- a/" in result.diff
        assert "+++ b/" in result.diff
        assert "-hello world" in result.diff
        assert "+hello Python" in result.diff

    async def test_edit_preserves_content(self, temp_file_in_project):
        temp_file = temp_file_in_project
        """Test that editing actually modifies the file."""
        result = await edit_file_content(
            temp_file, old_string="second line", new_string="modified line"
        )

        # Check file was modified
        with open(temp_file, "r") as f:
            content = f.read()

        assert "modified line" in content
        assert "second line" not in content

    async def test_edit_no_match_returns_error(self, temp_file_in_project):
        temp_file = temp_file_in_project
        """Test editing with no match returns error."""
        result = await edit_file_content(
            temp_file, old_string="nonexistent string", new_string="replacement"
        )

        assert result.replacements_made == 0
        assert result.error is not None
        assert result.diff is None

    async def test_edit_multiple_replacements(self, temp_file_in_project):
        temp_file = temp_file_in_project
        """Test editing with multiple replacements."""
        # Create file with repeated content
        with open(temp_file, "w") as f:
            f.write("repeat\nrepeat\nrepeat\n")

        result = await edit_file_content(temp_file, old_string="repeat", new_string="modified")

        assert result.replacements_made == 3
        assert result.diff is not None

    async def test_edit_with_expected_replacements(self, temp_file_in_project):
        temp_file = temp_file_in_project
        """Test editing with expected replacements check."""
        result = await edit_file_content(
            temp_file, old_string="hello world", new_string="hello Python", expected_replacements=1
        )

        assert result.replacements_made == 1
        assert result.error is None

    async def test_edit_with_wrong_expected_replacements(self, temp_file_in_project):
        temp_file = temp_file_in_project
        """Test editing with wrong expected replacements."""
        result = await edit_file_content(
            temp_file,
            old_string="hello world",
            new_string="hello Python",
            expected_replacements=5,  # Wrong count
        )

        assert result.replacements_made == 0
        assert "Expected 5 occurrences" in result.error

    async def test_edit_nonexistent_file(self, temp_dir):
        """Test editing a nonexistent file."""
        nonexistent = temp_dir / "nonexistent" / "file.txt"
        result = await edit_file_content(str(nonexistent), old_string="old", new_string="new")

        assert result.replacements_made == 0
        assert "File not found" in result.error or "does not exist" in result.error


class TestFileEditOutput:
    """Test FileEditOutput model."""

    def test_output_with_diff(self):
        """Test output with diff field."""
        output = FileEditOutput(
            file_path="/tmp/test.txt",
            replacements_made=1,
            diff="--- a/test.txt\n+++ b/test.txt\n@@ -1 +1 @@\n-old\n+new\n",
        )

        assert output.file_path == "/tmp/test.txt"
        assert output.replacements_made == 1
        assert output.diff is not None
        assert "old" in output.diff
        assert "new" in output.diff

    def test_output_with_error(self):
        """Test output with error."""
        output = FileEditOutput(
            file_path="/tmp/test.txt", replacements_made=0, error="File not found"
        )

        assert output.error == "File not found"
        assert output.diff is None

    def test_output_without_diff(self):
        """Test output without diff (backward compatibility)."""
        output = FileEditOutput(file_path="/tmp/test.txt", replacements_made=1)

        assert output.diff is None
        assert output.error is None
