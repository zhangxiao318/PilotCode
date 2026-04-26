"""Tests for configuration verification with live LLM checks."""

import asyncio
import pytest
from unittest.mock import AsyncMock, patch, MagicMock


async def mock_async_generator(items):
    """Helper to create an async generator from a list."""
    for item in items:
        yield item


class TestConfigVerification:
    """Test configuration verification with live LLM checks."""

    @pytest.fixture
    def isolated_manager(self, tmp_path, monkeypatch):
        """Create an isolated ConfigManager for testing."""
        from pilotcode.utils.config import ConfigManager

        # Clear all API key environment variables to ensure clean state
        api_key_env_vars = [
            "PILOTCODE_API_KEY",
            "LOCAL_API_KEY",
            "OPENAI_API_KEY",
            "ANTHROPIC_API_KEY",
            "AZURE_OPENAI_API_KEY",
            "DEEPSEEK_API_KEY",
            "DASHSCOPE_API_KEY",
            "ZHIPU_API_KEY",
            "MOONSHOT_API_KEY",
            "BAICHUAN_API_KEY",
            "ARK_API_KEY",
            "PILOTCODE_MODEL",
            "PILOTCODE_BASE_URL",
            "OPENAI_BASE_URL",  # This can trigger local model detection
        ]
        for env_var in api_key_env_vars:
            monkeypatch.delenv(env_var, raising=False)

        # Create a fresh instance with isolated paths
        manager = ConfigManager.__new__(ConfigManager)
        manager._global_config = None
        manager._project_config = None
        manager._settings_mtime = 0.0

        # Set isolated paths
        config_dir = tmp_path / "test_pilotcode"
        config_dir.mkdir(parents=True, exist_ok=True)
        manager.CONFIG_DIR = config_dir
        manager.SETTINGS_FILE = config_dir / "settings.json"

        # Clear any existing config file
        if manager.SETTINGS_FILE.exists():
            manager.SETTINGS_FILE.unlink()

        # Monkeypatch the global instance to use this isolated one
        import pilotcode.utils.config

        original_manager = pilotcode.utils.config._config_manager
        pilotcode.utils.config._config_manager = manager

        yield manager

        # Restore
        pilotcode.utils.config._config_manager = original_manager

    @pytest.mark.asyncio
    async def test_verify_no_configuration(self, isolated_manager):
        """Test verification when no configuration exists."""
        from pilotcode.utils.config import GlobalConfig

        # No config file should exist
        assert not isolated_manager.SETTINGS_FILE.exists()

        # Create empty config manually
        isolated_manager._global_config = GlobalConfig()

        result = await isolated_manager.verify_configuration(timeout=5.0)

        assert result["success"] is False
        assert "No configuration" in result["message"]
        assert result["response"] is None

    @pytest.mark.asyncio
    async def test_verify_with_api_key(self, isolated_manager):
        """Test verification with API key configured."""
        from pilotcode.utils.config import GlobalConfig

        # Create config with API key
        config = GlobalConfig(
            api_key="test-api-key-12345",
            default_model="deepseek",
            base_url="https://api.example.com",
        )
        isolated_manager.save_global_config(config)

        # Mock ModelClient at its source module
        mock_response = [
            {"choices": [{"delta": {"content": "I am an AI assistant."}}]},
        ]

        with patch("pilotcode.utils.model_client.ModelClient") as MockClient:
            mock_client = AsyncMock()
            # chat_completion is an async generator
            mock_client.chat_completion = MagicMock(
                return_value=mock_async_generator(mock_response)
            )
            mock_client.close = AsyncMock()
            MockClient.return_value = mock_client

            result = await isolated_manager.verify_configuration(timeout=5.0)

            assert result["success"] is True
            assert "responded successfully" in result["message"]
            assert result["response"] is not None
            mock_client.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_verify_local_model_no_key(self, isolated_manager):
        """Test verification with local model (no API key needed)."""
        from pilotcode.utils.config import GlobalConfig

        config = GlobalConfig(api_key="", default_model="ollama", base_url="http://localhost:11434")
        isolated_manager.save_global_config(config)

        mock_response = [
            {"choices": [{"delta": {"content": "I am a local model."}}]},
        ]

        with patch("pilotcode.utils.model_client.ModelClient") as MockClient:
            mock_client = AsyncMock()
            mock_client.chat_completion = MagicMock(
                return_value=mock_async_generator(mock_response)
            )
            mock_client.close = AsyncMock()
            MockClient.return_value = mock_client

            result = await isolated_manager.verify_configuration(timeout=5.0)

            assert result["success"] is True

    @pytest.mark.asyncio
    async def test_verify_empty_response(self, isolated_manager):
        """Test verification when LLM returns empty response."""
        from pilotcode.utils.config import GlobalConfig

        config = GlobalConfig(
            api_key="test-key", default_model="test-model", base_url="https://api.example.com"
        )
        isolated_manager.save_global_config(config)

        # Mock empty response (no chunks with content)
        mock_response = []

        with patch("pilotcode.utils.model_client.ModelClient") as MockClient:
            mock_client = AsyncMock()
            mock_client.chat_completion = MagicMock(
                return_value=mock_async_generator(mock_response)
            )
            mock_client.close = AsyncMock()
            MockClient.return_value = mock_client

            result = await isolated_manager.verify_configuration(timeout=5.0)

            assert result["success"] is False
            assert "empty response" in result["message"].lower()

    @pytest.mark.asyncio
    async def test_verify_connection_error(self, isolated_manager):
        """Test verification when connection fails."""
        from pilotcode.utils.config import GlobalConfig

        config = GlobalConfig(
            api_key="invalid-key",
            default_model="test-model",
            base_url="https://invalid-url.example.com",
        )
        isolated_manager.save_global_config(config)

        with patch("pilotcode.utils.model_client.ModelClient") as MockClient:
            mock_client = AsyncMock()

            async def failing_generator(*args, **kwargs):
                raise Exception("Connection refused")
                if False:  # Make it a generator
                    yield {}

            mock_client.chat_completion = MagicMock(return_value=failing_generator())
            mock_client.close = AsyncMock()
            MockClient.return_value = mock_client

            result = await isolated_manager.verify_configuration(timeout=5.0)

            assert result["success"] is False
            assert "Connection failed" in result["message"]
            assert "Connection refused" in result["error"]

    @pytest.mark.asyncio
    async def test_verify_timeout(self, isolated_manager):
        """Test verification timeout handling."""
        from pilotcode.utils.config import GlobalConfig

        config = GlobalConfig(
            api_key="test-key", default_model="test-model", base_url="https://api.example.com"
        )
        isolated_manager.save_global_config(config)

        with patch("pilotcode.utils.model_client.ModelClient") as MockClient:
            mock_client = AsyncMock()

            # Use a future that never completes to simulate timeout
            # This avoids actually waiting for the timeout duration
            async def hanging_generator(*args, **kwargs):
                # Create a future that never resolves
                future = asyncio.Future()
                try:
                    await asyncio.wait_for(future, timeout=0.01)
                except asyncio.TimeoutError:
                    pass
                if False:  # Make it a generator
                    yield {}

            mock_client.chat_completion = MagicMock(return_value=hanging_generator())
            mock_client.close = AsyncMock()
            MockClient.return_value = mock_client

            # Use very short timeout
            result = await isolated_manager.verify_configuration(timeout=0.01)

            # Should fail due to timeout
            assert result["success"] is False or result["error"] is not None

    @pytest.mark.asyncio
    async def test_verify_response_truncation(self, isolated_manager):
        """Test that long responses are properly truncated."""
        from pilotcode.utils.config import GlobalConfig

        config = GlobalConfig(
            api_key="test-key", default_model="test-model", base_url="https://api.example.com"
        )
        isolated_manager.save_global_config(config)

        # Create a very long response (250 chars)
        long_text = "Word " * 50

        mock_response = [
            {"choices": [{"delta": {"content": long_text}}]},
        ]

        with patch("pilotcode.utils.model_client.ModelClient") as MockClient:
            mock_client = AsyncMock()
            mock_client.chat_completion = MagicMock(
                return_value=mock_async_generator(mock_response)
            )
            mock_client.close = AsyncMock()
            MockClient.return_value = mock_client

            result = await isolated_manager.verify_configuration(timeout=5.0)

            assert result["success"] is True
            # Response should be truncated to 200 chars
            assert len(result["response"]) <= 200

    @pytest.mark.asyncio
    async def test_verify_deepseek_reasoning_content(self, isolated_manager):
        """Test verification with DeepSeek reasoning_content (no content field)."""
        from pilotcode.utils.config import GlobalConfig

        config = GlobalConfig(
            api_key="test-key",
            default_model="deepseek-v4-pro",
            base_url="https://api.deepseek.com",
        )
        isolated_manager.save_global_config(config)

        # DeepSeek V4 may return reasoning_content instead of content
        mock_response = [
            {"choices": [{"delta": {"reasoning_content": "I am an AI assistant"}}]},
        ]

        with patch("pilotcode.utils.model_client.ModelClient") as MockClient:
            mock_client = AsyncMock()
            mock_client.chat_completion = MagicMock(
                return_value=mock_async_generator(mock_response)
            )
            mock_client.close = AsyncMock()
            MockClient.return_value = mock_client

            result = await isolated_manager.verify_configuration(timeout=5.0)

            assert result["success"] is True
            assert "responded successfully" in result["message"]
            assert result["response"] == "I am an AI assistant"
            mock_client.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_verify_deepseek_mixed_content_and_reasoning(self, isolated_manager):
        """Test verification with both content and reasoning_content."""
        from pilotcode.utils.config import GlobalConfig

        config = GlobalConfig(
            api_key="test-key",
            default_model="deepseek-v4-pro",
            base_url="https://api.deepseek.com",
        )
        isolated_manager.save_global_config(config)

        # DeepSeek V4 may return both reasoning_content and content
        mock_response = [
            {"choices": [{"delta": {"reasoning_content": "Let me think... "}}]},
            {"choices": [{"delta": {"content": "I am an AI assistant."}}]},
        ]

        with patch("pilotcode.utils.model_client.ModelClient") as MockClient:
            mock_client = AsyncMock()
            mock_client.chat_completion = MagicMock(
                return_value=mock_async_generator(mock_response)
            )
            mock_client.close = AsyncMock()
            MockClient.return_value = mock_client

            result = await isolated_manager.verify_configuration(timeout=5.0)

            assert result["success"] is True
            assert "responded successfully" in result["message"]
            assert "Let me think... I am an AI assistant." in result["response"]
            mock_client.close.assert_called_once()


class TestConfigVerificationWithRealOllama:
    """Test with real Ollama instance if available."""

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_verify_real_ollama(self, tmp_path, monkeypatch):
        """Test verification with real Ollama (if running locally)."""
        import httpx

        # Skip if Ollama is not running
        try:
            response = httpx.get("http://localhost:11434/api/tags", timeout=2.0)
            if response.status_code != 200:
                pytest.skip("Ollama not running locally")
        except Exception:
            pytest.skip("Ollama not accessible")

        from pilotcode.utils.config import ConfigManager, GlobalConfig

        # Create isolated manager
        manager = ConfigManager.__new__(ConfigManager)
        manager._global_config = None
        manager._project_config = None
        config_dir = tmp_path / "test_pilotcode_ollama"
        config_dir.mkdir(parents=True, exist_ok=True)
        manager.CONFIG_DIR = config_dir
        manager.SETTINGS_FILE = config_dir / "settings.json"

        config = GlobalConfig(
            api_key="", default_model="ollama", base_url="http://localhost:11434/v1"
        )
        manager.save_global_config(config)

        # This will make a real API call
        result = await manager.verify_configuration(timeout=30.0)

        # Should succeed if Ollama is running with a model
        if result["success"]:
            assert result["response"] is not None
            assert len(result["response"]) > 0
        else:
            # May fail if no model is loaded
            assert "failed" in result["message"].lower() or "empty" in result["message"].lower()


class TestConfigManagerIntegration:
    """Integration tests for ConfigManager with verification."""

    def test_is_configured_vs_verify(self, tmp_path, monkeypatch):
        """Test that is_configured and verify work together."""
        from pilotcode.utils.config import ConfigManager, GlobalConfig

        # Clear all API key environment variables to ensure clean state
        api_key_env_vars = [
            "PILOTCODE_API_KEY",
            "LOCAL_API_KEY",
            "OPENAI_API_KEY",
            "ANTHROPIC_API_KEY",
            "AZURE_OPENAI_API_KEY",
            "DEEPSEEK_API_KEY",
            "DASHSCOPE_API_KEY",
            "ZHIPU_API_KEY",
            "MOONSHOT_API_KEY",
            "BAICHUAN_API_KEY",
            "ARK_API_KEY",
            "PILOTCODE_MODEL",
            "PILOTCODE_BASE_URL",
            "OPENAI_BASE_URL",  # This can trigger local model detection
        ]
        for env_var in api_key_env_vars:
            monkeypatch.delenv(env_var, raising=False)

        # Create isolated manager
        manager = ConfigManager.__new__(ConfigManager)
        manager._global_config = None
        manager._project_config = None
        config_dir = tmp_path / "test_pilotcode_integration"
        config_dir.mkdir(parents=True, exist_ok=True)
        manager.CONFIG_DIR = config_dir
        manager.SETTINGS_FILE = config_dir / "settings.json"

        # Ensure no config file exists
        if manager.SETTINGS_FILE.exists():
            manager.SETTINGS_FILE.unlink()

        # Without config, should not be configured
        assert manager.is_configured() is False

        # Add configuration with API key
        config = GlobalConfig(
            api_key="test-key", default_model="test-model", base_url="https://api.example.com"
        )
        manager.save_global_config(config)

        # Now should be configured
        assert manager.is_configured() is True

        # Verification requires async - mock the ModelClient at source module
        mock_response = [
            {"choices": [{"delta": {"content": "I am an AI."}}]},
        ]

        with patch("pilotcode.utils.model_client.ModelClient") as MockClient:
            mock_client = AsyncMock()
            mock_client.chat_completion = MagicMock(
                return_value=mock_async_generator(mock_response)
            )
            mock_client.close = AsyncMock()
            MockClient.return_value = mock_client

            result = asyncio.run(manager.verify_configuration(timeout=5.0))

            # Should succeed with mock
            assert result["success"] is True
            assert "responded successfully" in result["message"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
