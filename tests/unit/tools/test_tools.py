"""Tests for tool implementations."""

import pytest
import os
import tempfile

from pilotcode.tools.registry import get_tool_by_name
from pilotcode.tools.base import ToolUseContext
from pilotcode.tools.bash_tool import BashInput, BashTool
from pilotcode.tools.file_read_tool import FileReadInput, FileReadTool
from pilotcode.tools.file_write_tool import FileWriteInput, FileWriteTool
from pilotcode.tools.glob_tool import GlobInput, GlobTool
from pilotcode.tools.grep_tool import GrepInput, GrepTool, OutputMode


async def mock_can_use_tool(*args, **kwargs):
    """Mock permission callback that allows all operations."""
    return {"behavior": "allow"}


class TestBashTool:
    """Tests for BashTool."""

    def test_bash_tool_exists(self):
        """Test that bash tool is registered."""
        tool = get_tool_by_name("Bash")
        assert tool is not None
        assert tool.name == "Bash"

    @pytest.mark.asyncio
    async def test_bash_echo(self):
        """Test simple echo command."""
        tool = BashTool
        input_data = BashInput(command="echo hello world")

        result = await tool.call(
            input_data, ToolUseContext(), mock_can_use_tool, None, lambda x: None
        )

        assert not result.is_error
        assert "hello world" in result.data.stdout
        assert result.data.exit_code == 0

    @pytest.mark.asyncio
    async def test_bash_pwd(self):
        """Test pwd command."""
        tool = BashTool
        input_data = BashInput(command="pwd")

        result = await tool.call(
            input_data, ToolUseContext(), mock_can_use_tool, None, lambda x: None
        )

        assert not result.is_error
        assert result.data.exit_code == 0


class TestFileTools:
    """Tests for file tools."""

    @pytest.mark.asyncio
    async def test_file_write_and_read(self, project_root):
        """Test file write and read cycle."""
        import shutil

        tmpdir = project_root / "tests" / "tmp" / "test_tools_write_read"
        tmpdir.mkdir(parents=True, exist_ok=True)
        try:
            test_file = str(tmpdir / "test.txt")
            test_content = "Hello, World!"

            # Write file
            write_tool = FileWriteTool
            write_input = FileWriteInput(file_path=test_file, content=test_content)

            await write_tool.call(
                write_input, ToolUseContext(), mock_can_use_tool, None, lambda x: None
            )

            # Should fail without read first (conflict detection)
            # But we can bypass by setting up read_file_state
            context = ToolUseContext()
            import time

            context.read_file_state[test_file] = {"timestamp": time.time() + 1}

            await write_tool.call(write_input, context, mock_can_use_tool, None, lambda x: None)

            # Read file
            read_tool = FileReadTool
            read_input = FileReadInput(file_path=test_file)

            read_result = await read_tool.call(
                read_input, ToolUseContext(), mock_can_use_tool, None, lambda x: None
            )

            assert not read_result.is_error
            assert test_content in read_result.data.content
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)


class TestGlobTool:
    """Tests for GlobTool."""

    @pytest.mark.asyncio
    async def test_glob_python_files(self):
        """Test globbing Python files."""
        tool = GlobTool
        input_data = GlobInput(pattern="*.py", path=".")

        result = await tool.call(
            input_data, ToolUseContext(), mock_can_use_tool, None, lambda x: None
        )

        assert not result.is_error
        assert isinstance(result.data.filenames, list)

    @pytest.mark.asyncio
    async def test_glob_nonexistent_path(self):
        """Test glob with nonexistent path."""
        tool = GlobTool
        input_data = GlobInput(pattern="*", path="/nonexistent/path/12345")

        result = await tool.call(
            input_data, ToolUseContext(), mock_can_use_tool, None, lambda x: None
        )

        # Should return error in data
        assert result.data.total_count == 0


class TestGrepTool:
    """Tests for GrepTool."""

    @pytest.mark.asyncio
    async def test_grep_simple(self):
        """Test simple grep."""
        # Create a test file
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("hello world\n")
            f.write("hello python\n")
            f.write("goodbye world\n")
            test_file = f.name

        try:
            tool = GrepTool
            input_data = GrepInput(pattern="hello", path=test_file, output_mode=OutputMode.CONTENT)

            result = await tool.call(
                input_data, ToolUseContext(), mock_can_use_tool, None, lambda x: None
            )

            assert not result.is_error
            assert result.data.num_matches == 2
        finally:
            os.unlink(test_file)

    @pytest.mark.asyncio
    async def test_grep_files_with_matches(self):
        """Test grep files_with_matches mode."""
        tool = GrepTool
        input_data = GrepInput(
            pattern="def ", path=".", glob="*.py", output_mode=OutputMode.FILES_WITH_MATCHES
        )

        result = await tool.call(
            input_data, ToolUseContext(), mock_can_use_tool, None, lambda x: None
        )

        assert not result.is_error
        assert result.data.filenames is not None


class TestToolRegistry:
    """Tests for tool registry."""

    def test_all_tools_registered(self):
        """Test that all tools are registered."""
        from pilotcode.tools.registry import get_all_tools

        tools = get_all_tools()
        tool_names = [t.name for t in tools]

        assert "Bash" in tool_names
        assert "FileRead" in tool_names
        assert "FileWrite" in tool_names
        assert "Glob" in tool_names
        assert "Grep" in tool_names
        assert "FileEdit" in tool_names
        assert "AskUser" in tool_names
        assert "TodoWrite" in tool_names
        assert "WebSearch" in tool_names
        assert "WebFetch" in tool_names

    def test_tool_aliases(self):
        """Test tool aliases."""
        assert get_tool_by_name("bash") is not None  # Bash alias
        assert get_tool_by_name("read") is not None  # FileRead alias
        assert get_tool_by_name("write") is not None  # FileWrite alias
