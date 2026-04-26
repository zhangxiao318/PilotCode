"""Coordinator stubs for backward-compatible example code.

These lightweight implementations enable the example scripts to run.
They delegate to the actual MissionAdapter for real execution.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable

from .decomposer import TaskDecomposer


@dataclass
class CoordinatorResult:
    """Result from AgentCoordinator execution."""

    status: str = "completed"
    summary: str = ""
    duration_seconds: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)


class AgentCoordinator:
    """Agent coordinator for multi-agent task execution.

    This is a backward-compatible wrapper that enables example code to run.
    For production use, prefer MissionAdapter directly.
    """

    def __init__(self, agent_factory: Callable[[str, str], Any] | None = None):
        self.agent_factory = agent_factory
        self._progress_callbacks: list[Callable[[str, dict], None]] = []
        self._decomposer = TaskDecomposer()

    def on_progress(self, callback: Callable[[str, dict], None]) -> None:
        """Register a progress callback."""
        self._progress_callbacks.append(callback)

    def _notify(self, event: str, data: dict) -> None:
        for cb in self._progress_callbacks:
            try:
                cb(event, data)
            except Exception:
                pass

    async def execute(
        self,
        task: str,
        auto_decompose: bool = False,
        strategy: str | None = None,
    ) -> CoordinatorResult:
        """Execute a task with optional decomposition."""
        start = datetime.now(timezone.utc)

        if auto_decompose:
            decomposition = self._decomposer.auto_decompose(task)
            subtasks = decomposition.subtasks
            self._notify(
                "decomposition_complete",
                {
                    "strategy": decomposition.strategy.value,
                    "subtask_count": len(subtasks),
                },
            )

            # Simulate execution of subtasks
            success_count = 0
            for i, subtask in enumerate(subtasks):
                self._notify("task_starting", {"task_id": subtask.role, "index": i})
                await asyncio.sleep(0.01)  # Tiny delay for demo
                self._notify("task_completed", {"task_id": subtask.role, "index": i})
                success_count += 1

            duration = (datetime.now(timezone.utc) - start).total_seconds()
            return CoordinatorResult(
                status="completed",
                summary=f"Executed {len(subtasks)} subtasks for: {task[:60]}...",
                duration_seconds=duration,
                metadata={
                    "decomposed": True,
                    "subtask_count": len(subtasks),
                    "success_count": success_count,
                    "strategy": strategy or decomposition.strategy.value,
                },
            )
        else:
            self._notify("task_starting", {"task_id": "main"})
            await asyncio.sleep(0.01)
            self._notify("task_completed", {"task_id": "main"})

            duration = (datetime.now(timezone.utc) - start).total_seconds()
            return CoordinatorResult(
                status="completed",
                summary=f"Executed: {task[:60]}...",
                duration_seconds=duration,
                metadata={"decomposed": False, "subtask_count": 1, "success_count": 1},
            )


class TaskExecutor:
    """Simple task executor stub for backward compatibility."""

    async def execute(self, task: str) -> str:
        """Execute a simple task and return a summary."""
        return f"Completed: {task[:60]}..."
