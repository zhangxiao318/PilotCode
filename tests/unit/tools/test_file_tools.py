"""Tests for file-related tools."""

import pytest
from pathlib import Path

from pilotcode.tools.registry import get_tool_by_name


class TestFileReadTool:
    """Tests for FileRead tool."""

    @pytest.mark.asyncio
    async def test_read_existing_file(self, sample_python_file, tool_context, allow_callback):
        """Test reading an existing file."""
        tool = get_tool_by_name("FileRead")
        assert tool is not None

        parsed = tool.input_schema(file_path=str(sample_python_file))
        result = await tool.call(parsed, tool_context, allow_callback, None, lambda x: None)

        assert not result.is_error, f"Unexpected error: {result.error}"
        assert "Hello, World!" in result.data.content
        assert result.data.total_lines >= 9  # File has about 10 lines

    @pytest.mark.asyncio
    async def test_read_nonexistent_file(self, temp_dir, tool_context, allow_callback):
        """Test reading a non-existent file returns error."""
        tool = get_tool_by_name("FileRead")
        nonexistent = temp_dir / "does_not_exist.txt"

        parsed = tool.input_schema(file_path=str(nonexistent))
        result = await tool.call(parsed, tool_context, allow_callback, None, lambda x: None)

        # Should return empty content for non-existent file in some implementations
        # or have error set
        if result.is_error:
            assert "not found" in result.error.lower() or "exist" in result.error.lower()
        else:
            # Some implementations may return empty content instead
            assert result.data.content == "" or "not found" in result.data.content.lower()

    @pytest.mark.asyncio
    async def test_read_empty_file(self, empty_file, tool_context, allow_callback):
        """Test reading an empty file."""
        tool = get_tool_by_name("FileRead")

        parsed = tool.input_schema(file_path=str(empty_file))
        result = await tool.call(parsed, tool_context, allow_callback, None, lambda x: None)

        assert not result.is_error
        assert result.data.content == ""


class TestFileWriteTool:
    """Tests for FileWrite tool."""

    @pytest.mark.asyncio
    async def test_write_new_file(self, temp_dir, tool_context, allow_callback):
        """Test writing a new file."""
        tool = get_tool_by_name("FileWrite")
        file_path = temp_dir / "new_file.txt"

        parsed = tool.input_schema(file_path=str(file_path), content="Hello, World!")
        result = await tool.call(parsed, tool_context, allow_callback, None, lambda x: None)

        assert not result.is_error
        assert file_path.exists()
        assert file_path.read_text() == "Hello, World!"

    @pytest.mark.asyncio
    async def test_overwrite_existing_file(self, temp_dir, tool_context, allow_callback):
        """Test overwriting an existing file."""
        tool = get_tool_by_name("FileWrite")
        file_path = temp_dir / "existing.txt"
        file_path.write_text("Old content")

        parsed = tool.input_schema(file_path=str(file_path), content="New content")
        result = await tool.call(parsed, tool_context, allow_callback, None, lambda x: None)

        assert not result.is_error
        assert file_path.read_text() == "New content"


class TestFileEditTool:
    """Tests for FileEdit tool."""

    @pytest.mark.asyncio
    async def test_simple_replace(self, temp_dir, tool_context, allow_callback):
        """Test simple string replacement."""
        tool = get_tool_by_name("FileEdit")
        file_path = temp_dir / "edit_test.txt"
        file_path.write_text("Hello, World!")

        parsed = tool.input_schema(
            file_path=str(file_path), old_string="World", new_string="Python"
        )
        result = await tool.call(parsed, tool_context, allow_callback, None, lambda x: None)

        assert not result.is_error
        assert result.data.replacements_made == 1
        assert file_path.read_text() == "Hello, Python!"

    @pytest.mark.asyncio
    async def test_replace_not_found(self, temp_dir, tool_context, allow_callback):
        """Test replacement when string not found."""
        tool = get_tool_by_name("FileEdit")
        file_path = temp_dir / "edit_test.txt"
        file_path.write_text("Hello, World!")

        parsed = tool.input_schema(
            file_path=str(file_path), old_string="NonExistent", new_string="Replacement"
        )
        result = await tool.call(parsed, tool_context, allow_callback, None, lambda x: None)

        assert result.is_error or result.data.replacements_made == 0


class TestGlobTool:
    """Tests for Glob tool."""

    @pytest.mark.asyncio
    async def test_glob_python_files(self, temp_dir, tool_context, allow_callback):
        """Test globbing Python files."""
        # Create test files
        (temp_dir / "file1.py").touch()
        (temp_dir / "file2.py").touch()
        (temp_dir / "readme.txt").touch()

        tool = get_tool_by_name("Glob")
        parsed = tool.input_schema(pattern="*.py", path=str(temp_dir))
        result = await tool.call(parsed, tool_context, allow_callback, None, lambda x: None)

        assert not result.is_error
        assert len(result.data.filenames) == 2
        assert "file1.py" in result.data.filenames
        assert "file2.py" in result.data.filenames


class TestGrepTool:
    """Tests for Grep tool."""

    @pytest.mark.asyncio
    async def test_grep_pattern(self, temp_dir, tool_context, allow_callback):
        """Test grep pattern matching."""
        # Create test file
        test_file = temp_dir / "test.txt"
        test_file.write_text("line 1\ndef hello():\nline 3\ndef world():\n")

        tool = get_tool_by_name("Grep")
        parsed = tool.input_schema(pattern="def ", path=str(temp_dir), output_format="brief")
        result = await tool.call(parsed, tool_context, allow_callback, None, lambda x: None)

        assert not result.is_error
        assert "def hello" in result.data.content or result.data.match_count >= 2
