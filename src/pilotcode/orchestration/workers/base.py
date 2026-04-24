"""Base worker class for P-EVR orchestration."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable
from abc import ABC, abstractmethod

from ..task_spec import TaskSpec
from ..orchestrator import ExecutionResult


@dataclass
class WorkerContext:
    """Context passed to a worker during execution."""

    objective: str = ""
    constraints: Any = None
    acceptance_criteria: list[Any] = field(default_factory=list)
    context_budget: int = 16000
    previous_attempts: list[dict[str, Any]] = field(default_factory=list)
    related_files: list[str] = field(default_factory=list)
    project_context: dict[str, Any] = field(default_factory=dict)


class BaseWorker(ABC):
    """Abstract base class for all workers.

    Workers are stateless. All state is maintained by the Orchestrator.
    """

    worker_type: str = "base"

    @abstractmethod
    async def execute(self, task: TaskSpec, context: WorkerContext) -> ExecutionResult:
        """Execute a task.

        Args:
            task: The TaskSpec to execute
            context: WorkerContext with objective, constraints, etc.

        Returns:
            ExecutionResult
        """
        raise NotImplementedError

    def _build_prompt(self, task: TaskSpec, context: WorkerContext) -> str:
        """Build the execution prompt for the worker.

        Includes Goal Anchoring to prevent context drift.
        """
        parts = [
            f"[任务] {task.title}",
            f"[目标] {task.objective}",
            "",
        ]

        if task.constraints.max_lines:
            parts.append(f"[约束] 文件不超过 {task.constraints.max_lines} 行")
        if task.constraints.must_use:
            parts.append(f"[必须使用] {', '.join(task.constraints.must_use)}")
        if task.constraints.must_not_use:
            parts.append(f"[禁止使用] {', '.join(task.constraints.must_not_use)}")
        if task.constraints.patterns:
            parts.append(f"[必须遵循] {', '.join(task.constraints.patterns)}")

        parts.extend(
            [
                "",
                "[验收标准]",
            ]
        )
        for ac in task.acceptance_criteria:
            parts.append(f"  - {ac.description}")

        if context.previous_attempts:
            parts.extend(
                [
                    "",
                    "[返工上下文]",
                    f"  这是第 {len(context.previous_attempts) + 1} 次尝试。",
                ]
            )
            last = context.previous_attempts[-1]
            if "feedback" in last:
                parts.append(f"  上次反馈: {last['feedback'][:500]}")
            if "preserve" in last:
                parts.append(f"  保留部分: {last['preserve']}")
            if "must_change" in last:
                parts.append(f"  必须修改: {last['must_change']}")

        parts.extend(
            [
                "",
                "[重要] 专注于当前任务目标，不要偏离。只修改与任务直接相关的代码。",
            ]
        )

        return "\n".join(parts)
