"""Testing Commands - Run tests and show coverage.

This module provides testing commands:
- /test - Run project tests
- /coverage - Show test coverage
- /benchmark - Run benchmarks (if available)

Supports multiple test frameworks:
- pytest (Python)
- unittest (Python)
- jest (JavaScript/TypeScript)
- cargo test (Rust)
- go test (Go)
"""

from __future__ import annotations

import asyncio
import json
import os
import re
from typing import Optional, Any
from dataclasses import dataclass
from enum import Enum

from rich.console import Console
from rich.table import Table
from rich.panel import Panel

from pilotcode.types.command import CommandContext
from pilotcode.commands.base import CommandHandler, register_command
from pilotcode.commands.async_runner import run_command_streaming

console = Console()


class TestFramework(str, Enum):
    """Supported test frameworks."""

    PYTEST = "pytest"
    UNITTEST = "unittest"
    JEST = "jest"
    CARGO = "cargo"
    GO = "go"
    UNKNOWN = "unknown"

    __test__ = False


@dataclass
class TestResult:
    """Test execution result."""

    __test__ = False

    framework: TestFramework
    total: int = 0
    passed: int = 0
    failed: int = 0
    skipped: int = 0
    errors: int = 0
    duration: float = 0.0
    output: str = ""
    coverage: Optional[float] = None
    failed_tests: list[dict[str, Any]] = None

    def __post_init__(self):
        if self.failed_tests is None:
            self.failed_tests = []

    @property
    def success_rate(self) -> float:
        if self.total == 0:
            return 0.0
        return (self.passed / self.total) * 100

    @property
    def is_success(self) -> bool:
        return self.failed == 0 and self.errors == 0 and self.total > 0


def detect_test_framework(cwd: str) -> TestFramework:
    """Detect test framework based on project files."""
    if os.path.exists(os.path.join(cwd, "pytest.ini")):
        return TestFramework.PYTEST
    if os.path.exists(os.path.join(cwd, "pyproject.toml")):
        with open(os.path.join(cwd, "pyproject.toml"), "r") as f:
            content = f.read()
            if "[tool.pytest" in content:
                return TestFramework.PYTEST
    if any(
        f.startswith("test_") and f.endswith(".py")
        for f in os.listdir(cwd)
        if os.path.isfile(os.path.join(cwd, f))
    ):
        return TestFramework.PYTEST

    if os.path.exists(os.path.join(cwd, "package.json")):
        with open(os.path.join(cwd, "package.json"), "r") as f:
            content = f.read()
            if "jest" in content:
                return TestFramework.JEST

    if os.path.exists(os.path.join(cwd, "Cargo.toml")):
        return TestFramework.CARGO

    if os.path.exists(os.path.join(cwd, "go.mod")):
        return TestFramework.GO

    if any(f.endswith(".py") for f in os.listdir(cwd) if os.path.isfile(os.path.join(cwd, f))):
        return TestFramework.PYTEST

    return TestFramework.UNKNOWN


async def run_pytest_tests(
    cwd: str,
    test_path: Optional[str] = None,
    verbose: bool = False,
    markers: Optional[list[str]] = None,
    max_failures: Optional[int] = None,
) -> TestResult:
    """Run pytest tests asynchronously with live output."""
    cmd = ["python", "-m", "pytest"]
    if verbose:
        cmd.append("-v")
    cmd.extend(["--tb=short", "-q"])
    if markers:
        for marker in markers:
            cmd.extend(["-m", marker])
    if max_failures:
        cmd.extend(["--maxfail", str(max_failures)])
    if test_path:
        cmd.append(test_path)

    start_time = __import__("time").time()
    timeout = 30 if os.environ.get("PYTEST_CURRENT_TEST") else 300

    try:
        returncode, stdout, stderr = await run_command_streaming(
            cmd,
            cwd=cwd,
            total_timeout=timeout,
            inactivity_timeout=30,
        )
        duration = __import__("time").time() - start_time
        return parse_pytest_output(stdout, stderr, duration)
    except asyncio.CancelledError:
        raise
    except asyncio.TimeoutError:
        return TestResult(
            framework=TestFramework.PYTEST,
            errors=1,
            output="Test execution timed out",
            duration=timeout,
        )
    except Exception as e:
        return TestResult(
            framework=TestFramework.PYTEST,
            errors=1,
            output=str(e),
            duration=0.0,
        )


def parse_pytest_output(stdout: str, stderr: str, duration: float) -> TestResult:
    """Parse pytest output."""
    result = TestResult(
        framework=TestFramework.PYTEST,
        duration=duration,
        output=stdout + ("\n" + stderr if stderr else ""),
    )

    summary_pattern = (
        r"(\d+) passed(?:, (\d+) failed)?(?:, (\d+) skipped)?(?:, (\d+) error)? in ([\d.]+)s"
    )

    for line in stdout.split("\n"):
        match = re.search(summary_pattern, line)
        if match:
            result.passed = int(match.group(1))
            result.failed = int(match.group(2)) if match.group(2) else 0
            result.skipped = int(match.group(3)) if match.group(3) else 0
            result.errors = int(match.group(4)) if match.group(4) else 0
            result.total = result.passed + result.failed + result.skipped + result.errors
            break

    failed_test_pattern = r"(FAILED|ERROR) (.+?)::(.+?) - (.+)"
    for match in re.finditer(failed_test_pattern, stdout):
        result.failed_tests.append(
            {
                "status": match.group(1),
                "file": match.group(2),
                "test": match.group(3),
                "message": match.group(4),
            }
        )

    return result


async def run_coverage(
    cwd: str,
    test_path: Optional[str] = None,
    format: str = "terminal",
) -> dict[str, Any]:
    """Run tests with coverage asynchronously."""
    cmd = [
        "python",
        "-m",
        "pytest",
        "--cov=.",
        f"--cov-report={format}",
        "-q",
    ]
    if test_path:
        cmd.append(test_path)

    try:
        returncode, stdout, stderr = await run_command_streaming(
            cmd,
            cwd=cwd,
            total_timeout=300,
            inactivity_timeout=30,
        )
        return parse_coverage_output(stdout, stderr)
    except asyncio.CancelledError:
        raise
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "total_coverage": 0.0,
            "files": [],
        }


def parse_coverage_output(stdout: str, stderr: str) -> dict[str, Any]:
    """Parse coverage output."""
    result = {
        "success": True,
        "total_coverage": 0.0,
        "files": [],
        "output": stdout + ("\n" + stderr if stderr else ""),
    }

    total_pattern = r"TOTAL\s+\d+\s+\d+\s+(\d+)%"
    match = re.search(total_pattern, stdout)
    if match:
        result["total_coverage"] = int(match.group(1))

    file_pattern = r"^([^\s]+\.py)\s+(\d+)\s+(\d+)\s+(\d+)%"
    for line in stdout.split("\n"):
        match = re.match(file_pattern, line)
        if match:
            result["files"].append(
                {
                    "file": match.group(1),
                    "statements": int(match.group(2)),
                    "missing": int(match.group(3)),
                    "coverage": int(match.group(4)),
                }
            )

    return result


async def run_jest_tests(cwd: str, test_path: Optional[str] = None) -> TestResult:
    """Run Jest tests asynchronously."""
    cmd = ["npm", "test", "--", "--json", "--silent"]
    if test_path:
        cmd.extend(["--testPathPattern", test_path])

    try:
        returncode, stdout, stderr = await run_command_streaming(
            cmd,
            cwd=cwd,
            total_timeout=300,
            inactivity_timeout=30,
        )
        try:
            data = json.loads(stdout)
            return TestResult(
                framework=TestFramework.JEST,
                total=data.get("numTotalTests", 0),
                passed=data.get("numPassedTests", 0),
                failed=data.get("numFailedTests", 0),
                skipped=data.get("numPendingTests", 0),
                duration=data.get("testResults", [{}])[0].get("perfStats", {}).get("end", 0) / 1000,
                output=stdout,
            )
        except json.JSONDecodeError:
            return TestResult(
                framework=TestFramework.JEST,
                output=stdout + stderr,
            )
    except asyncio.CancelledError:
        raise
    except Exception as e:
        return TestResult(
            framework=TestFramework.JEST,
            errors=1,
            output=str(e),
        )


async def run_cargo_tests(cwd: str) -> TestResult:
    """Run Cargo tests asynchronously."""
    try:
        returncode, stdout, stderr = await run_command_streaming(
            ["cargo", "test"],
            cwd=cwd,
            total_timeout=300,
            inactivity_timeout=30,
        )
        stdout_combined = stdout + ("\n" + stderr if stderr else "")
        passed = len(re.findall(r"test \S+ \.\.\. ok", stdout_combined))
        failed = len(re.findall(r"test \S+ \.\.\. FAILED", stdout_combined))

        summary_match = re.search(
            r"test result: (\w+)\.(\d+) passed; (\d+) failed;", stdout_combined
        )
        if summary_match:
            passed = int(summary_match.group(2))
            failed = int(summary_match.group(3))

        return TestResult(
            framework=TestFramework.CARGO,
            total=passed + failed,
            passed=passed,
            failed=failed,
            output=stdout_combined,
        )
    except asyncio.CancelledError:
        raise
    except Exception as e:
        return TestResult(
            framework=TestFramework.CARGO,
            errors=1,
            output=str(e),
        )


async def run_go_tests(cwd: str, test_path: Optional[str] = None) -> TestResult:
    """Run Go tests asynchronously."""
    cmd = ["go", "test", "-v"]
    if test_path:
        cmd.append(test_path)
    else:
        cmd.append("./...")

    try:
        returncode, stdout, stderr = await run_command_streaming(
            cmd,
            cwd=cwd,
            total_timeout=300,
            inactivity_timeout=30,
        )
        stdout_combined = stdout + ("\n" + stderr if stderr else "")
        passed = len(re.findall(r"^--- PASS:", stdout_combined, re.MULTILINE))
        failed = len(re.findall(r"^--- FAIL:", stdout_combined, re.MULTILINE))

        summary_match = re.search(r"(\d+) passed, (\d+) failed", stdout_combined)
        if summary_match:
            passed = int(summary_match.group(1))
            failed = int(summary_match.group(2))

        return TestResult(
            framework=TestFramework.GO,
            total=passed + failed,
            passed=passed,
            failed=failed,
            output=stdout_combined,
        )
    except asyncio.CancelledError:
        raise
    except Exception as e:
        return TestResult(
            framework=TestFramework.GO,
            errors=1,
            output=str(e),
        )


async def test_command(args: list[str], context: CommandContext) -> str:
    """Run project tests.

    Usage: /test [path] [--verbose] [--maxfail=N]
    """
    if os.environ.get("PYTEST_CURRENT_TEST"):
        return "[dim]Skipping test command during pytest run[/dim]"

    test_path: Optional[str] = None
    verbose = False
    max_failures: Optional[int] = None

    for arg in args:
        if arg == "--verbose" or arg == "-v":
            verbose = True
        elif arg.startswith("--maxfail="):
            try:
                max_failures = int(arg.split("=")[1])
            except ValueError:
                pass
        elif arg == "--help" or arg == "-h":
            return """[bold]Test Command[/bold]

Usage: /test [path] [options]

Options:
  --verbose, -v       Show detailed output
  --maxfail=N         Stop after N failures

Examples:
  /test
  /test tests/test_specific.py
  /test --verbose
  /test --maxfail=3
"""
        elif not arg.startswith("-"):
            test_path = arg

    framework = detect_test_framework(context.cwd)
    if framework == TestFramework.UNKNOWN:
        return (
            "[yellow]Could not detect test framework. Supported: pytest, jest, cargo, go[/yellow]"
        )

    console.print(f"[cyan]Running {framework.value} tests...[/cyan]")

    if framework == TestFramework.PYTEST:
        result = await run_pytest_tests(
            context.cwd,
            test_path=test_path,
            verbose=verbose,
            max_failures=max_failures,
        )
    elif framework == TestFramework.JEST:
        result = await run_jest_tests(context.cwd, test_path)
    elif framework == TestFramework.CARGO:
        result = await run_cargo_tests(context.cwd)
    elif framework == TestFramework.GO:
        result = await run_go_tests(context.cwd, test_path)
    else:
        return f"[red]Unsupported test framework: {framework}[/red]"

    if result.total == 0 and not result.output:
        return "[yellow]No tests found[/yellow]"

    table = Table(title=f"Test Results ({framework.value})")
    table.add_column("Metric", style="cyan")
    table.add_column("Count", justify="right")
    table.add_column("Status", style="green")

    table.add_row("Total", str(result.total), "")
    table.add_row("Passed", str(result.passed), "[green]✓[/green]" if result.passed > 0 else "")
    table.add_row("Failed", str(result.failed), "[red]✗[/red]" if result.failed > 0 else "")
    table.add_row(
        "Skipped", str(result.skipped), "[yellow]⊘[/yellow]" if result.skipped > 0 else ""
    )
    table.add_row("Errors", str(result.errors), "[red]![/red]" if result.errors > 0 else "")
    table.add_row("Duration", f"{result.duration:.2f}s", "")
    table.add_row("Success Rate", f"{result.success_rate:.1f}%", "")

    console.print(table)

    if result.failed_tests:
        console.print("\n[bold red]Failed Tests:[/bold red]")
        for test in result.failed_tests:
            console.print(f"  [red]✗[/red] {test['file']}::{test['test']}")
            if test.get("message"):
                console.print(f"    [dim]{test['message'][:100]}[/dim]")

    if verbose or result.failed > 0 or result.errors > 0:
        if result.output:
            output_preview = result.output[-2000:] if len(result.output) > 2000 else result.output
            console.print(Panel(output_preview, title="Output", border_style="blue"))

    if result.is_success:
        return f"\n[green]✓ All {result.passed} tests passed![/green]"
    else:
        return f"\n[red]✗ {result.failed} test(s) failed, {result.errors} error(s)[/red]"


async def coverage_command(args: list[str], context: CommandContext) -> str:
    """Show test coverage.

    Usage: /coverage [path] [--format=terminal|html|json]
    """
    test_path: Optional[str] = None
    format = "terminal"

    for arg in args:
        if arg.startswith("--format="):
            format = arg.split("=")[1]
        elif arg == "--help" or arg == "-h":
            return """[bold]Coverage Command[/bold]

Usage: /coverage [path] [options]

Options:
  --format=TYPE       Output format: terminal, html, json (default: terminal)

Examples:
  /coverage
  /coverage src/
  /coverage --format=html
"""
        elif not arg.startswith("-"):
            test_path = arg

    framework = detect_test_framework(context.cwd)
    if framework != TestFramework.PYTEST:
        return "[yellow]Coverage report currently only supported for pytest projects[/yellow]"

    console.print("[cyan]Running tests with coverage...[/cyan]")

    result = await run_coverage(context.cwd, test_path, format)

    if not result["success"]:
        return f"[red]Coverage failed: {result.get('error', 'Unknown error')}[/red]"

    total = result["total_coverage"]
    if total >= 80:
        color = "green"
    elif total >= 60:
        color = "yellow"
    else:
        color = "red"

    console.print(f"\n[bold]Total Coverage: [{color}]{total}%[/{color}][/bold]\n")

    if result["files"]:
        table = Table(title="File Coverage")
        table.add_column("File", style="cyan")
        table.add_column("Statements", justify="right")
        table.add_column("Missing", justify="right")
        table.add_column("Coverage", justify="right")

        sorted_files = sorted(result["files"], key=lambda x: x["coverage"])
        for file_info in sorted_files[:20]:
            cov = file_info["coverage"]
            if cov >= 80:
                cov_style = "green"
            elif cov >= 60:
                cov_style = "yellow"
            else:
                cov_style = "red"

            table.add_row(
                file_info["file"],
                str(file_info["statements"]),
                str(file_info["missing"]),
                f"[{cov_style}]{cov}%[/{cov_style}]",
            )

        if len(result["files"]) > 20:
            table.add_row(f"... and {len(result['files']) - 20} more files", "", "", "")

        console.print(table)

    bar_width = 50
    filled = int((total / 100) * bar_width)
    bar = "█" * filled + "░" * (bar_width - filled)
    console.print(f"\n[{color}]{bar}[/{color}] {total}%")

    return ""


async def benchmark_command(args: list[str], context: CommandContext) -> str:
    """Run benchmarks if available.

    Usage: /benchmark
    """
    if args and args[0] in ["--help", "-h"]:
        return """[bold]Benchmark Command[/bold]

Usage: /benchmark

Runs project benchmarks. Currently supports pytest-benchmark for Python.
"""

    framework = detect_test_framework(context.cwd)
    if framework != TestFramework.PYTEST:
        return "[yellow]Benchmarks currently only supported for pytest projects[/yellow]"

    console.print("[cyan]Running benchmarks...[/cyan]")

    try:
        returncode, stdout, stderr = await run_command_streaming(
            ["python", "-m", "pytest", "--benchmark-only", "-v"],
            cwd=context.cwd,
            total_timeout=300,
            inactivity_timeout=30,
        )

        output = stdout
        if stderr:
            output += "\n" + stderr

        if "benchmark" not in output.lower() and returncode != 0:
            return "[yellow]No benchmarks found. Install pytest-benchmark to use this feature.[/yellow]"

        console.print(
            Panel(
                output[-1500:] if len(output) > 1500 else output,
                title="Benchmark Results",
                border_style="blue",
            )
        )
        return ""

    except asyncio.CancelledError:
        return "Benchmark cancelled by user"
    except Exception as e:
        return f"[red]Benchmark failed: {e}[/red]"


# Register commands
register_command(
    CommandHandler(
        name="test",
        description="Run project tests",
        handler=test_command,
        aliases=["t", "run-tests"],
    )
)

register_command(
    CommandHandler(
        name="coverage",
        description="Show test coverage report",
        handler=coverage_command,
        aliases=["cov"],
    )
)

register_command(
    CommandHandler(
        name="benchmark",
        description="Run project benchmarks",
        handler=benchmark_command,
        aliases=["bench"],
    )
)
