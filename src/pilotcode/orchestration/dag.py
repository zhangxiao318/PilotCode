"""DAG construction and topological execution for P-EVR orchestration.

Maps to P-EVR Architecture Section 2.3:
- Plans are Directed Acyclic Graphs (DAGs), not linear lists
- Tasks execute only when all dependencies are VERIFIED
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from collections import deque

from .task_spec import TaskSpec, Phase, Mission
from .state_machine import TaskState


@dataclass
class DagNode:
    """A node in the execution DAG."""

    task_id: str
    task: TaskSpec
    state: TaskState = TaskState.PENDING
    depth: int = 0  # topological depth (0 = root)
    result: Any = None
    error: str | None = None
    artifacts: dict[str, Any] = field(default_factory=dict)


@dataclass
class DagEdge:
    """A dependency edge in the DAG."""

    from_task: str
    to_task: str
    required_state: TaskState = TaskState.VERIFIED


class DagExecutor:
    """Builds and executes a DAG of tasks.

    Uses Kahn's algorithm for topological sorting.
    """

    def __init__(self, mission: Mission):
        self.mission = mission
        self.nodes: dict[str, DagNode] = {}
        self.edges: list[DagEdge] = []
        self._in_degree: dict[str, int] = {}
        self._outgoing: dict[str, list[str]] = {}
        self._topo_order: list[str] = []
        self._built = False

    def build(self) -> list[str]:
        """Build the DAG and return topological order.

        Raises:
            ValueError: If cycles are detected.
        """
        if self._built:
            return self._topo_order

        # Clear any stale data in case of rebuild
        self.nodes.clear()
        self.edges.clear()
        self._in_degree.clear()
        self._outgoing.clear()

        # Create nodes
        for phase in self.mission.phases:
            for task in phase.tasks:
                self.nodes[task.id] = DagNode(task_id=task.id, task=task)
                self._in_degree[task.id] = 0
                self._outgoing[task.id] = []

        # Create edges from task dependencies
        for phase in self.mission.phases:
            for task in phase.tasks:
                for dep_id in task.dependencies:
                    if dep_id not in self.nodes:
                        raise ValueError(f"Task '{task.id}' depends on unknown task '{dep_id}'")
                    edge = DagEdge(from_task=dep_id, to_task=task.id)
                    self.edges.append(edge)
                    self._in_degree[task.id] += 1
                    self._outgoing[dep_id].append(task.id)

        # Topological sort (Kahn's algorithm)
        queue = deque([tid for tid, deg in self._in_degree.items() if deg == 0])
        topo_order = []

        while queue:
            task_id = queue.popleft()
            topo_order.append(task_id)
            for next_id in self._outgoing[task_id]:
                self._in_degree[next_id] -= 1
                if self._in_degree[next_id] == 0:
                    queue.append(next_id)

        if len(topo_order) != len(self.nodes):
            # Find cycle members
            cycle_nodes = set(self.nodes.keys()) - set(topo_order)
            raise ValueError(f"Cycle detected in task dependencies: {cycle_nodes}")

        # Calculate depth for each node
        depths: dict[str, int] = {}
        for tid in topo_order:
            max_parent_depth = 0
            for edge in self.edges:
                if edge.to_task == tid:
                    max_parent_depth = max(max_parent_depth, depths.get(edge.from_task, 0))
            depths[tid] = max_parent_depth + 1
            self.nodes[tid].depth = depths[tid]

        self._topo_order = topo_order
        self._built = True
        return topo_order

    def get_ready_tasks(self) -> list[DagNode]:
        """Get all tasks whose dependencies are satisfied.

        Returns tasks that are in PENDING state and all dependencies are VERIFIED.
        """
        if not self._built:
            self.build()

        ready = []
        for node in self.nodes.values():
            if node.state != TaskState.PENDING:
                continue

            # Check all dependencies (VERIFIED or DONE counts as satisfied)
            deps_satisfied = True
            for edge in self.edges:
                if edge.to_task == node.task_id:
                    dep_node = self.nodes[edge.from_task]
                    if dep_node.state not in {TaskState.VERIFIED, TaskState.DONE}:
                        deps_satisfied = False
                        break

            if deps_satisfied:
                ready.append(node)

        # Sort by depth (shallower first) then by topo order
        order_map = {tid: i for i, tid in enumerate(self._topo_order)}
        ready.sort(key=lambda n: (n.depth, order_map[n.task_id]))
        return ready

    def get_blocked_tasks(self) -> list[tuple[DagNode, list[str]]]:
        """Get tasks that are blocked by incomplete dependencies.

        Returns list of (node, blocking_dep_ids).
        """
        if not self._built:
            self.build()

        blocked = []
        for node in self.nodes.values():
            if node.state != TaskState.PENDING:
                continue

            blocking = []
            for edge in self.edges:
                if edge.to_task == node.task_id:
                    dep_node = self.nodes[edge.from_task]
                    if dep_node.state != TaskState.VERIFIED:
                        blocking.append(edge.from_task)

            if blocking:
                blocked.append((node, blocking))

        return blocked

    def update_task_state(self, task_id: str, state: TaskState) -> None:
        """Update the state of a task node."""
        if task_id not in self.nodes:
            raise ValueError(f"Unknown task: {task_id}")
        self.nodes[task_id].state = state

    def update_task_result(
        self, task_id: str, result: Any, artifacts: dict[str, Any] | None = None
    ) -> None:
        """Update the result of a completed task."""
        if task_id not in self.nodes:
            raise ValueError(f"Unknown task: {task_id}")
        self.nodes[task_id].result = result
        if artifacts:
            self.nodes[task_id].artifacts.update(artifacts)

    def get_execution_path(self) -> list[list[str]]:
        """Get tasks grouped by topological depth (execution waves).

        Each inner list can be executed in parallel (no dependencies within).
        """
        if not self._built:
            self.build()

        waves: dict[int, list[str]] = {}
        for tid in self._topo_order:
            depth = self.nodes[tid].depth
            if depth not in waves:
                waves[depth] = []
            waves[depth].append(tid)

        return [waves[d] for d in sorted(waves.keys())]

    def all_done(self) -> bool:
        """Check if all tasks are in terminal states."""
        terminal = {TaskState.DONE, TaskState.CANCELLED, TaskState.REJECTED}
        return all(n.state in terminal for n in self.nodes.values())

    def all_verified(self) -> bool:
        """Check if all tasks are verified or done."""
        return all(
            n.state in {TaskState.VERIFIED, TaskState.DONE, TaskState.CANCELLED}
            for n in self.nodes.values()
        )

    def get_node(self, task_id: str) -> DagNode | None:
        """Get a DAG node by task ID."""
        return self.nodes.get(task_id)

    def get_critical_path(self) -> list[str]:
        """Estimate the critical path (longest dependency chain).

        Returns task IDs along the longest path.
        """
        if not self._built:
            self.build()

        # Dynamic programming: longest path ending at each node
        longest: dict[str, list[str]] = {}
        for tid in self._topo_order:
            # Find the longest path to this node
            best_pred: str | None = None
            best_len = 0
            for edge in self.edges:
                if edge.to_task == tid:
                    pred_len = len(longest.get(edge.from_task, []))
                    if pred_len > best_len:
                        best_len = pred_len
                        best_pred = edge.from_task

            if best_pred:
                longest[tid] = longest[best_pred] + [tid]
            else:
                longest[tid] = [tid]

        if not longest:
            return []

        return max(longest.values(), key=len)


def build_dag_from_phases(phases: list[Phase]) -> DagExecutor:
    """Convenience function to build a DAG from phases."""
    mission = Mission(
        mission_id="auto",
        title="Auto mission",
        requirement="",
        phases=phases,
    )
    return DagExecutor(mission)
