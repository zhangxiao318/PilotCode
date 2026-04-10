"""Automatic plugin updates.

Handles checking for and applying plugin updates.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from .types import PluginInstallation, PluginScope
from .versioning import VersionManager, UpdateChecker


@dataclass
class UpdatePolicy:
    """Policy for automatic updates."""

    enabled: bool = True
    auto_install: bool = False  # If True, install without prompting
    check_interval_hours: int = 24
    allowed_sources: list[str] = None  # List of allowed marketplace sources
    exclude_plugins: list[str] = None  # List of plugins to never auto-update

    def __post_init__(self):
        if self.allowed_sources is None:
            self.allowed_sources = ["claude-plugins-official"]
        if self.exclude_plugins is None:
            self.exclude_plugins = []


@dataclass
class UpdateRecord:
    """Record of an update check or installation."""

    plugin_id: str
    timestamp: datetime
    old_version: str
    new_version: str
    success: bool
    error_message: Optional[str] = None


class AutoUpdater:
    """Manages automatic plugin updates.

    Handles:
    - Scheduled update checks
    - Update policy enforcement
    - Auto-installation of updates
    - Update history
    """

    def __init__(self, manager, policy: Optional[UpdatePolicy] = None):
        from .manager import PluginManager

        self.manager: PluginManager = manager
        self.policy = policy or UpdatePolicy()
        self.version_manager = VersionManager()
        self.update_checker = UpdateChecker(manager)
        self._last_check_file = manager.config.plugins_dir / ".last_update_check"
        self._history_file = manager.config.plugins_dir / "update_history.json"
        self._running = False
        self._task: Optional[asyncio.Task] = None

    def should_check(self) -> bool:
        """Check if it's time for an update check based on policy."""
        if not self.policy.enabled:
            return False

        if not self._last_check_file.exists():
            return True

        try:
            last_check_str = self._last_check_file.read_text().strip()
            last_check = datetime.fromisoformat(last_check_str)

            interval = timedelta(hours=self.policy.check_interval_hours)
            return datetime.now() - last_check >= interval
        except (ValueError, IOError):
            return True

    def record_check(self) -> None:
        """Record that an update check was performed."""
        try:
            self._last_check_file.write_text(datetime.now().isoformat())
        except IOError:
            pass

    async def check_and_update(
        self,
        dry_run: bool = False,
        specific_plugins: Optional[list[str]] = None,
    ) -> dict[str, dict]:
        """Check for updates and optionally install them.

        Args:
            dry_run: If True, only check but don't install
            specific_plugins: Only check/update these plugins

        Returns:
            Dict of plugin_id -> update info
        """
        if not self.policy.enabled:
            return {}

        # Check for available updates
        updates = await self.update_checker.check_all()

        # Filter by policy
        filtered_updates = self._apply_policy(updates)

        if specific_plugins:
            filtered_updates = {k: v for k, v in filtered_updates.items() if k in specific_plugins}

        if dry_run:
            self.record_check()
            return filtered_updates

        # Install updates
        installed = {}
        for plugin_id, update_info in filtered_updates.items():
            try:
                # Check if auto-install is allowed
                if self._can_auto_install(plugin_id, update_info):
                    success = await self._install_update(plugin_id, update_info)
                    if success:
                        installed[plugin_id] = update_info
                        self._record_update(
                            plugin_id,
                            update_info["current"],
                            update_info["latest"],
                            True,
                        )
            except Exception as e:
                self._record_update(
                    plugin_id,
                    update_info["current"],
                    update_info["latest"],
                    False,
                    str(e),
                )

        self.record_check()
        return installed

    def _apply_policy(self, updates: dict[str, dict]) -> dict[str, dict]:
        """Apply update policy to filter updates."""
        filtered = {}

        for plugin_id, info in updates.items():
            # Check if plugin is excluded
            if plugin_id in self.policy.exclude_plugins:
                continue

            # Check if source is allowed
            marketplace = info.get("marketplace", "")
            if self.policy.allowed_sources:
                if marketplace not in self.policy.allowed_sources:
                    continue

            filtered[plugin_id] = info

        return filtered

    def _can_auto_install(self, plugin_id: str, update_info: dict) -> bool:
        """Check if an update can be auto-installed."""
        if not self.policy.auto_install:
            return False

        # Only auto-install from trusted sources
        marketplace = update_info.get("marketplace", "")
        if marketplace not in self.policy.allowed_sources:
            return False

        return True

    async def _install_update(
        self,
        plugin_id: str,
        update_info: dict,
    ) -> bool:
        """Install an update for a plugin.

        Args:
            plugin_id: Plugin to update
            update_info: Update information

        Returns:
            True if successful
        """
        # Get current installation
        installation = self.manager._get_installation(plugin_id)
        if not installation:
            return False

        # Reinstall with force
        try:
            await self.manager.install_plugin(
                plugin_id,
                scope=installation.scope,
                force=True,
            )
            return True
        except Exception:
            return False

    def _record_update(
        self,
        plugin_id: str,
        old_version: str,
        new_version: str,
        success: bool,
        error_message: Optional[str] = None,
    ) -> None:
        """Record an update in history."""
        record = UpdateRecord(
            plugin_id=plugin_id,
            timestamp=datetime.now(),
            old_version=old_version,
            new_version=new_version,
            success=success,
            error_message=error_message,
        )

        # Load existing history
        history = self._load_history()

        # Add new record
        history.append(
            {
                "plugin_id": record.plugin_id,
                "timestamp": record.timestamp.isoformat(),
                "old_version": record.old_version,
                "new_version": record.new_version,
                "success": record.success,
                "error_message": record.error_message,
            }
        )

        # Keep only last 100 records
        history = history[-100:]

        # Save
        self._save_history(history)

    def _load_history(self) -> list[dict]:
        """Load update history."""
        if not self._history_file.exists():
            return []

        try:
            import json

            with open(self._history_file, "r") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return []

    def _save_history(self, history: list[dict]) -> None:
        """Save update history."""
        try:
            import json

            with open(self._history_file, "w") as f:
                json.dump(history, f, indent=2)
        except IOError:
            pass

    def get_update_history(
        self,
        plugin_id: Optional[str] = None,
        limit: int = 20,
    ) -> list[UpdateRecord]:
        """Get update history.

        Args:
            plugin_id: Filter by plugin, or all if None
            limit: Maximum number of records

        Returns:
            List of update records
        """
        history = self._load_history()

        records = []
        for item in reversed(history):  # Newest first
            if plugin_id and item.get("plugin_id") != plugin_id:
                continue

            records.append(
                UpdateRecord(
                    plugin_id=item["plugin_id"],
                    timestamp=datetime.fromisoformat(item["timestamp"]),
                    old_version=item["old_version"],
                    new_version=item["new_version"],
                    success=item["success"],
                    error_message=item.get("error_message"),
                )
            )

            if len(records) >= limit:
                break

        return records

    async def start_background_checks(self) -> None:
        """Start background update checking.

        This runs periodic checks in the background.
        """
        if self._running:
            return

        self._running = True
        self._task = asyncio.create_task(self._background_loop())

    async def stop_background_checks(self) -> None:
        """Stop background update checking."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    async def _background_loop(self) -> None:
        """Background loop for update checks."""
        while self._running:
            try:
                if self.should_check():
                    await self.check_and_update(dry_run=not self.policy.auto_install)

                # Sleep for 1 hour before checking again
                await asyncio.sleep(3600)

            except asyncio.CancelledError:
                break
            except Exception:
                # Log error but continue
                await asyncio.sleep(3600)


class MarketplaceUpdater:
    """Handles marketplace catalog updates."""

    def __init__(self, manager):
        from .manager import PluginManager

        self.manager: PluginManager = manager

    async def update_all(self) -> dict[str, bool]:
        """Update all marketplaces.

        Returns:
            Dict of marketplace_name -> success
        """
        return await self.manager.marketplace.update_all()

    async def update_marketplace(self, name: str) -> bool:
        """Update a specific marketplace.

        Args:
            name: Marketplace name

        Returns:
            True if successful
        """
        try:
            await self.manager.marketplace.update_marketplace(name)
            return True
        except Exception:
            return False

    async def check_outdated_plugins(self) -> list[dict]:
        """Check which plugins have newer versions in their marketplaces.

        Returns:
            List of outdated plugin info
        """
        outdated = []

        for installation in self.manager.config.load_installed_plugins():
            plugin_id = installation.plugin_id

            try:
                # Get current version
                manifest = self.manager._load_manifest(installation.install_path)
                current_version = manifest.version or "unknown"

                # Find in marketplace
                if "@" in plugin_id:
                    name, marketplace = plugin_id.rsplit("@", 1)
                    entry = self.manager.marketplace.find_plugin(name, marketplace)
                    if entry:
                        entry, _ = entry
                        if entry.version and entry.version != current_version:
                            outdated.append(
                                {
                                    "plugin_id": plugin_id,
                                    "current": current_version,
                                    "available": entry.version,
                                    "marketplace": marketplace,
                                }
                            )
            except Exception:
                pass

        return outdated
