"""Result types for P-EVR orchestration.

Extracted to avoid circular imports between orchestrator, verifiers, and workers.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ExecutionResult:
    """Result of executing a single task."""

    task_id: str
    success: bool
    output: Any = None
    error: str | None = None
    artifacts: dict[str, Any] = field(default_factory=dict)
    token_usage: int = 0
    time_spent_seconds: float = 0.0
