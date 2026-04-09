"""Marketplace management.

Handles discovery, caching, and downloading of plugins from marketplaces.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Optional

from .types import (
    PluginMarketplace,
    PluginMarketplaceEntry,
    MarketplaceSource,
    KnownMarketplace,
)
from .config import PluginConfig
from ..sources.github import GitHubSource
from ..sources.base import SourceError


class MarketplaceError(Exception):
    """Error related to marketplace operations."""
    pass


class MarketplaceManager:
    """Manages plugin marketplaces.
    
    Responsibilities:
    - Load and cache marketplace catalogs
    - Search for plugins in marketplaces
    - Download marketplace updates
    """
    
    # Official Anthropic marketplace
    OFFICIAL_MARKETPLACE_NAME = "claude-plugins-official"
    OFFICIAL_MARKETPLACE_SOURCE = MarketplaceSource(
        source="github",
        repo="anthropics/claude-plugins-official"
    )
    
    def __init__(self, config: Optional[PluginConfig] = None):
        self.config = config or PluginConfig()
        self._marketplaces: dict[str, PluginMarketplace] = {}
        self._github_source = GitHubSource()
    
    async def initialize(self) -> None:
        """Initialize marketplace manager and load cached marketplaces."""
        # Load known marketplaces from config
        known = self.config.load_known_marketplaces()
        
        # Load cached marketplace data
        for name in known:
            await self._load_cached_marketplace(name)
        
        # Auto-add official marketplace if not present
        if self.OFFICIAL_MARKETPLACE_NAME not in known:
            await self.add_marketplace(
                self.OFFICIAL_MARKETPLACE_NAME,
                self.OFFICIAL_MARKETPLACE_SOURCE,
                auto_update=True
            )
    
    async def add_marketplace(
        self,
        name: str,
        source: MarketplaceSource,
        auto_update: bool = True
    ) -> KnownMarketplace:
        """Add a new marketplace.
        
        Args:
            name: Marketplace name (must be unique)
            source: Source configuration
            auto_update: Whether to auto-update on startup
            
        Returns:
            The created KnownMarketplace entry
        """
        # Validate name
        if " " in name:
            raise MarketplaceError("Marketplace name cannot contain spaces")
        if "/" in name or "\\" in name:
            raise MarketplaceError("Marketplace name cannot contain path separators")
        
        # Create install location
        install_location = str(self.config.get_marketplace_cache_path(name))
        
        known_marketplace = KnownMarketplace(
            source=source,
            install_location=install_location,
            auto_update=auto_update
        )
        
        # Save to config
        known = self.config.load_known_marketplaces()
        known[name] = known_marketplace
        self.config.save_known_marketplaces(known)
        
        # Download marketplace data
        await self.update_marketplace(name)
        
        return known_marketplace
    
    async def remove_marketplace(self, name: str) -> bool:
        """Remove a marketplace.
        
        Returns:
            True if removed, False if not found
        """
        known = self.config.load_known_marketplaces()
        if name not in known:
            return False
        
        # Remove from config
        del known[name]
        self.config.save_known_marketplaces(known)
        
        # Remove cached data
        cache_path = self.config.get_marketplace_cache_path(name)
        if cache_path.exists():
            shutil.rmtree(cache_path)
        
        # Remove from memory
        if name in self._marketplaces:
            del self._marketplaces[name]
        
        return True
    
    async def update_marketplace(self, name: str) -> PluginMarketplace:
        """Update marketplace data from source.
        
        Args:
            name: Marketplace name
            
        Returns:
            Updated marketplace data
        """
        known = self.config.load_known_marketplaces()
        if name not in known:
            raise MarketplaceError(f"Unknown marketplace: {name}")
        
        marketplace_config = known[name]
        source = marketplace_config.source
        
        # Download based on source type
        if source.source in ("github", "git"):
            await self._update_from_git(name, source, marketplace_config)
        elif source.source == "url":
            await self._update_from_url(name, source, marketplace_config)
        elif source.source == "file":
            await self._update_from_file(name, source, marketplace_config)
        elif source.source == "directory":
            await self._update_from_directory(name, source, marketplace_config)
        else:
            raise MarketplaceError(f"Unsupported source type: {source.source}")
        
        # Reload from cache
        return await self._load_cached_marketplace(name)
    
    async def _update_from_git(
        self,
        name: str,
        source: MarketplaceSource,
        config: KnownMarketplace
    ) -> None:
        """Update marketplace from git source."""
        target_path = Path(config.install_location)
        
        try:
            result = await self._github_source.download(
                source.model_dump(exclude_none=True),
                target_path,
                force=True
            )
            
            if not result.success:
                raise MarketplaceError(f"Failed to download: {result.error}")
            
            # Update last_updated timestamp
            from datetime import datetime
            known = self.config.load_known_marketplaces()
            if name in known:
                known[name].last_updated = datetime.utcnow().isoformat()
                self.config.save_known_marketplaces(known)
                
        except SourceError as e:
            raise MarketplaceError(f"Failed to update marketplace: {e}")
    
    async def _update_from_url(
        self,
        name: str,
        source: MarketplaceSource,
        config: KnownMarketplace
    ) -> None:
        """Update marketplace from URL."""
        import aiohttp
        
        if not source.url:
            raise MarketplaceError("URL source requires 'url' field")
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(source.url, timeout=30) as response:
                    if response.status != 200:
                        raise MarketplaceError(f"HTTP {response.status}")
                    
                    data = await response.json()
                    
                    # Save to cache
                    target_path = Path(config.install_location)
                    target_path.mkdir(parents=True, exist_ok=True)
                    
                    marketplace_file = target_path / "marketplace.json"
                    with open(marketplace_file, "w") as f:
                        json.dump(data, f, indent=2)
                    
                    # Update timestamp
                    from datetime import datetime
                    known = self.config.load_known_marketplaces()
                    if name in known:
                        known[name].last_updated = datetime.utcnow().isoformat()
                        self.config.save_known_marketplaces(known)
                        
        except aiohttp.ClientError as e:
            raise MarketplaceError(f"Failed to fetch URL: {e}")
    
    async def _update_from_file(
        self,
        name: str,
        source: MarketplaceSource,
        config: KnownMarketplace
    ) -> None:
        """Update marketplace from local file."""
        if not source.file_path:
            raise MarketplaceError("File source requires 'path' field")
        
        source_path = Path(source.file_path)
        if not source_path.exists():
            raise MarketplaceError(f"File not found: {source_path}")
        
        # Copy to cache
        target_path = Path(config.install_location)
        target_path.mkdir(parents=True, exist_ok=True)
        
        shutil.copy2(source_path, target_path / "marketplace.json")
    
    async def _update_from_directory(
        self,
        name: str,
        source: MarketplaceSource,
        config: KnownMarketplace
    ) -> None:
        """Update marketplace from local directory."""
        if not source.file_path:
            raise MarketplaceError("Directory source requires 'path' field")
        
        source_path = Path(source.file_path)
        marketplace_file = source_path / ".claude-plugin" / "marketplace.json"
        
        if not marketplace_file.exists():
            marketplace_file = source_path / "marketplace.json"
        
        if not marketplace_file.exists():
            raise MarketplaceError(f"marketplace.json not found in {source_path}")
        
        # Copy to cache
        target_path = Path(config.install_location)
        target_path.mkdir(parents=True, exist_ok=True)
        
        shutil.copy2(marketplace_file, target_path / "marketplace.json")
    
    async def _load_cached_marketplace(self, name: str) -> Optional[PluginMarketplace]:
        """Load marketplace from cache."""
        cache_path = self.config.get_marketplace_cache_path(name)
        marketplace_file = cache_path / "marketplace.json"
        
        if not marketplace_file.exists():
            return None
        
        try:
            with open(marketplace_file, "r") as f:
                data = json.load(f)
            
            marketplace = PluginMarketplace(**data)
            self._marketplaces[name] = marketplace
            return marketplace
        except (json.JSONDecodeError, TypeError) as e:
            print(f"Warning: Failed to load marketplace {name}: {e}")
            return None
    
    def get_marketplace(self, name: str) -> Optional[PluginMarketplace]:
        """Get a loaded marketplace by name."""
        return self._marketplaces.get(name)
    
    def list_marketplaces(self) -> list[str]:
        """List all loaded marketplace names."""
        return list(self._marketplaces.keys())
    
    def find_plugin(
        self,
        plugin_name: str,
        marketplace_name: Optional[str] = None
    ) -> Optional[tuple[PluginMarketplaceEntry, str]]:
        """Find a plugin across all marketplaces or in a specific one.
        
        Returns:
            Tuple of (entry, marketplace_name) or None
        """
        if marketplace_name:
            marketplace = self._marketplaces.get(marketplace_name)
            if marketplace:
                for entry in marketplace.plugins:
                    if entry.name == plugin_name:
                        return entry, marketplace_name
            return None
        
        # Search all marketplaces
        for name, marketplace in self._marketplaces.items():
            for entry in marketplace.plugins:
                if entry.name == plugin_name:
                    return entry, name
        
        return None
    
    def search_plugins(
        self,
        query: str,
        marketplace_name: Optional[str] = None
    ) -> list[tuple[PluginMarketplaceEntry, str]]:
        """Search for plugins by query string.
        
        Returns:
            List of (entry, marketplace_name) tuples
        """
        query = query.lower()
        results = []
        
        marketplaces = (
            {marketplace_name: self._marketplaces[marketplace_name]}
            if marketplace_name and marketplace_name in self._marketplaces
            else self._marketplaces
        )
        
        for name, marketplace in marketplaces.items():
            for entry in marketplace.plugins:
                if (
                    query in entry.name.lower()
                    or query in entry.description.lower()
                    or any(query in kw.lower() for kw in entry.keywords)
                ):
                    results.append((entry, name))
        
        return results
    
    async def update_all(self) -> dict[str, bool]:
        """Update all marketplaces.
        
        Returns:
            Dict of marketplace_name -> success
        """
        known = self.config.load_known_marketplaces()
        results = {}
        
        for name in known:
            try:
                await self.update_marketplace(name)
                results[name] = True
            except Exception as e:
                print(f"Failed to update marketplace {name}: {e}")
                results[name] = False
        
        return results
