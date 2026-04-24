"""Task specification models for P-EVR orchestration."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from enum import Enum


class ComplexityLevel(Enum):
    """Task complexity levels."""

    VERY_SIMPLE = 1
    SIMPLE = 2
    MODERATE = 3
    COMPLEX = 4
    VERY_COMPLEX = 5


@dataclass
class Constraints:
    """Execution constraints for a task."""

    max_lines: int | None = None
    must_use: list[str] = field(default_factory=list)
    must_not_use: list[str] = field(default_factory=list)
    patterns: list[str] = field(default_factory=list)
    forbidden_patterns: list[str] = field(default_factory=list)


@dataclass
class AcceptanceCriterion:
    """A single acceptance criterion for task verification."""

    description: str
    verification_method: str = "manual"  # "manual", "test", "lint", "review"
    auto_verify: bool = False


@dataclass
class TaskSpec:
    """Specification for a single executable task.

    Maps to P-EVR Architecture Section 2.2.
    """

    id: str
    title: str
    objective: str
    inputs: list[str] = field(default_factory=list)
    outputs: list[str] = field(default_factory=list)
    dependencies: list[str] = field(default_factory=list)
    estimated_complexity: ComplexityLevel = ComplexityLevel.MODERATE
    acceptance_criteria: list[AcceptanceCriterion] = field(default_factory=list)
    constraints: Constraints = field(default_factory=Constraints)
    context_budget: int = 16000  # tokens
    phase_id: str = ""  # parent phase
    worker_type: str = "auto"  # "simple", "standard", "complex", "debug", "auto"
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "objective": self.objective,
            "inputs": self.inputs,
            "outputs": self.outputs,
            "dependencies": self.dependencies,
            "estimated_complexity": self.estimated_complexity.value,
            "acceptance_criteria": [
                {"description": ac.description, "verification_method": ac.verification_method}
                for ac in self.acceptance_criteria
            ],
            "constraints": {
                "max_lines": self.constraints.max_lines,
                "must_use": self.constraints.must_use,
                "must_not_use": self.constraints.must_not_use,
                "patterns": self.constraints.patterns,
            },
            "context_budget": self.context_budget,
            "phase_id": self.phase_id,
            "worker_type": self.worker_type,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TaskSpec:
        acs = [
            AcceptanceCriterion(
                description=ac["description"],
                verification_method=ac.get("verification_method", "manual"),
            )
            for ac in data.get("acceptance_criteria", [])
        ]
        c = data.get("constraints", {})
        return cls(
            id=data["id"],
            title=data["title"],
            objective=data["objective"],
            inputs=data.get("inputs", []),
            outputs=data.get("outputs", []),
            dependencies=data.get("dependencies", []),
            estimated_complexity=ComplexityLevel(data.get("estimated_complexity", 3)),
            acceptance_criteria=acs,
            constraints=Constraints(
                max_lines=c.get("max_lines"),
                must_use=c.get("must_use", []),
                must_not_use=c.get("must_not_use", []),
                patterns=c.get("patterns", []),
            ),
            context_budget=data.get("context_budget", 16000),
            phase_id=data.get("phase_id", ""),
            worker_type=data.get("worker_type", "auto"),
            metadata=data.get("metadata", {}),
        )


@dataclass
class Phase:
    """A phase in a mission (strategic grouping of tasks).

    Maps to P-EVR Architecture Section 2.1 three-layer decomposition.
    """

    phase_id: str
    title: str
    description: str
    tasks: list[TaskSpec] = field(default_factory=list)
    dependencies: list[str] = field(default_factory=list)  # phase-level dependencies
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "phase_id": self.phase_id,
            "title": self.title,
            "description": self.description,
            "tasks": [t.to_dict() for t in self.tasks],
            "dependencies": self.dependencies,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Phase:
        return cls(
            phase_id=data["phase_id"],
            title=data["title"],
            description=data["description"],
            tasks=[TaskSpec.from_dict(t) for t in data.get("tasks", [])],
            dependencies=data.get("dependencies", []),
        )


@dataclass
class Mission:
    """Top-level mission (equivalent to P-EVR's Mission).

    Maps to P-EVR Architecture Section 2.1.
    """

    mission_id: str
    title: str
    requirement: str
    phases: list[Phase] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: str = ""
    context_budget: int = 16000  # Total context window budget in tokens
    context_strategy: str = "balanced"  # Strategy name (for serialization)

    def to_dict(self) -> dict[str, Any]:
        return {
            "mission_id": self.mission_id,
            "title": self.title,
            "requirement": self.requirement,
            "phases": [p.to_dict() for p in self.phases],
            "metadata": self.metadata,
            "created_at": self.created_at,
            "context_budget": self.context_budget,
            "context_strategy": self.context_strategy,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Mission:
        return cls(
            mission_id=data["mission_id"],
            title=data["title"],
            requirement=data["requirement"],
            phases=[Phase.from_dict(p) for p in data.get("phases", [])],
            metadata=data.get("metadata", {}),
            created_at=data.get("created_at", ""),
            context_budget=data.get("context_budget", 16000),
            context_strategy=data.get("context_strategy", "balanced"),
        )

    def all_tasks(self) -> list[TaskSpec]:
        """Flatten all tasks across all phases."""
        tasks = []
        for phase in self.phases:
            tasks.extend(phase.tasks)
        return tasks

    def get_task(self, task_id: str) -> TaskSpec | None:
        """Find a task by ID."""
        for phase in self.phases:
            for task in phase.tasks:
                if task.id == task_id:
                    return task
        return None
