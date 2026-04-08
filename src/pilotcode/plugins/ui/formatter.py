"""Rich text formatting for plugin UI."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..core.types import LoadedPlugin, PluginMarketplace


class PluginFormatter:
    """Formats plugin information for display."""
    
    ICON_ENABLED = "✓"
    ICON_DISABLED = "○"
    ICON_ERROR = "✗"
    ICON_WARNING = "⚠"
    ICON_INFO = "ℹ"
    
    @staticmethod
    def format_plugin_status(enabled: bool) -> str:
        """Format plugin status icon."""
        return PluginFormatter.ICON_ENABLED if enabled else PluginFormatter.ICON_DISABLED
    
    @staticmethod
    def format_version(version: str, latest: str | None = None) -> str:
        """Format version string."""
        if latest and version != latest:
            return f"{version} → {latest}"
        return version
    
    @staticmethod
    def format_plugin_list(
        plugins: list,
        show_status: bool = True,
        show_source: bool = True,
    ) -> str:
        """Format a list of plugins."""
        if not plugins:
            return "  No plugins found."
        
        lines = []
        for plugin in plugins:
            status_icon = ""
            if show_status:
                status_icon = f"{PluginFormatter.format_plugin_status(plugin.enabled)} "
            
            source_info = ""
            if show_source and hasattr(plugin, 'source'):
                source_info = f" ({plugin.source})"
            
            lines.append(f"  {status_icon}{plugin.manifest.name}{source_info}")
            
            if plugin.manifest.description:
                lines.append(f"      {plugin.manifest.description}")
        
        return "\n".join(lines)
    
    @staticmethod
    def format_marketplace(
        marketplace,
        show_plugins: bool = True,
    ) -> str:
        """Format marketplace information."""
        lines = [
            f"{marketplace.name}",
            f"  {marketplace.description}",
            f"  Plugins: {len(marketplace.plugins)}",
        ]
        
        if show_plugins and marketplace.plugins:
            lines.append("")
            for plugin in marketplace.plugins[:10]:  # Show first 10
                lines.append(f"    • {plugin.name}: {plugin.description}")
            
            if len(marketplace.plugins) > 10:
                lines.append(f"    ... and {len(marketplace.plugins) - 10} more")
        
        return "\n".join(lines)
    
    @staticmethod
    def format_installation_result(success: bool, plugin_id: str, message: str) -> str:
        """Format installation result."""
        if success:
            return f"{PluginFormatter.ICON_ENABLED} Installed {plugin_id}"
        return f"{PluginFormatter.ICON_ERROR} Failed to install {plugin_id}: {message}"
    
    @staticmethod
    def format_update_info(updates: dict) -> str:
        """Format update information."""
        if not updates:
            return "All plugins are up to date."
        
        lines = ["Available updates:"]
        for plugin_id, info in updates.items():
            lines.append(
                f"  {plugin_id}: {info['current']} → {info['latest']}"
            )
        return "\n".join(lines)


# Convenience functions
def format_plugin_list(plugins: list, **kwargs) -> str:
    """Format plugin list."""
    return PluginFormatter.format_plugin_list(plugins, **kwargs)


def format_marketplace(marketplace, **kwargs) -> str:
    """Format marketplace."""
    return PluginFormatter.format_marketplace(marketplace, **kwargs)
