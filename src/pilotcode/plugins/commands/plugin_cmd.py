"""Plugin management command (/plugin).

Provides subcommands:
    /plugin list              - List installed plugins
    /plugin install <name>    - Install a plugin
    /plugin uninstall <name>  - Uninstall a plugin
    /plugin enable <name>     - Enable a plugin
    /plugin disable <name>    - Disable a plugin
    /plugin search <query>    - Search for plugins
    /plugin marketplaces      - List marketplaces
    /plugin update            - Update all marketplaces
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ...commands.base import CommandContext

from ..core.manager import PluginManager, get_plugin_manager
from ..core.types import PluginScope


async def plugin_command(args: list[str], context: "CommandContext") -> str:
    """Handle /plugin command."""
    if not args:
        return _help_text()

    subcommand = args[0].lower()
    sub_args = args[1:] if len(args) > 1 else []

    manager = await get_plugin_manager()

    handlers = {
        "list": _handle_list,
        "install": _handle_install,
        "uninstall": _handle_uninstall,
        "remove": _handle_uninstall,  # Alias
        "enable": _handle_enable,
        "disable": _handle_disable,
        "search": _handle_search,
        "marketplaces": _handle_marketplaces,
        "update": _handle_update,
        "help": _handle_help,
    }

    handler = handlers.get(subcommand)
    if handler:
        return await handler(sub_args, manager)

    return f"Unknown subcommand: {subcommand}\n\n{_help_text()}"


def _help_text() -> str:
    """Get help text."""
    return """Plugin management commands:

  /plugin list                    - List installed plugins
  /plugin install <name>          - Install a plugin
  /plugin uninstall <name>        - Uninstall a plugin
  /plugin enable <name>           - Enable a plugin
  /plugin disable <name>          - Disable a plugin
  /plugin search <query>          - Search for plugins
  /plugin marketplaces            - List configured marketplaces
  /plugin update                  - Update all marketplaces
  /plugin update plugins [name]   - Check/update plugins
  /plugin update check            - Check for all updates
  /plugin help                    - Show this help

Examples:
  /plugin install docker@claude-plugins-official
  /plugin enable docker
  /plugin search git
  /plugin update plugins          - Check for plugin updates
  /plugin update plugins --all    - Update all plugins
"""


async def _handle_list(args: list[str], manager: PluginManager) -> str:
    """Handle list subcommand."""
    result = await manager.load_plugins()

    lines = ["Installed Plugins:", ""]

    if not result.enabled and not result.disabled:
        lines.append("  No plugins installed.")
        return "\n".join(lines)

    # Enabled plugins
    if result.enabled:
        lines.append("Enabled:")
        for plugin in sorted(result.enabled, key=lambda p: p.name):
            lines.append(f"  ✓ {plugin.manifest.name} ({plugin.source})")
            if plugin.manifest.description:
                lines.append(f"    {plugin.manifest.description}")

    # Disabled plugins
    if result.disabled:
        if result.enabled:
            lines.append("")
        lines.append("Disabled:")
        for plugin in sorted(result.disabled, key=lambda p: p.name):
            lines.append(f"  ○ {plugin.manifest.name} ({plugin.source})")

    if result.errors:
        lines.append("")
        lines.append("Errors:")
        for error in result.errors:
            lines.append(f"  ! {error}")

    return "\n".join(lines)


async def _handle_install(args: list[str], manager: PluginManager) -> str:
    """Handle install subcommand."""
    if not args:
        return "Usage: /plugin install <name[@marketplace]> [--force]"

    plugin_spec = args[0]
    force = "--force" in args or "-f" in args

    # Parse scope
    scope = PluginScope.USER
    if "--scope" in args:
        idx = args.index("--scope")
        if idx + 1 < len(args):
            scope_str = args[idx + 1].lower()
            try:
                scope = PluginScope(scope_str)
            except ValueError:
                return f"Invalid scope: {scope_str}. Use: user, project, local"

    try:
        plugin = await manager.install_plugin(plugin_spec, scope=scope, force=force)
        return f"✓ Installed {plugin.manifest.name}@{plugin.source}"
    except Exception as e:
        return f"✗ Installation failed: {e}"


async def _handle_uninstall(args: list[str], manager: PluginManager) -> str:
    """Handle uninstall subcommand."""
    if not args:
        return "Usage: /plugin uninstall <name[@marketplace]>"

    plugin_spec = args[0]

    success = await manager.uninstall_plugin(plugin_spec)
    if success:
        return f"✓ Uninstalled {plugin_spec}"
    else:
        return f"✗ Plugin not found: {plugin_spec}"


async def _handle_enable(args: list[str], manager: PluginManager) -> str:
    """Handle enable subcommand."""
    if not args:
        return "Usage: /plugin enable <name[@marketplace]>"

    plugin_spec = args[0]

    success = await manager.enable_plugin(plugin_spec)
    if success:
        return f"✓ Enabled {plugin_spec}"
    else:
        return f"✗ Plugin not found: {plugin_spec}"


async def _handle_disable(args: list[str], manager: PluginManager) -> str:
    """Handle disable subcommand."""
    if not args:
        return "Usage: /plugin disable <name[@marketplace]>"

    plugin_spec = args[0]

    success = await manager.disable_plugin(plugin_spec)
    if success:
        return f"✓ Disabled {plugin_spec}"
    else:
        return f"✗ Plugin not found: {plugin_spec}"


async def _handle_search(args: list[str], manager: PluginManager) -> str:
    """Handle search subcommand."""
    if not args:
        return "Usage: /plugin search <query>"

    query = " ".join(args)
    results = manager.marketplace.search_plugins(query)

    if not results:
        return f"No plugins found matching '{query}'"

    lines = [f"Search results for '{query}':", ""]

    for entry, marketplace_name in results:
        lines.append(f"  {entry.name}@{marketplace_name}")
        if entry.description:
            lines.append(f"    {entry.description}")
        if entry.author:
            lines.append(f"    Author: {entry.author.name}")
        lines.append("")

    return "\n".join(lines)


async def _handle_marketplaces(args: list[str], manager: PluginManager) -> str:
    """Handle marketplaces subcommand."""
    known = manager.config.load_known_marketplaces()

    if not known:
        return "No marketplaces configured."

    lines = ["Configured Marketplaces:", ""]

    for name, config in sorted(known.items()):
        source_type = config.source.source
        lines.append(f"  {name}")
        lines.append(f"    Source: {source_type}")

        if config.source.repo:
            lines.append(f"    Repo: {config.source.repo}")
        if config.source.url:
            lines.append(f"    URL: {config.source.url}")
        if config.last_updated:
            lines.append(f"    Last Updated: {config.last_updated}")
        lines.append(f"    Auto-update: {config.auto_update}")
        lines.append("")

    return "\n".join(lines)


async def _handle_update(args: list[str], manager: PluginManager) -> str:
    """Handle update subcommand."""
    # Check for sub-subcommand
    if args and args[0] in ("plugins", "pkgs"):
        return await _handle_update_plugins(args[1:], manager)

    if args and args[0] == "check":
        return await _handle_update_check(args[1:], manager)

    # Default: update marketplaces
    lines = ["Updating marketplaces...", ""]

    results = await manager.update_marketplaces()

    for name, success in sorted(results.items()):
        status = "✓" if success else "✗"
        lines.append(f"  {status} {name}")

    # Reload plugins after update
    await manager.load_plugins()

    return "\n".join(lines)


async def _handle_update_plugins(args: list[str], manager: PluginManager) -> str:
    """Handle 'update plugins' subcommand."""
    specific_plugin = args[0] if args else None

    lines = ["Checking for plugin updates...", ""]

    if specific_plugin:
        # Update specific plugin
        success = await manager.update_plugin(specific_plugin)
        if success:
            lines.append(f"  ✓ {specific_plugin} updated")
        else:
            lines.append(f"  ✗ {specific_plugin} update failed")
    else:
        # Check for available updates
        updates = await manager.check_for_updates()

        if not updates:
            lines.append("All plugins are up to date.")
            return "\n".join(lines)

        lines.append("Available updates:")
        for plugin_id, info in sorted(updates.items()):
            lines.append(f"  {plugin_id}: {info['current']} → {info['latest']}")

        lines.append("")
        lines.append("Run '/plugin update plugins <name>' to update a specific plugin.")
        lines.append("Or run '/plugin update plugins --all' to update all.")

        # Auto-update if --all flag
        if "--all" in args:
            lines.append("")
            lines.append("Updating all plugins...")
            for plugin_id in list(updates.keys()):
                success = await manager.update_plugin(plugin_id)
                status = "✓" if success else "✗"
                lines.append(f"  {status} {plugin_id}")

    return "\n".join(lines)


async def _handle_update_check(args: list[str], manager: PluginManager) -> str:
    """Handle 'update check' subcommand."""
    lines = ["Checking for updates...", ""]

    # Check marketplace updates
    lines.append("Marketplace updates:")
    # This would check if marketplace sources have new commits
    lines.append("  (Use '/plugin update' to refresh marketplaces)")

    lines.append("")

    # Check plugin updates
    lines.append("Plugin updates:")
    updates = await manager.check_for_updates()

    if updates:
        for plugin_id, info in sorted(updates.items()):
            lines.append(f"  {plugin_id}: {info['current']} → {info['latest']}")
    else:
        lines.append("  All plugins are up to date.")

    return "\n".join(lines)


async def _handle_help(args: list[str], manager: PluginManager) -> str:
    """Handle help subcommand."""
    return _help_text()


def register_plugin_command():
    """Register the /plugin command with the command system."""
    try:
        from ...commands.base import CommandHandler, register_command

        register_command(
            CommandHandler(name="plugin", description="Manage plugins", handler=plugin_command)
        )
    except ImportError:
        # Command system not available yet
        pass
