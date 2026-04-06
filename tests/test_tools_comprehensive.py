"""Comprehensive unit tests for all tool categories."""

import os
import time

import pytest

from pilotcode.tools.base import ToolUseContext
from pilotcode.tools.registry import get_tool_by_name, get_all_tools
from tests.conftest import create_test_file


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
async def _allow_callback(*args, **kwargs):
    return {"behavior": "allow"}


def _convert_paths_to_strings(data: dict) -> dict:
    """Convert Path objects to strings in input data."""
    from pathlib import Path

    result = {}
    for key, value in data.items():
        if isinstance(value, Path):
            result[key] = str(value)
        else:
            result[key] = value
    return result


async def call_tool(tool_name: str, input_data: dict, context: ToolUseContext | None = None):
    """Helper to call a tool by name with default allow callback."""
    tool = get_tool_by_name(tool_name)
    assert tool is not None, f"Tool {tool_name} not found"
    ctx = context or ToolUseContext()
    # Convert Path objects to strings
    input_data = _convert_paths_to_strings(input_data)
    parsed = tool.input_schema(**input_data)
    return await tool.call(
        parsed,
        ctx,
        _allow_callback,
        None,
        lambda x: None,
    )


# ---------------------------------------------------------------------------
# File tools
# ---------------------------------------------------------------------------
class TestFileWriteTool:
    @pytest.mark.asyncio
    async def test_write_new_file(self, temp_dir):
        path = os.path.join(temp_dir, "new.txt")
        result = await call_tool("FileWrite", {"file_path": path, "content": "hello"})
        assert not result.is_error
        assert os.path.exists(path)
        assert open(path).read() == "hello"

    @pytest.mark.asyncio
    async def test_overwrite_with_read_first(self, temp_dir):
        path = os.path.join(temp_dir, "overwrite.txt")
        open(path, "w").write("old")

        ctx = ToolUseContext()
        # Simulate read first
        ctx.read_file_state[path] = {"timestamp": time.time() + 1}

        result = await call_tool(
            "FileWrite",
            {"file_path": path, "content": "new"},
            ctx,
        )
        assert not result.is_error
        assert open(path).read() == "new"


class TestFileReadTool:
    @pytest.mark.asyncio
    async def test_read_file(self, temp_dir):
        path = create_test_file(temp_dir, "readme.md", "# Title")
        result = await call_tool("FileRead", {"file_path": path})
        assert not result.is_error
        assert "# Title" in result.data.content

    @pytest.mark.asyncio
    async def test_read_nonexistent(self, temp_dir):
        path = os.path.join(temp_dir, "missing.txt")
        result = await call_tool("FileRead", {"file_path": path})
        # FileRead returns empty content for missing files rather than an error
        assert not result.is_error
        assert result.data.content == ""


class TestFileEditTool:
    @pytest.mark.asyncio
    async def test_simple_replace(self, temp_dir):
        path = create_test_file(temp_dir, "code.py", "print('old')\n")
        result = await call_tool(
            "FileEdit",
            {
                "file_path": path,
                "old_string": "print('old')",
                "new_string": "print('new')",
            },
        )
        assert not result.is_error
        assert "print('new')" in open(path).read()

    @pytest.mark.asyncio
    async def test_replace_not_found(self, temp_dir):
        path = create_test_file(temp_dir, "code.py", "print('old')\n")
        result = await call_tool(
            "FileEdit",
            {
                "file_path": path,
                "old_string": "nonexistent",
                "new_string": "new",
            },
        )
        # FileEdit reports 0 replacements rather than an error
        assert not result.is_error
        assert result.data.replacements_made == 0


# ---------------------------------------------------------------------------
# Shell tools
# ---------------------------------------------------------------------------
class TestBashTool:
    @pytest.mark.asyncio
    async def test_echo(self):
        result = await call_tool("Bash", {"command": "echo test123"})
        assert not result.is_error
        assert "test123" in result.data.stdout
        assert result.data.exit_code == 0

    @pytest.mark.asyncio
    async def test_stderr(self):
        result = await call_tool("Bash", {"command": "echo error >&2"})
        assert not result.is_error
        assert "error" in result.data.stderr

    @pytest.mark.asyncio
    async def test_invalid_command(self):
        result = await call_tool("Bash", {"command": "not_a_real_command_12345"})
        # Bash returns non-zero but tool itself succeeds
        assert result.data.exit_code != 0

    @pytest.mark.asyncio
    async def test_timeout(self):
        result = await call_tool("Bash", {"command": "sleep 10", "timeout": 1})
        assert "timed out" in result.data.stderr.lower() or result.data.exit_code == -1


# ---------------------------------------------------------------------------
# Search tools
# ---------------------------------------------------------------------------
class TestGlobTool:
    @pytest.mark.asyncio
    async def test_glob_py_files(self, temp_dir):
        create_test_file(temp_dir, "a.py", "")
        create_test_file(temp_dir, "b.py", "")
        create_test_file(temp_dir, "c.txt", "")
        result = await call_tool("Glob", {"pattern": "*.py", "path": temp_dir})
        assert not result.is_error
        filenames = [os.path.basename(f) for f in result.data.filenames]
        assert "a.py" in filenames
        assert "b.py" in filenames
        assert "c.txt" not in filenames


class TestGrepTool:
    @pytest.mark.asyncio
    async def test_grep_content(self, temp_dir):
        create_test_file(temp_dir, "sample.txt", "hello world\nhello python\n")
        result = await call_tool(
            "Grep",
            {
                "pattern": "hello",
                "path": temp_dir,
                "glob": "*.txt",
                "output_mode": "content",
            },
        )
        assert not result.is_error
        assert result.data.num_matches >= 2

    @pytest.mark.asyncio
    async def test_grep_files_with_matches(self, temp_dir):
        create_test_file(temp_dir, "a.txt", "target")
        create_test_file(temp_dir, "b.txt", "other")
        result = await call_tool(
            "Grep",
            {
                "pattern": "target",
                "path": temp_dir,
                "glob": "*.txt",
                "output_mode": "files_with_matches",
            },
        )
        assert not result.is_error
        assert any("a.txt" in f for f in result.data.filenames)


# ---------------------------------------------------------------------------
# Git tools (only test if inside a git repo)
# ---------------------------------------------------------------------------
class TestGitTools:
    @pytest.mark.asyncio
    async def test_git_status_in_repo(self):
        # This test runs in PilotCode which is a git repo
        result = await call_tool("GitStatus", {"repo_path": "."})
        assert not result.is_error
        # Should contain branch info or file status
        assert result.data.branch is not None or "branch" in result.data.status.lower()

    @pytest.mark.asyncio
    async def test_git_branch(self):
        result = await call_tool("GitBranch", {"repo_path": "."})
        assert not result.is_error
        assert len(result.data.branches) > 0


# ---------------------------------------------------------------------------
# Web tools (requires network, mark optional)
# ---------------------------------------------------------------------------
class TestWebTools:
    @pytest.mark.asyncio
    @pytest.mark.skip(reason="Network-dependent; run manually with --run-web-tests")
    async def test_web_search(self):
        result = await call_tool("WebSearch", {"query": "python factorial"})
        assert not result.is_error
        assert len(result.data.results) > 0 or "error" not in str(result.data).lower()

    @pytest.mark.asyncio
    @pytest.mark.skip(reason="Network-dependent; run manually with --run-web-tests")
    async def test_web_fetch(self):
        result = await call_tool("WebFetch", {"url": "https://example.com"})
        assert not result.is_error
        assert "example" in result.data.content.lower()


# ---------------------------------------------------------------------------
# Config / Todo / Brief tools
# ---------------------------------------------------------------------------
class TestMiscTools:
    @pytest.mark.asyncio
    async def test_todo_write(self, temp_dir):
        result = await call_tool(
            "TodoWrite", {"todos": [{"content": "test todo", "status": "in_progress"}]}
        )
        assert not result.is_error

    @pytest.mark.asyncio
    async def test_brief_tool(self):
        result = await call_tool("Brief", {"content": "a" * 500})
        assert not result.is_error
        assert len(result.data.summary) < 500

    @pytest.mark.asyncio
    async def test_config_tool(self, temp_dir):
        result = await call_tool("Config", {"action": "get", "key": "theme"})
        assert not result.is_error


# ---------------------------------------------------------------------------
# Registry tests
# ---------------------------------------------------------------------------
class TestRegistry:
    def test_all_tools_loadable(self):
        tools = get_all_tools()
        assert len(tools) >= 40
        for tool in tools:
            assert tool.name
            assert tool.input_schema is not None
            assert tool.call is not None

    def test_get_tool_by_alias(self):
        assert get_tool_by_name("bash") is not None
        assert get_tool_by_name("read") is not None
        assert get_tool_by_name("write") is not None
