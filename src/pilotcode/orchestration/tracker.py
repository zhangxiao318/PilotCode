"""Global mission tracker for P-EVR orchestration.

All agents/workers share this tracker to query task status, progress, and state.
Maps to P-EVR Architecture Section 6 (Memory & State Management).
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field, asdict
from typing import Callable
from datetime import datetime, timezone
from pathlib import Path

from .task_spec import Mission
from .state_machine import TaskState, StateMachine, StateChangeEvent
from .dag import DagExecutor, DagNode


@dataclass
class AgentProgress:
    """Snapshot of an agent's current progress."""

    agent_id: str
    agent_type: str
    current_task_id: str | None = None
    status: str = "idle"  # "idle", "running", "paused", "error"
    progress_pct: float = 0.0
    current_action: str = ""
    started_at: str = ""
    elapsed_seconds: float = 0.0


@dataclass
class BlockedTask:
    """A task that is blocked by incomplete dependencies."""

    task_id: str
    task_title: str
    blocking_task_ids: list[str]
    blocking_task_titles: list[str] = field(default_factory=list)


@dataclass
class MissionSnapshot:
    """Serializable snapshot of a mission's current state."""

    mission_id: str
    title: str
    status: str  # "pending", "running", "paused", "completed", "failed"
    total_tasks: int
    completed_tasks: int
    verified_tasks: int
    failed_tasks: int
    blocked_tasks: int
    in_progress_tasks: int
    ready_tasks: int
    critical_path_length: int
    started_at: str | None = None
    updated_at: str | None = None
    task_states: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict:

        return asdict(self)


class MissionTracker:
    """Global mission tracking center.

    Singleton-like pattern: use get_tracker() to get the global instance.
    """

    def __init__(self, db_path: str | None = None):
        self._missions: dict[str, Mission] = {}
        self._dag_executors: dict[str, DagExecutor] = {}
        self._state_machines: dict[str, dict[str, StateMachine]] = {}
        self._agent_progress: dict[str, AgentProgress] = {}
        self._event_callbacks: list[Callable[[str, dict], None]] = []
        self._db_path = db_path
        self._db_conn: sqlite3.Connection | None = None
        if db_path:
            self._init_db()

    def _init_db(self) -> None:
        """Initialize SQLite persistence with WAL mode for concurrent access."""
        Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
        self._db_conn = sqlite3.connect(self._db_path)
        self._db_conn.execute("PRAGMA journal_mode=WAL")
        self._db_conn.execute("""
            CREATE TABLE IF NOT EXISTS missions (
                mission_id TEXT PRIMARY KEY,
                data TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)
        self._db_conn.execute("""
            CREATE TABLE IF NOT EXISTS state_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                mission_id TEXT NOT NULL,
                task_id TEXT NOT NULL,
                from_state TEXT NOT NULL,
                to_state TEXT NOT NULL,
                transition TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                reason TEXT,
                actor TEXT
            )
        """)
        self._db_conn.commit()

    def register_mission(self, mission: Mission, dag: DagExecutor | None = None) -> None:
        """Register a new mission."""
        self._missions[mission.mission_id] = mission

        if dag is None:
            dag = DagExecutor(mission)
            dag.build()
        self._dag_executors[mission.mission_id] = dag

        # Initialize state machines for all tasks (bind DagNode for auto-sync)
        self._state_machines[mission.mission_id] = {}
        for task in mission.all_tasks():
            node = dag.nodes.get(task.id)
            sm = StateMachine(task.id, node=node)
            sm.on_state_change(lambda evt, mid=mission.mission_id: self._on_state_change(mid, evt))
            self._state_machines[mission.mission_id][task.id] = sm

        self._persist_mission(mission)
        self._emit("mission:registered", {"mission_id": mission.mission_id})

    def _on_state_change(self, mission_id: str, event: StateChangeEvent) -> None:
        """Handle state change events from StateMachines."""
        # NOTE: DagNode state is already synchronized by StateMachine.state setter.
        # We only need to invalidate the ready-task cache here.
        dag = self._dag_executors.get(mission_id)
        if dag:
            dag._ready_cache = None

        # Persist to DB (reuse single connection)
        if self._db_conn:
            self._db_conn.execute(
                "INSERT INTO state_events (mission_id, task_id, from_state, to_state, transition, timestamp, reason, actor) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    mission_id,
                    event.task_id,
                    event.from_state.value,
                    event.to_state.value,
                    event.transition.value,
                    event.timestamp,
                    event.reason,
                    event.actor,
                ),
            )
            self._db_conn.commit()

        self._emit(
            "task:state_changed",
            {
                "mission_id": mission_id,
                "task_id": event.task_id,
                "from": event.from_state.value,
                "to": event.to_state.value,
                "transition": event.transition.value,
            },
        )

    def close(self) -> None:
        """Close the database connection."""
        if self._db_conn:
            self._db_conn.close()
            self._db_conn = None

    def _persist_mission(self, mission: Mission) -> None:
        """Persist mission to SQLite."""
        if not self._db_conn:
            return
        self._db_conn.execute(
            "INSERT OR REPLACE INTO missions (mission_id, data, updated_at) VALUES (?, ?, ?)",
            (
                mission.mission_id,
                json.dumps(mission.to_dict()),
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        self._db_conn.commit()

    def get_mission(self, mission_id: str) -> Mission | None:
        """Get a mission by ID."""
        return self._missions.get(mission_id)

    def get_dag(self, mission_id: str) -> DagExecutor | None:
        """Get the DAG executor for a mission."""
        return self._dag_executors.get(mission_id)

    def get_state_machine(self, mission_id: str, task_id: str) -> StateMachine | None:
        """Get the state machine for a specific task."""
        return self._state_machines.get(mission_id, {}).get(task_id)

    def get_ready_tasks(self, mission_id: str) -> list[DagNode]:
        """Get all tasks ready to execute."""
        dag = self._dag_executors.get(mission_id)
        if not dag:
            return []
        return dag.get_ready_tasks()

    def get_blocked_tasks(self, mission_id: str) -> list[BlockedTask]:
        """Get all blocked tasks with reasons."""
        dag = self._dag_executors.get(mission_id)
        if not dag:
            return []

        mission = self._missions.get(mission_id)
        blocked = []
        for node, dep_ids in dag.get_blocked_tasks():
            titles = []
            for did in dep_ids:
                task = mission.get_task(did) if mission else None
                titles.append(task.title if task else did)
            blocked.append(
                BlockedTask(
                    task_id=node.task_id,
                    task_title=node.task.title,
                    blocking_task_ids=dep_ids,
                    blocking_task_titles=titles,
                )
            )
        return blocked

    def get_agent_progress(self, agent_id: str) -> AgentProgress | None:
        """Get an agent's current progress."""
        return self._agent_progress.get(agent_id)

    def update_agent_progress(self, progress: AgentProgress) -> None:
        """Update an agent's progress."""
        self._agent_progress[progress.agent_id] = progress
        self._emit(
            "agent:progress",
            {
                "agent_id": progress.agent_id,
                "status": progress.status,
                "task_id": progress.current_task_id,
                "progress_pct": progress.progress_pct,
            },
        )

    def get_snapshot(self, mission_id: str) -> MissionSnapshot | None:
        """Get a serializable snapshot of mission state."""
        mission = self._missions.get(mission_id)
        dag = self._dag_executors.get(mission_id)
        if not mission or not dag:
            return None

        task_states = {tid: node.state.value for tid, node in dag.nodes.items()}
        counts = {
            TaskState.DONE: 0,
            TaskState.CANCELLED: 0,
            TaskState.REJECTED: 0,
            TaskState.VERIFIED: 0,
            TaskState.IN_PROGRESS: 0,
            TaskState.BLOCKED: 0,
            TaskState.PENDING: 0,
        }
        for state in task_states.values():
            s = TaskState(state)
            if s in counts:
                counts[s] += 1

        total = len(dag.nodes)
        done = counts[TaskState.DONE]
        failed = counts[TaskState.CANCELLED] + counts[TaskState.REJECTED]
        terminal = done + failed

        status = "pending"
        if terminal == total:
            status = "completed" if failed == 0 else "failed"
        elif counts[TaskState.IN_PROGRESS] > 0:
            status = "running"
        elif counts[TaskState.BLOCKED] > 0:
            status = "paused"

        critical_path = dag.get_critical_path()

        return MissionSnapshot(
            mission_id=mission_id,
            title=mission.title,
            status=status,
            total_tasks=total,
            completed_tasks=done,
            verified_tasks=counts[TaskState.VERIFIED],
            failed_tasks=failed,
            blocked_tasks=counts[TaskState.BLOCKED],
            in_progress_tasks=counts[TaskState.IN_PROGRESS],
            ready_tasks=len(dag.get_ready_tasks()),
            critical_path_length=len(critical_path),
            task_states=task_states,
        )

    def on_event(self, callback: Callable[[str, dict], None]) -> None:
        """Subscribe to tracker events."""
        self._event_callbacks.append(callback)

    def _emit(self, event_type: str, data: dict) -> None:
        """Emit an event to all subscribers."""
        for cb in self._event_callbacks:
            try:
                cb(event_type, data)
            except Exception:
                import logging

                logging.getLogger(__name__).warning(
                    "Event callback failed for %s", event_type, exc_info=True
                )

    def list_missions(self) -> list[str]:
        """List all registered mission IDs."""
        return list(self._missions.keys())

    def all_done(self, mission_id: str) -> bool:
        """Check if all tasks in a mission are done."""
        dag = self._dag_executors.get(mission_id)
        return dag.all_done() if dag else False


# Global instance
_tracker: MissionTracker | None = None


def get_tracker(db_path: str | None = None) -> MissionTracker:
    """Get global mission tracker instance."""
    global _tracker
    if _tracker is None:
        _tracker = MissionTracker(db_path=db_path)
    return _tracker


def reset_tracker() -> None:
    """Reset global tracker (mainly for testing)."""
    global _tracker
    _tracker = None
