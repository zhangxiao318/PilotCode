"""Tests for config module."""

import os
import json
import pytest
import tempfile
from pathlib import Path
from dataclasses import asdict

from pilotcode.utils.config import (
    GlobalConfig,
    ProjectConfig,
    ConfigManager,
    get_config_manager,
    get_global_config,
    save_global_config,
    is_configured,
    get_config_status,
    ensure_configured,
)


class TestGlobalConfig:
    """Tests for GlobalConfig."""

    def test_default_values(self):
        """Test default global config values."""
        config = GlobalConfig()

        assert config.theme == "default"
        assert config.verbose is False
        assert config.auto_compact is True
        assert config.api_key is None
        # base_url and default_model are set by __post_init__
        assert config.base_url is not None  # Set from model info
        assert config.allowed_tools == []
        assert config.mcp_servers == {}
        # default_model should be set from get_default_model()
        assert config.default_model is not None

    def test_custom_values(self):
        """Test custom global config values."""
        config = GlobalConfig(
            theme="dark",
            verbose=True,
            auto_compact=False,
            api_key="sk-test123",
            base_url="https://api.example.com",
            default_model="gpt-4",
            model_provider="openai",
            allowed_tools=["Bash", "FileRead"],
            mcp_servers={"filesystem": {"command": "npx"}},
        )

        assert config.theme == "dark"
        assert config.verbose is True
        assert config.auto_compact is False
        assert config.api_key == "sk-test123"
        assert config.base_url == "https://api.example.com"
        assert config.default_model == "gpt-4"
        assert config.model_provider == "openai"
        assert config.allowed_tools == ["Bash", "FileRead"]
        assert config.mcp_servers == {"filesystem": {"command": "npx"}}

    def test_post_init_sets_default_model(self):
        """Test that __post_init__ sets default model."""
        config = GlobalConfig(default_model="")

        # Should have default model set
        assert config.default_model != ""

    def test_asdict_serialization(self):
        """Test that config can be serialized to dict."""
        config = GlobalConfig(theme="dark", api_key="secret")

        data = asdict(config)

        assert data["theme"] == "dark"
        assert data["api_key"] == "secret"
        assert "default_model" in data


class TestProjectConfig:
    """Tests for ProjectConfig."""

    def test_default_values(self):
        """Test default project config values."""
        config = ProjectConfig()

        assert config.allowed_tools == []
        assert config.mcp_servers is None
        assert config.custom_instructions is None

    def test_custom_values(self):
        """Test custom project config values."""
        config = ProjectConfig(
            allowed_tools=["Bash"],
            mcp_servers={"github": {"command": "npx"}},
            custom_instructions="Always use Python 3.10+",
        )

        assert config.allowed_tools == ["Bash"]
        assert config.mcp_servers == {"github": {"command": "npx"}}
        assert config.custom_instructions == "Always use Python 3.10+"


class TestConfigManager:
    """Tests for ConfigManager."""

    @pytest.fixture
    def temp_config_dir(self, monkeypatch, tmp_path):
        """Create temporary config directory."""
        config_dir = tmp_path / "config"
        config_dir.mkdir()

        # Patch CONFIG_DIR
        original_dir = ConfigManager.CONFIG_DIR
        ConfigManager.CONFIG_DIR = config_dir
        ConfigManager.SETTINGS_FILE = config_dir / "settings.json"

        yield config_dir

        # Restore
        ConfigManager.CONFIG_DIR = original_dir
        ConfigManager.SETTINGS_FILE = original_dir / "settings.json"

    def test_initialization_creates_config_dir(self, tmp_path):
        """Test that initialization creates config directory."""
        config_dir = tmp_path / "new_config"

        original_dir = ConfigManager.CONFIG_DIR
        ConfigManager.CONFIG_DIR = config_dir
        ConfigManager.SETTINGS_FILE = config_dir / "settings.json"

        try:
            manager = ConfigManager()
            assert config_dir.exists()
        finally:
            ConfigManager.CONFIG_DIR = original_dir
            ConfigManager.SETTINGS_FILE = original_dir / "settings.json"

    def test_load_global_config_default(self, temp_config_dir):
        """Test loading global config without file."""
        manager = ConfigManager()
        # Reset cached config
        manager._global_config = None

        config = manager.load_global_config()

        assert isinstance(config, GlobalConfig)
        assert config.theme == "default"

    def test_load_global_config_from_file(self, temp_config_dir):
        """Test loading global config from file."""
        # Create settings file
        settings_file = temp_config_dir / "settings.json"
        settings_data = {"theme": "dark", "verbose": True, "api_key": "test-key"}
        settings_file.write_text(json.dumps(settings_data))

        manager = ConfigManager()
        config = manager.load_global_config()

        assert config.theme == "dark"
        assert config.verbose is True

    def test_save_global_config(self, temp_config_dir):
        """Test saving global config."""
        manager = ConfigManager()
        config = GlobalConfig(theme="solarized", api_key="new-key")

        manager.save_global_config(config)

        # Verify file was created
        settings_file = temp_config_dir / "settings.json"
        assert settings_file.exists()

        # Verify content
        saved_data = json.loads(settings_file.read_text())
        assert saved_data["theme"] == "solarized"
        assert saved_data["api_key"] == "new-key"

    def test_env_override_theme(self, temp_config_dir, monkeypatch):
        """Test environment variable override for theme."""
        monkeypatch.setenv("PILOTCODE_THEME", "monokai")

        manager = ConfigManager()
        manager._global_config = None  # Reset cache
        config = manager.load_global_config()

        assert config.theme == "monokai"

    def test_env_override_boolean(self, temp_config_dir, monkeypatch):
        """Test environment variable override for boolean."""
        monkeypatch.setenv("PILOTCODE_VERBOSE", "true")

        manager = ConfigManager()
        manager._global_config = None
        config = manager.load_global_config()

        assert config.verbose is True

    def test_env_override_api_key(self, temp_config_dir, monkeypatch):
        """Test environment variable override for API key."""
        monkeypatch.setenv("PILOTCODE_API_KEY", "env-api-key")

        manager = ConfigManager()
        manager._global_config = None
        config = manager.load_global_config()

        assert config.api_key == "env-api-key"

    def test_legacy_env_var(self, temp_config_dir, monkeypatch):
        """Test legacy environment variable."""
        monkeypatch.setenv("LOCAL_API_KEY", "legacy-key")

        manager = ConfigManager()
        manager._global_config = None
        config = manager.load_global_config()

        assert config.api_key == "legacy-key"

    def test_load_project_config_not_found(self, temp_config_dir):
        """Test loading project config when file doesn't exist."""
        manager = ConfigManager()

        config = manager.load_project_config("/nonexistent/path")

        assert config is None

    def test_load_project_config(self, temp_config_dir, tmp_path):
        """Test loading project config."""
        # Create project config
        project_dir = tmp_path / "project"
        project_dir.mkdir()
        config_file = project_dir / ".pilotcode.json"
        config_data = {
            "allowed_tools": ["Bash", "FileRead"],
            "custom_instructions": "Test instructions",
        }
        config_file.write_text(json.dumps(config_data))

        manager = ConfigManager()
        config = manager.load_project_config(str(project_dir))

        assert config is not None
        assert config.allowed_tools == ["Bash", "FileRead"]
        assert config.custom_instructions == "Test instructions"

    def test_find_git_root(self, temp_config_dir, tmp_path):
        """Test finding git root."""
        # Create git repo structure
        git_root = tmp_path / "repo"
        git_root.mkdir()
        (git_root / ".git").mkdir()
        subdir = git_root / "subdir"
        subdir.mkdir()

        manager = ConfigManager()
        found_root = manager._find_git_root(str(subdir))

        assert found_root == str(git_root)

    def test_find_git_root_not_found(self, temp_config_dir, tmp_path):
        """Test finding git root when not in repo."""
        non_git_dir = tmp_path / "nogit"
        non_git_dir.mkdir()

        manager = ConfigManager()
        found_root = manager._find_git_root(str(non_git_dir))

        assert found_root is None

    def test_is_configured_with_api_key(self, temp_config_dir, monkeypatch):
        """Test is_configured with API key."""
        monkeypatch.setenv("PILOTCODE_API_KEY", "test-key")

        manager = ConfigManager()
        manager._global_config = None

        assert manager.is_configured() is True

    def test_is_configured_without_api_key(self, temp_config_dir, monkeypatch):
        """Test is_configured without API key."""
        # Ensure no API key is set (clear all possible API key env vars)
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
        ]
        for key in api_key_env_vars:
            monkeypatch.delenv(key, raising=False)

        manager = ConfigManager()
        manager._global_config = None
        # Set empty config
        config = GlobalConfig(api_key=None)
        manager._global_config = config

        assert manager.is_configured() is False

    def test_get_config_status(self, temp_config_dir, monkeypatch):
        """Test getting config status."""
        monkeypatch.setenv("PILOTCODE_THEME", "dark")

        manager = ConfigManager()
        manager._global_config = None
        status = manager.get_config_status()

        assert "configured" in status
        assert "config_file_exists" in status
        assert "config_file_path" in status
        assert "model" in status
        assert "env_overrides" in status


class TestGlobalFunctions:
    """Tests for global config functions."""

    def test_get_config_manager_singleton(self):
        """Test that get_config_manager returns singleton."""
        manager1 = get_config_manager()
        manager2 = get_config_manager()

        assert manager1 is manager2

    def test_get_global_config(self, tmp_path, monkeypatch):
        """Test getting global config."""
        # Use temp config dir
        config_dir = tmp_path / "config"
        config_dir.mkdir()

        original_dir = ConfigManager.CONFIG_DIR
        ConfigManager.CONFIG_DIR = config_dir
        ConfigManager.SETTINGS_FILE = config_dir / "settings.json"

        try:
            # Reset singleton
            import pilotcode.utils.config

            pilotcode.utils.config._config_manager = None

            config = get_global_config()
            assert isinstance(config, GlobalConfig)
        finally:
            ConfigManager.CONFIG_DIR = original_dir
            ConfigManager.SETTINGS_FILE = original_dir / "settings.json"

    def test_ensure_configured(self, tmp_path, monkeypatch):
        """Test ensure_configured function."""
        monkeypatch.setenv("PILOTCODE_API_KEY", "test-key")

        # Reset singleton
        import pilotcode.utils.config

        pilotcode.utils.config._config_manager = None

        assert ensure_configured() is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
