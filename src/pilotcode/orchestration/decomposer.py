"""Task decomposition for automatic mission planning.

Provides heuristic-based task analysis and decomposition.
This is a lightweight implementation that enables the example code to run.
A full LLM-driven decomposer can be added later.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class DecompositionStrategy(Enum):
    """Strategy for decomposing a task."""

    NONE = "none"
    SEQUENTIAL = "sequential"
    PARALLEL = "parallel"
    HIERARCHICAL = "hierarchical"


@dataclass
class Subtask:
    """A single subtask produced by decomposition."""

    role: str
    description: str
    dependencies: list[str] = field(default_factory=list)
    prompt: str = ""  # Execution prompt for the subtask
    estimated_complexity: int = 3  # 1-5
    estimated_duration_seconds: float = 30.0


@dataclass
class DecompositionResult:
    """Result of task decomposition analysis."""

    strategy: DecompositionStrategy
    confidence: float  # 0-1
    reasoning: str
    subtasks: list[Subtask] = field(default_factory=list)


class TaskDecomposer:
    """Heuristic task decomposer.

    Analyzes task descriptions to determine whether and how to decompose them.
    This implementation uses rule-based heuristics; a future version may use LLM.
    """

    def analyze(self, task: str) -> DecompositionResult:
        """Analyze a task and return decomposition metadata (no subtasks)."""
        word_count = len(task.split())
        lower = task.lower()
        has_and = " and " in lower or "," in task
        has_then = " then " in lower or "first" in lower
        if word_count < 10 and not has_and:
            return DecompositionResult(
                strategy=DecompositionStrategy.NONE,
                confidence=0.9,
                reasoning="Task is simple and atomic",
                subtasks=[],
            )
        elif has_then:
            return DecompositionResult(
                strategy=DecompositionStrategy.SEQUENTIAL,
                confidence=0.7,
                reasoning="Task contains sequential keywords",
                subtasks=[],
            )
        elif has_and and word_count > 15:
            return DecompositionResult(
                strategy=DecompositionStrategy.PARALLEL,
                confidence=0.65,
                reasoning="Task has multiple independent components",
                subtasks=[],
            )
        else:
            return DecompositionResult(
                strategy=DecompositionStrategy.HIERARCHICAL,
                confidence=0.6,
                reasoning="Task is complex, needs hierarchical decomposition",
                subtasks=[],
            )

    def auto_decompose(self, task: str) -> DecompositionResult:
        """Decompose a task into subtasks."""
        analysis = self.analyze(task)
        lower = task.lower()

        subtasks: list[Subtask] = []

        if analysis.strategy == DecompositionStrategy.NONE:
            subtasks = [Subtask(role="executor", description=task, dependencies=[])]
        elif analysis.strategy == DecompositionStrategy.SEQUENTIAL:
            if "implement" in lower or "build" in lower:
                subtasks = [
                    Subtask(
                        role="planner",
                        description="Design the architecture and API",
                        dependencies=[],
                    ),
                    Subtask(
                        role="implementer",
                        description="Implement the core logic",
                        dependencies=["planner"],
                    ),
                    Subtask(
                        role="tester",
                        description="Write and run tests",
                        dependencies=["implementer"],
                    ),
                ]
            elif "refactor" in lower:
                subtasks = [
                    Subtask(
                        role="analyst",
                        description="Analyze current code and identify issues",
                        dependencies=[],
                    ),
                    Subtask(
                        role="refactorer",
                        description="Apply refactoring changes",
                        dependencies=["analyst"],
                    ),
                    Subtask(
                        role="tester",
                        description="Verify behavior is preserved",
                        dependencies=["refactorer"],
                    ),
                ]
            elif "fix" in lower or "bug" in lower:
                subtasks = [
                    Subtask(
                        role="investigator",
                        description="Reproduce and diagnose the bug",
                        dependencies=[],
                    ),
                    Subtask(
                        role="fixer", description="Apply the fix", dependencies=["investigator"]
                    ),
                    Subtask(
                        role="tester", description="Add regression test", dependencies=["fixer"]
                    ),
                ]
            else:
                subtasks = [
                    Subtask(role="step1", description=f"Step 1: Analyze {task}", dependencies=[]),
                    Subtask(
                        role="step2", description=f"Step 2: Execute {task}", dependencies=["step1"]
                    ),
                ]
        elif analysis.strategy == DecompositionStrategy.PARALLEL:
            if "test" in lower:
                subtasks = [
                    Subtask(
                        role="implementer", description="Implement the feature", dependencies=[]
                    ),
                    Subtask(role="tester", description="Write unit tests", dependencies=[]),
                    Subtask(
                        role="reviewer",
                        description="Review and integrate",
                        dependencies=["implementer", "tester"],
                    ),
                ]
            else:
                subtasks = [
                    Subtask(role="worker_a", description="Handle component A", dependencies=[]),
                    Subtask(role="worker_b", description="Handle component B", dependencies=[]),
                    Subtask(
                        role="integrator",
                        description="Integrate results",
                        dependencies=["worker_a", "worker_b"],
                    ),
                ]
        else:  # HIERARCHICAL
            subtasks = [
                Subtask(
                    role="architect",
                    description="Define overall structure and interfaces",
                    dependencies=[],
                ),
                Subtask(
                    role="implementer",
                    description="Implement sub-components",
                    dependencies=["architect"],
                ),
                Subtask(
                    role="integrator",
                    description="Integrate and validate",
                    dependencies=["implementer"],
                ),
                Subtask(
                    role="tester", description="End-to-end testing", dependencies=["integrator"]
                ),
            ]

        return DecompositionResult(
            strategy=analysis.strategy,
            confidence=analysis.confidence,
            reasoning=analysis.reasoning,
            subtasks=subtasks,
        )
