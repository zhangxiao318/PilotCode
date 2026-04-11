"""Base class for plugin sources."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


class SourceError(Exception):
    """Error downloading from a source."""

    pass


@dataclass
class DownloadResult:
    """Result of downloading a plugin."""

    path: Path
    version: Optional[str] = None  # Git SHA or version tag
    success: bool = True
    error: Optional[str] = None


class PluginSource(ABC):
    """Base class for plugin sources."""

    @abstractmethod
    async def download(
        self, source_config: dict, target_path: Path, force: bool = False
    ) -> DownloadResult:
        """Download plugin to target path.

        Args:
            source_config: Source-specific configuration
            target_path: Where to download the plugin
            force: Whether to overwrite existing files

        Returns:
            DownloadResult with path and version info
        """
        pass

    @abstractmethod
    def can_handle(self, source_type: str) -> bool:
        """Check if this source can handle the given source type."""
        pass
