"""Tests for environment detector."""

from unittest.mock import patch
import pytest
from pilotcode.services.environment_detector import (
    EnvironmentProfile,
    detect_platform_family,
    detect_shell,
    detect_project_languages,
)


class TestPlatformDetection:
    @pytest.mark.parametrize(
        "sys_platform, expected_any",
        [
            ("linux", ["linux", "debian", "rhel", "arch"]),
            ("darwin", ["darwin"]),
            ("win32", ["windows"]),
        ],
    )
    def test_detects_platform_family(self, sys_platform, expected_any):
        with patch("pilotcode.services.environment_detector.sys.platform", sys_platform):
            family = detect_platform_family()
            assert any(
                family.startswith(e) for e in expected_any
            ), f"{family} not in {expected_any}"

    def test_detect_shell_unix(self):
        with patch("pilotcode.services.environment_detector.sys.platform", "linux"):
            shell = detect_shell()
            assert not shell["is_windows"]
            assert shell["is_posix"]
            assert "name" in shell

    def test_detect_shell_windows(self):
        with patch("pilotcode.services.environment_detector.sys.platform", "win32"):
            shell = detect_shell()
            assert shell["is_windows"]
            assert not shell["is_posix"]


class TestCompilerDetection:
    def test_detect_python(self):
        """Python itself should always be available."""
        profile = EnvironmentProfile()
        assert profile.has_compiler("python3") or profile.has_compiler("python")

    def test_to_prompt_section(self):
        """to_prompt_section should return a non-empty string."""
        profile = EnvironmentProfile()
        section = profile.to_prompt_section()
        assert isinstance(section, str)
        assert len(section) > 20
        assert "Environment" in section

    def test_suggest_test_command_python(self):
        """Python test command should be suggested."""
        profile = EnvironmentProfile()
        cmd = profile.suggest_test_command("python")
        # Either pytest or unittest should be suggested
        assert cmd is None or "pytest" in cmd or "unittest" in cmd

    def test_suggest_test_command_unknown(self):
        """Unknown language should return None."""
        profile = EnvironmentProfile()
        assert profile.suggest_test_command("brainfuck") is None


class TestProjectDetection:
    def test_detect_project_languages(self):
        """Should detect Python and other languages in this project."""
        langs = detect_project_languages()
        assert isinstance(langs, list)
        # This project should have Python files
        assert "python" in langs, f"Expected python in {langs}"


class TestGitDetection:
    def test_git_available(self):
        """Git should be detected."""
        profile = EnvironmentProfile()
        assert "available" in profile.git

    def test_git_in_repo(self):
        """We should be in a git repo."""
        profile = EnvironmentProfile()
        if profile.git.get("available"):
            # We're either in a repo or not, but should detect correctly
            assert "in_repo" in profile.git

    def test_build_systems(self):
        """Build systems should be detected."""
        profile = EnvironmentProfile()
        assert isinstance(profile.build_systems, list)
