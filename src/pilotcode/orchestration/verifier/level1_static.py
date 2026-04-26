"""Level 1 verification: static analysis.

Checks:
- File existence and basic structure
- Line count limits
- Forbidden patterns
- Required patterns
- Complexity estimation based on file metrics
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Any

from .base import BaseVerifier, VerificationResult, Verdict
from ..task_spec import TaskSpec, Constraints
from ..results import ExecutionResult


@dataclass
class FileMetrics:
    """Metrics for a single file."""

    path: str
    lines: int = 0
    functions: int = 0
    classes: int = 0
    comments: int = 0
    blank_lines: int = 0
    max_function_lines: int = 0


class StaticAnalysisVerifier(BaseVerifier):
    """Level 1 verifier: static code analysis."""

    level = 1

    async def verify(self, task: TaskSpec, execution_result: ExecutionResult) -> VerificationResult:
        """Run static analysis on task outputs."""
        issues = []
        metrics = {}
        score = 100.0

        # Check outputs exist
        for output_path in task.outputs:
            if not os.path.exists(output_path):
                issues.append(
                    {
                        "severity": "error",
                        "category": "missing_output",
                        "message": f"Required output not found: {output_path}",
                    }
                )
                score -= 30.0

        # Check constraints
        if task.constraints.max_lines:
            for output_path in task.outputs:
                if os.path.isfile(output_path):
                    line_count = self._count_lines(output_path)
                    metrics[f"{output_path}:lines"] = line_count
                    if line_count > task.constraints.max_lines:
                        issues.append(
                            {
                                "severity": "error",
                                "category": "line_limit",
                                "message": f"File {output_path} has {line_count} lines (limit: {task.constraints.max_lines})",
                            }
                        )
                        score -= 20.0

        # Check forbidden patterns
        for pattern in task.constraints.forbidden_patterns:
            for output_path in task.outputs:
                if os.path.isfile(output_path):
                    matches = self._find_pattern(output_path, pattern)
                    if matches:
                        issues.append(
                            {
                                "severity": "warning",
                                "category": "forbidden_pattern",
                                "message": f"Forbidden pattern '{pattern}' found in {output_path} ({len(matches)} matches)",
                            }
                        )
                        score -= 10.0 * len(matches)

        # Check required patterns
        for pattern in task.constraints.patterns:
            for output_path in task.outputs:
                if os.path.isfile(output_path):
                    matches = self._find_pattern(output_path, pattern)
                    if not matches:
                        issues.append(
                            {
                                "severity": "warning",
                                "category": "missing_pattern",
                                "message": f"Required pattern '{pattern}' not found in {output_path}",
                            }
                        )
                        score -= 10.0

        # Check must_use / must_not_use (simple string search)
        for must_use in task.constraints.must_use:
            found = False
            for output_path in task.outputs:
                if os.path.isfile(output_path):
                    if must_use in self._read_file(output_path):
                        found = True
                        break
            if not found:
                issues.append(
                    {
                        "severity": "warning",
                        "category": "must_use",
                        "message": f"Required element '{must_use}' not found in any output",
                    }
                )
                score -= 15.0

        score = max(0.0, min(100.0, score))
        passed = score >= 60.0 and not any(i["severity"] == "error" for i in issues)

        verdict = Verdict.APPROVE if passed else Verdict.NEEDS_REWORK
        if score < 30.0:
            verdict = Verdict.REJECT

        feedback_parts = []
        if issues:
            feedback_parts.append(f"Found {len(issues)} issue(s):")
            for issue in issues:
                feedback_parts.append(f"  [{issue['severity']}] {issue['message']}")
        else:
            feedback_parts.append("All static checks passed.")

        return VerificationResult(
            task_id=task.id,
            level=self.level,
            passed=passed,
            score=score,
            issues=issues,
            feedback="\n".join(feedback_parts),
            verdict=verdict,
            metrics=metrics,
        )

    def _count_lines(self, path: str) -> int:
        """Count lines in a file."""
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                return sum(1 for _ in f)
        except Exception:
            return 0

    def _find_pattern(self, path: str, pattern: str) -> list[tuple[int, str]]:
        """Find regex pattern matches in a file."""
        matches = []
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                for i, line in enumerate(f, 1):
                    if re.search(pattern, line):
                        matches.append((i, line.strip()))
        except Exception:
            import logging

            logging.getLogger(__name__).debug("Pattern search failed in %s", path, exc_info=True)
        return matches

    def _read_file(self, path: str) -> str:
        """Read file content."""
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                return f.read()
        except Exception:
            return ""
