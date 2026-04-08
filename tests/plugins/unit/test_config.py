"""Unit tests for plugin configuration."""

import json
import pytest


try:
    from pilotcode.plugins.core.config import PluginConfig
    from pilotcode.plugins.core.types import (
        KnownMarketplace,
        MarketplaceSource,
        PluginInstallation,
        PluginScope,
    )
    PLUGINS_AVAILABLE = True
except ImportError:
    PLUGINS_AVAILABLE = False

pytestmark = [
    pytest.mark.plugin,
    pytest.mark.plugin_unit,
    pytest.mark.unit,
    pytest.mark.skipif(not PLUGINS_AVAILABLE, reason="Plugin system not available"),
]


class TestPluginConfig:
    """Test PluginConfig class."""
    
    def test_directory_creation(self, temp_config_dir):
        """Test that config directories are created."""
        config = PluginConfig(config_dir=temp_config_dir)
        
        assert config.config_dir == temp_config_dir
        assert config.plugins_dir.exists()
        assert config.cache_dir.exists()
        assert config.marketplaces_cache_dir.exists()
    
    def test_default_config_dir(self):
        """Test default config directory is used."""
        config = PluginConfig()
        
        # Should be in user's home directory
        assert ".config" in str(config.config_dir) or "AppData" in str(config.config_dir)
    
    def test_known_marketplaces_file_path(self, temp_config_dir):
        """Test known marketplaces file path."""
        config = PluginConfig(config_dir=temp_config_dir)
        
        expected = temp_config_dir / "plugins" / "known_marketplaces.json"
        assert config.known_marketplaces_file == expected
    
    def test_installed_plugins_file_path(self, temp_config_dir):
        """Test installed plugins file path."""
        config = PluginConfig(config_dir=temp_config_dir)
        
        expected = temp_config_dir / "plugins" / "installed_plugins.json"
        assert config.installed_plugins_file == expected
    
    def test_save_and_load_known_marketplaces(self, plugin_config):
        """Test saving and loading known marketplaces."""
        source = MarketplaceSource(source="github", repo="test/repo")
        marketplaces = {
            "test": KnownMarketplace(
                source=source,
                install_location="test-loc",
                auto_update=True,
            )
        }
        
        plugin_config.save_known_marketplaces(marketplaces)
        loaded = plugin_config.load_known_marketplaces()
        
        assert "test" in loaded
        assert loaded["test"].source.repo == "test/repo"
        assert loaded["test"].auto_update is True
    
    def test_load_empty_known_marketplaces(self, plugin_config):
        """Test loading when file doesn't exist."""
        loaded = plugin_config.load_known_marketplaces()
        assert loaded == {}
    
    def test_save_and_load_installed_plugins(self, plugin_config):
        """Test saving and loading installed plugins."""
        from datetime import datetime
        
        installations = [
            PluginInstallation(
                plugin_id="test@marketplace",
                scope=PluginScope.USER,
                install_path=plugin_config.config_dir / "test",
                version="1.0.0",
                installed_at=datetime.now(),
            )
        ]
        
        plugin_config.save_installed_plugins(installations)
        loaded = plugin_config.load_installed_plugins()
        
        assert len(loaded) == 1
        assert loaded[0].plugin_id == "test@marketplace"
        assert loaded[0].scope == PluginScope.USER
    
    def test_load_installed_plugins_empty(self, plugin_config):
        """Test loading when no installations exist."""
        loaded = plugin_config.load_installed_plugins()
        assert loaded == []
    
    def test_plugin_cache_path(self, plugin_config):
        """Test plugin cache path generation."""
        path = plugin_config.get_plugin_cache_path("test@marketplace")
        
        assert plugin_config.cache_dir in path.parents
        assert "test_marketplace" in path.name
    
    def test_plugin_cache_path_with_version(self, plugin_config):
        """Test plugin cache path with version."""
        path = plugin_config.get_plugin_cache_path("test@marketplace", version="1.0.0")
        
        assert "1.0.0" in path.name
    
    def test_marketplace_cache_path(self, plugin_config):
        """Test marketplace cache path."""
        path = plugin_config.get_marketplace_cache_path("my-marketplace")
        
        assert plugin_config.marketplaces_cache_dir in path.parents
        assert path.name == "my-marketplace"
    
    def test_corrupted_known_marketplaces_file(self, plugin_config):
        """Test handling of corrupted marketplaces file."""
        # Write invalid JSON
        plugin_config.known_marketplaces_file.parent.mkdir(parents=True, exist_ok=True)
        plugin_config.known_marketplaces_file.write_text("invalid json")
        
        loaded = plugin_config.load_known_marketplaces()
        assert loaded == {}
    
    def test_load_old_format_installed_plugins(self, plugin_config):
        """Test loading old format (dict instead of list)."""
        # Save in old format
        old_format = {
            "test@marketplace": [
                {
                    "scope": "user",
                    "install_path": str(plugin_config.config_dir / "test"),
                    "version": "1.0.0",
                    "installed_at": "2024-01-01T00:00:00",
                }
            ]
        }
        plugin_config.installed_plugins_file.parent.mkdir(parents=True, exist_ok=True)
        with open(plugin_config.installed_plugins_file, "w") as f:
            json.dump(old_format, f)
        
        loaded = plugin_config.load_installed_plugins()
        assert len(loaded) == 1
        assert loaded[0].plugin_id == "test@marketplace"
