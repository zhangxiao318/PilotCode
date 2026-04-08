"""Plugin sources for downloading plugins from various locations."""

from .github import GitHubSource
from .base import SourceError, DownloadResult

__all__ = ["GitHubSource", "SourceError", "DownloadResult"]
