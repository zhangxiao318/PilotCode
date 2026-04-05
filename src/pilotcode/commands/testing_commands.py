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

import os
import re
import json
import subprocess
from typing import Optional, Any
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.tree import Tree

from pilotcode.types.command import CommandContext
from pilotcode.commands.base import CommandHandler, register_command

console = Console()


class TestFramework(str, Enum):
    """Supported test frameworks."""
    PYTEST = "pytest"
    UNITTEST = "unittest"
    JEST = "jest"
    CARGO = "cargo"
    GO = "go"
    UNKNOWN = "unknown"


@dataclass
class TestResult:
    """Test execution result."""
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
        """Calculate success rate."""
        if self.total == 0:
            return 0.0
        return (self.passed / self.total) * 100
    
    @property
    def is_success(self) -> bool:
        """Check if all tests passed."""
        return self.failed == 0 and self.errors == 0 and self.total > 0


def detect_test_framework(cwd: str) -> TestFramework:
    """Detect test framework based on project files."""
    # Check for pytest
    if os.path.exists(os.path.join(cwd, "pytest.ini")):
        return TestFramework.PYTEST
    if os.path.exists(os.path.join(cwd, "pyproject.toml")):
        with open(os.path.join(cwd, "pyproject.toml"), "r") as f:
            content = f.read()
            if "[tool.pytest" in content:
                return TestFramework.PYTEST
    if any(f.startswith("test_") and f.endswith(".py") for f in os.listdir(cwd) if os.path.isfile(os.path.join(cwd, f))):
        return TestFramework.PYTEST
    
    # Check for package.json (jest)
    if os.path.exists(os.path.join(cwd, "package.json")):
        with open(os.path.join(cwd, "package.json"), "r") as f:
            content = f.read()
            if "jest" in content:
                return TestFramework.JEST
    
    # Check for Cargo.toml (Rust)
    if os.path.exists(os.path.join(cwd, "Cargo.toml")):
        return TestFramework.CARGO
    
    # Check for go.mod (Go)
    if os.path.exists(os.path.join(cwd, "go.mod")):
        return TestFramework.GO
    
    # Default to pytest for Python files
    if any(f.endswith(".py") for f in os.listdir(cwd) if os.path.isfile(os.path.join(cwd, f))):
        return TestFramework.PYTEST
    
    return TestFramework.UNKNOWN


def run_pytest_tests(
    cwd: str,
    test_path: Optional[str] = None,
    verbose: bool = False,
    markers: Optional[list[str]] = None,
    max_failures: Optional[int] = None,
) -> TestResult:
    """Run pytest tests."""
    cmd = ["python", "-m", "pytest"]
    
    # Add options
    if verbose:
        cmd.append("-v")
    
    # JSON output for parsing
    cmd.extend(["--tb=short", "-q"])
    
    # Markers
    if markers:
        for marker in markers:
            cmd.extend(["-m", marker])
    
    # Max failures
    if max_failures:
        cmd.extend(["--maxfail", str(max_failures)])
    
    # Test path
    if test_path:
        cmd.append(test_path)
    
    start_time = __import__('time').time()
    
    try:
        result = subprocess.run(
            cmd,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=300,  # 5 minute timeout
        )
        duration = __import__('time').time() - start_time
        
        return parse_pytest_output(result.stdout, result.stderr, duration)
    
    except subprocess.TimeoutExpired:
        return TestResult(
            framework=TestFramework.PYTEST,
            errors=1,
            output="Test execution timed out after 5 minutes",
            duration=300.0,
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
    
    # Parse summary line
    # Example: "5 passed, 2 failed, 1 skipped in 0.45s"
    # or: "1 passed in 0.12s"
    summary_pattern = r'(\d+) passed(?:, (\d+) failed)?(?:, (\d+) skipped)?(?:, (\d+) error)? in ([\d.]+)s'
    
    for line in stdout.split('\n'):
        match = re.search(summary_pattern, line)
        if match:
            result.passed = int(match.group(1))
            result.failed = int(match.group(2)) if match.group(2) else 0
            result.skipped = int(match.group(3)) if match.group(3) else 0
            result.errors = int(match.group(4)) if match.group(4) else 0
            result.total = result.passed + result.failed + result.skipped + result.errors
            break
    
    # Parse failed tests
    failed_test_pattern = r'(FAILED|ERROR) (.+?)::(.+?) - (.+)'
    for match in re.finditer(failed_test_pattern, stdout):
        result.failed_tests.append({
            'status': match.group(1),
            'file': match.group(2),
            'test': match.group(3),
            'message': match.group(4),
        })
    
    return result


def run_coverage(
    cwd: str,
    test_path: Optional[str] = None,
    format: str = "terminal",
) -> dict[str, Any]:
    """Run tests with coverage."""
    cmd = [
        "python", "-m", "pytest",
        "--cov=.",
        f"--cov-report={format}",
        "-q",
    ]
    
    if test_path:
        cmd.append(test_path)
    
    try:
        result = subprocess.run(
            cmd,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=300,
        )
        
        return parse_coverage_output(result.stdout, result.stderr)
    
    except Exception as e:
        return {
            'success': False,
            'error': str(e),
            'total_coverage': 0.0,
            'files': [],
        }


def parse_coverage_output(stdout: str, stderr: str) -> dict[str, Any]:
    """Parse coverage output."""
    result = {
        'success': True,
        'total_coverage': 0.0,
        'files': [],
        'output': stdout + ("\n" + stderr if stderr else ""),
    }
    
    # Parse total coverage
    # Example: "TOTAL 1234 567 54%"
    total_pattern = r'TOTAL\s+\d+\s+\d+\s+(\d+)%'
    match = re.search(total_pattern, stdout)
    if match:
        result['total_coverage'] = int(match.group(1))
    
    # Parse file coverage
    # Example: "src/module.py 100 20 80%"
    file_pattern = r'^([^\s]+\.py)\s+(\d+)\s+(\d+)\s+(\d+)%'
    for line in stdout.split('\n'):
        match = re.match(file_pattern, line)
        if match:
            result['files'].append({
                'file': match.group(1),
                'statements': int(match.group(2)),
                'missing': int(match.group(3)),
                'coverage': int(match.group(4)),
            })
    
    return result


def run_jest_tests(cwd: str, test_path: Optional[str] = None) -> TestResult:
    """Run Jest tests."""
    cmd = ["npm", "test", "--", "--json", "--silent"]
    
    if test_path:
        cmd.extend(["--testPathPattern", test_path])
    
    try:
        result = subprocess.run(
            cmd,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=300,
        )
        
        # Parse JSON output
        try:
            data = json.loads(result.stdout)
            return TestResult(
                framework=TestFramework.JEST,
                total=data.get('numTotalTests', 0),
                passed=data.get('numPassedTests', 0),
                failed=data.get('numFailedTests', 0),
                skipped=data.get('numPendingTests', 0),
                duration=data.get('testResults', [{}])[0].get('perfStats', {}).get('end', 0) / 1000,
                output=result.stdout,
            )
        except json.JSONDecodeError:
            return TestResult(
                framework=TestFramework.JEST,
                output=result.stdout + result.stderr,
            )
    
    except Exception as e:
        return TestResult(
            framework=TestFramework.JEST,
            errors=1,
            output=str(e),
        )


def run_cargo_tests(cwd: str) -> TestResult:
    """Run Cargo tests."""
    cmd = ["cargo", "test"]
    
    try:
        result = subprocess.run(
            cmd,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=300,
        )
        
        # Parse output
        stdout = result.stdout
        
        # Count test results
        passed = len(re.findall(r'test \S+ \.\.\. ok', stdout))
        failed = len(re.findall(r'test \S+ \.\.\. FAILED', stdout))
        
        # Try to find summary
        summary_match = re.search(r'test result: (\w+)\.(\d+) passed; (\d+) failed;', stdout)
        if summary_match:
            passed = int(summary_match.group(2))
            failed = int(summary_match.group(3))
        
        return TestResult(
            framework=TestFramework.CARGO,
            total=passed + failed,
            passed=passed,
            failed=failed,
            output=stdout,
        )
    
    except Exception as e:
        return TestResult(
            framework=TestFramework.CARGO,
            errors=1,
            output=str(e),
        )


def run_go_tests(cwd: str, test_path: Optional[str] = None) -> TestResult:
    """Run Go tests."""
    cmd = ["go", "test", "-v"]
    
    if test_path:
        cmd.append(test_path)
    else:
        cmd.append("./...")
    
    try:
        result = subprocess.run(
            cmd,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=300,
        )
        
        stdout = result.stdout
        
        # Parse output
        passed = len(re.findall(r'^--- PASS:', stdout, re.MULTILINE))
        failed = len(re.findall(r'^--- FAIL:', stdout, re.MULTILINE))
        
        # Try to find summary
        summary_match = re.search(r'(\d+) passed, (\d+) failed', stdout)
        if summary_match:
            passed = int(summary_match.group(1))
            failed = int(summary_match.group(2))
        
        return TestResult(
            framework=TestFramework.GO,
            total=passed + failed,
            passed=passed,
            failed=failed,
            output=stdout,
        )
    
    except Exception as e:
        return TestResult(
            framework=TestFramework.GO,
            errors=1,
            output=str(e),
        )


async def test_command(args: list[str], context: CommandContext) -> str:
    """Run project tests.
    
    Usage: /test [path] [--verbose] [--maxfail=N]
    
    Automatically detects test framework based on project structure.
    
    Examples:
      /test
      /test tests/test_specific.py
      /test --verbose
      /test --maxfail=5
    """
    # Parse arguments
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
    
    # Detect framework
    framework = detect_test_framework(context.cwd)
    
    if framework == TestFramework.UNKNOWN:
        return "[yellow]Could not detect test framework. Supported: pytest, jest, cargo, go[/yellow]"
    
    # Run tests with progress
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task(f"Running {framework.value} tests...", total=None)
        
        if framework == TestFramework.PYTEST:
            result = run_pytest_tests(
                context.cwd,
                test_path=test_path,
                verbose=verbose,
                max_failures=max_failures,
            )
        elif framework == TestFramework.JEST:
            result = run_jest_tests(context.cwd, test_path)
        elif framework == TestFramework.CARGO:
            result = run_cargo_tests(context.cwd)
        elif framework == TestFramework.GO:
            result = run_go_tests(context.cwd, test_path)
        else:
            return f"[red]Unsupported test framework: {framework}[/red]"
        
        progress.update(task, completed=True)
    
    # Display results
    if result.total == 0 and not result.output:
        return "[yellow]No tests found[/yellow]"
    
    # Summary table
    table = Table(title=f"Test Results ({framework.value})")
    table.add_column("Metric", style="cyan")
    table.add_column("Count", justify="right")
    table.add_column("Status", style="green")
    
    table.add_row("Total", str(result.total), "")
    table.add_row("Passed", str(result.passed), "[green]✓[/green]" if result.passed > 0 else "")
    table.add_row("Failed", str(result.failed), "[red]✗[/red]" if result.failed > 0 else "")
    table.add_row("Skipped", str(result.skipped), "[yellow]⊘[/yellow]" if result.skipped > 0 else "")
    table.add_row("Errors", str(result.errors), "[red]![/red]" if result.errors > 0 else "")
    table.add_row("Duration", f"{result.duration:.2f}s", "")
    table.add_row("Success Rate", f"{result.success_rate:.1f}%", "")
    
    console.print(table)
    
    # Show failed tests
    if result.failed_tests:
        console.print("\n[bold red]Failed Tests:[/bold red]")
        for test in result.failed_tests:
            console.print(f"  [red]✗[/red] {test['file']}::{test['test']}")
            if test.get('message'):
                console.print(f"    [dim]{test['message'][:100]}[/dim]")
    
    # Show output if verbose or failures
    if verbose or result.failed > 0 or result.errors > 0:
        if result.output:
            output_preview = result.output[-2000:] if len(result.output) > 2000 else result.output
            console.print(Panel(output_preview, title="Output", border_style="blue"))
    
    # Final status
    if result.is_success:
        return f"\n[green]✓ All {result.passed} tests passed![/green]"
    else:
        return f"\n[red]✗ {result.failed} test(s) failed, {result.errors} error(s)[/red]"


async def coverage_command(args: list[str], context: CommandContext) -> str:
    """Show test coverage.
    
    Usage: /coverage [path] [--format=terminal|html|json]
    
    Examples:
      /coverage
      /coverage src/
      /coverage --format=html
"""
    # Parse arguments
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
    
    # Detect framework
    framework = detect_test_framework(context.cwd)
    
    if framework != TestFramework.PYTEST:
        return f"[yellow]Coverage report currently only supported for pytest projects[/yellow]"
    
    # Run coverage
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task("Running tests with coverage...", total=None)
        
        result = run_coverage(context.cwd, test_path, format)
        
        progress.update(task, completed=True)
    
    if not result['success']:
        return f"[red]Coverage failed: {result.get('error', 'Unknown error')}[/red]"
    
    # Display results
    total = result['total_coverage']
    
    # Color based on coverage
    if total >= 80:
        color = "green"
    elif total >= 60:
        color = "yellow"
    else:
        color = "red"
    
    console.print(f"\n[bold]Total Coverage: [{color}]{total}%[/{color}][/bold]\n")
    
    # File coverage table
    if result['files']:
        table = Table(title="File Coverage")
        table.add_column("File", style="cyan")
        table.add_column("Statements", justify="right")
        table.add_column("Missing", justify="right")
        table.add_column("Coverage", justify="right")
        
        # Sort by coverage (ascending) to show worst first
        sorted_files = sorted(result['files'], key=lambda x: x['coverage'])
        
        for file_info in sorted_files[:20]:  # Show top 20
            cov = file_info['coverage']
            if cov >= 80:
                cov_style = "green"
            elif cov >= 60:
                cov_style = "yellow"
            else:
                cov_style = "red"
            
            table.add_row(
                file_info['file'],
                str(file_info['statements']),
                str(file_info['missing']),
                f"[{cov_style}]{cov}%[/{cov_style}]",
            )
        
        if len(result['files']) > 20:
            table.add_row(f"... and {len(result['files']) - 20} more files", "", "", "")
        
        console.print(table)
    
    # Coverage bar
    bar_width = 50
    filled = int((total / 100) * bar_width)
    bar = "█" * filled + "░" * (bar_width - filled)
    console.print(f"\n[{color}]{bar}[/{color}] {total}%")
    
    return ""


async def benchmark_command(args: list[str], context: CommandContext) -> str:
    """Run benchmarks if available.
    
    Usage: /benchmark
    
    Runs project benchmarks. Requires pytest-benchmark for Python projects.
    """
    if args and args[0] in ["--help", "-h"]:
        return """[bold]Benchmark Command[/bold]

Usage: /benchmark

Runs project benchmarks. Currently supports pytest-benchmark for Python.
"""
    
    framework = detect_test_framework(context.cwd)
    
    if framework != TestFramework.PYTEST:
        return "[yellow]Benchmarks currently only supported for pytest projects[/yellow]"
    
    # Check for pytest-benchmark
    cmd = ["python", "-m", "pytest", "--benchmark-only", "-v"]
    
    try:
        result = subprocess.run(
            cmd,
            cwd=context.cwd,
            capture_output=True,
            text=True,
            timeout=300,
        )
        
        if "benchmark" not in result.stdout.lower() and result.returncode != 0:
            return "[yellow]No benchmarks found. Install pytest-benchmark to use this feature.[/yellow]"
        
        # Parse benchmark results
        output = result.stdout
        
        # Show summary
        console.print(Panel(output[-1500:] if len(output) > 1500 else output, 
                          title="Benchmark Results", border_style="blue"))
        
        return ""
    
    except Exception as e:
        return f"[red]Benchmark failed: {e}[/red]"


# Register commands
register_command(CommandHandler(
    name="test",
    description="Run project tests",
    handler=test_command,
    aliases=["t", "run-tests"],
))

register_command(CommandHandler(
    name="coverage",
    description="Show test coverage report",
    handler=coverage_command,
    aliases=["cov"],
))

register_command(CommandHandler(
    name="benchmark",
    description="Run project benchmarks",
    handler=benchmark_command,
    aliases=["bench"],
))
