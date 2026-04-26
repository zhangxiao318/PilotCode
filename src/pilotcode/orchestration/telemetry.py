"""Telemetry and metrics collection for P-EVR orchestration."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class TaskMetric:
    """Metrics for a single task execution."""

    task_id: str
    worker_type: str
    started_at: str
    completed_at: str
    duration_seconds: float
    token_usage: int
    success: bool
    verification_levels: list[int] = field(default_factory=list)
    rework_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "worker_type": self.worker_type,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "duration_seconds": self.duration_seconds,
            "token_usage": self.token_usage,
            "success": self.success,
            "verification_levels": self.verification_levels,
            "rework_count": self.rework_count,
        }


@dataclass
class MissionMetrics:
    """Metrics for a full mission execution."""

    mission_id: str
    started_at: str
    completed_at: str | None = None
    total_tasks: int = 0
    completed_tasks: int = 0
    failed_tasks: int = 0
    retried_tasks: int = 0
    total_token_usage: int = 0
    total_duration_seconds: float = 0.0
    task_metrics: list[TaskMetric] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "mission_id": self.mission_id,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "total_tasks": self.total_tasks,
            "completed_tasks": self.completed_tasks,
            "failed_tasks": self.failed_tasks,
            "retried_tasks": self.retried_tasks,
            "total_token_usage": self.total_token_usage,
            "total_duration_seconds": self.total_duration_seconds,
            "task_metrics": [t.to_dict() for t in self.task_metrics],
        }
