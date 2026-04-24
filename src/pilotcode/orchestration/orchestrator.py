"""Core orchestrator for P-EVR: Plan-Execute-Verify-Reflect.

Drives the full lifecycle:
  Plan → DAG Build → Execute (Worker) → Verify (L1/L2/L3) → Reflect
                                    ↓
                              NEEDS_REWORK → Execute (retry)
                                    ↓
                              VERIFIED → Next batch
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any, Callable, Awaitable
from datetime import datetime, timezone

from .task_spec import Mission, TaskSpec, ComplexityLevel
from .state_machine import TaskState, StateMachine, Transition, InvalidTransitionError
from .dag import DagExecutor, DagNode
from .tracker import MissionTracker, get_tracker, AgentProgress


@dataclass
class OrchestratorConfig:
    """Configuration for the orchestrator."""

    max_concurrent_workers: int = 3
    auto_approve_simple: bool = True  # Auto-approve complexity=1 tasks
    enable_l1_verification: bool = True
    enable_l2_verification: bool = True
    enable_l3_verification: bool = True
    max_rework_attempts: int = 3
    db_path: str | None = None


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


@dataclass
class VerificationResult:
    """Result of verifying a task."""

    task_id: str
    level: int  # 1, 2, or 3
    passed: bool
    score: float = 0.0  # 0-100
    issues: list[dict[str, Any]] = field(default_factory=list)
    feedback: str = ""
    verdict: str = "PENDING"  # "APPROVE", "NEEDS_REWORK", "REJECT"


class Orchestrator:
    """Main orchestrator for P-EVR mission execution.

    Usage:
        orch = Orchestrator(config)
        mission = orch.plan(requirement="Implement OAuth2 API")
        result = await orch.run(mission)
    """

    def __init__(self, config: OrchestratorConfig | None = None):
        self.config = config or OrchestratorConfig()
        self.tracker = get_tracker(db_path=self.config.db_path)
        self._worker_registry: dict[str, Callable[[TaskSpec, dict], Awaitable[ExecutionResult]]] = (
            {}
        )
        self._verifier_registry: dict[
            int, Callable[[TaskSpec, ExecutionResult], Awaitable[VerificationResult]]
        ] = {}
        self._progress_callbacks: list[Callable[[str, dict], None]] = []
        self._semaphore = asyncio.Semaphore(self.config.max_concurrent_workers)

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register_worker(
        self,
        worker_type: str,
        handler: Callable[[TaskSpec, dict], Awaitable[ExecutionResult]],
    ) -> None:
        """Register a worker for a specific task type."""
        self._worker_registry[worker_type] = handler

    def register_verifier(
        self,
        level: int,
        handler: Callable[[TaskSpec, ExecutionResult], Awaitable[VerificationResult]],
    ) -> None:
        """Register a verifier for a specific level."""
        self._verifier_registry[level] = handler

    def on_progress(self, callback: Callable[[str, dict], None]) -> None:
        """Register progress callback."""
        self._progress_callbacks.append(callback)

    def _notify(self, event: str, data: dict) -> None:
        """Notify progress callbacks."""
        for cb in self._progress_callbacks:
            try:
                cb(event, data)
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Plan
    # ------------------------------------------------------------------

    def plan(self, requirement: str, mission_id: str | None = None) -> Mission:
        """Plan a mission from a requirement.

        This is a placeholder that creates a simple mission structure.
        In production, this would call an LLM Planner to decompose the requirement.
        """
        mid = mission_id or f"mission_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"
        mission = Mission(
            mission_id=mid,
            title=requirement[:80],
            requirement=requirement,
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        return mission

    def set_mission_plan(self, mission: Mission) -> None:
        """Set the planned mission and build DAG."""
        dag = DagExecutor(mission)
        dag.build()
        self.tracker.register_mission(mission, dag)

    # ------------------------------------------------------------------
    # Execute
    # ------------------------------------------------------------------

    async def run(self, mission: Mission) -> dict[str, Any]:
        """Execute a full mission.

        Returns summary of execution results.
        """
        self.set_mission_plan(mission)
        mid = mission.mission_id

        self._notify(
            "mission:started",
            {"mission_id": mid, "total_tasks": len(mission.all_tasks())},
        )

        # Main execution loop
        while not self.tracker.all_done(mid):
            ready = self.tracker.get_ready_tasks(mid)
            if not ready:
                # Check if anything is in progress
                snapshot = self.tracker.get_snapshot(mid)
                if snapshot and snapshot.in_progress_tasks == 0:
                    # Nothing ready, nothing in progress - possible deadlock or all blocked
                    blocked = self.tracker.get_blocked_tasks(mid)
                    if blocked:
                        self._notify(
                            "mission:blocked",
                            {"mission_id": mid, "blocked_count": len(blocked)},
                        )
                    break
                # Wait a bit and retry
                await asyncio.sleep(0.5)
                continue

            # Execute ready tasks (up to concurrency limit)
            tasks = [self._execute_task(mid, node) for node in ready]
            await asyncio.gather(*tasks, return_exceptions=True)

        # Final summary
        snapshot = self.tracker.get_snapshot(mid)
        self._notify(
            "mission:completed",
            {"mission_id": mid, "snapshot": asdict(snapshot) if snapshot else {}},
        )

        return {
            "mission_id": mid,
            "snapshot": snapshot.to_dict() if snapshot else {},
        }

    async def _execute_task(self, mission_id: str, node: DagNode) -> None:
        """Execute a single task through the full P-EVR cycle."""
        task = node.task
        task_id = task.id
        sm = self.tracker.get_state_machine(mission_id, task_id)

        if not sm:
            return

        # Skip if not pending
        if sm.state != TaskState.PENDING:
            return

        async with self._semaphore:
            # 1. ASSIGN
            try:
                sm.transition(Transition.ASSIGN, actor="orchestrator")
            except InvalidTransitionError:
                return

            # 2. START
            try:
                sm.transition(Transition.START, actor="orchestrator")
            except InvalidTransitionError:
                return

            self._notify(
                "task:started",
                {"mission_id": mission_id, "task_id": task_id, "title": task.title},
            )

            # 3. EXECUTE (Worker)
            start_time = datetime.now(timezone.utc)
            exec_result = await self._run_worker(task)
            elapsed = (datetime.now(timezone.utc) - start_time).total_seconds()

            # 4. SUBMIT
            try:
                sm.transition(Transition.SUBMIT, actor="worker")
            except InvalidTransitionError:
                return

            self._notify(
                "task:submitted",
                {
                    "mission_id": mission_id,
                    "task_id": task_id,
                    "success": exec_result.success,
                    "time_spent": elapsed,
                },
            )

            # 5. VERIFY
            await self._verify_task(mission_id, task, exec_result, sm)

    async def _run_worker(self, task: TaskSpec) -> ExecutionResult:
        """Run the appropriate worker for a task."""
        worker_type = task.worker_type
        if worker_type == "auto":
            worker_type = self._select_worker_type(task)

        handler = self._worker_registry.get(worker_type)
        if not handler:
            return ExecutionResult(
                task_id=task.id,
                success=False,
                error=f"No worker registered for type '{worker_type}'",
            )

        # Build working memory context
        context = {
            "objective": task.objective,
            "constraints": task.constraints,
            "acceptance_criteria": task.acceptance_criteria,
            "context_budget": task.context_budget,
        }

        try:
            return await handler(task, context)
        except Exception as e:
            return ExecutionResult(
                task_id=task.id,
                success=False,
                error=f"Worker execution failed: {e}",
            )

    def _select_worker_type(self, task: TaskSpec) -> str:
        """Auto-select worker type based on task complexity."""
        complexity = task.estimated_complexity
        if complexity == ComplexityLevel.VERY_SIMPLE:
            return "simple"
        elif complexity in (ComplexityLevel.SIMPLE, ComplexityLevel.MODERATE):
            return "standard"
        elif complexity == ComplexityLevel.COMPLEX:
            return "complex"
        else:
            return "complex"

    # ------------------------------------------------------------------
    # Verify
    # ------------------------------------------------------------------

    async def _verify_task(
        self,
        mission_id: str,
        task: TaskSpec,
        exec_result: ExecutionResult,
        sm: StateMachine,
    ) -> None:
        """Run verification pipeline for a task."""
        task_id = task.id

        # Begin review
        try:
            sm.transition(Transition.BEGIN_REVIEW, actor="verifier")
        except InvalidTransitionError:
            return

        # L1: Static analysis
        if self.config.enable_l1_verification:
            l1 = await self._run_verifier(1, task, exec_result)
            if not l1.passed:
                self._handle_verification_failure(mission_id, task, sm, l1)
                return

        # L2: Tests
        if self.config.enable_l2_verification:
            l2 = await self._run_verifier(2, task, exec_result)
            if not l2.passed:
                self._handle_verification_failure(mission_id, task, sm, l2)
                return

        # L3: Code Review
        if self.config.enable_l3_verification and task.estimated_complexity.value >= 3:
            l3 = await self._run_verifier(3, task, exec_result)
            if not l3.passed:
                self._handle_verification_failure(mission_id, task, sm, l3)
                return

        # Auto-approve very simple tasks
        if (
            self.config.auto_approve_simple
            and task.estimated_complexity == ComplexityLevel.VERY_SIMPLE
        ):
            pass  # Already passed L1

        # All verifications passed
        try:
            sm.transition(Transition.APPROVE, actor="verifier")
        except InvalidTransitionError:
            return

        try:
            sm.transition(Transition.COMPLETE, actor="orchestrator")
        except InvalidTransitionError:
            return

        # Update DAG with result
        dag = self.tracker.get_dag(mission_id)
        if dag:
            dag.update_task_result(task_id, exec_result.output, exec_result.artifacts)

        self._notify(
            "task:verified",
            {"mission_id": mission_id, "task_id": task_id},
        )

    async def _run_verifier(
        self, level: int, task: TaskSpec, exec_result: ExecutionResult
    ) -> VerificationResult:
        """Run a specific verification level."""
        handler = self._verifier_registry.get(level)
        if not handler:
            # No verifier registered - auto-pass
            return VerificationResult(
                task_id=task.id,
                level=level,
                passed=True,
                score=100.0,
                verdict="APPROVE",
            )

        try:
            return await handler(task, exec_result)
        except Exception as e:
            return VerificationResult(
                task_id=task.id,
                level=level,
                passed=False,
                score=0.0,
                feedback=f"Verifier error: {e}",
                verdict="REJECT",
            )

    def _handle_verification_failure(
        self,
        mission_id: str,
        task: TaskSpec,
        sm: StateMachine,
        v_result: VerificationResult,
    ) -> None:
        """Handle a verification failure."""
        task_id = task.id

        # Determine severity
        if v_result.verdict == "REJECT":
            # Critical - reject and potentially trigger redesign
            try:
                sm.transition(Transition.REJECT, reason=v_result.feedback, actor="verifier")
            except InvalidTransitionError:
                pass
            self._notify(
                "task:rejected",
                {
                    "mission_id": mission_id,
                    "task_id": task_id,
                    "level": v_result.level,
                    "feedback": v_result.feedback,
                },
            )
        else:
            # Needs rework
            try:
                sm.transition(
                    Transition.REQUEST_REWORK,
                    reason=v_result.feedback,
                    actor="verifier",
                )
            except InvalidTransitionError:
                pass
            self._notify(
                "task:needs_rework",
                {
                    "mission_id": mission_id,
                    "task_id": task_id,
                    "level": v_result.level,
                    "feedback": v_result.feedback,
                },
            )

    # ------------------------------------------------------------------
    # Rework
    # ------------------------------------------------------------------

    async def retry_task(self, mission_id: str, task_id: str) -> None:
        """Retry a task that is in NEEDS_REWORK state.

        This can be called after fixing issues identified during verification.
        """
        sm = self.tracker.get_state_machine(mission_id, task_id)
        if not sm or sm.state != TaskState.NEEDS_REWORK:
            return

        try:
            sm.transition(Transition.RESUME, actor="orchestrator")
        except InvalidTransitionError:
            return

        dag = self.tracker.get_dag(mission_id)
        if not dag:
            return

        node = dag.get_node(task_id)
        if node:
            await self._execute_task(mission_id, node)

    # ------------------------------------------------------------------
    # Cancel / Pause
    # ------------------------------------------------------------------

    def cancel_mission(self, mission_id: str) -> None:
        """Cancel all pending tasks in a mission."""
        dag = self.tracker.get_dag(mission_id)
        if not dag:
            return

        for task_id, node in dag.nodes.items():
            sm = self.tracker.get_state_machine(mission_id, task_id)
            if sm and sm.state in {TaskState.PENDING, TaskState.ASSIGNED}:
                try:
                    sm.transition(Transition.CANCEL, actor="user")
                except InvalidTransitionError:
                    pass

        self._notify("mission:cancelled", {"mission_id": mission_id})

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------

    def get_snapshot(self, mission_id: str) -> dict[str, Any] | None:
        """Get mission snapshot."""
        snap = self.tracker.get_snapshot(mission_id)
        return snap.to_dict() if snap else None


def asdict(obj: Any) -> dict:
    """Helper to convert dataclass to dict."""
    from dataclasses import asdict as _asdict

    return _asdict(obj)
