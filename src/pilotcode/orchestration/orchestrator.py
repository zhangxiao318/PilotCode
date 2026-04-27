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
from dataclasses import dataclass
from typing import Any, Callable, Awaitable
from datetime import datetime, timezone

from .task_spec import Mission, TaskSpec, ComplexityLevel
from .state_machine import TaskState, StateMachine, Transition, InvalidTransitionError
from .dag import DagExecutor, DagNode
from .tracker import get_tracker
from .results import ExecutionResult
from .verifier.base import VerificationResult, Verdict


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
        self._task_completed_event = asyncio.Event()

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

    def clear_progress_callbacks(self) -> None:
        """Clear all registered progress callbacks."""
        self._progress_callbacks.clear()

    def _notify(self, event: str, data: dict) -> None:
        """Notify progress callbacks."""
        for cb in self._progress_callbacks:
            try:
                cb(event, data)
            except Exception:
                import logging

                logging.getLogger(__name__).exception("Progress callback failed for %s", event)

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
        """Execute a full mission with cascade failure detection and auto-retry.

        Returns summary of execution results.
        """
        self.set_mission_plan(mission)
        mid = mission.mission_id

        self._notify(
            "mission:started",
            {"mission_id": mid, "total_tasks": len(mission.all_tasks())},
        )
        mission_started_at = datetime.now(timezone.utc)

        # Initialize Reflector for periodic health checks
        from .rework.reflector import Reflector

        reflector = Reflector()
        last_health_check = asyncio.get_event_loop().time()
        HEALTH_CHECK_INTERVAL = 30.0  # seconds

        # Hook into state changes to detect task completion events
        def _on_task_complete(event: Any) -> None:
            if event.to_state in {
                TaskState.DONE,
                TaskState.REJECTED,
                TaskState.CANCELLED,
                TaskState.NEEDS_REWORK,
            }:
                self._task_completed_event.set()

        for sm in self.tracker._state_machines.get(mid, {}).values():
            sm.on_state_change(_on_task_complete)

        # Active worker tasks: asyncio.Task -> DagNode mapping
        active_workers: dict[asyncio.Task, DagNode] = {}

        # Seed initial ready tasks
        self._enqueue_ready(mid, active_workers)

        # Main event-driven execution loop
        while not self.tracker.all_done(mid):
            # --- Periodic health check ---
            now = asyncio.get_event_loop().time()
            if now - last_health_check > HEALTH_CHECK_INTERVAL:
                health = reflector.check(mid, self.tracker)
                if not health.healthy:
                    self._notify(
                        "mission:health_warning",
                        {
                            "mission_id": mid,
                            "risks": health.risks,
                            "recommendations": health.recommendations,
                        },
                    )
                    if reflector.should_trigger_redesign(mid, self.tracker):
                        self._notify(
                            "mission:redesign_triggered",
                            {"mission_id": mid, "reason": "Critical health risks detected"},
                        )
                last_health_check = now

            # --- Fill worker slots ---
            self._enqueue_ready(mid, active_workers)

            if not active_workers:
                # Nothing running and nothing ready — wait for completion event
                if self.tracker.all_done(mid):
                    break
                self._task_completed_event.clear()
                await self._task_completed_event.wait()
                continue

            # --- Wait for at least one worker to finish ---
            done, _ = await asyncio.wait(
                active_workers.keys(),
                return_when=asyncio.FIRST_COMPLETED,
            )

            for task in done:
                node = active_workers.pop(task)
                try:
                    await task
                except Exception as exc:
                    self._notify(
                        "task:exception",
                        {"mission_id": mid, "task_id": node.task_id, "error": str(exc)},
                    )

                # Handle NEEDS_REWORK
                sm = self.tracker.get_state_machine(mid, node.task_id)
                if sm and sm.state == TaskState.NEEDS_REWORK:
                    await self._smart_retry(mid, node.task_id)

        # Final summary
        snapshot = self.tracker.get_snapshot(mid)
        self._notify(
            "mission:completed",
            {"mission_id": mid, "snapshot": asdict(snapshot) if snapshot else {}},
        )

        # Collect task outputs and metrics for reporting
        task_outputs: dict[str, Any] = {}
        total_token_usage = 0
        dag = self.tracker.get_dag(mid)
        if dag:
            for task_id, node in dag.nodes.items():
                if node.result is not None:
                    task_outputs[task_id] = {
                        "title": node.task.title,
                        "output": node.result,
                        "artifacts": node.artifacts,
                    }
                exec_res = node.artifacts.get("_exec_result")
                if isinstance(exec_res, ExecutionResult):
                    total_token_usage += exec_res.token_usage

        mission_duration = (datetime.now(timezone.utc) - mission_started_at).total_seconds()

        metrics = {
            "mission_id": mid,
            "started_at": mission_started_at.isoformat(),
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "total_tasks": snapshot.total_tasks if snapshot else 0,
            "completed_tasks": snapshot.completed_tasks if snapshot else 0,
            "failed_tasks": snapshot.failed_tasks if snapshot else 0,
            "total_token_usage": total_token_usage,
            "total_duration_seconds": mission_duration,
        }

        return {
            "mission_id": mid,
            "snapshot": snapshot.to_dict() if snapshot else {},
            "task_outputs": task_outputs,
            "metrics": metrics,
        }

    def _enqueue_ready(self, mission_id: str, active_workers: dict[asyncio.Task, DagNode]) -> None:
        """Launch ready tasks until concurrency limit is reached."""
        while len(active_workers) < self.config.max_concurrent_workers:
            ready = self.tracker.get_ready_tasks(mission_id)
            launched = False
            for node in ready:
                if len(active_workers) >= self.config.max_concurrent_workers:
                    break
                if self._has_failed_dependency(mission_id, node):
                    self._cancel_downstream_tasks(mission_id, node.task_id)
                    continue
                # Skip if this task is already being executed
                if node.task_id in {n.task_id for n in active_workers.values()}:
                    continue
                # Skip if state machine shows this task is no longer pending
                # (e.g., after rework completion or state sync issues)
                sm = self.tracker.get_state_machine(mission_id, node.task_id)
                if sm and sm.state not in (TaskState.PENDING, TaskState.IN_PROGRESS):
                    continue
                task = asyncio.create_task(self._execute_task(mission_id, node))
                active_workers[task] = node
                launched = True
            if not launched:
                break

    async def _execute_task(self, mission_id: str, node: DagNode) -> None:
        """Execute a single task through the full P-EVR cycle."""
        task = node.task
        task_id = task.id
        sm = self.tracker.get_state_machine(mission_id, task_id)

        if not sm:
            return

        # Skip if not in a state where execution can begin
        if sm.state not in (TaskState.PENDING, TaskState.IN_PROGRESS):
            return

        try:
            async with self._semaphore:
                # 1. ASSIGN (skip if already IN_PROGRESS after rework)
                if sm.state == TaskState.IN_PROGRESS:
                    # Rework retry: already transitioned to IN_PROGRESS by _smart_retry
                    pass
                else:
                    try:
                        sm.transition(Transition.ASSIGN, actor="orchestrator")
                    except InvalidTransitionError:
                        return

                # 2. START (skip if already IN_PROGRESS after rework)
                if sm.state == TaskState.IN_PROGRESS:
                    pass
                else:
                    try:
                        sm.transition(Transition.START, actor="orchestrator")
                    except InvalidTransitionError:
                        return

                self._notify(
                    "task:started",
                    {"mission_id": mission_id, "task_id": task_id, "title": task.title},
                )

                # 3. EXECUTE (Worker) with timeout
                start_time = datetime.now(timezone.utc)
                try:
                    exec_result = await asyncio.wait_for(
                        self._run_worker(task),
                        timeout=task.timeout_seconds,
                    )
                except asyncio.TimeoutError:
                    elapsed = (datetime.now(timezone.utc) - start_time).total_seconds()
                    exec_result = ExecutionResult(
                        task_id=task.id,
                        success=False,
                        error=f"Task timed out after {task.timeout_seconds}s",
                        time_spent_seconds=elapsed,
                    )
                    self._notify(
                        "task:timeout",
                        {
                            "mission_id": mission_id,
                            "task_id": task_id,
                            "timeout": task.timeout_seconds,
                            "elapsed": elapsed,
                        },
                    )
                    # Store exec result for metrics even on timeout
                    dag = self.tracker.get_dag(mission_id)
                    if dag:
                        dag.nodes[task_id].artifacts["_exec_result"] = exec_result

                    # Cancel downstream tasks on timeout
                    self._cancel_downstream_tasks(mission_id, task_id)
                    # Transition to REJECTED
                    try:
                        sm.transition(
                            Transition.REJECT,
                            reason=f"Timeout after {task.timeout_seconds}s",
                            actor="orchestrator",
                        )
                    except InvalidTransitionError:
                        pass
                    return

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

                # Progressive disclosure: emit task execution details
                if getattr(exec_result, "details", None):
                    self._notify(
                        "task:details",
                        {
                            "mission_id": mission_id,
                            "task_id": task_id,
                            "details": exec_result.details,
                        },
                    )

                # 5. VERIFY
                await self._verify_task(mission_id, task, exec_result, sm)
        finally:
            # Sync DAG node state with state machine so downstream
            # dependency checks and ready-queue logic see the true state.
            if sm:
                dag = self.tracker.get_dag(mission_id)
                if dag:
                    dag.update_task_state(task_id, sm.state)

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
        l1: VerificationResult | None = None
        if self.config.enable_l1_verification:
            l1 = await self._run_verifier(1, task, exec_result)
            if not l1.passed:
                self._handle_verification_failure(mission_id, task, sm, l1)
                return

        # Auto-approve very simple tasks: skip L2/L3
        is_auto_simple = (
            self.config.auto_approve_simple
            and task.estimated_complexity == ComplexityLevel.VERY_SIMPLE
        )

        # L2: Tests
        l2: VerificationResult | None = None
        if self.config.enable_l2_verification and not is_auto_simple:
            l2 = await self._run_verifier(2, task, exec_result)
            if not l2.passed:
                self._handle_verification_failure(mission_id, task, sm, l2)
                return

        # L3: Code Review
        l3: VerificationResult | None = None
        if (
            self.config.enable_l3_verification
            and task.estimated_complexity.value >= 3
            and not is_auto_simple
        ):
            l3 = await self._run_verifier(3, task, exec_result)
            if not l3.passed:
                self._handle_verification_failure(mission_id, task, sm, l3)
                return

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
            # Store full ExecutionResult for retry analysis
            dag.nodes[task_id].artifacts["_exec_result"] = exec_result
            # Store verification results for runtime calibration
            if l1 is not None:
                dag.nodes[task_id].artifacts["_verification_1"] = l1
            if l2 is not None:
                dag.nodes[task_id].artifacts["_verification_2"] = l2
            if l3 is not None:
                dag.nodes[task_id].artifacts["_verification_3"] = l3

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
                verdict=Verdict.APPROVE,
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
                verdict=Verdict.REJECT,
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
        if v_result.verdict == Verdict.REJECT:
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

    # ------------------------------------------------------------------
    # Cascade failure & smart retry
    # ------------------------------------------------------------------

    def _has_failed_dependency(self, mission_id: str, node: DagNode) -> bool:
        """Check if any dependency of this node is in a terminal failure state."""
        dag = self.tracker.get_dag(mission_id)
        if not dag:
            return False
        for edge in dag.edges:
            if edge.to_task == node.task_id:
                dep_node = dag.nodes.get(edge.from_task)
                if dep_node and dep_node.state in {TaskState.REJECTED, TaskState.CANCELLED}:
                    return True
        return False

    def _cancel_downstream_tasks(self, mission_id: str, failed_task_id: str) -> None:
        """Recursively cancel all tasks that depend on a failed task."""
        dag = self.tracker.get_dag(mission_id)
        if not dag:
            return

        def _cancel_recursive(task_id: str) -> None:
            for edge in dag.edges:
                if edge.from_task == task_id:
                    downstream = edge.to_task
                    sm = self.tracker.get_state_machine(mission_id, downstream)
                    if sm and sm.state == TaskState.PENDING:
                        try:
                            sm.transition(Transition.CANCEL, actor="orchestrator")
                        except InvalidTransitionError:
                            pass
                        self._notify(
                            "task:cancelled_dependency_failure",
                            {
                                "mission_id": mission_id,
                                "task_id": downstream,
                                "failed_dep": task_id,
                            },
                        )
                    # Recursively cancel downstream of downstream
                    _cancel_recursive(downstream)

        _cancel_recursive(failed_task_id)

    def _count_rework_attempts(self, mission_id: str, task_id: str) -> int:
        """Count how many times this task has been retried."""
        dag = self.tracker.get_dag(mission_id)
        if not dag:
            return 0
        node = dag.get_node(task_id)
        if not node:
            return 0
        return node.artifacts.get("rework_count", 0)

    def _analyze_failure(self, task: TaskSpec, exec_result: ExecutionResult) -> dict[str, Any]:
        """Analyze why a task failed and suggest adjustments."""
        error = exec_result.error or ""
        output = exec_result.output or ""
        combined = (error + " " + output).lower()

        analysis = {
            "root_cause": "unknown",
            "suggested_adjustments": [],
            "escalate": False,
        }

        if "file not found" in combined or "no such file" in combined:
            analysis["root_cause"] = "missing_file"
            analysis["suggested_adjustments"].append(
                "Add file existence check or create missing files first"
            )
        elif "permission" in combined or "access denied" in combined:
            analysis["root_cause"] = "permission_error"
            analysis["suggested_adjustments"].append("Check workspace boundaries and permissions")
        elif "syntax" in combined or "indent" in combined or "unexpected" in combined:
            analysis["root_cause"] = "syntax_error"
            analysis["suggested_adjustments"].append(
                "Verify code syntax before writing; use smaller edits"
            )
        elif "import" in combined or "module" in combined:
            analysis["root_cause"] = "dependency_issue"
            analysis["suggested_adjustments"].append("Check existing imports and module structure")
        elif "test" in combined and ("fail" in combined or "error" in combined):
            analysis["root_cause"] = "test_failure"
            analysis["suggested_adjustments"].append(
                "Run tests locally before submitting; fix failing assertions"
            )
        elif not exec_result.success:
            analysis["root_cause"] = "execution_failure"
            analysis["suggested_adjustments"].append("Break task into smaller sub-tasks")

        return analysis

    def _adjust_task_for_retry(self, task: TaskSpec, analysis: dict[str, Any]) -> TaskSpec:
        """Create an adjusted copy of the task based on failure analysis."""
        from copy import deepcopy

        adjusted = deepcopy(task)

        # Add failure context to objective
        adjusted.objective += (
            f"\n\n[PREVIOUS ATTEMPT FAILED: {analysis['root_cause']}]\n"
            f"Adjustments: {', '.join(analysis['suggested_adjustments'])}"
        )

        # If syntax issues, reduce max_lines to force smaller edits
        if analysis["root_cause"] == "syntax_error":
            if adjusted.constraints.max_lines is None or adjusted.constraints.max_lines > 50:
                adjusted.constraints.max_lines = 50

        # If missing files, add must_use hint
        if analysis["root_cause"] == "missing_file":
            adjusted.constraints.must_use.append("FileRead before FileWrite")

        # Escalate complexity if needed
        if analysis["escalate"] and adjusted.estimated_complexity.value < 5:
            adjusted.estimated_complexity = ComplexityLevel(adjusted.estimated_complexity.value + 1)

        return adjusted

    async def _smart_retry(self, mission_id: str, task_id: str) -> None:
        """Intelligently retry a task with failure analysis and adjustments."""
        dag = self.tracker.get_dag(mission_id)
        node = dag.get_node(task_id) if dag else None
        if not node:
            return

        rework_count = node.artifacts.get("rework_count", 0) + 1
        node.artifacts["rework_count"] = rework_count

        if rework_count > self.config.max_rework_attempts:
            self._notify(
                "task:max_rework_exceeded",
                {"mission_id": mission_id, "task_id": task_id, "attempts": rework_count},
            )
            # Transition to REJECTED so downstream gets cancelled
            sm = self.tracker.get_state_machine(mission_id, task_id)
            if sm and sm.state == TaskState.NEEDS_REWORK:
                try:
                    sm.transition(
                        Transition.REJECT,
                        reason="Max rework attempts exceeded",
                        actor="orchestrator",
                    )
                except InvalidTransitionError:
                    pass
            self._cancel_downstream_tasks(mission_id, task_id)
            return

        # Analyze last failure
        last_result = node.artifacts.get("_exec_result")
        if isinstance(last_result, ExecutionResult):
            analysis = self._analyze_failure(node.task, last_result)
        else:
            analysis = {
                "root_cause": "unknown",
                "suggested_adjustments": ["Retry with fresh context"],
                "escalate": False,
            }

        self._notify(
            "task:retry_analysis",
            {
                "mission_id": mission_id,
                "task_id": task_id,
                "attempt": rework_count,
                "root_cause": analysis["root_cause"],
                "adjustments": analysis["suggested_adjustments"],
            },
        )

        # Adjust task
        adjusted_task = self._adjust_task_for_retry(node.task, analysis)
        adjusted_node = DagNode(task_id=task_id, task=adjusted_task)
        adjusted_node.state = TaskState.PENDING
        adjusted_node.depth = node.depth
        adjusted_node.artifacts = dict(node.artifacts)

        # Replace node in DAG
        dag.nodes[task_id] = adjusted_node

        # Reset state machine to PENDING so the main loop's _enqueue_ready
        # will re-schedule this task on the next iteration.
        # Do NOT synchronously await _execute_task here — that bypasses the
        # main event loop and causes a deadlock when the task fails again
        # (NEEDS_REWORK is not PENDING, so _enqueue_ready skips it, leaving
        # active_workers empty with no one to wake the event).
        sm = self.tracker.get_state_machine(mission_id, task_id)
        if sm:
            sm.state = TaskState.PENDING

        # Wake the main loop so it re-evaluates ready tasks immediately.
        self._task_completed_event.set()

    async def retry_task(self, mission_id: str, task_id: str) -> None:
        """Public API: retry a task that is in NEEDS_REWORK state."""
        await self._smart_retry(mission_id, task_id)

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
