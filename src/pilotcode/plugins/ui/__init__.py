"""UI components for plugin management.

Provides rich text formatting and interactive UI for the plugin system.
"""

from .formatter import PluginFormatter, format_plugin_list, format_marketplace
from .interactive import PluginSelector, confirm_action

__all__ = [
    "PluginFormatter",
    "format_plugin_list",
    "format_marketplace",
    "PluginSelector",
    "confirm_action",
]
