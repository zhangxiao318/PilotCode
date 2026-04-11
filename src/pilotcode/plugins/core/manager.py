"""Plugin manager - main entry point for plugin operations.

This module provides the high-level API for:
- Installing/uninstalling plugins
- Enabling/disabling plugins
- Loading plugin components
- Managing dependencies
- Version control and updates
"""

from __future__ import annotations

import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Optional

from .types import (
    PluginManifest,
    LoadedPlugin,
    PluginScope,
    PluginInstallation,
    PluginLoadResult,
    HooksConfig,
)
from .config import PluginConfig
from .marketplace import MarketplaceManager
from .dependencies import DependencyResolver, DependencyGraph
from .versioning import VersionManager, UpdateChecker
from .autoupdate import AutoUpdater, UpdatePolicy, MarketplaceUpdater
from ..sources.github import GitHubSource
from ..sources.base import SourceError, DownloadResult


class PluginError(Exception):
    """Error related to plugin operations."""

    pass


class PluginManager:
    """Main plugin manager.

    This is the primary interface for plugin operations.

    Example:
        manager = PluginManager()
        await manager.initialize()

        # Install a plugin
        await manager.install_plugin("docker@claude-plugins-official")

        # Load all enabled plugins
        result = await manager.load_plugins()
    """

    def __init__(self, config: Optional[PluginConfig] = None):
        self.config = config or PluginConfig()
        self.marketplace = MarketplaceManager(self.config)
        self._github_source = GitHubSource()
        self._loaded_plugins: dict[str, LoadedPlugin] = {}

        # Phase 2 components
        self.dependency_resolver = DependencyResolver(self)
        self.version_manager = VersionManager()
        self.update_checker = UpdateChecker(self)
        self.auto_updater: Optional[AutoUpdater] = None
        self.marketplace_updater = MarketplaceUpdater(self)

    async def initialize(self) -> None:
        """Initialize the plugin manager."""
        await self.marketplace.initialize()

        # Initialize auto-updater if enabled
        # (disabled by default, can be enabled via settings)

    async def install_plugin(
        self, plugin_spec: str, scope: PluginScope = PluginScope.USER, force: bool = False
    ) -> LoadedPlugin:
        """Install a plugin.

        Args:
            plugin_spec: Plugin specification (name@marketplace or just name)
            scope: Installation scope (user, project, local)
            force: Whether to reinstall if already exists

        Returns:
            The installed plugin
        """
        # Parse plugin spec
        if "@" in plugin_spec:
            plugin_name, marketplace_name = plugin_spec.rsplit("@", 1)
        else:
            plugin_name = plugin_spec
            marketplace_name = None

        # Find plugin in marketplace
        if marketplace_name:
            result = self.marketplace.find_plugin(plugin_name, marketplace_name)
            if not result:
                raise PluginError(
                    f"Plugin '{plugin_name}' not found in marketplace '{marketplace_name}'"
                )
            entry, found_marketplace = result
        else:
            # Search all marketplaces
            result = self.marketplace.find_plugin(plugin_name)
            if not result:
                raise PluginError(
                    f"Plugin '{plugin_name}' not found in any marketplace. "
                    "Try specifying the marketplace: name@marketplace"
                )
            entry, found_marketplace = result

        plugin_id = f"{plugin_name}@{found_marketplace}"

        # Check if already installed
        existing = self._get_installation(plugin_id)
        if existing and not force:
            raise PluginError(
                f"Plugin '{plugin_id}' is already installed. " "Use --force to reinstall."
            )

        # Download plugin
        cache_path = self.config.get_plugin_cache_path(plugin_id)

        try:
            if isinstance(entry.source, str):
                # Source is a simple string (GitHub repo or path)
                if "/" in entry.source and not entry.source.startswith(("http", "/", ".")):
                    # Looks like a GitHub repo
                    source_config = {"source": "github", "repo": entry.source}
                else:
                    # Local path
                    source_config = {"source": "directory", "path": entry.source}
            else:
                # Source is a dict
                source_config = entry.source

            # Handle local directory sources
            if source_config.get("source") == "directory":
                source_path = Path(source_config.get("path"))
                if not source_path.exists():
                    raise PluginError(f"Local plugin path does not exist: {source_path}")

                # Copy to cache
                if cache_path.exists() and force:
                    shutil.rmtree(cache_path)

                if cache_path.exists():
                    raise PluginError(
                        f"Plugin already exists at {cache_path}. Use --force to overwrite."
                    )

                shutil.copytree(source_path, cache_path)
                result = DownloadResult(success=True, path=cache_path)
            else:
                # Use git source for github/git sources
                result = await self._github_source.download(source_config, cache_path, force=force)

            if not result.success:
                raise PluginError(f"Failed to download plugin: {result.error}")

            # Load and validate manifest
            manifest = self._load_manifest(cache_path)

            # Create installation record
            installation = PluginInstallation(
                plugin_id=plugin_id,
                scope=scope,
                install_path=cache_path,
                version=entry.version or result.version or "unknown",
                installed_at=datetime.now(),
                project_path=(
                    str(Path.cwd()) if scope in (PluginScope.PROJECT, PluginScope.LOCAL) else None
                ),
            )

            # Save installation record
            self._save_installation(installation)

            # Auto-enable
            await self.enable_plugin(plugin_id, scope)

            # Load the plugin
            loaded = await self._load_plugin_from_path(cache_path, plugin_id, manifest)
            loaded.scope = scope
            loaded.installed_at = installation.installed_at

            self._loaded_plugins[plugin_id] = loaded

            return loaded

        except SourceError as e:
            raise PluginError(f"Installation failed: {e}")

    async def uninstall_plugin(self, plugin_spec: str, scope: Optional[PluginScope] = None) -> bool:
        """Uninstall a plugin.

        Args:
            plugin_spec: Plugin ID (name@marketplace)
            scope: Optional scope to uninstall from

        Returns:
            True if uninstalled, False if not found
        """
        # Find installation
        installation = self._get_installation(plugin_spec)
        if not installation:
            # Try to find by name only
            for inst in self.config.load_installed_plugins():
                if inst.plugin_id.startswith(f"{plugin_spec}@"):
                    installation = inst
                    plugin_spec = inst.plugin_id
                    break

        if not installation:
            return False

        # Check scope if specified
        if scope and installation.scope != scope:
            return False

        # Disable first
        await self.disable_plugin(plugin_spec)

        # Remove from loaded plugins
        if plugin_spec in self._loaded_plugins:
            del self._loaded_plugins[plugin_spec]

        # Remove installation record
        self._remove_installation(plugin_spec)

        # Remove cache
        if installation.install_path.exists():
            shutil.rmtree(installation.install_path)

        return True

    async def enable_plugin(self, plugin_spec: str, scope: Optional[PluginScope] = None) -> bool:
        """Enable a plugin.

        Args:
            plugin_spec: Plugin ID (name@marketplace)
            scope: Scope to enable in (defaults to where it's installed)

        Returns:
            True if enabled, False if not found
        """
        # Resolve full plugin_id if partial
        plugin_id = self._resolve_plugin_id(plugin_spec)
        if not plugin_id:
            return False

        # Update settings
        settings = self.config.load_settings()
        settings.enabled_plugins[plugin_id] = True
        self.config.save_settings(settings)

        # Reload if already loaded
        if plugin_id in self._loaded_plugins:
            self._loaded_plugins[plugin_id].enabled = True

        return True

    async def disable_plugin(self, plugin_spec: str) -> bool:
        """Disable a plugin.

        Args:
            plugin_spec: Plugin ID (name@marketplace)

        Returns:
            True if disabled, False if not found
        """
        plugin_id = self._resolve_plugin_id(plugin_spec)
        if not plugin_id:
            return False

        # Update settings
        settings = self.config.load_settings()
        settings.enabled_plugins[plugin_id] = False
        self.config.save_settings(settings)

        # Update loaded plugin
        if plugin_id in self._loaded_plugins:
            self._loaded_plugins[plugin_id].enabled = False

        return True

    async def load_plugins(self) -> PluginLoadResult:
        """Load all enabled plugins.

        Returns:
            PluginLoadResult with enabled, disabled, and errors
        """
        result = PluginLoadResult()
        settings = self.config.load_settings()
        installations = self.config.load_installed_plugins()

        for installation in installations:
            plugin_id = installation.plugin_id

            try:
                # Check if enabled
                is_enabled = settings.enabled_plugins.get(plugin_id, True)

                # Load manifest
                manifest = self._load_manifest(installation.install_path)

                # Load plugin
                loaded = await self._load_plugin_from_path(
                    installation.install_path, plugin_id, manifest
                )
                loaded.enabled = is_enabled
                loaded.scope = installation.scope
                loaded.installed_at = installation.installed_at

                self._loaded_plugins[plugin_id] = loaded

                if is_enabled:
                    result.enabled.append(loaded)
                else:
                    result.disabled.append(loaded)

            except Exception as e:
                result.errors.append(f"Failed to load {plugin_id}: {e}")

        return result

    async def _load_plugin_from_path(
        self, path: Path, plugin_id: str, manifest: PluginManifest
    ) -> LoadedPlugin:
        """Load a plugin from a path."""
        # Determine source from plugin_id
        if "@" in plugin_id:
            source = plugin_id.split("@", 1)[1]
        else:
            source = "local"

        loaded = LoadedPlugin(
            name=manifest.name, manifest=manifest, path=path, source=source, enabled=True
        )

        # Load hooks config
        if manifest.hooks:
            if isinstance(manifest.hooks, str):
                # Path to hooks.json
                hooks_path = path / manifest.hooks
                if hooks_path.exists():
                    with open(hooks_path, "r") as f:
                        hooks_data = json.load(f)
                    loaded.hooks_config = HooksConfig(**hooks_data.get("hooks", {}))
            else:
                loaded.hooks_config = manifest.hooks

        # Load MCP servers
        if manifest.mcp_servers:
            loaded.mcp_servers = manifest.mcp_servers

        # Set component paths
        if manifest.commands:
            if isinstance(manifest.commands, str):
                loaded.commands_path = path / manifest.commands
            else:
                loaded.commands_path = path / "commands"

        if manifest.agents:
            if isinstance(manifest.agents, str):
                loaded.agents_path = path / manifest.agents
            else:
                loaded.agents_path = path / "agents"

        if manifest.skills:
            if isinstance(manifest.skills, str):
                loaded.skills_path = path / manifest.skills
            else:
                loaded.skills_path = path / "skills"

        return loaded

    def _load_manifest(self, path: Path) -> PluginManifest:
        """Load plugin.json manifest."""
        manifest_file = path / "plugin.json"

        # Also check .claude-plugin directory
        if not manifest_file.exists():
            manifest_file = path / ".claude-plugin" / "plugin.json"

        if not manifest_file.exists():
            # Create default manifest from directory name
            return PluginManifest(name=path.name)

        with open(manifest_file, "r") as f:
            data = json.load(f)

        return PluginManifest(**data)

    def _get_installation(self, plugin_id: str) -> Optional[PluginInstallation]:
        """Get installation record for a plugin."""
        installations = self.config.load_installed_plugins()
        for inst in installations:
            if inst.plugin_id == plugin_id:
                return inst
        return None

    def _save_installation(self, installation: PluginInstallation) -> None:
        """Save or update installation record."""
        installations = self.config.load_installed_plugins()

        # Remove existing if any
        installations = [i for i in installations if i.plugin_id != installation.plugin_id]

        # Add new
        installations.append(installation)

        self.config.save_installed_plugins(installations)

    def _remove_installation(self, plugin_id: str) -> None:
        """Remove installation record."""
        installations = self.config.load_installed_plugins()
        installations = [i for i in installations if i.plugin_id != plugin_id]
        self.config.save_installed_plugins(installations)

    def _resolve_plugin_id(self, spec: str) -> Optional[str]:
        """Resolve partial plugin spec to full plugin_id."""
        if "@" in spec:
            return spec

        # Find by name
        for inst in self.config.load_installed_plugins():
            if inst.plugin_id.startswith(f"{spec}@"):
                return inst.plugin_id

        return None

    def get_loaded_plugin(self, plugin_id: str) -> Optional[LoadedPlugin]:
        """Get a loaded plugin by ID."""
        return self._loaded_plugins.get(plugin_id)

    def list_loaded_plugins(self) -> list[LoadedPlugin]:
        """List all loaded plugins."""
        return list(self._loaded_plugins.values())

    # ==========================================================================
    # Phase 2: Dependency Management
    # ==========================================================================

    async def check_dependencies(
        self,
        plugin_id: str,
        install_missing: bool = False,
    ) -> DependencyGraph:
        """Check and resolve dependencies for a plugin.

        Args:
            plugin_id: Plugin to check
            install_missing: Auto-install missing dependencies

        Returns:
            DependencyGraph with resolution status
        """
        return await self.dependency_resolver.resolve_dependencies(
            plugin_id,
            install_missing=install_missing,
        )

    def check_reverse_dependencies(self, plugin_id: str) -> list[str]:
        """Check which plugins depend on this one.

        Args:
            plugin_id: Plugin to check

        Returns:
            List of plugin IDs that depend on this one
        """
        return self.dependency_resolver.check_reverse_dependencies(plugin_id)

    async def install_with_dependencies(
        self,
        plugin_spec: str,
        scope: PluginScope = PluginScope.USER,
    ) -> LoadedPlugin:
        """Install a plugin and its dependencies.

        Args:
            plugin_spec: Plugin to install
            scope: Installation scope

        Returns:
            The installed plugin
        """
        # First install the main plugin
        plugin = await self.install_plugin(plugin_spec, scope=scope)

        # Then resolve and install dependencies
        graph = await self.check_dependencies(plugin.name, install_missing=True)

        # Report any issues
        errors = graph.validate()
        if errors:
            for error in errors:
                print(f"Dependency warning: {error}")

        return plugin

    # ==========================================================================
    # Phase 2: Version Management
    # ==========================================================================

    def get_plugin_version(self, plugin_id: str) -> Optional[str]:
        """Get the version of an installed plugin.

        Args:
            plugin_id: Plugin identifier

        Returns:
            Version string or None
        """
        installation = self._get_installation(plugin_id)
        if not installation:
            return None

        try:
            manifest = self._load_manifest(installation.install_path)
            return manifest.version
        except Exception:
            return None

    async def check_for_updates(self) -> dict[str, dict]:
        """Check all plugins for available updates.

        Returns:
            Dict of plugin_id -> update info
        """
        return await self.update_checker.check_all()

    async def update_plugin(self, plugin_id: str) -> bool:
        """Update a plugin to the latest version.

        Args:
            plugin_id: Plugin to update

        Returns:
            True if updated or already up to date
        """
        # Check if update is available
        updates = await self.check_for_updates()

        if plugin_id not in updates:
            return True  # Already up to date

        updates[plugin_id]

        # Get current installation
        installation = self._get_installation(plugin_id)
        if not installation:
            return False

        # Reinstall with force
        try:
            await self.install_plugin(
                plugin_id,
                scope=installation.scope,
                force=True,
            )
            return True
        except Exception as e:
            print(f"Failed to update {plugin_id}: {e}")
            return False

    def compare_versions(self, v1: str, v2: str) -> int:
        """Compare two version strings.

        Returns:
            -1 if v1 < v2, 0 if equal, 1 if v1 > v2
        """
        return self.version_manager.compare_versions(v1, v2)

    # ==========================================================================
    # Phase 2: Auto-Update
    # ==========================================================================

    def setup_auto_update(self, policy: Optional[UpdatePolicy] = None) -> None:
        """Setup automatic updates.

        Args:
            policy: Update policy (uses default if None)
        """
        self.auto_updater = AutoUpdater(self, policy)

    async def start_auto_update(self) -> None:
        """Start automatic background updates."""
        if self.auto_updater:
            await self.auto_updater.start_background_checks()

    async def stop_auto_update(self) -> None:
        """Stop automatic background updates."""
        if self.auto_updater:
            await self.auto_updater.stop_background_checks()

    async def run_auto_update(self, dry_run: bool = True) -> dict[str, dict]:
        """Run auto-update check and optionally install.

        Args:
            dry_run: If True, only check without installing

        Returns:
            Available or installed updates
        """
        if not self.auto_updater:
            self.setup_auto_update()

        return await self.auto_updater.check_and_update(dry_run=dry_run)

    # ==========================================================================
    # Phase 2: Marketplace Management
    # ==========================================================================

    async def update_marketplaces(self) -> dict[str, bool]:
        """Update all marketplace catalogs.

        Returns:
            Dict of marketplace_name -> success
        """
        return await self.marketplace_updater.update_all()

    async def update_marketplace(self, name: str) -> bool:
        """Update a specific marketplace.

        Args:
            name: Marketplace name

        Returns:
            True if successful
        """
        return await self.marketplace_updater.update_marketplace(name)

    async def check_outdated_plugins(self) -> list[dict]:
        """Check which plugins have updates in their marketplaces.

        Returns:
            List of outdated plugin info
        """
        return await self.marketplace_updater.check_outdated_plugins()


# Global manager instance
_manager: Optional[PluginManager] = None


async def get_plugin_manager(config: Optional[PluginConfig] = None) -> PluginManager:
    """Get global plugin manager instance."""
    global _manager
    if _manager is None:
        _manager = PluginManager(config)
        await _manager.initialize()
    return _manager
