"""PilotCode Plugin System.

A simplified but compatible implementation of the ClaudeCode plugin system.

Usage:
    from pilotcode.plugins import get_plugin_manager
    
    manager = get_plugin_manager()
    await manager.install_plugin("docker@claude-plugins-official")
    await manager.load_plugins()
"""

from .core.manager import PluginManager, get_plugin_manager
from .core.types import (
    PluginManifest,
    MarketplaceSource,
    LoadedPlugin,
    PluginScope,
    SkillDefinition,
    HooksConfig,
)

__all__ = [
    "PluginManager",
    "get_plugin_manager",
    "PluginManifest",
    "MarketplaceSource",
    "LoadedPlugin",
    "PluginScope",
    "SkillDefinition",
    "HooksConfig",
]
