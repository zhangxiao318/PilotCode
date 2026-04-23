"""Tests for Testing Commands."""

import os
import pytest
from unittest.mock import patch, MagicMock

from pilotcode.commands.testing_commands import (
    TestFramework,
    TestResult,
    detect_test_framework,
    parse_pytest_output,
    parse_coverage_output,
    test_command as run_test_cmd,
    coverage_command as run_coverage_cmd,
    benchmark_command as run_benchmark_cmd,
)


# Fixtures
@pytest.fixture
def command_context():
    """Create a mock command context."""
    ctx = MagicMock()
    ctx.cwd = "/test/project"
    return ctx


@pytest.fixture
def mock_subprocess_run():
    """Mock subprocess.run."""
    with patch("subprocess.run") as mock:
        yield mock


# Test TestFramework enum
class TestFrameworkEnum:
    """Test TestFramework enum."""

    def test_framework_values(self):
        """Test framework enum values."""
        assert TestFramework.PYTEST == "pytest"
        assert TestFramework.JEST == "jest"
        assert TestFramework.CARGO == "cargo"
        assert TestFramework.GO == "go"
        assert TestFramework.UNKNOWN == "unknown"


# Test TestResult dataclass
class TestResultData:
    """Test TestResult dataclass."""

    def test_result_creation(self):
        """Test creating TestResult."""
        result = TestResult(
            framework=TestFramework.PYTEST,
            total=10,
            passed=8,
            failed=2,
        )
        assert result.framework == TestFramework.PYTEST
        assert result.total == 10
        assert result.passed == 8
        assert result.failed == 2

    def test_success_rate(self):
        """Test success rate calculation."""
        result = TestResult(
            framework=TestFramework.PYTEST,
            total=10,
            passed=8,
        )
        assert result.success_rate == 80.0

    def test_success_rate_zero(self):
        """Test success rate with zero tests."""
        result = TestResult(framework=TestFramework.PYTEST)
        assert result.success_rate == 0.0

    def test_is_success_true(self):
        """Test is_success when all pass."""
        result = TestResult(
            framework=TestFramework.PYTEST,
            total=5,
            passed=5,
            failed=0,
        )
        assert result.is_success is True

    def test_is_success_false(self):
        """Test is_success when failures exist."""
        result = TestResult(
            framework=TestFramework.PYTEST,
            total=5,
            passed=4,
            failed=1,
        )
        assert result.is_success is False

    def test_is_success_no_tests(self):
        """Test is_success with no tests."""
        result = TestResult(framework=TestFramework.PYTEST)
        assert result.is_success is False


# Test detect_test_framework
class TestFrameworkDetection:
    """Test framework detection."""

    def test_detect_pytest_ini(self, tmp_path):
        """Test detection via pytest.ini."""
        (tmp_path / "pytest.ini").write_text("[pytest]")
        framework = detect_test_framework(str(tmp_path))
        assert framework == TestFramework.PYTEST

    def test_detect_pyproject_toml(self, tmp_path):
        """Test detection via pyproject.toml."""
        (tmp_path / "pyproject.toml").write_text("[tool.pytest.ini_options]")
        framework = detect_test_framework(str(tmp_path))
        assert framework == TestFramework.PYTEST

    def test_detect_test_files(self, tmp_path):
        """Test detection via test files."""
        (tmp_path / "test_something.py").write_text("")
        framework = detect_test_framework(str(tmp_path))
        assert framework == TestFramework.PYTEST

    def test_detect_package_json(self, tmp_path):
        """Test detection via package.json."""
        (tmp_path / "package.json").write_text('{"dependencies": {"jest": "^27.0.0"}}')
        framework = detect_test_framework(str(tmp_path))
        assert framework == TestFramework.JEST

    def test_detect_cargo(self, tmp_path):
        """Test detection via Cargo.toml."""
        (tmp_path / "Cargo.toml").write_text("[package]")
        framework = detect_test_framework(str(tmp_path))
        assert framework == TestFramework.CARGO

    def test_detect_go(self, tmp_path):
        """Test detection via go.mod."""
        (tmp_path / "go.mod").write_text("module test")
        framework = detect_test_framework(str(tmp_path))
        assert framework == TestFramework.GO

    def test_detect_unknown(self, tmp_path):
        """Test detection with unknown project."""
        framework = detect_test_framework(str(tmp_path))
        assert framework == TestFramework.UNKNOWN


# Test parse_pytest_output
class TestPytestOutputParsing:
    """Test pytest output parsing."""

    def test_parse_all_passed(self):
        """Test parsing all passed output."""
        stdout = "5 passed in 0.45s"
        result = parse_pytest_output(stdout, "", 0.45)

        assert result.total == 5
        assert result.passed == 5
        assert result.failed == 0
        assert result.skipped == 0

    def test_parse_with_failures(self):
        """Test parsing with failures."""
        stdout = "3 passed, 2 failed in 1.23s"
        result = parse_pytest_output(stdout, "", 1.23)

        assert result.total == 5
        assert result.passed == 3
        assert result.failed == 2

    def test_parse_with_skipped(self):
        """Test parsing with skipped tests."""
        stdout = "4 passed, 1 failed, 2 skipped in 0.89s"
        result = parse_pytest_output(stdout, "", 0.89)

        assert result.total == 7
        assert result.passed == 4
        assert result.failed == 1
        assert result.skipped == 2

    def test_parse_with_errors(self):
        """Test parsing with errors."""
        stdout = "2 passed, 1 failed, 1 error in 0.56s"
        result = parse_pytest_output(stdout, "", 0.56)

        assert result.total == 4
        assert result.passed == 2
        assert result.failed == 1
        assert result.errors == 1


# Test parse_coverage_output
class TestCoverageParsing:
    """Test coverage output parsing."""

    def test_parse_total_coverage(self):
        """Test parsing total coverage."""
        stdout = "TOTAL 1234 567 54%"
        result = parse_coverage_output(stdout, "")

        assert result["total_coverage"] == 54

    def test_parse_file_coverage(self):
        """Test parsing file coverage."""
        stdout = """src/module.py 100 20 80%
src/utils.py 50 10 80%
TOTAL 150 30 80%"""
        result = parse_coverage_output(stdout, "")

        assert len(result["files"]) == 2
        assert result["files"][0]["file"] == "src/module.py"
        assert result["files"][0]["coverage"] == 80


# Test commands
class TestTestExecution:
    """Test test command."""

    @pytest.mark.asyncio
    async def test_test_no_framework(self, command_context):
        """Test with unknown framework."""
        with patch(
            "pilotcode.commands.testing_commands.detect_test_framework",
            return_value=TestFramework.UNKNOWN,
        ):
            # Clear PYTEST_CURRENT_TEST to test actual command logic
            with patch.dict(os.environ, {"PYTEST_CURRENT_TEST": ""}, clear=False):
                result = await run_test_cmd([], command_context)
                assert "Could not detect" in result

    @pytest.mark.asyncio
    async def test_test_help(self, command_context):
        """Test help output."""
        with patch.dict(os.environ, {"PYTEST_CURRENT_TEST": ""}, clear=False):
            result = await run_test_cmd(["--help"], command_context)
            assert "Usage:" in result


class TestCoverageCmd:
    """Test coverage command."""

    @pytest.mark.asyncio
    async def test_coverage_non_pytest(self, command_context):
        """Test coverage with non-pytest project."""
        with patch(
            "pilotcode.commands.testing_commands.detect_test_framework",
            return_value=TestFramework.JEST,
        ):
            result = await run_coverage_cmd([], command_context)
            assert "only supported for pytest" in result

    @pytest.mark.asyncio
    async def test_coverage_help(self, command_context):
        """Test help output."""
        result = await run_coverage_cmd(["--help"], command_context)
        assert "Usage:" in result


class TestBenchmarkCmd:
    """Test benchmark command."""

    @pytest.mark.asyncio
    async def test_benchmark_non_pytest(self, command_context):
        """Test benchmark with non-pytest project."""
        with patch(
            "pilotcode.commands.testing_commands.detect_test_framework",
            return_value=TestFramework.JEST,
        ):
            result = await run_benchmark_cmd([], command_context)
            assert "only supported for pytest" in result

    @pytest.mark.asyncio
    async def test_benchmark_help(self, command_context):
        """Test help output."""
        result = await run_benchmark_cmd(["--help"], command_context)
        assert "Usage:" in result


# Test command registration
class TestCommandRegistration:
    """Test that commands are properly registered."""

    def test_test_command_registered(self):
        """Test test command is registered."""
        from pilotcode.commands.testing_commands import test_command as cmd

        assert cmd is not None

    def test_coverage_command_registered(self):
        """Test coverage command is registered."""
        from pilotcode.commands.testing_commands import coverage_command as cmd

        assert cmd is not None

    def test_benchmark_command_registered(self):
        """Test benchmark command is registered."""
        from pilotcode.commands.testing_commands import benchmark_command as cmd

        assert cmd is not None
