"""Level 2 verification: test execution.

Runs unit tests and integration tests for task outputs.
"""

from __future__ import annotations

import os
import subprocess
import sys
from typing import Any

from .base import BaseVerifier, VerificationResult, Verdict
from ..task_spec import TaskSpec
from ..results import ExecutionResult


class PytestRunnerVerifier(BaseVerifier):
    """Level 2 verifier: runs tests against task outputs."""

    level = 2

    def __init__(self, test_command: str | None = None):
        """Initialize with optional test command.

        Args:
            test_command: Command to run tests (e.g., "pytest tests/ -q")
        """
        self.test_command = test_command

    async def verify(self, task: TaskSpec, execution_result: ExecutionResult) -> VerificationResult:
        """Run tests for the task.

        Strategy:
        1. Look for test files matching task outputs
        2. Run pytest if available
        3. Check exit code
        """
        issues = []
        metrics = {}
        score = 100.0

        # Auto-discover test files
        test_files = self._discover_tests(task)
        metrics["test_files_found"] = len(test_files)

        if not test_files:
            # No tests found - not a failure, but warn
            return VerificationResult(
                task_id=task.id,
                level=self.level,
                passed=True,
                score=80.0,
                issues=[
                    {
                        "severity": "info",
                        "category": "no_tests",
                        "message": "No test files found for this task",
                    }
                ],
                feedback="No tests to run. Consider adding tests for better coverage.",
                verdict=Verdict.APPROVE,
                metrics=metrics,
            )

        # Run tests
        if self.test_command:
            result = await self._run_command(self.test_command)
        else:
            result = await self._run_pytest(test_files)

        metrics["exit_code"] = result["exit_code"]
        metrics["stdout_lines"] = len(result["stdout"].splitlines())
        metrics["stderr_lines"] = len(result["stderr"].splitlines())

        if result["exit_code"] != 0:
            issues.append(
                {
                    "severity": "error",
                    "category": "test_failure",
                    "message": f"Tests failed with exit code {result['exit_code']}",
                }
            )
            score -= 50.0

            # Parse test output for details
            failed_tests = self._parse_failures(result["stdout"] + result["stderr"])
            for test_name in failed_tests[:5]:  # Limit to first 5
                issues.append(
                    {
                        "severity": "error",
                        "category": "failed_test",
                        "message": f"Failed: {test_name}",
                    }
                )

        # Check for coverage if available
        coverage = self._extract_coverage(result["stdout"])
        if coverage is not None:
            metrics["coverage_pct"] = coverage
            if coverage < 50.0:
                issues.append(
                    {
                        "severity": "warning",
                        "category": "low_coverage",
                        "message": f"Test coverage {coverage:.1f}% is below 50%",
                    }
                )
                score -= 10.0

        score = max(0.0, min(100.0, score))
        passed = score >= 60.0 and not any(i["severity"] == "error" for i in issues)

        verdict = Verdict.APPROVE if passed else Verdict.NEEDS_REWORK
        if score < 30.0:
            verdict = Verdict.REJECT

        feedback = "Tests passed." if passed else f"Tests failed:\n{result['stdout'][:1000]}"

        return VerificationResult(
            task_id=task.id,
            level=self.level,
            passed=passed,
            score=score,
            issues=issues,
            feedback=feedback,
            verdict=verdict,
            metrics=metrics,
        )

    def _discover_tests(self, task: TaskSpec) -> list[str]:
        """Discover test files related to task outputs."""
        test_files = []
        for output in task.outputs:
            base = os.path.splitext(output)[0]
            # Common test naming conventions
            candidates = [
                f"{base}_test.py",
                f"test_{os.path.basename(base)}.py",
                f"tests/{os.path.basename(base)}_test.py",
                f"tests/test_{os.path.basename(base)}.py",
            ]
            for candidate in candidates:
                if os.path.exists(candidate):
                    test_files.append(candidate)
        return test_files

    async def _run_command(self, *cmd: str) -> dict[str, Any]:
        """Run a command asynchronously with argument list (safe from injection)."""
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await proc.communicate()
            return {
                "exit_code": proc.returncode or 0,
                "stdout": stdout.decode("utf-8", errors="replace"),
                "stderr": stderr.decode("utf-8", errors="replace"),
            }
        except Exception as e:
            return {
                "exit_code": -1,
                "stdout": "",
                "stderr": str(e),
            }

    async def _run_pytest(self, test_files: list[str]) -> dict[str, Any]:
        """Run pytest on discovered test files."""
        if not test_files:
            return {"exit_code": 0, "stdout": "No tests found", "stderr": ""}

        return await self._run_command(
            sys.executable, "-m", "pytest", *test_files, "-q", "--tb=short"
        )

    def _parse_failures(self, output: str) -> list[str]:
        """Parse pytest output for failed test names."""
        failed = []
        for line in output.splitlines():
            if "FAILED" in line or "ERROR" in line:
                # Extract test name
                parts = line.split()
                for part in parts:
                    if "::" in part or "test_" in part:
                        failed.append(part)
                        break
        return failed

    def _extract_coverage(self, output: str) -> float | None:
        """Extract coverage percentage from output."""
        import re

        match = re.search(r"(\d+)%", output)
        if match:
            return float(match.group(1))
        return None


import asyncio
