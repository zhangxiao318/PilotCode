"""Tests for update checker functionality."""

import pytest
from datetime import timedelta
from unittest.mock import AsyncMock, patch

from pilotcode.services.update_checker import (
    UpdateChecker,
    UpdateCheckResult,
    UpdateInfo,
    UpdateStatus,
    get_update_checker,
    should_check_updates,
)


class TestUpdateStatus:
    """Tests for UpdateStatus enum."""

    def test_enum_values(self):
        """Test enum values."""
        assert UpdateStatus.UP_TO_DATE.value == "up_to_date"
        assert UpdateStatus.UPDATE_AVAILABLE.value == "update_available"
        assert UpdateStatus.CHECK_FAILED.value == "check_failed"


class TestVersionParsing:
    """Tests for version parsing."""

    def test_parse_simple_version(self):
        """Test parsing simple version."""
        checker = UpdateChecker("1.2.3")
        parsed = checker._parse_version("1.2.3")
        assert parsed == (1, 2, 3)

    def test_parse_version_with_v_prefix(self):
        """Test parsing version with v prefix."""
        checker = UpdateChecker("1.0.0")
        parsed = checker._parse_version("v1.2.3")
        assert parsed == (1, 2, 3)

    def test_parse_prerelease_version(self):
        """Test parsing prerelease version."""
        checker = UpdateChecker("1.0.0")
        parsed = checker._parse_version("1.2.3-alpha")
        assert parsed == (1, 2, 3)

    def test_compare_versions_equal(self):
        """Test comparing equal versions."""
        checker = UpdateChecker("1.0.0")
        assert checker._compare_versions("1.0.0", "1.0.0") == 0

    def test_compare_versions_less(self):
        """Test where v1 < v2."""
        checker = UpdateChecker("1.0.0")
        assert checker._compare_versions("1.0.0", "1.1.0") == -1

    def test_compare_versions_greater(self):
        """Test where v1 > v2."""
        checker = UpdateChecker("2.0.0")
        assert checker._compare_versions("2.0.0", "1.9.9") == 1


class TestUpdateChecker:
    """Tests for UpdateChecker."""

    def test_init_defaults(self):
        """Test initialization with defaults."""
        checker = UpdateChecker("1.0.0")

        assert checker.current_version == "1.0.0"
        assert checker.package_name is None
        assert checker.github_repo is None

    def test_init_with_pypi(self):
        """Test initialization with PyPI."""
        checker = UpdateChecker("1.0.0", package_name="pilotcode")

        assert checker.package_name == "pilotcode"

    def test_init_with_github(self):
        """Test initialization with GitHub."""
        checker = UpdateChecker("1.0.0", github_repo=("owner", "repo"))

        assert checker.github_repo == ("owner", "repo")

    @pytest.mark.asyncio
    async def test_check_no_sources(self):
        """Test check with no update sources."""
        checker = UpdateChecker("1.0.0")

        result = await checker.check_for_updates(force=True)

        assert result.status == UpdateStatus.CHECK_FAILED
        assert "Could not fetch" in result.error

    @pytest.mark.asyncio
    async def test_check_up_to_date(self):
        """Test check when up to date."""
        checker = UpdateChecker("1.0.0", package_name="test-package")

        # Mock PyPI response
        mock_response = {
            "version": "1.0.0",
            "release_notes": "Test release",
            "download_url": "https://example.com",
        }

        with patch.object(checker, "_fetch_pypi_version", new_callable=AsyncMock) as mock:
            mock.return_value = mock_response
            result = await checker.check_for_updates(force=True)

        assert result.status == UpdateStatus.UP_TO_DATE
        assert result.info is not None
        assert result.info.update_available is False

    @pytest.mark.asyncio
    async def test_check_update_available(self):
        """Test check when update is available."""
        checker = UpdateChecker("1.0.0", package_name="test-package")

        mock_response = {
            "version": "2.0.0",
            "release_notes": "New features",
            "download_url": "https://example.com",
        }

        with patch.object(checker, "_fetch_pypi_version", new_callable=AsyncMock) as mock:
            mock.return_value = mock_response
            result = await checker.check_for_updates(force=True)  # Force to avoid cache

        assert result.status == UpdateStatus.UPDATE_AVAILABLE
        assert result.info is not None
        assert result.info.update_available is True
        assert result.info.latest_version == "2.0.0"

    @pytest.mark.asyncio
    async def test_check_skipped_due_to_interval(self):
        """Test that check is skipped if checked recently."""
        checker = UpdateChecker("1.0.0")

        # Mock last check time
        checker._save_check_result(
            UpdateCheckResult(status=UpdateStatus.UP_TO_DATE, message="Test")
        )

        result = await checker.check_for_updates(force=False)

        assert result.status == UpdateStatus.CHECK_SKIPPED

    def test_determine_priority_critical(self):
        """Test priority detection for critical updates."""
        checker = UpdateChecker("1.0.0")

        info = {"release_notes": "Security fix for CVE-2024-1234"}
        priority = checker._determine_priority(-1, info)

        assert priority == "critical"

    def test_determine_priority_recommended(self):
        """Test priority detection for recommended updates."""
        checker = UpdateChecker("1.0.0")

        info = {"release_notes": "New features", "version": "2.0.0"}
        priority = checker._determine_priority(-1, info)

        assert priority == "recommended"

    def test_format_update_message_up_to_date(self):
        """Test formatting up-to-date message."""
        checker = UpdateChecker("1.0.0")

        result = UpdateCheckResult(status=UpdateStatus.UP_TO_DATE, message="Up to date (1.0.0)")

        msg = checker.format_update_message(result)
        assert "✓" in msg
        assert "1.0.0" in msg

    def test_format_update_message_update_available(self):
        """Test formatting update available message."""
        checker = UpdateChecker("1.0.0")

        result = UpdateCheckResult(
            status=UpdateStatus.UPDATE_AVAILABLE,
            info=UpdateInfo(
                current_version="1.0.0",
                latest_version="2.0.0",
                update_available=True,
                download_url="https://example.com",
            ),
            message="Update available",
        )

        msg = checker.format_update_message(result)
        assert "⬆️" in msg
        assert "2.0.0" in msg
        assert "example.com" in msg

    def test_cached_result_valid(self):
        """Test getting valid cached result."""
        checker = UpdateChecker("1.0.0")

        # Save a recent result
        checker._save_check_result(
            UpdateCheckResult(status=UpdateStatus.UP_TO_DATE, message="Test")
        )

        cached = checker.get_cached_result()

        assert cached is not None
        assert cached.status == UpdateStatus.UP_TO_DATE

    def test_cached_result_expired(self):
        """Test that expired cache returns None."""
        # Use negative interval to ensure cache is always expired
        checker = UpdateChecker("1.0.0", check_interval=timedelta(seconds=-1))

        # Save a result
        checker._save_check_result(
            UpdateCheckResult(status=UpdateStatus.UP_TO_DATE, message="Test")
        )

        cached = checker.get_cached_result()

        # Should be None because interval is negative (always expired)
        assert cached is None


class TestGlobalFunctions:
    """Tests for global functions."""

    def test_get_update_checker(self):
        """Test getting global checker."""
        checker1 = get_update_checker("1.0.0")
        checker2 = get_update_checker("1.0.0")
        assert checker1 is checker2

    def test_should_check_updates_default(self):
        """Test default update check behavior."""
        assert should_check_updates() is True

    def test_should_check_updates_disabled(self, monkeypatch):
        """Test disabling update checks."""
        monkeypatch.setenv("PILOTCODE_NO_UPDATE_CHECK", "1")
        assert should_check_updates() is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
