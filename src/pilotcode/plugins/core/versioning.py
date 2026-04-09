"""Version management for plugins.

Handles version detection, comparison, and update checking.
"""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from ..sources.github import GitHubSource


@dataclass
class VersionInfo:
    """Version information for a plugin."""
    version: str  # Semantic version or commit SHA
    git_sha: Optional[str] = None
    git_branch: Optional[str] = None
    git_tag: Optional[str] = None
    source_type: str = "unknown"  # git, npm, file
    last_check: Optional[str] = None
    
    def is_git_based(self) -> bool:
        """Check if this is a git-based version."""
        return self.git_sha is not None


class VersionComparator:
    """Compare version strings."""
    
    @staticmethod
    def parse_semver(version: str) -> tuple[int, int, int, str]:
        """Parse a semantic version string.
        
        Returns:
            Tuple of (major, minor, patch, prerelease)
        """
        # Remove 'v' prefix if present
        version = version.lstrip("vV")
        
        # Split by '+' (build metadata)
        version = version.split("+")[0]
        
        # Split by '-' (pre-release)
        parts = version.split("-")
        main_version = parts[0]
        prerelease = parts[1] if len(parts) > 1 else ""
        
        # Parse main version
        version_parts = main_version.split(".")
        major = int(version_parts[0]) if len(version_parts) > 0 else 0
        minor = int(version_parts[1]) if len(version_parts) > 1 else 0
        patch = int(version_parts[2]) if len(version_parts) > 2 else 0
        
        return (major, minor, patch, prerelease)
    
    @staticmethod
    def compare(v1: str, v2: str) -> int:
        """Compare two versions.
        
        Returns:
            -1 if v1 < v2, 0 if equal, 1 if v1 > v2
        """
        try:
            m1, mn1, p1, pr1 = VersionComparator.parse_semver(v1)
            m2, mn2, p2, pr2 = VersionComparator.parse_semver(v2)
        except ValueError:
            # Fallback to string comparison
            return (v1 > v2) - (v1 < v2)
        
        # Compare major, minor, patch
        for a, b in [(m1, m2), (mn1, mn2), (p1, p2)]:
            if a != b:
                return 1 if a > b else -1
        
        # Handle pre-release versions
        # A version without pre-release is greater than one with
        if not pr1 and pr2:
            return 1
        if pr1 and not pr2:
            return -1
        if pr1 and pr2:
            # Compare pre-release strings
            if pr1 != pr2:
                return 1 if pr1 > pr2 else -1
        
        return 0
    
    @staticmethod
    def is_newer(v1: str, v2: str) -> bool:
        """Check if v1 is newer than v2."""
        return VersionComparator.compare(v1, v2) > 0
    
    @staticmethod
    def is_same(v1: str, v2: str) -> bool:
        """Check if two versions are equal."""
        return VersionComparator.compare(v1, v2) == 0


class VersionManager:
    """Manages plugin versions.
    
    Handles:
    - Detecting current version from various sources
    - Checking for updates
    - Recording version history
    """
    
    def __init__(self):
        self.comparator = VersionComparator()
        self._github_source = GitHubSource()
    
    def detect_version(self, plugin_path: Path, source_type: str = "git") -> VersionInfo:
        """Detect version information from a plugin directory.
        
        Args:
            plugin_path: Path to the plugin directory
            source_type: Type of source (git, npm, file)
            
        Returns:
            VersionInfo with detected version
        """
        info = VersionInfo(version="unknown", source_type=source_type)
        
        if source_type == "git":
            # Try to get git info
            git_info = self._get_git_info(plugin_path)
            if git_info:
                info.git_sha = git_info.get("sha")
                info.git_branch = git_info.get("branch")
                info.git_tag = git_info.get("tag")
                
                # Use tag as version if available
                if info.git_tag:
                    info.version = info.git_tag.lstrip("v")
                elif info.git_sha:
                    info.version = info.git_sha[:12]
        
        # Try to read from plugin.json
        manifest_file = plugin_path / "plugin.json"
        if manifest_file.exists():
            import json
            try:
                with open(manifest_file, "r") as f:
                    manifest = json.load(f)
                manifest_version = manifest.get("version")
                if manifest_version:
                    info.version = manifest_version
            except (json.JSONDecodeError, IOError):
                pass
        
        return info
    
    def _get_git_info(self, path: Path) -> Optional[dict]:
        """Get git information from a directory."""
        try:
            # Check if it's a git repo
            result = subprocess.run(
                ["git", "-C", str(path), "rev-parse", "--git-dir"],
                capture_output=True,
                text=True,
            )
            if result.returncode != 0:
                return None
            
            info = {}
            
            # Get SHA
            result = subprocess.run(
                ["git", "-C", str(path), "rev-parse", "HEAD"],
                capture_output=True,
                text=True,
            )
            if result.returncode == 0:
                info["sha"] = result.stdout.strip()
            
            # Get branch
            result = subprocess.run(
                ["git", "-C", str(path), "rev-parse", "--abbrev-ref", "HEAD"],
                capture_output=True,
                text=True,
            )
            if result.returncode == 0:
                info["branch"] = result.stdout.strip()
            
            # Get tag (if on a tag)
            result = subprocess.run(
                ["git", "-C", str(path), "describe", "--tags", "--exact-match"],
                capture_output=True,
                text=True,
            )
            if result.returncode == 0:
                info["tag"] = result.stdout.strip()
            
            return info
            
        except (subprocess.SubprocessError, FileNotFoundError):
            return None
    
    async def check_for_update(
        self,
        plugin_id: str,
        current_version: str,
        source_config: dict,
    ) -> Optional[VersionInfo]:
        """Check if an update is available.
        
        Args:
            plugin_id: Plugin identifier
            current_version: Current installed version
            source_config: Source configuration for the plugin
            
        Returns:
            VersionInfo for the latest version if different, None otherwise
        """
        source_type = source_config.get("source")
        
        if source_type == "github":
            return await self._check_github_update(
                source_config.get("repo"),
                source_config.get("ref"),
                current_version,
            )
        elif source_type == "git":
            return await self._check_git_update(
                source_config.get("url"),
                source_config.get("ref"),
                current_version,
            )
        elif source_type == "npm":
            return await self._check_npm_update(
                source_config.get("package"),
                current_version,
            )
        
        return None
    
    async def _check_github_update(
        self,
        repo: str,
        ref: Optional[str],
        current_version: str,
    ) -> Optional[VersionInfo]:
        """Check GitHub for updates."""
        try:
            # Use GitHub API to get latest commit
            latest_sha = await self._github_source.get_latest_commit(repo, ref)
            
            if not latest_sha:
                return None
            
            # Compare SHAs
            current_short = current_version[:12] if len(current_version) >= 40 else current_version
            latest_short = latest_sha[:12]
            
            if current_short == latest_short:
                return None  # Up to date
            
            # Check if it's a semver version
            try:
                # Try to get latest release/tag
                import aiohttp
                async with aiohttp.ClientSession() as session:
                    url = f"https://api.github.com/repos/{repo}/releases/latest"
                    async with session.get(url, timeout=10) as response:
                        if response.status == 200:
                            data = await response.json()
                            tag_name = data.get("tag_name", "")
                            if tag_name:
                                return VersionInfo(
                                    version=tag_name.lstrip("v"),
                                    git_sha=latest_sha,
                                    git_tag=tag_name,
                                    source_type="git",
                                )
            except Exception:
                pass
            
            # Return SHA-based version
            return VersionInfo(
                version=latest_sha[:12],
                git_sha=latest_sha,
                source_type="git",
            )
            
        except Exception:
            return None
    
    async def _check_git_update(
        self,
        url: str,
        ref: Optional[str],
        current_version: str,
    ) -> Optional[VersionInfo]:
        """Check generic git repo for updates."""
        # For generic git, we'd need to fetch the remote
        # This is a simplified version
        return None
    
    async def _check_npm_update(
        self,
        package: str,
        current_version: str,
    ) -> Optional[VersionInfo]:
        """Check NPM registry for updates."""
        try:
            import aiohttp
            async with aiohttp.ClientSession() as session:
                url = f"https://registry.npmjs.org/{package}/latest"
                async with session.get(url, timeout=10) as response:
                    if response.status == 200:
                        data = await response.json()
                        latest_version = data.get("version", "")
                        
                        if self.comparator.is_newer(latest_version, current_version):
                            return VersionInfo(
                                version=latest_version,
                                source_type="npm",
                            )
        except Exception:
            pass
        
        return None
    
    def compare_versions(self, v1: str, v2: str) -> int:
        """Compare two versions.
        
        Returns:
            -1 if v1 < v2, 0 if equal, 1 if v1 > v2
        """
        return self.comparator.compare(v1, v2)
    
    def is_update_available(self, current: str, latest: str) -> bool:
        """Check if an update is available."""
        return self.comparator.is_newer(latest, current)
    
    def format_version(self, version: str, max_length: int = 12) -> str:
        """Format a version string for display.
        
        Args:
            version: Version string (could be long SHA)
            max_length: Maximum length to display
            
        Returns:
            Formatted version string
        """
        if len(version) > max_length:
            # It's probably a SHA
            return version[:max_length]
        return version


class UpdateChecker:
    """Checks for plugin updates."""
    
    def __init__(self, manager):
        from .manager import PluginManager
        self.manager: PluginManager = manager
        self.version_manager = VersionManager()
    
    async def check_all(self) -> dict[str, dict]:
        """Check all installed plugins for updates.
        
        Returns:
            Dict mapping plugin_id to update info
        """
        updates = {}
        
        for installation in self.manager.config.load_installed_plugins():
            plugin_id = installation.plugin_id
            
            try:
                # Find the marketplace entry
                result = self._find_marketplace_entry(plugin_id)
                if not result:
                    continue
                
                entry, marketplace = result
                
                # Get current version
                manifest = self.manager._load_manifest(installation.install_path)
                current_version = manifest.version or "unknown"
                
                # Get source config from entry
                source_config = self._get_source_config(entry)
                
                # Check for update
                latest = await self.version_manager.check_for_update(
                    plugin_id,
                    current_version,
                    source_config,
                )
                
                if latest:
                    updates[plugin_id] = {
                        "current": current_version,
                        "latest": latest.version,
                        "git_sha": latest.git_sha,
                        "marketplace": marketplace,
                    }
                    
            except Exception as e:
                # Log error but continue checking other plugins
                print(f"Error checking updates for {plugin_id}: {e}")
        
        return updates
    
    def _find_marketplace_entry(self, plugin_id: str):
        """Find the marketplace entry for a plugin."""
        if "@" in plugin_id:
            name, marketplace = plugin_id.rsplit("@", 1)
        else:
            name = plugin_id
            marketplace = None
        
        if marketplace:
            mp = self.manager.marketplace.get_marketplace(marketplace)
            if mp:
                for entry in mp.plugins:
                    if entry.name == name:
                        return entry, marketplace
        
        # Search all marketplaces
        for mp_name in self.manager.marketplace.list_marketplaces():
            mp = self.manager.marketplace.get_marketplace(mp_name)
            if mp:
                for entry in mp.plugins:
                    if entry.name == name:
                        return entry, mp_name
        
        return None
    
    def _get_source_config(self, entry) -> dict:
        """Get source config from marketplace entry."""
        source = entry.source
        
        if isinstance(source, str):
            if "/" in source and not source.startswith(("http", "/", ".")):
                return {"source": "github", "repo": source}
            else:
                return {"source": "directory", "path": source}
        else:
            return source if isinstance(source, dict) else {}
