"""Tests for slash commands."""

import pytest

from pilotcode.commands.base import (
    parse_command,
    process_user_input,
    get_command_registry,
    CommandContext,
)


class TestCommandParsing:
    """Tests for command parsing utilities."""

    def test_parse_simple_command(self):
        name, args = parse_command("/help")
        assert name == "help"
        assert args == []

    def test_parse_command_with_args(self):
        name, args = parse_command("/git log --oneline")
        assert name == "git"
        assert args == ["log", "--oneline"]

    def test_parse_not_a_command(self):
        name, args = parse_command("hello world")
        assert name is None
        assert args == []

    def test_parse_empty(self):
        name, args = parse_command("")
        assert name is None


class TestBuiltInCommands:
    """Tests for built-in commands."""

    @pytest.mark.asyncio
    async def test_help_command(self):
        ctx = CommandContext(cwd=".")
        is_cmd, result = await process_user_input("/help", ctx)
        assert is_cmd is True
        assert "Available commands" in result

    @pytest.mark.asyncio
    async def test_clear_command(self):
        ctx = CommandContext(cwd=".")
        is_cmd, result = await process_user_input("/clear", ctx)
        assert is_cmd is True
        assert "Screen cleared" in result

    @pytest.mark.asyncio
    async def test_quit_command(self):
        ctx = CommandContext(cwd=".")
        with pytest.raises(SystemExit):
            await process_user_input("/quit", ctx)

    @pytest.mark.asyncio
    async def test_unknown_command(self):
        ctx = CommandContext(cwd=".")
        is_cmd, result = await process_user_input("/notreal", ctx)
        assert is_cmd is True
        assert "Unknown command" in result


class TestGitCommands:
    """Tests for git-related slash commands."""

    @pytest.mark.asyncio
    async def test_branch_command(self):
        ctx = CommandContext(cwd=".")
        is_cmd, result = await process_user_input("/branch", ctx)
        assert is_cmd is True
        # Should list branches since we're in a git repo
        assert "branch" in result.lower() or "*" in result

    @pytest.mark.asyncio
    async def test_diff_command_no_args(self):
        ctx = CommandContext(cwd=".")
        is_cmd, result = await process_user_input("/diff", ctx)
        assert is_cmd is True


class TestCommandRegistry:
    """Tests for the command registry."""

    def test_commands_are_registered(self):
        registry = get_command_registry()
        essential = ["help", "clear", "quit", "git", "branch", "config"]
        for cmd in essential:
            assert registry.has_command(cmd), f"Command /{cmd} should be registered"

    def test_command_aliases(self):
        registry = get_command_registry()
        assert registry.get("h") is not None  # alias for help
        assert registry.get("q") is not None  # alias for quit
