"""Tests for basic commands.

This module combines tests for:
- config command (configuration management)
- model command (model information display)
- status command (system status display)
- new command (new conversation)
"""

import pytest
import subprocess
from pathlib import Path
from unittest.mock import patch, MagicMock

from pilotcode.commands.config_cmd import config_command
from pilotcode.commands.model_cmd import model_command
from pilotcode.commands.status_cmd import status_command
from pilotcode.commands.base import new_command, CommandContext

# =============================================================================
# Config Command Tests
# =============================================================================


class TestConfigCommand:
    """Tests for config command."""

    @pytest.fixture
    def context(self, tmp_path):
        """Create a command context."""
        return CommandContext(cwd=str(tmp_path))

    @pytest.mark.asyncio
    async def test_config_no_args_shows_all(self, context):
        """Test /config with no arguments shows all config."""
        mock_config = MagicMock()
        mock_config.__dict__ = {"theme": "test_theme", "api_key": "test_key", "verbose": False}

        with patch("pilotcode.utils.config.get_global_config", return_value=mock_config):
            result = await config_command([], context)

        assert "Configuration:" in result
        assert "test_theme" in result

    @pytest.mark.asyncio
    async def test_config_get_existing_key(self, context):
        """Test /config get <key> with existing key."""
        mock_config = MagicMock()
        mock_config.theme = "dark"

        with patch("pilotcode.utils.config.get_global_config", return_value=mock_config):
            result = await config_command(["get", "theme"], context)

        assert "theme" in result
        assert "dark" in result

    @pytest.mark.asyncio
    async def test_config_get_unknown_key(self, context):
        """Test /config get <key> with unknown key."""
        mock_config = MagicMock()
        mock_config.unknown_key = None

        with patch("pilotcode.utils.config.get_global_config", return_value=mock_config):
            result = await config_command(["get", "unknown_key"], context)

        assert "Unknown key" in result

    @pytest.mark.asyncio
    async def test_config_set_string_value(self, context):
        """Test /config set <key> <value> with string value."""
        mock_config = MagicMock()
        mock_config.theme = "default"

        mock_manager = MagicMock()

        with patch("pilotcode.utils.config.get_global_config", return_value=mock_config):
            with patch("pilotcode.utils.config.get_config_manager", return_value=mock_manager):
                result = await config_command(["set", "theme", "dark"], context)

        assert "Set theme" in result
        assert "dark" in result

    @pytest.mark.asyncio
    async def test_config_set_boolean_value(self, context):
        """Test /config set with boolean value."""
        mock_config = MagicMock()
        mock_config.verbose = False

        mock_manager = MagicMock()

        with patch("pilotcode.utils.config.get_global_config", return_value=mock_config):
            with patch("pilotcode.utils.config.get_config_manager", return_value=mock_manager):
                result = await config_command(["set", "verbose", "true"], context)

        assert "Set verbose" in result
        assert "True" in result

    @pytest.mark.asyncio
    async def test_config_set_unknown_key(self, context):
        """Test /config set with unknown key."""

        class MockConfig:
            def __init__(self):
                self.theme = "default"

            def __getattr__(self, name):
                if name == "unknown_key":
                    raise AttributeError(f"'{name}' not found")
                return super().__getattribute__(name)

        mock_config = MockConfig()

        with patch("pilotcode.utils.config.get_global_config", return_value=mock_config):
            result = await config_command(["set", "unknown_key", "value"], context)

        assert "Unknown key" in result

    @pytest.mark.asyncio
    async def test_config_reset(self, context):
        """Test /config reset."""
        mock_manager = MagicMock()

        with patch("pilotcode.utils.config.get_config_manager", return_value=mock_manager):
            with patch("pilotcode.utils.config.GlobalConfig") as MockGlobalConfig:
                MockGlobalConfig.return_value = MagicMock()
                result = await config_command(["reset"], context)

        assert "reset to defaults" in result.lower()

    @pytest.mark.asyncio
    async def test_config_unknown_action(self, context):
        """Test /config with unknown action."""
        result = await config_command(["unknown"], context)

        assert "Unknown action" in result


# =============================================================================
# Model Command Tests
# =============================================================================


class TestModelCommand:
    """Tests for model command."""

    @pytest.fixture
    def context(self, tmp_path):
        """Create a command context."""
        return CommandContext(cwd=str(tmp_path))

    @pytest.mark.asyncio
    async def test_model_shows_current_model(self, context):
        """Test /model shows current model information."""
        mock_config = MagicMock()
        mock_config.default_model = "gpt-4"
        mock_config.base_url = "https://api.example.com"

        mock_model_info = MagicMock()
        mock_model_info.display_name = "GPT-4"
        mock_model_info.default_model = "gpt-4"
        mock_model_info.provider = MagicMock(value="openai")
        mock_model_info.context_window = 128000
        mock_model_info.max_tokens = 4096
        mock_model_info.supports_tools = True
        mock_model_info.supports_vision = True

        with patch("pilotcode.commands.model_cmd.get_global_config", return_value=mock_config):
            with patch(
                "pilotcode.utils.models_config.get_model_info", return_value=mock_model_info
            ):
                result = await model_command([], context)

        assert "Current model: gpt-4" in result
        assert "GPT-4" in result
        assert "Context window:" in result
        assert "Tools:" in result

    @pytest.mark.asyncio
    async def test_model_no_model_info(self, context):
        """Test /model when model info is not found."""
        mock_config = MagicMock()
        mock_config.default_model = "unknown-model"
        mock_config.base_url = "https://api.example.com"

        with patch("pilotcode.commands.model_cmd.get_global_config", return_value=mock_config):
            with patch("pilotcode.utils.models_config.get_model_info", return_value=None):
                result = await model_command([], context)

        assert "Current model: unknown-model" in result
        assert "Base URL:" in result

    @pytest.mark.asyncio
    async def test_model_shows_base_url(self, context):
        """Test /model shows base URL."""
        mock_config = MagicMock()
        mock_config.default_model = "gpt-3.5"
        mock_config.base_url = "https://custom.api.com"

        with patch("pilotcode.commands.model_cmd.get_global_config", return_value=mock_config):
            with patch("pilotcode.utils.models_config.get_model_info", return_value=None):
                result = await model_command([], context)

        assert "https://custom.api.com" in result


# =============================================================================
# Status Command Tests
# =============================================================================


class TestStatusCommand:
    """Tests for status command."""

    @pytest.fixture
    def context(self, tmp_path):
        """Create a command context."""
        return CommandContext(cwd=str(tmp_path))

    @pytest.fixture
    def git_repo(self, tmp_path):
        """Create a temporary git repository."""
        subprocess.run(["git", "init"], cwd=tmp_path, capture_output=True, check=True)
        subprocess.run(
            ["git", "config", "user.email", "test@test.com"],
            cwd=tmp_path,
            capture_output=True,
            check=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Test User"],
            cwd=tmp_path,
            capture_output=True,
            check=True,
        )
        (tmp_path / "README.md").write_text("# Test")
        subprocess.run(["git", "add", "."], cwd=tmp_path, capture_output=True, check=True)
        subprocess.run(
            ["git", "commit", "-m", "Initial commit"], cwd=tmp_path, capture_output=True, check=True
        )
        return tmp_path

    @pytest.mark.asyncio
    async def test_status_shows_header(self, context):
        """Test /status shows status header."""
        mock_config = MagicMock()
        mock_config.default_model = "gpt-4"
        mock_config.theme = "default"

        with patch("pilotcode.utils.config.get_global_config", return_value=mock_config):
            with patch("pilotcode.utils.models_config.get_model_info", return_value=None):
                with patch(
                    "pilotcode.utils.models_config.get_model_context_window", return_value=128000
                ):
                    result = await status_command([], context)

        assert "PilotCode Status" in result
        assert "Working directory:" in result
        assert "Time:" in result

    @pytest.mark.asyncio
    async def test_status_shows_git_info(self, git_repo):
        """Test /status shows git status in a repo."""
        context = CommandContext(cwd=str(git_repo))

        mock_config = MagicMock()
        mock_config.default_model = "gpt-4"
        mock_config.theme = "default"

        with patch("pilotcode.utils.config.get_global_config", return_value=mock_config):
            with patch("pilotcode.utils.models_config.get_model_info", return_value=None):
                with patch(
                    "pilotcode.utils.models_config.get_model_context_window", return_value=128000
                ):
                    result = await status_command([], context)

        assert "Git:" in result

    @pytest.mark.asyncio
    async def test_status_shows_model_info(self, context):
        """Test /status shows model information."""
        mock_config = MagicMock()
        mock_config.default_model = "gpt-4-test"
        mock_config.theme = "default"

        mock_model_info = MagicMock()
        mock_model_info.context_window = 128000
        mock_model_info.max_tokens = 4096
        mock_model_info.supports_tools = True
        mock_model_info.supports_vision = False

        with patch("pilotcode.utils.config.get_global_config", return_value=mock_config):
            with patch(
                "pilotcode.utils.models_config.get_model_info", return_value=mock_model_info
            ):
                with patch(
                    "pilotcode.utils.models_config.get_model_context_window", return_value=128000
                ):
                    result = await status_command([], context)

        assert "Model: gpt-4-test" in result
        assert "Context window:" in result
        assert "Tools:" in result
        assert "Vision:" in result

    @pytest.mark.asyncio
    async def test_status_shows_theme(self, context):
        """Test /status shows theme."""
        mock_config = MagicMock()
        mock_config.default_model = "gpt-4"
        mock_config.theme = "dark"

        with patch("pilotcode.utils.config.get_global_config", return_value=mock_config):
            with patch("pilotcode.utils.models_config.get_model_info", return_value=None):
                with patch(
                    "pilotcode.utils.models_config.get_model_context_window", return_value=128000
                ):
                    result = await status_command([], context)

        assert "Theme: dark" in result

    @pytest.mark.asyncio
    async def test_status_with_query_engine(self, context):
        """Test /status shows conversation context when query_engine is available."""
        mock_config = MagicMock()
        mock_config.default_model = "gpt-4"
        mock_config.theme = "default"

        mock_model_info = MagicMock()
        mock_model_info.context_window = 128000
        mock_model_info.max_tokens = 4096
        mock_model_info.supports_tools = True
        mock_model_info.supports_vision = False

        mock_message = MagicMock()
        mock_message.content = "Test message"

        mock_qe = MagicMock()
        mock_qe.messages = [mock_message, mock_message]
        mock_qe.config.max_tokens = 128000

        context_with_qe = CommandContext(cwd=str(context.cwd), query_engine=mock_qe)

        with patch("pilotcode.utils.config.get_global_config", return_value=mock_config):
            with patch(
                "pilotcode.utils.models_config.get_model_info", return_value=mock_model_info
            ):
                with patch(
                    "pilotcode.utils.models_config.get_model_context_window", return_value=128000
                ):
                    with patch(
                        "pilotcode.services.token_estimation.estimate_tokens", return_value=10
                    ):
                        result = await status_command([], context_with_qe)

        assert "Conversation Context:" in result
        assert "Messages:" in result
        assert "Tokens:" in result


# =============================================================================
# New Command Tests
# =============================================================================


class TestNewCommand:
    """Tests for new command."""

    @pytest.fixture
    def context(self, tmp_path):
        """Create a command context."""
        return CommandContext(cwd=str(tmp_path))

    @pytest.fixture
    def context_with_qe(self, tmp_path):
        """Create a command context with mock query engine."""
        mock_qe = MagicMock()
        mock_qe.messages = ["message1", "message2", "message3"]
        mock_qe.clear_history = MagicMock()
        mock_qe._compaction_count = 5
        mock_qe._last_compaction_message_count = 10
        return CommandContext(cwd=str(tmp_path), query_engine=mock_qe)

    @pytest.mark.asyncio
    async def test_new_clears_history(self, context_with_qe):
        """Test /new clears conversation history."""
        result = await new_command([], context_with_qe)

        assert "New conversation started" in result
        assert "3 previous message(s) cleared" in result
        context_with_qe.query_engine.clear_history.assert_called_once()

    @pytest.mark.asyncio
    async def test_new_resets_compaction_stats(self, context_with_qe):
        """Test /new resets compaction stats."""
        await new_command([], context_with_qe)

        assert context_with_qe.query_engine._compaction_count == 0
        assert context_with_qe.query_engine._last_compaction_message_count == 0

    @pytest.mark.asyncio
    async def test_new_without_query_engine(self, context):
        """Test /new works even without query_engine."""
        result = await new_command([], context)

        assert "Query engine not available" in result

    @pytest.mark.asyncio
    async def test_new_with_args_ignored(self, context_with_qe):
        """Test /new ignores extra arguments."""
        result = await new_command(["some", "args"], context_with_qe)

        assert "New conversation started" in result
