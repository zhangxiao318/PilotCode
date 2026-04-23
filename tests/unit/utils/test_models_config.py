"""Tests for models_config module."""

import pytest
from unittest.mock import MagicMock, patch

from pilotcode.utils.models_config import (
    get_model_context_window,
    get_model_max_tokens,
    get_model_info,
    ModelInfo,
    ModelProvider,
)


class TestGetModelContextWindow:
    """Tests for get_model_context_window."""

    def test_local_model_uses_config_context_window(self, monkeypatch):
        """Local model: priority 1 is GlobalConfig.context_window."""
        mock_config = MagicMock()
        mock_config.context_window = 31072
        mock_config.base_url = "http://172.19.201.40:3530/v1"
        mock_config.default_model = "ollama"

        with patch("pilotcode.utils.config.get_global_config", return_value=mock_config):
            result = get_model_context_window()

        assert result == 31072

    def test_local_model_zero_returns_safe_fallback(self, monkeypatch):
        """Local model with context_window==0: must NOT fall back to models.json."""
        mock_config = MagicMock()
        mock_config.context_window = 0
        mock_config.base_url = "http://172.19.201.40:3530/v1"
        mock_config.default_model = "ollama"

        with patch("pilotcode.utils.config.get_global_config", return_value=mock_config):
            result = get_model_context_window()

        # Must return safe fallback, NOT the ollama static value (131072)
        assert result == 128_000

    def test_remote_model_uses_models_json(self, monkeypatch):
        """Remote model: fall back to models.json when config.context_window==0."""
        mock_config = MagicMock()
        mock_config.context_window = 0
        mock_config.base_url = "https://api.openai.com/v1"
        mock_config.default_model = "openai"

        with patch("pilotcode.utils.config.get_global_config", return_value=mock_config):
            result = get_model_context_window()

        # openai in models.json has context_window=128000
        assert result == 128_000

    def test_remote_model_config_priority_over_models_json(self, monkeypatch):
        """Remote model: config.context_window still has highest priority."""
        mock_config = MagicMock()
        mock_config.context_window = 64000
        mock_config.base_url = "https://api.openai.com/v1"
        mock_config.default_model = "openai"

        with patch("pilotcode.utils.config.get_global_config", return_value=mock_config):
            result = get_model_context_window()

        assert result == 64000


class TestGetModelMaxTokens:
    """Tests for get_model_max_tokens."""

    def test_local_model_returns_safe_fallback(self, monkeypatch):
        """Local model: must NOT fall back to models.json."""
        mock_config = MagicMock()
        mock_config.base_url = "http://172.19.201.40:3530/v1"
        mock_config.default_model = "ollama"

        with patch("pilotcode.utils.config.get_global_config", return_value=mock_config):
            result = get_model_max_tokens()

        # Must return safe fallback, NOT the ollama static value (4096)
        assert result == 4096

    def test_remote_model_uses_models_json(self, monkeypatch):
        """Remote model: fall back to models.json."""
        mock_config = MagicMock()
        mock_config.base_url = "https://api.openai.com/v1"
        mock_config.default_model = "openai"

        with patch("pilotcode.utils.config.get_global_config", return_value=mock_config):
            result = get_model_max_tokens()

        # openai in models.json has max_tokens=4096
        assert result == 4096


class TestGetModelInfo:
    """Tests for get_model_info."""

    def test_existing_model(self):
        """Test retrieving an existing model."""
        info = get_model_info("deepseek")
        assert info is not None
        assert info.name == "deepseek"
        assert info.provider == ModelProvider.DEEPSEEK

    def test_nonexistent_model(self):
        """Test retrieving a non-existent model."""
        info = get_model_info("nonexistent-model-xyz")
        assert info is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
