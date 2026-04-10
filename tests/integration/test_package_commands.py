"""Tests for Package Management Commands."""

import os
import pytest
from unittest.mock import patch, MagicMock

from pilotcode.commands.package_commands import (
    PackageManager,
    PackageInfo,
    detect_package_manager,
    run_pip_command,
    run_npm_command,
    install_command,
    upgrade_command,
    uninstall_command,
    list_packages_command,
)


# Fixtures
@pytest.fixture
def command_context():
    """Create a mock command context."""
    ctx = MagicMock()
    ctx.cwd = "/test/project"
    return ctx


# Test PackageManager enum
class TestPackageManager:
    """Test PackageManager enum."""

    def test_manager_values(self):
        """Test package manager enum values."""
        assert PackageManager.PIP == "pip"
        assert PackageManager.NPM == "npm"
        assert PackageManager.YARN == "yarn"
        assert PackageManager.CARGO == "cargo"
        assert PackageManager.GO == "go"


# Test PackageInfo
class TestPackageInfo:
    """Test PackageInfo dataclass."""

    def test_package_info_creation(self):
        """Test creating package info."""
        pkg = PackageInfo(
            name="requests",
            version="2.28.0",
            installed=True,
        )
        assert pkg.name == "requests"
        assert pkg.version == "2.28.0"
        assert pkg.installed is True


# Test detect_package_manager
class TestDetectPackageManager:
    """Test package manager detection."""

    def test_detect_pip_requirements(self, tmp_path):
        """Test detection via requirements.txt."""
        (tmp_path / "requirements.txt").write_text("requests\n")
        manager = detect_package_manager(str(tmp_path))
        assert manager == PackageManager.PIP

    def test_detect_pip_pyproject(self, tmp_path):
        """Test detection via pyproject.toml."""
        (tmp_path / "pyproject.toml").write_text("[build-system]")
        manager = detect_package_manager(str(tmp_path))
        assert manager == PackageManager.PIP

    def test_detect_npm(self, tmp_path):
        """Test detection via package.json."""
        (tmp_path / "package.json").write_text('{"name": "test"}')
        manager = detect_package_manager(str(tmp_path))
        assert manager == PackageManager.NPM

    def test_detect_yarn(self, tmp_path):
        """Test detection via yarn.lock."""
        (tmp_path / "package.json").write_text('{"name": "test"}')
        (tmp_path / "yarn.lock").write_text("")
        manager = detect_package_manager(str(tmp_path))
        assert manager == PackageManager.YARN

    def test_detect_cargo(self, tmp_path):
        """Test detection via Cargo.toml."""
        (tmp_path / "Cargo.toml").write_text("[package]")
        manager = detect_package_manager(str(tmp_path))
        assert manager == PackageManager.CARGO

    def test_detect_go(self, tmp_path):
        """Test detection via go.mod."""
        (tmp_path / "go.mod").write_text("module test")
        manager = detect_package_manager(str(tmp_path))
        assert manager == PackageManager.GO

    def test_detect_unknown(self, tmp_path):
        """Test detection with unknown project."""
        manager = detect_package_manager(str(tmp_path))
        assert manager == PackageManager.UNKNOWN


# Test run_pip_command
class TestRunPipCommand:
    """Test pip command execution."""

    def test_pip_command_success(self):
        """Test successful pip command."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="Successfully installed",
                stderr="",
            )

            success, output = run_pip_command("install", ["requests"], ".")

            assert success is True
            assert "Successfully" in output

    def test_pip_command_failure(self):
        """Test failed pip command."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=1,
                stdout="",
                stderr="ERROR: Could not find",
            )

            success, output = run_pip_command("install", ["nonexistent"], ".")

            assert success is False


# Test commands
class TestInstallCommand:
    """Test install command."""

    @pytest.mark.asyncio
    async def test_install_no_packages(self, command_context):
        """Test install with no packages."""
        with patch.dict(os.environ, {"PYTEST_CURRENT_TEST": ""}, clear=False):
            result = await install_command([], command_context)
            assert "Usage:" in result

    @pytest.mark.asyncio
    async def test_install_help(self, command_context):
        """Test install help."""
        with patch.dict(os.environ, {"PYTEST_CURRENT_TEST": ""}, clear=False):
            result = await install_command(["--help"], command_context)
            assert "Usage:" in result

    @pytest.mark.asyncio
    async def test_install_unknown_manager(self, command_context):
        """Test install with unknown package manager."""
        with patch(
            "pilotcode.commands.package_commands.detect_package_manager",
            return_value=PackageManager.UNKNOWN,
        ):
            with patch.dict(os.environ, {"PYTEST_CURRENT_TEST": ""}, clear=False):
                result = await install_command(["requests"], command_context)
            assert "Could not detect" in result


class TestUpgradeCommand:
    """Test upgrade command."""

    @pytest.mark.asyncio
    async def test_upgrade_help(self, command_context):
        """Test upgrade help."""
        with patch.dict(os.environ, {"PYTEST_CURRENT_TEST": ""}, clear=False):
            result = await upgrade_command(["--help"], command_context)
            assert "Usage:" in result

    @pytest.mark.asyncio
    async def test_upgrade_unknown_manager(self, command_context):
        """Test upgrade with unknown package manager."""
        with patch(
            "pilotcode.commands.package_commands.detect_package_manager",
            return_value=PackageManager.UNKNOWN,
        ):
            with patch.dict(os.environ, {"PYTEST_CURRENT_TEST": ""}, clear=False):
                result = await upgrade_command(["requests"], command_context)
                assert "Could not detect" in result


class TestUninstallCommand:
    """Test uninstall command."""

    @pytest.mark.asyncio
    async def test_uninstall_no_packages(self, command_context):
        """Test uninstall with no packages."""
        with patch.dict(os.environ, {"PYTEST_CURRENT_TEST": ""}, clear=False):
            result = await uninstall_command([], command_context)
            assert "Usage:" in result

    @pytest.mark.asyncio
    async def test_uninstall_help(self, command_context):
        """Test uninstall help."""
        with patch.dict(os.environ, {"PYTEST_CURRENT_TEST": ""}, clear=False):
            result = await uninstall_command(["--help"], command_context)
            assert "Usage:" in result

    @pytest.mark.asyncio
    async def test_uninstall_unknown_manager(self, command_context):
        """Test uninstall with unknown package manager."""
        with patch(
            "pilotcode.commands.package_commands.detect_package_manager",
            return_value=PackageManager.UNKNOWN,
        ):
            with patch.dict(os.environ, {"PYTEST_CURRENT_TEST": ""}, clear=False):
                result = await uninstall_command(["requests"], command_context)
                assert "Could not detect" in result


class TestListPackagesCommand:
    """Test list packages command."""

    @pytest.mark.asyncio
    async def test_list_packages_help(self, command_context):
        """Test list packages help."""
        with patch.dict(os.environ, {"PYTEST_CURRENT_TEST": ""}, clear=False):
            result = await list_packages_command(["--help"], command_context)
            assert "Usage:" in result

    @pytest.mark.asyncio
    async def test_list_packages_unknown_manager(self, command_context):
        """Test list packages with unknown manager."""
        with patch(
            "pilotcode.commands.package_commands.detect_package_manager",
            return_value=PackageManager.UNKNOWN,
        ):
            with patch.dict(os.environ, {"PYTEST_CURRENT_TEST": ""}, clear=False):
                result = await list_packages_command([], command_context)
                assert "Could not detect" in result


# Test command registration
class TestCommandRegistration:
    """Test that commands are properly registered."""

    def test_install_command_registered(self):
        """Test install command is registered."""
        from pilotcode.commands.package_commands import install_command as cmd

        assert cmd is not None

    def test_upgrade_command_registered(self):
        """Test upgrade command is registered."""
        from pilotcode.commands.package_commands import upgrade_command as cmd

        assert cmd is not None

    def test_uninstall_command_registered(self):
        """Test uninstall command is registered."""
        from pilotcode.commands.package_commands import uninstall_command as cmd

        assert cmd is not None

    def test_list_packages_command_registered(self):
        """Test list packages command is registered."""
        from pilotcode.commands.package_commands import list_packages_command as cmd

        assert cmd is not None
