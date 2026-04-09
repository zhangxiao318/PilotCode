"""Core plugin system components."""

from .types import (
    PluginManifest,
    MarketplaceSource,
    LoadedPlugin,
    PluginScope,
    SkillDefinition,
    HooksConfig,
    MCPServerConfig,
    PluginMarketplace,
    PluginMarketplaceEntry,
)
from .manager import PluginManager, get_plugin_manager
from .config import PluginConfig, get_plugin_config

__all__ = [
    "PluginManifest",
    "MarketplaceSource",
    "LoadedPlugin",
    "PluginScope",
    "SkillDefinition",
    "HooksConfig",
    "MCPServerConfig",
    "PluginMarketplace",
    "PluginMarketplaceEntry",
    "PluginManager",
    "get_plugin_manager",
    "PluginConfig",
    "get_plugin_config",
]
