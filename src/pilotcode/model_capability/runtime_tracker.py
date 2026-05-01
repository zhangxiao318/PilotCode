"""Runtime success-rate tracker.

Replaces the old RuntimeCalibrator.  No longer mutates benchmark scores.
Instead it records per-task-type success rates in a sliding window and
exposes them for AdaptiveConfigMapper to consume.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

from .schema import RuntimeStats

_JSON_ERROR_PATTERNS = [
    r"json\.JSONDecodeError",
    r"Expecting.*delimiter",
    r"Extra data",
    r"invalid json",
    r"malformed json",
    r"解析.*json",
    r"JSON.*错误",
]

_SYNTAX_ERROR_PATTERNS = [
    r"SyntaxError",
    r"IndentationError",
    r"unexpected indent",
    r"invalid syntax",
    r"EOF.*while scanning",
]

_LOGIC_ERROR_PATTERNS = [
    r"AssertionError",
    r"ValueError",
    r"TypeError",
    r"AttributeError",
    r"IndexError",
    r"KeyError",
    r"NameError",
    r"RuntimeError",
    r"测试.*失败",
    r"assert.*failed",
]

_TIMEOUT_PATTERNS = [
    r"TimeoutError",
    r"asyncio\.TimeoutError",
    r"timed out",
    r"timeout",
]


def _matches_any(text: str, patterns: list[str]) -> bool:
    if not text:
        return False
    lowered = text.lower()
    for p in patterns:
        if re.search(p, text, re.IGNORECASE) or re.search(p, lowered):
            return True
    return False


def classify_failure(error_text: str | None, output_text: str | None = None) -> str:
    """Classify failure type from error/output text.

    Returns one of: json_error, syntax_error, logic_error, timeout, unknown.
    """
    combined = ""
    if error_text:
        combined += error_text + "\n"
    if output_text:
        combined += output_text
    if not combined:
        return "unknown"
    if _matches_any(combined, _JSON_ERROR_PATTERNS):
        return "json_error"
    if _matches_any(combined, _SYNTAX_ERROR_PATTERNS):
        return "syntax_error"
    if _matches_any(combined, _TIMEOUT_PATTERNS):
        return "timeout"
    if _matches_any(combined, _LOGIC_ERROR_PATTERNS):
        return "logic_error"
    return "unknown"


def classify_planning_failure(raw_plan: str | None, parse_error: str | None = None) -> str:
    """Classify planning failure type.

    Returns one of: invalid_json, missing_fields, invalid_dag,
    poor_granularity, unknown.
    """
    if not raw_plan:
        return "unknown"
    try:
        data = json.loads(raw_plan)
    except json.JSONDecodeError:
        return "invalid_json"
    if not isinstance(data, dict):
        return "invalid_json"
    if "phases" not in data:
        return "missing_fields"

    all_task_ids = set()
    all_deps = []
    for phase in data.get("phases", []):
        for task in phase.get("tasks", []):
            tid = task.get("task_id", "")
            if tid:
                all_task_ids.add(tid)
            for dep in task.get("dependencies", []):
                all_deps.append((tid, dep))

    for _, dep in all_deps:
        if dep not in all_task_ids:
            return "invalid_dag"

    dep_map: dict[str, set[str]] = {tid: set() for tid in all_task_ids}
    for tid, dep in all_deps:
        if tid in dep_map:
            dep_map[tid].add(dep)
    for tid, deps in dep_map.items():
        for dep in deps:
            if tid in dep_map.get(dep, set()):
                return "invalid_dag"

    task_count = sum(len(p.get("tasks", [])) for p in data.get("phases", []))
    if task_count < 2 or task_count > 20:
        return "poor_granularity"

    return "unknown"


@dataclass
class TaskOutcome:
    """Outcome of a single task execution."""

    task_id: str
    success: bool
    completion_percentage: float = 1.0
    correctness_score: float = 1.0
    error_text: str | None = None
    output_text: str | None = None
    raw_llm_output: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class RuntimeTracker:
    """Tracks per-task-type success rates without mutating benchmark scores.

    Usage:
        tracker = RuntimeTracker()
        tracker.record_task_outcome(outcome)
        stats = tracker.get_stats()
        # stats.get_rate("json") -> 0.6
        # stats.is_struggling("json") -> True
    """

    def __init__(self, window_size: int = 10):
        self.stats = RuntimeStats(window_size=window_size)

    @property
    def total_tasks(self) -> int:
        return sum(
            len(getattr(self.stats, f"{t}_attempts", []))
            for t in ("json", "code", "planning", "reasoning", "review")
        )

    @property
    def total_successes(self) -> int:
        return sum(
            sum(getattr(self.stats, f"{t}_attempts", []))
            for t in ("json", "code", "planning", "reasoning", "review")
        )

    def record_task_outcome(self, outcome: TaskOutcome) -> None:
        """Record an execution outcome and update the relevant task-type window."""
        failure_type = classify_failure(outcome.error_text, outcome.output_text)

        # Determine which task-type window to update
        if failure_type == "json_error":
            self.stats.record("json", outcome.success)
        elif failure_type == "syntax_error":
            self.stats.record("code", outcome.success)
        elif failure_type == "logic_error":
            self.stats.record("code", outcome.success)
        elif failure_type == "timeout":
            self.stats.record("reasoning", outcome.success)
        else:
            # Default to code for unclassifiable failures
            self.stats.record("code", outcome.success)

    def record_planning_outcome(
        self,
        task_id: str,
        raw_plan: str | None = None,
        parse_error: str | None = None,
        success: bool = False,
    ) -> None:
        """Record a planning outcome."""
        self.stats.record("planning", success)

    def record_verification_outcome(
        self,
        task_id: str,
        verifier_level: int,
        verifier_passed: bool,
        verifier_output_valid: bool,
    ) -> None:
        """Record a verification outcome."""
        self.stats.record("review", verifier_output_valid and verifier_passed)

    def get_stats(self) -> RuntimeStats:
        """Return current runtime statistics."""
        return self.stats

    def get_success_rate(self) -> float:
        """Overall success rate across all task types."""
        if self.total_tasks == 0:
            return 1.0
        return self.total_successes / self.total_tasks

    def reset(self) -> None:
        """Clear all runtime statistics."""
        self.stats = RuntimeStats(window_size=self.stats.window_size)
