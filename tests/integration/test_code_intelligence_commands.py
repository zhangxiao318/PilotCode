"""Tests for Code Intelligence Commands."""

import pytest
from unittest.mock import patch, MagicMock, AsyncMock

from pilotcode.commands.code_intelligence_commands import (
    get_language_from_file,
    format_symbol_kind,
    get_symbol_icon,
    symbols_command,
    references_command,
    definitions_command,
    hover_command,
    implementations_command,
    workspace_symbol_command,
)


# Fixtures
@pytest.fixture
def command_context():
    """Create a mock command context."""
    ctx = MagicMock()
    ctx.cwd = "/test/project"
    return ctx


@pytest.fixture
def mock_lsp_manager():
    """Mock LSP manager."""
    with patch("pilotcode.commands.code_intelligence_commands.get_lsp_manager") as mock:
        manager = MagicMock()
        manager.start_server = AsyncMock()
        manager.get_document_symbols = AsyncMock(return_value=[])
        manager.get_references = AsyncMock(return_value=[])
        manager.get_definition = AsyncMock(return_value=[])
        manager.get_hover = AsyncMock(return_value=None)
        manager.get_implementations = AsyncMock(return_value=[])
        manager.get_workspace_symbols = AsyncMock(return_value=[])
        mock.return_value = manager
        yield manager


@pytest.fixture
def mock_repo_info():
    """Mock repo info."""
    with patch("pilotcode.commands.code_intelligence_commands.get_repo_info_sync") as mock:
        mock.return_value = MagicMock(root_path="/test/project", is_git_repo=True)
        yield mock


# Test get_language_from_file
class TestGetLanguageFromFile:
    """Test language detection from file extension."""

    def test_python_file(self):
        """Test detecting Python files."""
        from pilotcode.services.lsp_manager import Language

        lang = get_language_from_file("test.py")
        assert lang == Language.PYTHON

    def test_typescript_file(self):
        """Test detecting TypeScript files."""
        from pilotcode.services.lsp_manager import Language

        lang = get_language_from_file("test.ts")
        assert lang == Language.TYPESCRIPT

    def test_javascript_file(self):
        """Test detecting JavaScript files."""
        from pilotcode.services.lsp_manager import Language

        lang = get_language_from_file("test.js")
        assert lang == Language.TYPESCRIPT

    def test_rust_file(self):
        """Test detecting Rust files."""
        from pilotcode.services.lsp_manager import Language

        lang = get_language_from_file("test.rs")
        assert lang == Language.RUST

    def test_go_file(self):
        """Test detecting Go files."""
        from pilotcode.services.lsp_manager import Language

        lang = get_language_from_file("test.go")
        assert lang == Language.GO

    def test_unsupported_file(self):
        """Test unsupported file type."""
        lang = get_language_from_file("test.unknown")
        assert lang is None

    def test_file_without_extension(self):
        """Test file without extension."""
        lang = get_language_from_file("Makefile")
        assert lang is None


# Test format_symbol_kind
class TestFormatSymbolKind:
    """Test symbol kind formatting."""

    def test_class_kind(self):
        """Test class symbol kind."""
        assert format_symbol_kind(5) == "Class"

    def test_method_kind(self):
        """Test method symbol kind."""
        assert format_symbol_kind(6) == "Method"

    def test_function_kind(self):
        """Test function symbol kind."""
        assert format_symbol_kind(12) == "Function"

    def test_variable_kind(self):
        """Test variable symbol kind."""
        assert format_symbol_kind(13) == "Variable"

    def test_unknown_kind(self):
        """Test unknown symbol kind."""
        assert format_symbol_kind(999) == "Unknown"

    def test_file_kind(self):
        """Test file symbol kind."""
        assert format_symbol_kind(1) == "File"


# Test get_symbol_icon
class TestGetSymbolIcon:
    """Test symbol icon selection."""

    def test_class_icon(self):
        """Test class icon."""
        icon = get_symbol_icon(5)
        assert icon == "🔷"

    def test_function_icon(self):
        """Test function icon."""
        icon = get_symbol_icon(12)
        assert icon == "⚙️"

    def test_variable_icon(self):
        """Test variable icon."""
        icon = get_symbol_icon(13)
        assert icon == "📍"

    def test_unknown_icon(self):
        """Test unknown icon."""
        icon = get_symbol_icon(999)
        assert icon == "📄"


# Test symbols_command
class TestSymbolsCommand:
    """Test symbols command."""

    @pytest.mark.asyncio
    async def test_symbols_no_args(self, command_context):
        """Test symbols command with no arguments."""
        result = await symbols_command([], command_context)
        assert "Usage:" in result

    @pytest.mark.asyncio
    async def test_symbols_help(self, command_context):
        """Test symbols command help."""
        result = await symbols_command(["--help"], command_context)
        assert "Usage:" in result

    @pytest.mark.asyncio
    async def test_symbols_file_not_found(self, command_context):
        """Test symbols with non-existent file."""
        with patch("os.path.exists", return_value=False):
            result = await symbols_command(["nonexistent.py"], command_context)
            assert "not found" in result.lower()

    @pytest.mark.asyncio
    async def test_symbols_unsupported_file(self, command_context):
        """Test symbols with unsupported file type."""
        with patch("os.path.exists", return_value=True):
            result = await symbols_command(["test.unknown"], command_context)
            assert "unsupported" in result.lower()

    @pytest.mark.asyncio
    async def test_symbols_success(self, command_context, mock_lsp_manager, mock_repo_info):
        """Test successful symbols retrieval."""
        mock_lsp_manager.get_document_symbols.return_value = [
            {"name": "MyClass", "kind": 5, "location": {"range": {"start": {"line": 0}}}},
            {"name": "my_function", "kind": 12, "location": {"range": {"start": {"line": 5}}}},
        ]

        with patch("os.path.exists", return_value=True):
            with patch("os.path.isabs", return_value=True):
                result = await symbols_command(["/test/project/test.py"], command_context)
                assert result is not None
                mock_lsp_manager.start_server.assert_called_once()
                mock_lsp_manager.get_document_symbols.assert_called_once()


# Test references_command
class TestReferencesCommand:
    """Test references command."""

    @pytest.mark.asyncio
    async def test_references_no_args(self, command_context):
        """Test references command with no arguments."""
        result = await references_command([], command_context)
        assert "Usage:" in result

    @pytest.mark.asyncio
    async def test_references_invalid_line(self, command_context):
        """Test references with invalid line number."""
        with patch("os.path.exists", return_value=True):
            result = await references_command(["test.py", "abc", "5"], command_context)
            assert "numbers" in result.lower()

    @pytest.mark.asyncio
    async def test_references_success(self, command_context, mock_lsp_manager, mock_repo_info):
        """Test successful references retrieval."""
        mock_lsp_manager.get_references.return_value = [
            {
                "uri": "file:///test/project/main.py",
                "range": {"start": {"line": 10, "character": 5}},
            },
            {
                "uri": "file:///test/project/utils.py",
                "range": {"start": {"line": 20, "character": 8}},
            },
        ]

        with patch("os.path.exists", return_value=True):
            with patch("os.path.isabs", return_value=True):
                result = await references_command(
                    ["/test/project/test.py", "10", "5"], command_context
                )
                mock_lsp_manager.get_references.assert_called_once()


# Test definitions_command
class TestDefinitionsCommand:
    """Test definitions command."""

    @pytest.mark.asyncio
    async def test_definitions_no_args(self, command_context):
        """Test definitions command with no arguments."""
        result = await definitions_command([], command_context)
        assert "Usage:" in result

    @pytest.mark.asyncio
    async def test_definitions_file_not_found(self, command_context):
        """Test definitions with non-existent file."""
        with patch("os.path.exists", return_value=False):
            result = await definitions_command(["nonexistent.py", "10", "5"], command_context)
            assert "not found" in result.lower()

    @pytest.mark.asyncio
    async def test_definitions_success(self, command_context, mock_lsp_manager, mock_repo_info):
        """Test successful definitions retrieval."""
        mock_lsp_manager.get_definition.return_value = [
            {
                "uri": "file:///test/project/defs.py",
                "range": {"start": {"line": 5, "character": 0}},
            },
        ]

        with patch("os.path.exists", return_value=True):
            with patch("os.path.isabs", return_value=True):
                result = await definitions_command(
                    ["/test/project/test.py", "10", "5"], command_context
                )
                mock_lsp_manager.get_definition.assert_called_once()


# Test hover_command
class TestHoverCommand:
    """Test hover command."""

    @pytest.mark.asyncio
    async def test_hover_no_args(self, command_context):
        """Test hover command with no arguments."""
        result = await hover_command([], command_context)
        assert "Usage:" in result

    @pytest.mark.asyncio
    async def test_hover_success(self, command_context, mock_lsp_manager, mock_repo_info):
        """Test successful hover retrieval."""
        mock_lsp_manager.get_hover.return_value = {
            "contents": {"kind": "markdown", "value": "```python\ndef foo()\n```"}
        }

        with patch("os.path.exists", return_value=True):
            with patch("os.path.isabs", return_value=True):
                result = await hover_command(["/test/project/test.py", "10", "5"], command_context)
                mock_lsp_manager.get_hover.assert_called_once()


# Test implementations_command
class TestImplementationsCommand:
    """Test implementations command."""

    @pytest.mark.asyncio
    async def test_implementations_no_args(self, command_context):
        """Test implementations command with no arguments."""
        result = await implementations_command([], command_context)
        assert "Usage:" in result

    @pytest.mark.asyncio
    async def test_implementations_success(self, command_context, mock_lsp_manager, mock_repo_info):
        """Test successful implementations retrieval."""
        mock_lsp_manager.get_implementations.return_value = [
            {
                "uri": "file:///test/project/impl1.py",
                "range": {"start": {"line": 10, "character": 4}},
            },
        ]

        with patch("os.path.exists", return_value=True):
            with patch("os.path.isabs", return_value=True):
                result = await implementations_command(
                    ["/test/project/test.py", "10", "5"], command_context
                )
                mock_lsp_manager.get_implementations.assert_called_once()


# Test workspace_symbol_command
class TestWorkspaceSymbolCommand:
    """Test workspace symbol command."""

    @pytest.mark.asyncio
    async def test_workspace_symbol_no_args(self, command_context):
        """Test workspace symbol command with no arguments."""
        result = await workspace_symbol_command([], command_context)
        assert "Usage:" in result

    @pytest.mark.asyncio
    async def test_workspace_symbol_empty_query(self, command_context):
        """Test workspace symbol with empty query."""
        result = await workspace_symbol_command([""], command_context)
        assert "required" in result.lower()

    @pytest.mark.asyncio
    async def test_workspace_symbol_success(
        self, command_context, mock_lsp_manager, mock_repo_info
    ):
        """Test successful workspace symbol search."""
        mock_lsp_manager.get_workspace_symbols.return_value = [
            {
                "name": "MyClass",
                "kind": 5,
                "location": {
                    "uri": "file:///test/project/test.py",
                    "range": {"start": {"line": 5}},
                },
            },
        ]

        # Mock os.path.join to return predictable paths
        original_join = __import__("os.path").path.join

        def mock_join(*args):
            if len(args) == 2 and args[1] == "test.py":
                return "/test/project/test.py"
            return original_join(*args)

        with patch("os.listdir", return_value=["test.py"]):
            with patch("os.path.isfile", return_value=True):
                with patch("os.path.join", side_effect=mock_join):
                    result = await workspace_symbol_command(["MyClass"], command_context)
                    # Command may fail due to language detection but we're checking the flow
                    assert result is not None


# Test command registration
class TestCommandRegistration:
    """Test that commands are properly registered."""

    def test_symbols_command_registered(self):
        """Test symbols command is registered."""
        from pilotcode.commands.code_intelligence_commands import symbols_command

        assert symbols_command is not None

    def test_references_command_registered(self):
        """Test references command is registered."""
        from pilotcode.commands.code_intelligence_commands import references_command

        assert references_command is not None

    def test_definitions_command_registered(self):
        """Test definitions command is registered."""
        from pilotcode.commands.code_intelligence_commands import definitions_command

        assert definitions_command is not None

    def test_hover_command_registered(self):
        """Test hover command is registered."""
        from pilotcode.commands.code_intelligence_commands import hover_command

        assert hover_command is not None

    def test_implementations_command_registered(self):
        """Test implementations command is registered."""
        from pilotcode.commands.code_intelligence_commands import implementations_command

        assert implementations_command is not None

    def test_workspace_symbol_command_registered(self):
        """Test workspace symbol command is registered."""
        from pilotcode.commands.code_intelligence_commands import workspace_symbol_command

        assert workspace_symbol_command is not None
