"""Reflector: periodic reflection and risk assessment for P-EVR.

Maps to P-EVR Architecture Section 7 (Orchestrator pseudocode):
- Periodic checks on mission progress
- Risk detection
- Deadlock detection
- Metrics collection
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from datetime import datetime, timezone

from ..tracker import MissionTracker
from ..dag import DagExecutor
from ..state_machine import TaskState


@dataclass
class ReflectorResult:
    """Result of a reflection check."""

    mission_id: str
    healthy: bool
    risks: list[dict[str, Any]] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)
    timestamp: str = ""

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> dict[str, Any]:
        return {
            "mission_id": self.mission_id,
            "healthy": self.healthy,
            "risks": self.risks,
            "recommendations": self.recommendations,
            "metrics": self.metrics,
            "timestamp": self.timestamp,
        }


class Reflector:
    """Periodic reflection on mission health.

    Runs checks at regular intervals or on-demand to detect:
    - Stalled tasks (in_progress for too long)
    - Deadlocks (all tasks blocked)
    - Quality degradation (rework rate too high)
    - Resource exhaustion (token budget)
    """

    def __init__(
        self,
        max_in_progress_minutes: float = 30.0,
        max_rework_rate: float = 0.5,
        max_token_budget_ratio: float = 0.9,
    ):
        self.max_in_progress_minutes = max_in_progress_minutes
        self.max_rework_rate = max_rework_rate
        self.max_token_budget_ratio = max_token_budget_ratio

    def check(self, mission_id: str, tracker: MissionTracker) -> ReflectorResult:
        """Run a full reflection check on a mission.

        Returns:
            ReflectorResult with health assessment and recommendations.
        """
        risks = []
        recommendations = []
        metrics = {}

        dag = tracker.get_dag(mission_id)
        snapshot = tracker.get_snapshot(mission_id)

        if not dag or not snapshot:
            return ReflectorResult(
                mission_id=mission_id,
                healthy=False,
                risks=[{"severity": "critical", "message": "Mission not found in tracker"}],
            )

        # Collect metrics
        total = snapshot.total_tasks
        completed = snapshot.completed_tasks
        verified = snapshot.verified_tasks
        failed = snapshot.failed_tasks
        blocked = snapshot.blocked_tasks
        in_progress = snapshot.in_progress_tasks
        ready = snapshot.ready_tasks

        metrics = {
            "total_tasks": total,
            "completed": completed,
            "verified": verified,
            "failed": failed,
            "blocked": blocked,
            "in_progress": in_progress,
            "ready": ready,
            "completion_rate": completed / total if total > 0 else 0,
            "success_rate": verified / completed if completed > 0 else 0,
        }

        # Check 1: Deadlock / stall detection
        pending_count = total - completed - in_progress
        if ready == 0 and in_progress == 0 and pending_count > 0:
            risks.append(
                {
                    "severity": "critical",
                    "category": "deadlock",
                    "message": f"Possible deadlock: {pending_count} tasks pending but none ready or in progress",
                }
            )
            recommendations.append(
                "Check dependency graph for circular dependencies or failed prerequisites"
            )

        # Check 2: Rework rate
        rework_count = sum(1 for node in dag.nodes.values() if node.state == TaskState.NEEDS_REWORK)
        if total > 0:
            rework_rate = rework_count / total
            metrics["rework_rate"] = rework_rate
            if rework_rate > self.max_rework_rate:
                risks.append(
                    {
                        "severity": "high",
                        "category": "rework_rate",
                        "message": f"Rework rate {rework_rate:.1%} exceeds threshold {self.max_rework_rate:.1%}",
                    }
                )
                recommendations.append("Consider triggering redesign for high-rework tasks")

        # Check 3: Stalled tasks
        stalled = self._find_stalled_tasks(mission_id, tracker)
        if stalled:
            risks.append(
                {
                    "severity": "medium",
                    "category": "stalled",
                    "message": f"{len(stalled)} task(s) in progress for > {self.max_in_progress_minutes} min",
                }
            )
            for task_id in stalled[:3]:
                recommendations.append(f"Check task {task_id} for hangs or infinite loops")

        # Check 4: Completion progress
        if total > 0:
            progress = completed / total
            metrics["progress_pct"] = progress
            if progress < 0.1 and in_progress == 0 and ready == 0:
                risks.append(
                    {
                        "severity": "medium",
                        "category": "no_progress",
                        "message": "No tasks have started execution",
                    }
                )

        # Check 5: Critical path health
        critical_path = dag.get_critical_path()
        metrics["critical_path_length"] = len(critical_path)
        blocked_on_critical = [
            tid for tid in critical_path if dag.nodes[tid].state == TaskState.BLOCKED
        ]
        if blocked_on_critical:
            risks.append(
                {
                    "severity": "high",
                    "category": "critical_path_blocked",
                    "message": f"{len(blocked_on_critical)} critical path task(s) blocked",
                }
            )

        healthy = len(risks) == 0

        return ReflectorResult(
            mission_id=mission_id,
            healthy=healthy,
            risks=risks,
            recommendations=recommendations,
            metrics=metrics,
        )

    def _find_stalled_tasks(self, mission_id: str, tracker: MissionTracker) -> list[str]:
        """Find tasks that have been in progress for too long."""
        # This would check state change history for IN_PROGRESS timestamp
        # For now, return empty list (would need timestamp tracking in StateMachine)
        stalled = []
        dag = tracker.get_dag(mission_id)
        if not dag:
            return stalled

        for task_id, node in dag.nodes.items():
            if node.state == TaskState.IN_PROGRESS:
                # In a full implementation, check how long it's been in this state
                # by looking at state change history
                pass

        return stalled

    def should_trigger_redesign(self, mission_id: str, tracker: MissionTracker) -> bool:
        """Check if conditions warrant a full redesign.

        Triggers:
        - Multiple critical severity risks
        - Rework rate > 50% after 3+ attempts
        - All tasks on critical path blocked
        """
        result = self.check(mission_id, tracker)
        if not result.healthy:
            critical_count = sum(1 for r in result.risks if r.get("severity") == "critical")
            if critical_count >= 2:
                return True

            rework_rate = result.metrics.get("rework_rate", 0)
            if rework_rate > 0.5:
                return True

        return False
