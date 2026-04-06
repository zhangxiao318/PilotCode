"""Tests for command types module."""

import pytest
from typing import Awaitable

from pilotcode.types.command import (
    CommandContext,
    Command,
    PromptCommand,
    LocalCommand,
    LocalJSXCommand,
    LocalCommandResult,
)
from pilotcode.types.message import ContentBlock, TextBlock


class TestCommandContext:
    """Tests for CommandContext."""

    def test_creation(self):
        """Test creating CommandContext."""
        ctx = CommandContext(cwd="/tmp")

        assert ctx.cwd == "/tmp"
        assert ctx.verbose is False
        assert ctx.query_engine is None

    def test_creation_with_verbose(self):
        """Test creating CommandContext with verbose."""
        ctx = CommandContext(cwd="/home", verbose=True)

        assert ctx.cwd == "/home"
        assert ctx.verbose is True

    def test_creation_with_query_engine(self):
        """Test creating CommandContext with query engine."""
        mock_engine = {"name": "test_engine"}
        ctx = CommandContext(cwd="/", query_engine=mock_engine)

        assert ctx.query_engine == mock_engine


class TestCommand:
    """Tests for Command base class."""

    def test_creation(self):
        """Test creating Command."""
        cmd = Command(name="test", description="Test command", type="local")

        assert cmd.name == "test"
        assert cmd.description == "Test command"
        assert cmd.type == "local"
        assert cmd.aliases == []
        assert cmd.is_enabled is True
        assert cmd.is_hidden is False

    def test_creation_with_aliases(self):
        """Test creating Command with aliases."""
        cmd = Command(
            name="status", description="Show status", type="local", aliases=["st", "stat"]
        )

        assert cmd.aliases == ["st", "stat"]

    def test_disabled_command(self):
        """Test creating disabled Command."""
        cmd = Command(name="deprecated", description="Old command", type="local", is_enabled=False)

        assert cmd.is_enabled is False

    def test_hidden_command(self):
        """Test creating hidden Command."""
        cmd = Command(name="debug", description="Debug command", type="local", is_hidden=True)

        assert cmd.is_hidden is True


class TestLocalCommandResult:
    """Tests for LocalCommandResult."""

    def test_success_result(self):
        """Test successful command result."""
        result = LocalCommandResult(success=True, message="Done")

        assert result.success is True
        assert result.message == "Done"
        assert result.data is None

    def test_failure_result(self):
        """Test failed command result."""
        result = LocalCommandResult(
            success=False, message="Error occurred", data={"error_code": 500}
        )

        assert result.success is False
        assert result.message == "Error occurred"
        assert result.data["error_code"] == 500

    def test_result_with_data(self):
        """Test command result with data."""
        result = LocalCommandResult(success=True, data={"files": ["file1.txt", "file2.txt"]})

        assert result.success is True
        assert len(result.data["files"]) == 2


class TestPromptCommand:
    """Tests for PromptCommand."""

    async def mock_get_prompt(self, args, ctx):
        """Mock get_prompt function."""
        return [TextBlock(text=f"Prompt for {args}")]

    def test_creation(self):
        """Test creating PromptCommand."""
        cmd = PromptCommand(
            name="explain",
            description="Explain code",
            progress_message="Analyzing...",
            content_length=100,
            get_prompt=self.mock_get_prompt,
        )

        assert cmd.name == "explain"
        assert cmd.type == "prompt"
        assert cmd.progress_message == "Analyzing..."
        assert cmd.content_length == 100
        assert cmd.get_prompt is not None

    def test_default_type(self):
        """Test PromptCommand has correct default type."""
        cmd = PromptCommand(
            name="test",
            description="Test",
            progress_message="Working...",
            content_length=50,
            get_prompt=self.mock_get_prompt,
        )

        assert cmd.type == "prompt"


class TestLocalCommand:
    """Tests for LocalCommand."""

    async def mock_call(self, args, ctx):
        """Mock call function."""
        return LocalCommandResult(success=True, message=f"Executed {args}")

    def test_creation(self):
        """Test creating LocalCommand."""
        cmd = LocalCommand(name="ls", description="List files", call=self.mock_call)

        assert cmd.name == "ls"
        assert cmd.type == "local"
        assert cmd.supports_non_interactive is True
        assert cmd.call is not None

    def test_non_interactive_disabled(self):
        """Test LocalCommand with non-interactive disabled."""
        cmd = LocalCommand(
            name="interactive",
            description="Interactive command",
            supports_non_interactive=False,
            call=self.mock_call,
        )

        assert cmd.supports_non_interactive is False


class TestLocalJSXCommand:
    """Tests for LocalJSXCommand."""

    async def mock_jsx_call(self, args, ctx):
        """Mock JSX call function."""
        return {"component": "TestComponent", "props": {}}

    def test_creation(self):
        """Test creating LocalJSXCommand."""
        cmd = LocalJSXCommand(
            name="dashboard", description="Show dashboard", call=self.mock_jsx_call
        )

        assert cmd.name == "dashboard"
        assert cmd.type == "local_jsx"
        assert cmd.call is not None


class TestCommandSerialization:
    """Tests for command serialization."""

    def test_command_to_dict(self):
        """Test serializing Command to dict."""
        cmd = Command(name="test", description="Test command", type="local", aliases=["t"])

        data = cmd.dict()

        assert data["name"] == "test"
        assert data["description"] == "Test command"
        assert data["type"] == "local"
        assert data["aliases"] == ["t"]
        assert data["is_enabled"] is True

    def test_local_command_result_to_dict(self):
        """Test serializing LocalCommandResult to dict."""
        result = LocalCommandResult(success=True, message="Done", data={"count": 5})

        data = result.dict()

        assert data["success"] is True
        assert data["message"] == "Done"
        assert data["data"]["count"] == 5


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
