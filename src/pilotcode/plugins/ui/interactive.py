"""Interactive UI components for plugin management."""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from ..core.types import PluginMarketplaceEntry


class PluginSelector:
    """Interactive plugin selector.

    Provides numbered selection from a list.
    """

    def __init__(self, items: list):
        self.items = items
        self.selected: Optional[int] = None

    def display(self) -> str:
        """Display numbered list."""
        lines = [""]
        for i, item in enumerate(self.items, 1):
            if isinstance(item, str):
                lines.append(f"  {i}. {item}")
            elif hasattr(item, "name"):
                lines.append(f"  {i}. {item.name}")
                if hasattr(item, "description"):
                    lines.append(f"     {item.description}")
            else:
                lines.append(f"  {i}. {str(item)}")
        lines.append("")
        lines.append("Enter number to select (0 to cancel):")
        return "\n".join(lines)

    def select(self, choice: str) -> Optional:
        """Process selection."""
        try:
            num = int(choice)
            if num == 0:
                return None
            if 1 <= num <= len(self.items):
                self.selected = num - 1
                return self.items[self.selected]
        except ValueError:
            pass
        return None


class ConfirmDialog:
    """Yes/No confirmation dialog."""

    def __init__(self, message: str, default: bool = False):
        self.message = message
        self.default = default

    def display(self) -> str:
        """Display prompt."""
        default_str = "Y/n" if self.default else "y/N"
        return f"{self.message} [{default_str}]: "

    def parse(self, response: str) -> bool:
        """Parse response."""
        response = response.strip().lower()
        if response in ("y", "yes"):
            return True
        if response in ("n", "no"):
            return False
        return self.default


def confirm_action(
    action: str,
    plugin_id: str,
    details: Optional[str] = None,
) -> str:
    """Create confirmation prompt for an action.

    Args:
        action: Action name (install, uninstall, etc.)
        plugin_id: Plugin ID
        details: Optional additional details

    Returns:
        Confirmation prompt string
    """
    lines = [
        f"",
        f"Confirm {action}:",
        f"  Plugin: {plugin_id}",
    ]

    if details:
        lines.append(f"  {details}")

    lines.append(f"")
    lines.append(f"Proceed? [y/N]: ")

    return "\n".join(lines)


def format_search_results(
    results: list[tuple],
    query: str,
) -> str:
    """Format search results.

    Args:
        results: List of (entry, marketplace) tuples
        query: Search query

    Returns:
        Formatted string
    """
    if not results:
        return f"No plugins found matching '{query}'"

    lines = [
        f"Search results for '{query}':",
        "",
    ]

    for entry, marketplace in results[:20]:  # Limit to 20
        lines.append(f"  {entry.name}@{marketplace}")
        if entry.description:
            lines.append(f"    {entry.description}")
        if entry.author:
            lines.append(f"    Author: {entry.author.name}")
        lines.append("")

    if len(results) > 20:
        lines.append(f"  ... and {len(results) - 20} more results")

    return "\n".join(lines)


def format_dependency_tree(graph) -> str:
    """Format dependency tree.

    Args:
        graph: DependencyGraph

    Returns:
        Formatted tree string
    """
    lines = ["Dependencies:"]

    for node in graph.nodes.values():
        deps = graph.get_dependencies(node.plugin_id)
        if deps:
            lines.append(f"  {node.plugin_id}:")
            for dep in deps:
                lines.append(f"    → {dep}")
        else:
            lines.append(f"  {node.plugin_id} (no dependencies)")

    return "\n".join(lines)


def create_progress_bar(
    current: int,
    total: int,
    width: int = 30,
) -> str:
    """Create ASCII progress bar.

    Args:
        current: Current progress
        total: Total items
        width: Bar width

    Returns:
        Progress bar string
    """
    if total == 0:
        return "[" + " " * width + "] 0%"

    percent = current / total
    filled = int(width * percent)
    bar = "█" * filled + "░" * (width - filled)

    return f"[{bar}] {int(percent * 100)}%"


# Export main classes
__all__ = [
    "PluginSelector",
    "ConfirmDialog",
    "confirm_action",
    "format_search_results",
    "format_dependency_tree",
    "create_progress_bar",
]
