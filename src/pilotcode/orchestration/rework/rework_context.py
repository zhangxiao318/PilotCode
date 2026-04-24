"""Rework context preservation for P-EVR orchestration.

Maps to P-EVR Architecture Section 5.3:
- Preserve: what to keep from previous attempts
- Must_change: what needs to be fixed
- Lessons_learned: why the previous attempt failed
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from enum import Enum


class ReworkSeverity(Enum):
    """Severity levels for rework issues."""

    MINOR = "minor"  # Naming, formatting, comments
    MAJOR = "major"  # Logic error, missing boundaries
    CRITICAL = "critical"  # Architecture flaw, security vulnerability
    BLOCKED = "blocked"  # External dependency unavailable


@dataclass
class ReworkAttempt:
    """Record of a single execution attempt."""

    attempt_number: int
    code: str = ""
    test_results: dict[str, Any] = field(default_factory=dict)
    review_feedback: str = ""
    verification_score: float = 0.0
    token_usage: int = 0
    time_spent_seconds: float = 0.0


@dataclass
class ReworkContext:
    """Context preserved across rework attempts.

    This is passed back to the Worker on retry so it knows:
    - What worked before (preserve)
    - What needs fixing (must_change)
    - Why previous attempts failed (lessons_learned)
    """

    original_task_id: str
    original_objective: str = ""
    attempts: list[ReworkAttempt] = field(default_factory=list)
    preserve: list[str] = field(default_factory=list)
    must_change: list[str] = field(default_factory=list)
    lessons_learned: list[str] = field(default_factory=list)
    severity: ReworkSeverity = ReworkSeverity.MINOR
    max_attempts: int = 3

    def add_attempt(self, attempt: ReworkAttempt) -> None:
        """Record a new attempt."""
        self.attempts.append(attempt)

    def can_retry(self) -> bool:
        """Check if more retry attempts are allowed."""
        return len(self.attempts) < self.max_attempts

    def get_retry_strategy(self) -> dict[str, Any]:
        """Determine the best strategy for the next retry.

        Returns:
            Dict with strategy recommendation.
        """
        attempt_count = len(self.attempts)
        last = self.attempts[-1] if self.attempts else None

        strategy = {
            "attempt_number": attempt_count + 1,
            "worker_type": "debug",  # Default to debug worker for rework
            "context_budget_multiplier": 1.2 + (attempt_count * 0.1),
        }

        if self.severity == ReworkSeverity.CRITICAL:
            strategy["trigger_redesign"] = True
            strategy["worker_type"] = "complex"
        elif self.severity == ReworkSeverity.MAJOR:
            strategy["worker_type"] = "standard"
        elif self.severity == ReworkSeverity.MINOR:
            strategy["worker_type"] = "simple"

        if last:
            strategy["previous_feedback"] = last.review_feedback[:1000]
            strategy["previous_score"] = last.verification_score

        return strategy

    def to_dict(self) -> dict[str, Any]:
        return {
            "original_task_id": self.original_task_id,
            "original_objective": self.original_objective,
            "attempt_count": len(self.attempts),
            "preserve": self.preserve,
            "must_change": self.must_change,
            "lessons_learned": self.lessons_learned,
            "severity": self.severity.value,
            "max_attempts": self.max_attempts,
        }

    def generate_lesson(self) -> str:
        """Generate a lesson learned from all attempts."""
        if not self.attempts:
            return ""

        lessons = []
        for i, attempt in enumerate(self.attempts, 1):
            if attempt.review_feedback:
                lessons.append(f"Attempt {i}: {attempt.review_feedback[:200]}")

        return "\n".join(lessons)
