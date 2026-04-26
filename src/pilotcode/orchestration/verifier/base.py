"""Base classes for the verification layer."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from enum import Enum


class Verdict(Enum):
    """Verification verdict."""

    APPROVE = "APPROVE"
    NEEDS_REWORK = "NEEDS_REWORK"
    REJECT = "REJECT"
    PENDING = "PENDING"


@dataclass
class VerificationResult:
    """Result of a verification pass."""

    task_id: str
    level: int
    passed: bool
    score: float = 0.0  # 0-100
    issues: list[dict[str, Any]] = field(default_factory=list)
    feedback: str = ""
    verdict: Verdict = Verdict.PENDING
    metrics: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "level": self.level,
            "passed": self.passed,
            "score": self.score,
            "issues": self.issues,
            "feedback": self.feedback,
            "verdict": self.verdict.value,
            "metrics": self.metrics,
        }


class BaseVerifier:
    """Base class for all verifiers."""

    level: int = 0

    async def verify(self, task: Any, execution_result: Any) -> VerificationResult:
        """Run verification.

        Args:
            task: TaskSpec of the task being verified
            execution_result: ExecutionResult from the worker

        Returns:
            VerificationResult
        """
        raise NotImplementedError
