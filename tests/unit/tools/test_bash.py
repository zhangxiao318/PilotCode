"""Tests for Bash tool."""

import pytest

from pilotcode.tools.registry import get_tool_by_name
from tests.conftest import run_tool_test


class TestBashTool:
    """Tests for Bash tool."""
    
    @pytest.fixture
    def bash_tool(self):
        """Get the bash tool."""
        return get_tool_by_name("Bash")
    
    @pytest.mark.asyncio
    async def test_echo_command(self, bash_tool, tool_context, allow_callback):
        """Test simple echo command."""
        result = await run_tool_test(
            "Bash",
            {"command": "echo 'Hello, World!'", "description": "Test echo"},
            tool_context,
            allow_callback
        )
        
        assert not result.is_error, f"Unexpected error: {result.error}"
        assert "Hello, World!" in result.data.stdout
        assert result.data.exit_code == 0
    
    @pytest.mark.asyncio
    async def test_pwd_command(self, bash_tool, tool_context, allow_callback):
        """Test pwd command returns current directory."""
        result = await run_tool_test(
            "Bash",
            {"command": "pwd", "description": "Get current directory"},
            tool_context,
            allow_callback
        )
        
        assert not result.is_error
        assert result.data.stdout.strip()
        assert result.data.exit_code == 0
    
    @pytest.mark.asyncio
    async def test_stderr_output(self, bash_tool, tool_context, allow_callback):
        """Test that stderr is captured."""
        result = await run_tool_test(
            "Bash",
            {"command": "echo 'error' >&2", "description": "Test stderr"},
            tool_context,
            allow_callback
        )
        
        assert not result.is_error
        assert "error" in result.data.stderr
    
    @pytest.mark.asyncio
    async def test_exit_code_nonzero(self, bash_tool, tool_context, allow_callback):
        """Test non-zero exit code handling."""
        result = await run_tool_test(
            "Bash",
            {"command": "exit 1", "description": "Test exit code"},
            tool_context,
            allow_callback
        )
        
        # Should not have error but should have exit_code 1
        assert result.data.exit_code == 1
    
    @pytest.mark.asyncio
    async def test_pipe_command(self, bash_tool, tool_context, allow_callback):
        """Test command with pipes."""
        result = await run_tool_test(
            "Bash",
            {"command": "echo 'hello world' | tr ' ' '-'", "description": "Test pipe"},
            tool_context,
            allow_callback
        )
        
        assert not result.is_error
        assert "hello-world" in result.data.stdout
    
    @pytest.mark.asyncio
    async def test_environment_variables(self, bash_tool, tool_context, allow_callback):
        """Test environment variable access."""
        result = await run_tool_test(
            "Bash",
            {"command": "echo $HOME", "description": "Test env vars"},
            tool_context,
            allow_callback
        )
        
        assert not result.is_error
        assert result.data.stdout.strip()  # Should have some value
    
    @pytest.mark.asyncio
    async def test_timeout(self, bash_tool, tool_context, allow_callback):
        """Test timeout handling."""
        result = await run_tool_test(
            "Bash",
            {"command": "sleep 10", "description": "Test timeout", "timeout": 1},
            tool_context,
            allow_callback
        )
        
        assert result.is_error or "timeout" in result.data.stderr.lower()
    
    @pytest.mark.asyncio
    async def test_multiline_output(self, bash_tool, tool_context, allow_callback):
        """Test multiline output handling."""
        result = await run_tool_test(
            "Bash",
            {"command": "seq 1 5", "description": "Test multiline"},
            tool_context,
            allow_callback
        )
        
        assert not result.is_error
        lines = result.data.stdout.strip().split("\n")
        assert len(lines) == 5
        assert "1" in lines[0]
        assert "5" in lines[-1]


class TestBashToolSecurity:
    """Security tests for Bash tool."""
    
    @pytest.mark.asyncio
    async def test_dangerous_command_detection(self, tool_context, allow_callback):
        """Test that dangerous commands are flagged."""
        tool = get_tool_by_name("Bash")
        
        # Check if command is considered dangerous
        dangerous_commands = [
            "rm -rf /",
            "rm -rf ~",
            "> /etc/passwd",
            "dd if=/dev/zero of=/dev/sda",
        ]
        
        for cmd in dangerous_commands:
            parsed = tool.input_schema(command=cmd, description="Dangerous")
            
            # Tool should either deny or require confirmation
            result = await tool.call(
                parsed, tool_context,
                lambda *args, **kwargs: {"behavior": "ask"},  # Ask for confirmation
                None, lambda x: None
            )
            
            # Should not execute without confirmation
            assert result.is_error or "confirm" in str(result.data).lower() or result.data.exit_code != 0
