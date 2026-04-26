"""Comprehensive tests for P-EVR Orchestration framework.

Tests various complex plan combinations:
- Linear chains
- Parallel branches
- Diamond DAGs
- Multi-phase missions
- Rework cycles
- Verification pipelines
- Memory layers
"""

from __future__ import annotations

import sys
import os
import tempfile
import shutil
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from pilotcode.orchestration import (
    TaskSpec,
    Phase,
    Mission,
    Constraints,
    AcceptanceCriterion,
    TaskState,
    StateMachine,
    Transition,
    InvalidTransitionError,
    DagExecutor,
    MissionTracker,
    AgentProgress,
    Orchestrator,
    OrchestratorConfig,
    ExecutionResult,
)
from pilotcode.orchestration.verifier import (
    StaticAnalysisVerifier,
    CodeReviewVerifier,
)
from pilotcode.orchestration.context import (
    ProjectMemory,
    SessionMemory,
    WorkingMemory,
)
from pilotcode.orchestration.workers import (
    SimpleWorker,
    DebugWorker,
    WorkerContext,
)
from pilotcode.orchestration.rework import (
    ReworkContext,
    ReworkAttempt,
    ReworkSeverity,
    Reflector,
    ReflectorResult,
)

# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def tmpdir():
    d = tempfile.mkdtemp(prefix="pilotcode_orchestration_test_")
    yield d
    shutil.rmtree(d, ignore_errors=True)


@pytest.fixture
def tracker():
    t = MissionTracker()
    yield t
    # Cleanup
    from pilotcode.orchestration.tracker import reset_tracker

    reset_tracker()


@pytest.fixture
def simple_mission():
    """A simple linear mission: A → B → C"""
    return Mission(
        mission_id="test_linear",
        title="Linear Mission",
        requirement="Do A, then B, then C",
        phases=[
            Phase(
                phase_id="p1",
                title="Phase 1",
                description="Sequential tasks",
                tasks=[
                    TaskSpec(id="A", title="Task A", objective="Do A", outputs=["a.txt"]),
                    TaskSpec(
                        id="B",
                        title="Task B",
                        objective="Do B",
                        dependencies=["A"],
                        outputs=["b.txt"],
                    ),
                    TaskSpec(
                        id="C",
                        title="Task C",
                        objective="Do C",
                        dependencies=["B"],
                        outputs=["c.txt"],
                    ),
                ],
            ),
        ],
    )


@pytest.fixture
def parallel_mission():
    """A mission with parallel branches: A, B → C"""
    return Mission(
        mission_id="test_parallel",
        title="Parallel Mission",
        requirement="Do A and B in parallel, then C",
        phases=[
            Phase(
                phase_id="p1",
                title="Phase 1",
                description="Parallel tasks",
                tasks=[
                    TaskSpec(id="A", title="Task A", objective="Do A", outputs=["a.txt"]),
                    TaskSpec(id="B", title="Task B", objective="Do B", outputs=["b.txt"]),
                    TaskSpec(
                        id="C",
                        title="Task C",
                        objective="Do C",
                        dependencies=["A", "B"],
                        outputs=["c.txt"],
                    ),
                ],
            ),
        ],
    )


@pytest.fixture
def diamond_mission():
    """Diamond DAG: A → B, C → D"""
    return Mission(
        mission_id="test_diamond",
        title="Diamond Mission",
        requirement="A feeds B and C, both feed D",
        phases=[
            Phase(
                phase_id="p1",
                title="Phase 1",
                description="Diamond DAG",
                tasks=[
                    TaskSpec(id="A", title="Task A", objective="Do A", outputs=["a.txt"]),
                    TaskSpec(
                        id="B",
                        title="Task B",
                        objective="Do B",
                        dependencies=["A"],
                        outputs=["b.txt"],
                    ),
                    TaskSpec(
                        id="C",
                        title="Task C",
                        objective="Do C",
                        dependencies=["A"],
                        outputs=["c.txt"],
                    ),
                    TaskSpec(
                        id="D",
                        title="Task D",
                        objective="Do D",
                        dependencies=["B", "C"],
                        outputs=["d.txt"],
                    ),
                ],
            ),
        ],
    )


@pytest.fixture
def multi_phase_mission():
    """Multi-phase mission with cross-phase dependencies."""
    return Mission(
        mission_id="test_multiphase",
        title="Multi-Phase Mission",
        requirement="OAuth2 API implementation",
        phases=[
            Phase(
                phase_id="infra",
                title="Infrastructure",
                description="Setup",
                tasks=[
                    TaskSpec(
                        id="1.1",
                        title="Schema",
                        objective="Design DB schema",
                        outputs=["schema.sql"],
                    ),
                    TaskSpec(
                        id="1.2",
                        title="Config",
                        objective="Setup config",
                        dependencies=["1.1"],
                        outputs=["config.py"],
                    ),
                ],
            ),
            Phase(
                phase_id="core",
                title="Core Domain",
                description="Business logic",
                tasks=[
                    TaskSpec(
                        id="2.1",
                        title="User Entity",
                        objective="User model",
                        dependencies=["1.2"],
                        outputs=["user.py"],
                    ),
                    TaskSpec(
                        id="2.2",
                        title="Password Service",
                        objective="Hash passwords",
                        dependencies=["1.2"],
                        outputs=["password.py"],
                    ),
                    TaskSpec(
                        id="2.3",
                        title="JWT Service",
                        objective="JWT handling",
                        dependencies=["1.2"],
                        outputs=["jwt.py"],
                    ),
                ],
            ),
            Phase(
                phase_id="api",
                title="API Layer",
                description="REST endpoints",
                tasks=[
                    TaskSpec(
                        id="3.1",
                        title="Register",
                        objective="/register endpoint",
                        dependencies=["2.1", "2.2"],
                        outputs=["register.py"],
                    ),
                    TaskSpec(
                        id="3.2",
                        title="Login",
                        objective="/login endpoint",
                        dependencies=["2.1", "2.2", "2.3"],
                        outputs=["login.py"],
                    ),
                    TaskSpec(
                        id="3.3",
                        title="Refresh",
                        objective="/refresh endpoint",
                        dependencies=["2.3"],
                        outputs=["refresh.py"],
                    ),
                ],
            ),
            Phase(
                phase_id="verify",
                title="Verification",
                description="Testing",
                tasks=[
                    TaskSpec(
                        id="4.1",
                        title="E2E Tests",
                        objective="End-to-end tests",
                        dependencies=["3.1", "3.2", "3.3"],
                        outputs=["test_e2e.py"],
                    ),
                    TaskSpec(
                        id="4.2",
                        title="Security Audit",
                        objective="Security check",
                        dependencies=["3.1", "3.2", "3.3"],
                        outputs=["audit.md"],
                    ),
                ],
            ),
        ],
    )


@pytest.fixture
def complex_dag_mission():
    """Complex DAG with multiple paths and merge points."""
    tasks = [
        TaskSpec(id="T1", title="T1", objective="Root", outputs=["t1.txt"]),
        TaskSpec(
            id="T2", title="T2", objective="Branch 1A", dependencies=["T1"], outputs=["t2.txt"]
        ),
        TaskSpec(
            id="T3", title="T3", objective="Branch 1B", dependencies=["T1"], outputs=["t3.txt"]
        ),
        TaskSpec(
            id="T4", title="T4", objective="Branch 2A", dependencies=["T2"], outputs=["t4.txt"]
        ),
        TaskSpec(
            id="T5", title="T5", objective="Branch 2B", dependencies=["T2"], outputs=["t5.txt"]
        ),
        TaskSpec(
            id="T6", title="T6", objective="Merge 1", dependencies=["T3", "T4"], outputs=["t6.txt"]
        ),
        TaskSpec(
            id="T7", title="T7", objective="Merge 2", dependencies=["T5", "T6"], outputs=["t7.txt"]
        ),
        TaskSpec(id="T8", title="T8", objective="Leaf", dependencies=["T7"], outputs=["t8.txt"]),
    ]
    return Mission(
        mission_id="test_complex",
        title="Complex DAG",
        requirement="Multiple merge points",
        phases=[Phase(phase_id="p1", title="All", description="Complex", tasks=tasks)],
    )


# ============================================================================
# Test Suite 1: TaskSpec & Data Models
# ============================================================================


class TestTaskSpec:
    def test_task_spec_creation(self):
        t = TaskSpec(id="test", title="Test", objective="Do something")
        assert t.id == "test"
        assert t.estimated_complexity.value == 3

    def test_task_spec_serialization(self):
        t = TaskSpec(
            id="test",
            title="Test",
            objective="Do",
            constraints=Constraints(max_lines=100, must_use=["async"]),
            acceptance_criteria=[AcceptanceCriterion(description="Works")],
        )
        d = t.to_dict()
        t2 = TaskSpec.from_dict(d)
        assert t2.id == t.id
        assert t2.constraints.max_lines == 100

    def test_mission_flatten(self):
        m = Mission(
            mission_id="m1",
            title="Test",
            requirement="R",
            phases=[
                Phase("p1", "P1", "D1", tasks=[TaskSpec("A", "A", "A")]),
                Phase("p2", "P2", "D2", tasks=[TaskSpec("B", "B", "B")]),
            ],
        )
        assert len(m.all_tasks()) == 2
        assert m.get_task("A") is not None
        assert m.get_task("B") is not None
        assert m.get_task("C") is None


# ============================================================================
# Test Suite 2: State Machine
# ============================================================================


class TestStateMachine:
    def test_basic_flow(self):
        sm = StateMachine("task1")
        assert sm.state == TaskState.PENDING

        sm.transition(Transition.ASSIGN)
        assert sm.state == TaskState.ASSIGNED

        sm.transition(Transition.START)
        assert sm.state == TaskState.IN_PROGRESS

        sm.transition(Transition.SUBMIT)
        assert sm.state == TaskState.SUBMITTED

        sm.transition(Transition.BEGIN_REVIEW)
        assert sm.state == TaskState.UNDER_REVIEW

        sm.transition(Transition.APPROVE)
        assert sm.state == TaskState.VERIFIED

        sm.transition(Transition.COMPLETE)
        assert sm.state == TaskState.DONE

        assert sm.is_terminal()
        assert sm.is_verified()

    def test_rework_flow(self):
        sm = StateMachine("task1")
        sm.transition(Transition.ASSIGN)
        sm.transition(Transition.START)
        sm.transition(Transition.SUBMIT)
        sm.transition(Transition.BEGIN_REVIEW)
        sm.transition(Transition.REQUEST_REWORK)
        assert sm.state == TaskState.NEEDS_REWORK

        sm.transition(Transition.RESUME)
        assert sm.state == TaskState.IN_PROGRESS

    def test_invalid_transition(self):
        sm = StateMachine("task1")
        with pytest.raises(InvalidTransitionError):
            sm.transition(Transition.START)  # Can't start without assigning

    def test_history(self):
        sm = StateMachine("task1")
        sm.transition(Transition.ASSIGN, reason="auto")
        sm.transition(Transition.START, reason="worker_ready")
        hist = sm.get_history()
        assert len(hist) == 2
        assert hist[0].from_state == TaskState.PENDING
        assert hist[0].to_state == TaskState.ASSIGNED

    def test_valid_transitions(self):
        sm = StateMachine("task1")
        assert Transition.ASSIGN in sm.get_valid_transitions()
        assert Transition.START not in sm.get_valid_transitions()

    def test_can_transition(self):
        sm = StateMachine("task1")
        assert sm.can_transition(Transition.ASSIGN)
        assert not sm.can_transition(Transition.START)


# ============================================================================
# Test Suite 3: DAG Engine
# ============================================================================


class TestDagEngine:
    def test_linear_topological_sort(self, simple_mission):
        dag = DagExecutor(simple_mission)
        order = dag.build()
        assert order == ["A", "B", "C"]

    def test_parallel_topological_sort(self, parallel_mission):
        dag = DagExecutor(parallel_mission)
        order = dag.build()
        assert order[0] == "A" or order[0] == "B"
        assert "C" in order
        assert order.index("C") > order.index("A")
        assert order.index("C") > order.index("B")

    def test_diamond_topological_sort(self, diamond_mission):
        dag = DagExecutor(diamond_mission)
        order = dag.build()
        assert order[0] == "A"
        assert order[-1] == "D"
        assert order.index("D") > order.index("B")
        assert order.index("D") > order.index("C")

    def test_multi_phase_topological_sort(self, multi_phase_mission):
        dag = DagExecutor(multi_phase_mission)
        order = dag.build()
        # 1.1 must come before 1.2
        assert order.index("1.1") < order.index("1.2")
        # 1.2 must come before 2.x
        assert order.index("1.2") < order.index("2.1")
        # 2.x must come before 3.x
        assert order.index("2.1") < order.index("3.1")
        # 3.x must come before 4.x
        assert order.index("3.1") < order.index("4.1")

    def test_complex_dag_topological_sort(self, complex_dag_mission):
        dag = DagExecutor(complex_dag_mission)
        order = dag.build()
        assert order[0] == "T1"
        assert order[-1] == "T8"
        # T6 depends on T3 and T4
        assert order.index("T6") > order.index("T3")
        assert order.index("T6") > order.index("T4")
        # T7 depends on T5 and T6
        assert order.index("T7") > order.index("T5")
        assert order.index("T7") > order.index("T6")

    def test_cycle_detection(self):
        bad_mission = Mission(
            mission_id="bad",
            title="Bad",
            requirement="Circular",
            phases=[
                Phase(
                    phase_id="p1",
                    title="P1",
                    description="Cycle",
                    tasks=[
                        TaskSpec(id="A", title="A", objective="A", dependencies=["B"]),
                        TaskSpec(id="B", title="B", objective="B", dependencies=["A"]),
                    ],
                ),
            ],
        )
        dag = DagExecutor(bad_mission)
        with pytest.raises(ValueError) as exc:
            dag.build()
        assert "Cycle" in str(exc.value)

    def test_ready_tasks(self, parallel_mission):
        dag = DagExecutor(parallel_mission)
        dag.build()
        ready = dag.get_ready_tasks()
        assert len(ready) == 2
        assert {n.task_id for n in ready} == {"A", "B"}

        # Mark A as verified
        dag.update_task_state("A", TaskState.VERIFIED)
        ready = dag.get_ready_tasks()
        assert len(ready) == 1
        assert ready[0].task_id == "B"

        # Mark B as verified
        dag.update_task_state("B", TaskState.VERIFIED)
        ready = dag.get_ready_tasks()
        assert len(ready) == 1
        assert ready[0].task_id == "C"

    def test_blocked_tasks(self, parallel_mission):
        dag = DagExecutor(parallel_mission)
        dag.build()
        blocked = dag.get_blocked_tasks()
        # C is blocked by A and B
        assert len(blocked) == 1
        assert blocked[0][0].task_id == "C"
        assert set(blocked[0][1]) == {"A", "B"}

    def test_execution_waves(self, diamond_mission):
        dag = DagExecutor(diamond_mission)
        dag.build()
        waves = dag.get_execution_path()
        assert waves[0] == ["A"]  # Wave 1
        assert set(waves[1]) == {"B", "C"}  # Wave 2 (parallel)
        assert waves[2] == ["D"]  # Wave 3

    def test_critical_path(self, complex_dag_mission):
        dag = DagExecutor(complex_dag_mission)
        dag.build()
        cp = dag.get_critical_path()
        # Critical path should be T1 → T2 → T4 → T6 → T7 → T8 (length 6)
        assert len(cp) == 6
        assert cp[0] == "T1"
        assert cp[-1] == "T8"

    def test_all_done(self, simple_mission):
        dag = DagExecutor(simple_mission)
        dag.build()
        assert not dag.all_done()
        for tid in ["A", "B", "C"]:
            dag.update_task_state(tid, TaskState.DONE)
        assert dag.all_done()


# ============================================================================
# Test Suite 4: Mission Tracker
# ============================================================================


class TestMissionTracker:
    def test_register_mission(self, tracker, simple_mission):
        tracker.register_mission(simple_mission)
        assert tracker.get_mission("test_linear") is not None
        assert tracker.get_dag("test_linear") is not None

    def test_state_machine_tracking(self, tracker, simple_mission):
        tracker.register_mission(simple_mission)
        sm = tracker.get_state_machine("test_linear", "A")
        assert sm is not None
        assert sm.state == TaskState.PENDING

    def test_get_ready_tasks(self, tracker, parallel_mission):
        tracker.register_mission(parallel_mission)
        ready = tracker.get_ready_tasks("test_parallel")
        assert len(ready) == 2

    def test_get_blocked_tasks(self, tracker, parallel_mission):
        tracker.register_mission(parallel_mission)
        blocked = tracker.get_blocked_tasks("test_parallel")
        assert len(blocked) == 1
        assert blocked[0].task_id == "C"

    def test_snapshot(self, tracker, simple_mission):
        tracker.register_mission(simple_mission)
        snap = tracker.get_snapshot("test_linear")
        assert snap is not None
        assert snap.total_tasks == 3
        assert snap.status == "pending"

    def test_agent_progress(self, tracker):
        progress = AgentProgress(
            agent_id="agent1",
            agent_type="coder",
            current_task_id="T1",
            status="running",
            progress_pct=50.0,
        )
        tracker.update_agent_progress(progress)
        fetched = tracker.get_agent_progress("agent1")
        assert fetched is not None
        assert fetched.progress_pct == 50.0

    def test_event_subscription(self, tracker, simple_mission):
        events = []
        tracker.on_event(lambda t, d: events.append((t, d)))
        tracker.register_mission(simple_mission)
        assert len(events) > 0
        assert events[0][0] == "mission:registered"


# ============================================================================
# Test Suite 5: Orchestrator (Integration)
# ============================================================================


@pytest.mark.asyncio
class TestOrchestrator:
    async def test_orchestrator_simple_run(self, simple_mission, tmpdir):
        config = OrchestratorConfig(
            max_concurrent_workers=3,
            enable_l3_verification=False,
            auto_approve_simple=True,
        )
        orch = Orchestrator(config)

        # Register a mock worker
        async def mock_worker(task, ctx):
            return ExecutionResult(
                task_id=task.id,
                success=True,
                output={"mock": True},
                artifacts={},
            )

        orch.register_worker("simple", mock_worker)
        orch.register_worker("standard", mock_worker)
        orch.register_worker("complex", mock_worker)

        # Override outputs to not require real files
        for task in simple_mission.all_tasks():
            task.outputs = []

        result = await orch.run(simple_mission)
        assert result["mission_id"] == "test_linear"
        snap = result["snapshot"]
        assert snap["total_tasks"] == 3
        # All should be done (auto-approve + mock worker)
        assert snap["completed_tasks"] == 3

    async def test_orchestrator_parallel_run(self, parallel_mission, tmpdir):
        config = OrchestratorConfig(
            max_concurrent_workers=3,
            enable_l3_verification=False,
            auto_approve_simple=True,
        )
        orch = Orchestrator(config)

        execution_order = []

        async def tracking_worker(task, ctx):
            execution_order.append(task.id)
            return ExecutionResult(task_id=task.id, success=True, output={})

        orch.register_worker("simple", tracking_worker)
        orch.register_worker("standard", tracking_worker)

        for task in parallel_mission.all_tasks():
            task.outputs = []

        await orch.run(parallel_mission)

        # A and B should execute before C
        assert execution_order.index("C") > execution_order.index("A")
        assert execution_order.index("C") > execution_order.index("B")

    async def test_orchestrator_diamond_run(self, diamond_mission, tmpdir):
        config = OrchestratorConfig(
            max_concurrent_workers=3,
            enable_l3_verification=False,
            auto_approve_simple=True,
        )
        orch = Orchestrator(config)

        async def mock_worker(task, ctx):
            return ExecutionResult(task_id=task.id, success=True, output={})

        orch.register_worker("simple", mock_worker)
        orch.register_worker("standard", mock_worker)

        for task in diamond_mission.all_tasks():
            task.outputs = []

        result = await orch.run(diamond_mission)
        snap = result["snapshot"]
        assert snap["total_tasks"] == 4
        assert snap["completed_tasks"] == 4

    async def test_orchestrator_complex_dag(self, complex_dag_mission, tmpdir):
        config = OrchestratorConfig(
            max_concurrent_workers=3,
            enable_l3_verification=False,
            auto_approve_simple=True,
        )
        orch = Orchestrator(config)

        async def mock_worker(task, ctx):
            return ExecutionResult(task_id=task.id, success=True, output={})

        for wt in ["simple", "standard", "complex", "debug"]:
            orch.register_worker(wt, mock_worker)

        for task in complex_dag_mission.all_tasks():
            task.outputs = []

        result = await orch.run(complex_dag_mission)
        snap = result["snapshot"]
        assert snap["total_tasks"] == 8
        assert snap["completed_tasks"] == 8

    async def test_orchestrator_multi_phase(self, multi_phase_mission, tmpdir):
        config = OrchestratorConfig(
            max_concurrent_workers=3,
            enable_l3_verification=False,
            auto_approve_simple=True,
        )
        orch = Orchestrator(config)

        async def mock_worker(task, ctx):
            return ExecutionResult(task_id=task.id, success=True, output={})

        for wt in ["simple", "standard", "complex", "debug"]:
            orch.register_worker(wt, mock_worker)

        for task in multi_phase_mission.all_tasks():
            task.outputs = []

        result = await orch.run(multi_phase_mission)
        snap = result["snapshot"]
        assert snap["total_tasks"] == 10
        assert snap["completed_tasks"] == 10

    async def test_progress_callbacks(self, simple_mission):
        config = OrchestratorConfig(max_concurrent_workers=1, enable_l3_verification=False)
        orch = Orchestrator(config)

        events = []
        orch.on_progress(lambda e, d: events.append(e))

        async def mock_worker(task, ctx):
            return ExecutionResult(task_id=task.id, success=True, output={})

        orch.register_worker("simple", mock_worker)
        orch.register_worker("standard", mock_worker)

        for task in simple_mission.all_tasks():
            task.outputs = []

        await orch.run(simple_mission)

        assert "mission:started" in events
        assert "mission:completed" in events
        assert any("task:started" in e for e in events)
        assert any("task:verified" in e for e in events)

    async def test_cancel_mission(self, simple_mission):
        config = OrchestratorConfig(max_concurrent_workers=1, enable_l3_verification=False)
        orch = Orchestrator(config)
        orch.set_mission_plan(simple_mission)
        orch.cancel_mission("test_linear")

        sm = orch.tracker.get_state_machine("test_linear", "A")
        assert sm.state == TaskState.CANCELLED

    async def test_smart_retry_re_executes_task(self, simple_mission, tmpdir):
        """Verify that _smart_retry correctly re-executes a task after NEEDS_REWORK.

        Regression test: _execute_task used to fail with InvalidTransitionError
        when START was called on a task already in IN_PROGRESS (after RESUME).
        """
        config = OrchestratorConfig(
            max_concurrent_workers=1,
            enable_l3_verification=False,
            auto_approve_simple=False,
            max_rework_attempts=3,
        )
        orch = Orchestrator(config)

        target_file = os.path.join(tmpdir, "output.txt")

        task_calls = {"A": 0, "B": 0, "C": 0}

        async def flaky_worker(task, ctx):
            task_calls[task.id] += 1
            if task.id == "A" and task_calls[task.id] == 1:
                # First call for A: fail to create the file → L1 verification fails
                return ExecutionResult(
                    task_id=task.id,
                    success=True,  # worker itself succeeded, but file missing
                    output={},
                )
            # Subsequent calls: create the file → L1 verification passes
            with open(target_file, "w") as f:
                f.write("done")
            return ExecutionResult(
                task_id=task.id,
                success=True,
                output={},
            )

        orch.register_worker("simple", flaky_worker)
        orch.register_worker("standard", flaky_worker)

        # Register L1 verifier so missing outputs are caught
        from pilotcode.orchestration.verifier import StaticAnalysisVerifier

        l1_verifier = StaticAnalysisVerifier()
        orch.register_verifier(1, lambda task, result: l1_verifier.verify(task, result))

        # Set up the first task to require a specific output file
        for task in simple_mission.all_tasks():
            task.outputs = [target_file]

        result = await orch.run(simple_mission)
        snap = result["snapshot"]

        # Task A should have been retried (initial fail + retry success)
        assert task_calls["A"] == 2, f"Expected 2 calls for A, got {task_calls['A']}"
        assert task_calls["B"] == 1
        assert task_calls["C"] == 1
        # Mission should complete (first task retried and passed; B, C pass)
        assert snap["completed_tasks"] == 3


# ============================================================================
# Test Suite 6: Verifiers
# ============================================================================


@pytest.mark.asyncio
class TestVerifiers:
    async def test_l1_static_missing_output(self, tmpdir):
        v = StaticAnalysisVerifier()
        task = TaskSpec(
            id="test",
            title="Test",
            objective="Create file",
            outputs=[os.path.join(tmpdir, "nonexistent.txt")],
        )
        result = await v.verify(task, ExecutionResult(task_id="test", success=True, output={}))
        assert not result.passed
        assert result.level == 1
        assert any("not found" in i["message"].lower() for i in result.issues)

    async def test_l1_static_line_limit(self, tmpdir):
        v = StaticAnalysisVerifier()
        path = os.path.join(tmpdir, "toolong.txt")
        with open(path, "w") as f:
            f.write("\n".join([f"line {i}" for i in range(100)]))

        task = TaskSpec(
            id="test",
            title="Test",
            objective="Create short file",
            outputs=[path],
            constraints=Constraints(max_lines=50),
        )
        result = await v.verify(task, ExecutionResult(task_id="test", success=True, output={}))
        assert not result.passed
        assert any("lines" in i["message"] for i in result.issues)

    async def test_l1_static_forbidden_pattern(self, tmpdir):
        v = StaticAnalysisVerifier()
        path = os.path.join(tmpdir, "bad.py")
        with open(path, "w") as f:
            f.write("password = 'secret123'\n")

        task = TaskSpec(
            id="test",
            title="Test",
            objective="Safe code",
            outputs=[path],
            constraints=Constraints(forbidden_patterns=[r"password\s*=\s*['\"]"]),
        )
        result = await v.verify(task, ExecutionResult(task_id="test", success=True, output={}))
        # Forbidden pattern triggers warning but score may still be >=60
        assert any("forbidden" in i["message"].lower() for i in result.issues)

    async def test_l3_review_objective_alignment(self, tmpdir):
        v = CodeReviewVerifier()
        path = os.path.join(tmpdir, "code.py")
        with open(path, "w") as f:
            f.write("def jwt_sign(payload, secret):\n    return 'token'\n")

        task = TaskSpec(
            id="test",
            title="JWT",
            objective="Implement JWT signing with HMAC",
            outputs=[path],
            acceptance_criteria=[AcceptanceCriterion(description="Uses HMAC")],
        )
        result = await v.verify(task, ExecutionResult(task_id="test", success=True, output={}))
        assert result.level == 3
        assert result.score > 0


# ============================================================================
# Test Suite 7: Memory Layers
# ============================================================================


class TestMemoryLayers:
    def test_project_memory_save_load(self, tmpdir):
        pm = ProjectMemory(project_path=tmpdir)
        pm.tech_stack = ["Python", "FastAPI"]
        pm.architecture_patterns = ["Repository Pattern"]
        pm.save()

        pm2 = ProjectMemory.load(tmpdir)
        assert pm2.tech_stack == ["Python", "FastAPI"]

    def test_project_memory_learn(self, tmpdir):
        pm = ProjectMemory(project_path=tmpdir)
        pm.learn_from_rework("Use pydantic for validation", "auth module", 0.9)
        assert len(pm.learned_patterns) == 1

    def test_session_memory_archive(self, tmpdir):
        sm = SessionMemory(archive_dir=os.path.join(tmpdir, "sessions"))
        mission = Mission("m1", "Test", "R")
        sm.start_session(mission)
        sm.update_task_state("m1", "A", TaskState.VERIFIED)
        sm.record_artifact("m1", "A", ["a.txt"])

        path = sm.archive_session("m1")
        assert path is not None
        assert os.path.exists(os.path.join(path, "mission.json"))

    def test_working_memory_trace(self):
        wm = WorkingMemory("task1", "Do something")
        wm.add_trace("CREATE", "file.py", {"lines": 10})
        wm.add_trace("WRITE", "file.py", {"func": "main"})
        assert len(wm.trace) == 2
        assert wm.get_recent_trace(1)[0].operation == "WRITE"

    def test_working_memory_focus(self):
        wm = WorkingMemory("task1", "Do something")
        wm.set_focus("Implement auth")
        wm.set_focus("Add tests")
        assert wm.current_focus == "Add tests"
        assert "Implement auth" in wm.focus_history

    def test_working_memory_summary(self):
        wm = WorkingMemory("task1", "Do something")
        wm.metadata["outcome"] = "success"
        wm.metadata["key_decisions"] = ["Use JWT"]
        summary = wm.to_summary()
        assert summary.task_id == "task1"
        assert summary.outcome == "success"


# ============================================================================
# Test Suite 8: Rework & Reflection
# ============================================================================


class TestRework:
    def test_rework_context_can_retry(self):
        rc = ReworkContext(original_task_id="T1", max_attempts=3)
        assert rc.can_retry()
        rc.add_attempt(ReworkAttempt(attempt_number=1))
        assert rc.can_retry()
        rc.add_attempt(ReworkAttempt(attempt_number=2))
        rc.add_attempt(ReworkAttempt(attempt_number=3))
        assert not rc.can_retry()

    def test_rework_context_strategy_minor(self):
        rc = ReworkContext(original_task_id="T1", severity=ReworkSeverity.MINOR)
        strategy = rc.get_retry_strategy()
        assert strategy["worker_type"] == "simple"

    def test_rework_context_strategy_critical(self):
        rc = ReworkContext(original_task_id="T1", severity=ReworkSeverity.CRITICAL)
        strategy = rc.get_retry_strategy()
        assert strategy["trigger_redesign"] is True
        assert strategy["worker_type"] == "complex"

    def test_rework_context_lessons(self):
        rc = ReworkContext(original_task_id="T1")
        rc.add_attempt(ReworkAttempt(attempt_number=1, review_feedback="Missing error handling"))
        rc.add_attempt(ReworkAttempt(attempt_number=2, review_feedback="Still missing tests"))
        lesson = rc.generate_lesson()
        assert "Missing error handling" in lesson
        assert "Still missing tests" in lesson


class TestReflector:
    def test_reflector_healthy(self, tracker, simple_mission):
        tracker.register_mission(simple_mission)
        ref = Reflector()
        result = ref.check("test_linear", tracker)
        assert isinstance(result, ReflectorResult)
        # All pending, nothing blocked - should be healthy or have minor issues
        assert result.metrics["total_tasks"] == 3

    def test_reflector_deadlock(self, tracker, parallel_mission):
        tracker.register_mission(parallel_mission)
        # Mark A and B as cancelled - C is pending but its deps are not satisfied
        dag = tracker.get_dag("test_parallel")
        dag.update_task_state("A", TaskState.CANCELLED)
        dag.update_task_state("B", TaskState.CANCELLED)
        # C is still pending, but its deps are CANCELLED not VERIFIED/DONE

        ref = Reflector()
        result = ref.check("test_parallel", tracker)
        # C cannot proceed because deps are cancelled
        assert result.metrics["ready"] == 0
        assert result.metrics["in_progress"] == 0
        assert not result.healthy

    def test_reflector_critical_path_blocked(self, tracker, diamond_mission):
        tracker.register_mission(diamond_mission)
        dag = tracker.get_dag("test_diamond")
        dag.update_task_state("A", TaskState.VERIFIED)
        dag.update_task_state("B", TaskState.BLOCKED)
        dag.update_task_state("C", TaskState.BLOCKED)

        ref = Reflector()
        result = ref.check("test_diamond", tracker)
        assert any(r["category"] == "critical_path_blocked" for r in result.risks)

    def test_should_trigger_redesign(self, tracker, simple_mission):
        tracker.register_mission(simple_mission)
        ref = Reflector(max_rework_rate=0.1)
        # All tasks in NEEDS_REWORK
        dag = tracker.get_dag("test_linear")
        for tid in ["A", "B", "C"]:
            dag.update_task_state(tid, TaskState.NEEDS_REWORK)

        assert ref.should_trigger_redesign("test_linear", tracker)


# ============================================================================
# Test Suite 9: Workers
# ============================================================================


@pytest.mark.asyncio
class TestWorkers:
    async def test_simple_worker(self):
        w = SimpleWorker()
        task = TaskSpec(id="t1", title="Test", objective="Write hello", outputs=["out.txt"])
        result = await w.execute(task, WorkerContext())
        assert result.success
        assert result.task_id == "t1"

    async def test_debug_worker_preserves(self):
        w = DebugWorker()
        task = TaskSpec(id="t1", title="Fix", objective="Fix bug", outputs=["out.txt"])
        ctx = WorkerContext(previous_attempts=[{"feedback": "Missing null check"}])
        result = await w.execute(task, ctx)
        assert result.success
        assert "返工原则" in result.output["prompt"]

    async def test_worker_auto_selection(self):
        from pilotcode.orchestration.task_spec import ComplexityLevel

        orch = Orchestrator()
        assert (
            orch._select_worker_type(
                TaskSpec("t", "t", "t", estimated_complexity=ComplexityLevel.VERY_SIMPLE)
            )
            == "simple"
        )
        assert (
            orch._select_worker_type(
                TaskSpec("t", "t", "t", estimated_complexity=ComplexityLevel.SIMPLE)
            )
            == "standard"
        )
        assert (
            orch._select_worker_type(
                TaskSpec("t", "t", "t", estimated_complexity=ComplexityLevel.MODERATE)
            )
            == "standard"
        )
        assert (
            orch._select_worker_type(
                TaskSpec("t", "t", "t", estimated_complexity=ComplexityLevel.COMPLEX)
            )
            == "complex"
        )
        assert (
            orch._select_worker_type(
                TaskSpec("t", "t", "t", estimated_complexity=ComplexityLevel.VERY_COMPLEX)
            )
            == "complex"
        )
