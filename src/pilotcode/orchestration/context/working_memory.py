"""Layer 1: Working Memory.

Task-level memory for:
- Current task's code context
- Recent execution trace (last N steps)
- Current focus
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from datetime import datetime, timezone


@dataclass
class ExecutionTrace:
    """A single step in the execution trace."""

    step_number: int
    operation: str  # "CREATE", "READ", "WRITE", "EDIT", "DELETE", "TEST", "SHELL"
    target: str  # file path or target name
    details: dict[str, Any] = field(default_factory=dict)
    timestamp: str = ""

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat()


@dataclass
class CodeContext:
    """Code context for the current task."""

    primary_file: str = ""
    related_files: list[str] = field(default_factory=list)
    interfaces: list[str] = field(default_factory=list)
    imports: list[str] = field(default_factory=list)
    recent_changes: list[str] = field(default_factory=list)


@dataclass
class TaskSummary:
    """Compressed summary of a completed task (for L2 memory)."""

    task_id: str
    title: str
    outcome: str = ""  # "success", "failed", "rework"
    key_decisions: list[str] = field(default_factory=list)
    lessons_learned: list[str] = field(default_factory=list)
    token_usage: int = 0
    time_spent_seconds: float = 0.0


class WorkingMemory:
    """Working memory for a single task execution.

    Holds context during execution. When the task completes or switches,
    a TaskSummary is generated and stored in Session Memory (L2).
    """

    MAX_TRACE_LENGTH = 50  # Keep last 50 steps
    MAX_FOCUS_HISTORY = 5

    def __init__(self, task_id: str, task_objective: str = ""):
        self.task_id = task_id
        self.task_objective = task_objective
        self.code_context = CodeContext()
        self.trace: list[ExecutionTrace] = []
        self.current_focus: str = ""
        self.focus_history: list[str] = []
        self.token_usage: int = 0
        self.started_at: str = datetime.now(timezone.utc).isoformat()
        self.metadata: dict[str, Any] = {}

    def add_trace(self, operation: str, target: str, details: dict[str, Any] | None = None) -> None:
        """Add an execution trace step."""
        trace = ExecutionTrace(
            step_number=len(self.trace) + 1,
            operation=operation,
            target=target,
            details=details or {},
        )
        self.trace.append(trace)

        # Trim if too long
        if len(self.trace) > self.MAX_TRACE_LENGTH:
            self.trace = self.trace[-self.MAX_TRACE_LENGTH :]

    def set_focus(self, focus: str) -> None:
        """Update current focus."""
        if self.current_focus:
            self.focus_history.append(self.current_focus)
            if len(self.focus_history) > self.MAX_FOCUS_HISTORY:
                self.focus_history = self.focus_history[-self.MAX_FOCUS_HISTORY :]
        self.current_focus = focus

    def get_recent_trace(self, n: int = 5) -> list[ExecutionTrace]:
        """Get the last N trace steps."""
        return self.trace[-n:] if self.trace else []

    def get_context_summary(self, max_tokens: int = 2000) -> dict[str, Any]:
        """Generate a context summary for the LLM prompt.

        This is what gets injected into the worker's prompt to prevent
        context drift (Goal Anchoring in P-EVR).
        """
        recent_trace = self.get_recent_trace(5)

        return {
            "task_id": self.task_id,
            "objective": self.task_objective,
            "current_focus": self.current_focus,
            "recent_operations": [
                {"op": t.operation, "target": t.target, "step": t.step_number} for t in recent_trace
            ],
            "primary_file": self.code_context.primary_file,
            "related_files": self.code_context.related_files[:10],
            "focus_changes": self.focus_history[-3:],
        }

    def to_summary(self) -> TaskSummary:
        """Compress working memory into a TaskSummary for L2 storage."""
        return TaskSummary(
            task_id=self.task_id,
            title=self.task_objective[:100],
            outcome=self.metadata.get("outcome", "unknown"),
            key_decisions=self.metadata.get("key_decisions", []),
            lessons_learned=self.metadata.get("lessons_learned", []),
            token_usage=self.token_usage,
        )

    def estimate_token_count(self) -> int:
        """Rough estimate of token count for current working memory."""
        # Very rough heuristic: 1 token ≈ 4 characters
        total_chars = len(self.task_objective)
        total_chars += len(self.current_focus)
        for t in self.trace:
            total_chars += len(t.operation) + len(t.target) + str(t.details).__len__()
        return total_chars // 4
