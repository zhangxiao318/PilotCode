"""Automatic update checking service.

Following Claude Code's approach of checking for updates on startup
and prompting users to update when a new version is available.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any

import aiohttp


class UpdateStatus(Enum):
    """Status of update check."""

    UP_TO_DATE = "up_to_date"
    UPDATE_AVAILABLE = "update_available"
    CHECK_FAILED = "check_failed"
    CHECK_SKIPPED = "check_skipped"


@dataclass
class UpdateInfo:
    """Information about available update."""

    current_version: str
    latest_version: str
    update_available: bool
    release_notes: str | None = None
    download_url: str | None = None
    release_date: str | None = None
    priority: str = "normal"  # normal, recommended, critical


@dataclass
class UpdateCheckResult:
    """Result of update check."""

    status: UpdateStatus
    info: UpdateInfo | None = None
    message: str = ""
    error: str | None = None
    next_check_time: datetime | None = None


class UpdateChecker:
    """Checks for available updates.

    Supports multiple sources:
    - PyPI (for pip installations)
    - GitHub Releases (for standalone installations)
    - Custom update server
    """

    # Default check interval (24 hours)
    DEFAULT_CHECK_INTERVAL = timedelta(hours=24)

    # PyPI API endpoint
    PYPI_URL = "https://pypi.org/pypi/{package}/json"

    # GitHub API endpoint
    GITHUB_API_URL = "https://api.github.com/repos/{owner}/{repo}/releases/latest"

    def __init__(
        self,
        current_version: str,
        package_name: str | None = None,
        github_repo: tuple[str, str] | None = None,
        check_interval: timedelta | None = None,
        cache_dir: Path | None = None,
    ):
        """Initialize update checker.

        Args:
            current_version: Current installed version
            package_name: PyPI package name (if using PyPI)
            github_repo: (owner, repo) tuple (if using GitHub releases)
            check_interval: How often to check for updates
            cache_dir: Directory for caching check results
        """
        self.current_version = current_version
        self.package_name = package_name
        self.github_repo = github_repo
        self.check_interval = check_interval or self.DEFAULT_CHECK_INTERVAL

        # Cache for check results
        if cache_dir is None:
            from ..utils.paths import get_cache_dir

            cache_dir = get_cache_dir()
        self._cache_dir = cache_dir
        self._cache_file = self._cache_dir / "update_check.json"

        # Ensure cache directory exists
        self._cache_dir.mkdir(parents=True, exist_ok=True)

    def _parse_version(self, version: str) -> tuple[int, ...]:
        """Parse version string to comparable tuple.

        Supports formats like:
        - "1.2.3"
        - "1.2.3-alpha"
        - "v1.2.3"
        """
        # Remove 'v' prefix
        version = version.lstrip("vV")

        # Split by pre-release markers
        for marker in ["-", "+", "a", "b", "rc"]:
            if marker in version:
                version = version.split(marker)[0]
                break

        try:
            return tuple(int(x) for x in version.split(".") if x.isdigit())
        except ValueError:
            return (0, 0, 0)

    def _compare_versions(self, v1: str, v2: str) -> int:
        """Compare two version strings.

        Returns:
            -1 if v1 < v2
             0 if v1 == v2
             1 if v1 > v2
        """
        parsed1 = self._parse_version(v1)
        parsed2 = self._parse_version(v2)

        # Pad shorter version
        max_len = max(len(parsed1), len(parsed2))
        parsed1 = parsed1 + (0,) * (max_len - len(parsed1))
        parsed2 = parsed2 + (0,) * (max_len - len(parsed2))

        if parsed1 < parsed2:
            return -1
        elif parsed1 > parsed2:
            return 1
        else:
            return 0

    async def _fetch_pypi_version(self) -> dict[str, Any] | None:
        """Fetch latest version info from PyPI."""
        if not self.package_name:
            return None

        url = self.PYPI_URL.format(package=self.package_name)

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        return {
                            "version": data["info"]["version"],
                            "release_notes": data["info"].get("summary", ""),
                            "download_url": f"https://pypi.org/project/{self.package_name}/",
                            "release_date": (
                                data["urls"][0].get("upload_time_iso_8601")
                                if data.get("urls")
                                else None
                            ),
                        }
        except Exception:
            pass

        return None

    async def _fetch_github_version(self) -> dict[str, Any] | None:
        """Fetch latest version from GitHub releases."""
        if not self.github_repo:
            return None

        owner, repo = self.github_repo
        url = self.GITHUB_API_URL.format(owner=owner, repo=repo)

        try:
            async with aiohttp.ClientSession() as session:
                headers = {"Accept": "application/vnd.github.v3+json"}
                async with session.get(
                    url, headers=headers, timeout=aiohttp.ClientTimeout(total=10)
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        return {
                            "version": data["tag_name"],
                            "release_notes": data.get("body", "")[:1000],
                            "download_url": data.get("html_url", ""),
                            "release_date": data.get("published_at", ""),
                        }
        except Exception:
            pass

        return None

    async def check_for_updates(self, force: bool = False) -> UpdateCheckResult:
        """Check for available updates.

        Args:
            force: Force check even if recently checked

        Returns:
            UpdateCheckResult with status and info
        """
        # Check if we should skip (recently checked)
        if not force:
            last_check = self._get_last_check_time()
            if last_check and datetime.now() - last_check < self.check_interval:
                return UpdateCheckResult(
                    status=UpdateStatus.CHECK_SKIPPED,
                    message="Update check skipped (checked recently)",
                    next_check_time=last_check + self.check_interval,
                )

        # Try PyPI first, then GitHub
        latest_info = None

        if self.package_name:
            latest_info = await self._fetch_pypi_version()

        if not latest_info and self.github_repo:
            latest_info = await self._fetch_github_version()

        if not latest_info:
            return UpdateCheckResult(
                status=UpdateStatus.CHECK_FAILED,
                message="Failed to check for updates",
                error="Could not fetch version information from any source",
            )

        latest_version = latest_info["version"]
        comparison = self._compare_versions(self.current_version, latest_version)

        # Determine update availability
        if comparison < 0:
            status = UpdateStatus.UPDATE_AVAILABLE
            message = f"Update available: {self.current_version} → {latest_version}"
        elif comparison > 0:
            status = UpdateStatus.UP_TO_DATE
            message = f"Running development version ({self.current_version})"
        else:
            status = UpdateStatus.UP_TO_DATE
            message = f"Up to date ({self.current_version})"

        info = UpdateInfo(
            current_version=self.current_version,
            latest_version=latest_version,
            update_available=comparison < 0,
            release_notes=latest_info.get("release_notes"),
            download_url=latest_info.get("download_url"),
            release_date=latest_info.get("release_date"),
            priority=self._determine_priority(comparison, latest_info),
        )

        result = UpdateCheckResult(
            status=status,
            info=info,
            message=message,
            next_check_time=datetime.now() + self.check_interval,
        )

        # Cache result
        self._save_check_result(result)

        return result

    def _determine_priority(self, comparison: int, info: dict[str, Any]) -> str:
        """Determine update priority."""
        if comparison >= 0:
            return "none"

        # Check for critical keywords in release notes
        notes = (info.get("release_notes") or "").lower()
        critical_keywords = ["security", "critical", "cve", "vulnerability", "fix"]

        if any(kw in notes for kw in critical_keywords):
            return "critical"

        # Check version gap
        current = self._parse_version(self.current_version)
        latest = self._parse_version(info.get("version", "0.0.0"))

        if len(current) >= 1 and len(latest) >= 1:
            if latest[0] > current[0]:  # Major version bump
                return "recommended"

        return "normal"

    def _get_last_check_time(self) -> datetime | None:
        """Get timestamp of last check."""
        try:
            if self._cache_file.exists():
                with open(self._cache_file, "r") as f:
                    data = json.load(f)
                    return datetime.fromisoformat(data.get("timestamp", ""))
        except Exception:
            pass
        return None

    def _save_check_result(self, result: UpdateCheckResult) -> None:
        """Save check result to cache."""
        try:
            data = {
                "timestamp": datetime.now().isoformat(),
                "status": result.status.value,
                "message": result.message,
                "current_version": self.current_version,
            }
            if result.info:
                data["latest_version"] = result.info.latest_version
                data["update_available"] = result.info.update_available

            with open(self._cache_file, "w") as f:
                json.dump(data, f, indent=2)
        except Exception:
            pass

    def get_cached_result(self) -> UpdateCheckResult | None:
        """Get cached check result."""
        try:
            if not self._cache_file.exists():
                return None

            with open(self._cache_file, "r") as f:
                data = json.load(f)

            # Check if cache is still valid
            timestamp = datetime.fromisoformat(data.get("timestamp", ""))
            if datetime.now() - timestamp > self.check_interval:
                return None

            return UpdateCheckResult(
                status=UpdateStatus(data.get("status", "check_failed")),
                message=data.get("message", ""),
                info=(
                    UpdateInfo(
                        current_version=data.get("current_version", self.current_version),
                        latest_version=data.get("latest_version", "unknown"),
                        update_available=data.get("update_available", False),
                    )
                    if data.get("latest_version")
                    else None
                ),
                next_check_time=timestamp + self.check_interval,
            )
        except Exception:
            return None

    def format_update_message(self, result: UpdateCheckResult) -> str:
        """Format update check result for display."""
        if result.status == UpdateStatus.UP_TO_DATE:
            return f"✓ {result.message}"

        if result.status == UpdateStatus.UPDATE_AVAILABLE and result.info:
            lines = [
                "⬆️  Update available!",
                f"   Current: {result.info.current_version}",
                f"   Latest:  {result.info.latest_version}",
            ]

            if result.info.priority == "critical":
                lines.insert(1, "   ⚠️  This is a critical security update!")
            elif result.info.priority == "recommended":
                lines.append("   💡 This update is recommended")

            if result.info.download_url:
                lines.append(f"   Update: {result.info.download_url}")

            if result.info.release_notes:
                notes = result.info.release_notes[:200]
                if len(result.info.release_notes) > 200:
                    notes += "..."
                lines.append(f"   Notes: {notes}")

            return "\n".join(lines)

        if result.status == UpdateStatus.CHECK_FAILED:
            return f"⚠️  {result.message}"

        return result.message


# Global checker instance
_update_checker: UpdateChecker | None = None


def get_update_checker(current_version: str | None = None) -> UpdateChecker:
    """Get global update checker."""
    global _update_checker
    if _update_checker is None:
        if current_version is None:
            # Try to get from version module
            try:
                from ..version import __version__

                current_version = __version__
            except ImportError:
                current_version = "0.0.0"

        _update_checker = UpdateChecker(
            current_version=current_version,
            package_name="pilotcode",
            github_repo=("yourusername", "pilotcode"),  # Update with actual repo
        )
    return _update_checker


async def check_for_updates(
    current_version: str | None = None, force: bool = False
) -> UpdateCheckResult:
    """Convenience function to check for updates."""
    checker = get_update_checker(current_version)
    return await checker.check_for_updates(force=force)


def should_check_updates() -> bool:
    """Check if update check should be performed.

    Respects environment variable PILOTCODE_NO_UPDATE_CHECK.
    """
    return os.environ.get("PILOTCODE_NO_UPDATE_CHECK", "").lower() not in ("1", "true", "yes")
