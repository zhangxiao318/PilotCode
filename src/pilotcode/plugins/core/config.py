"""Plugin configuration management.

Manages plugin-related configuration files:
- known_marketplaces.json - Registered marketplaces
- installed_plugins.json - Installed plugin records
- settings.json - User settings including enabledPlugins
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Optional
from pydantic import BaseModel, Field

from .types import KnownMarketplace, PluginInstallation, PluginScope


class PluginSettings(BaseModel):
    """Plugin-related settings."""
    enabled_plugins: dict[str, bool] = Field(default_factory=dict)
    extra_known_marketplaces: dict[str, KnownMarketplace] = Field(default_factory=dict)


class PluginConfig:
    """Manages plugin configuration files.
    
    Directory structure:
    ~/.config/pilotcode/plugins/
        ├── known_marketplaces.json
        ├── installed_plugins.json
        └── cache/
            └── marketplaces/
    """
    
    def __init__(self, config_dir: Optional[Path] = None):
        if config_dir is None:
            config_dir = self._get_default_config_dir()
        self.config_dir = Path(config_dir)
        self.plugins_dir = self.config_dir / "plugins"
        self.cache_dir = self.plugins_dir / "cache"
        self.marketplaces_cache_dir = self.cache_dir / "marketplaces"
        
        # Ensure directories exist
        self._ensure_directories()
    
    def _get_default_config_dir(self) -> Path:
        """Get default configuration directory."""
        if os.name == "nt":  # Windows
            return Path(os.environ.get("APPDATA", Path.home() / "AppData/Roaming")) / "pilotcode"
        else:
            # Linux/macOS
            return Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "pilotcode"
    
    def _ensure_directories(self) -> None:
        """Create necessary directories if they don't exist."""
        self.plugins_dir.mkdir(parents=True, exist_ok=True)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.marketplaces_cache_dir.mkdir(parents=True, exist_ok=True)
    
    @property
    def known_marketplaces_file(self) -> Path:
        """Path to known_marketplaces.json."""
        return self.plugins_dir / "known_marketplaces.json"
    
    @property
    def installed_plugins_file(self) -> Path:
        """Path to installed_plugins.json."""
        return self.plugins_dir / "installed_plugins.json"
    
    def load_known_marketplaces(self) -> dict[str, KnownMarketplace]:
        """Load known marketplaces configuration."""
        if not self.known_marketplaces_file.exists():
            return {}
        
        try:
            with open(self.known_marketplaces_file, "r") as f:
                data = json.load(f)
            return {
                name: KnownMarketplace(**config)
                for name, config in data.items()
            }
        except (json.JSONDecodeError, TypeError) as e:
            print(f"Warning: Failed to load known_marketplaces.json: {e}")
            return {}
    
    def save_known_marketplaces(self, marketplaces: dict[str, KnownMarketplace]) -> None:
        """Save known marketplaces configuration."""
        data = {name: config.model_dump(by_alias=True) for name, config in marketplaces.items()}
        with open(self.known_marketplaces_file, "w") as f:
            json.dump(data, f, indent=2, default=str)
    
    def load_installed_plugins(self) -> list[PluginInstallation]:
        """Load installed plugins records."""
        if not self.installed_plugins_file.exists():
            return []
        
        try:
            with open(self.installed_plugins_file, "r") as f:
                data = json.load(f)
            
            # Handle both old format (dict) and new format (list)
            if isinstance(data, dict):
                # Convert old format
                installations = []
                for plugin_id, entries in data.items():
                    for entry in entries:
                        entry["plugin_id"] = plugin_id
                        installations.append(PluginInstallation(**entry))
                return installations
            else:
                return [PluginInstallation(**item) for item in data]
        except (json.JSONDecodeError, TypeError) as e:
            print(f"Warning: Failed to load installed_plugins.json: {e}")
            return []
    
    def save_installed_plugins(self, installations: list[PluginInstallation]) -> None:
        """Save installed plugins records."""
        data = [inst.model_dump(by_alias=True) for inst in installations]
        with open(self.installed_plugins_file, "w") as f:
            json.dump(data, f, indent=2, default=str)
    
    def load_settings(self) -> PluginSettings:
        """Load plugin settings from settings.json."""
        settings_file = self.config_dir / "settings.json"
        if not settings_file.exists():
            return PluginSettings()
        
        try:
            with open(settings_file, "r") as f:
                data = json.load(f)
            return PluginSettings(
                enabled_plugins=data.get("enabledPlugins", {}),
                extra_known_marketplaces={
                    name: KnownMarketplace(**config)
                    for name, config in data.get("extraKnownMarketplaces", {}).items()
                }
            )
        except (json.JSONDecodeError, TypeError) as e:
            print(f"Warning: Failed to load settings.json: {e}")
            return PluginSettings()
    
    def save_settings(self, settings: PluginSettings) -> None:
        """Save plugin settings to settings.json."""
        settings_file = self.config_dir / "settings.json"
        
        # Load existing settings
        existing = {}
        if settings_file.exists():
            try:
                with open(settings_file, "r") as f:
                    existing = json.load(f)
            except json.JSONDecodeError:
                pass
        
        # Update with plugin settings
        existing["enabledPlugins"] = settings.enabled_plugins
        existing["extraKnownMarketplaces"] = {
            name: config.model_dump(by_alias=True)
            for name, config in settings.extra_known_marketplaces.items()
        }
        
        with open(settings_file, "w") as f:
            json.dump(existing, f, indent=2, default=str)
    
    def get_plugin_cache_path(self, plugin_id: str, version: Optional[str] = None) -> Path:
        """Get cache path for a plugin.
        
        Args:
            plugin_id: Plugin identifier (name@marketplace)
            version: Optional version string
        """
        # Sanitize plugin_id for filesystem
        safe_id = plugin_id.replace("/", "_").replace("@", "_")
        if version:
            safe_id = f"{safe_id}_{version}"
        return self.cache_dir / safe_id
    
    def get_marketplace_cache_path(self, marketplace_name: str) -> Path:
        """Get cache path for a marketplace."""
        return self.marketplaces_cache_dir / marketplace_name


# Global config instance
_config: Optional[PluginConfig] = None


def get_plugin_config(config_dir: Optional[Path] = None) -> PluginConfig:
    """Get global plugin configuration instance."""
    global _config
    if _config is None or config_dir is not None:
        _config = PluginConfig(config_dir)
    return _config
