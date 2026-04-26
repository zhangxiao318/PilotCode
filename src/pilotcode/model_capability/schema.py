"""Data models for model capability assessment and adaptive configuration.

This module defines the core data structures for:
1. Model capability scores across multiple dimensions
2. Runtime calibration adjustments
3. Adaptive configuration derived from capability scores
"""

from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any


class PlanningStrategy(Enum):
    """Planning strategy based on model capability."""

    FULL_DAG = "full_dag"  # One-shot complete DAG planning
    PHASED = "phased"  # Phase-by-phase planning
    TEMPLATE_BASED = "template_based"  # Template-driven decomposition


class TaskGranularity(Enum):
    """Task granularity based on model capability."""

    FINE = "fine"  # 30-80 lines per task, single file focus
    MEDIUM = "medium"  # 80-150 lines per task, 1-2 files
    COARSE = "coarse"  # 150-300 lines per task, multi-file allowed


class VerifierStrategy(Enum):
    """Verifier strategy based on model capability."""

    FULL_L3 = "full_l3"  # L1 + L2 + structured JSON L3
    SIMPLIFIED_L3 = "simplified_l3"  # L1 + L2 + string-matching L3
    STATIC_ONLY = "static_only"  # L1 + L2 + static analysis only


@dataclass
class PlanningDimension:
    """Scores for planning capability."""

    score: float = 0.5
    dag_correctness: float = 0.5  # Can output valid DAG topology
    task_granularity_appropriateness: float = 0.5  # Task sizes are reasonable
    dependency_accuracy: float = 0.5  # Dependencies are correct


@dataclass
class TaskCompletionDimension:
    """Scores for task execution capability."""

    score: float = 0.5
    code_correctness: float = 0.5  # Generated code is correct
    test_pass_rate: float = 0.5  # Tests pass when expected


@dataclass
class JsonFormattingDimension:
    """Scores for structured output capability."""

    score: float = 0.5
    valid_json_rate: float = 0.5  # Percentage of valid JSON outputs
    schema_compliance: float = 0.5  # Follows required schema
    self_correction: float = 0.5  # Can fix own JSON errors when prompted


@dataclass
class ChainOfThoughtDimension:
    """Scores for reasoning capability."""

    score: float = 0.5
    reasoning_depth: float = 0.5  # Multi-step reasoning quality
    error_diagnosis: float = 0.5  # Can diagnose failures
    debugging_skill: float = 0.5  # Can trace and fix bugs


@dataclass
class CodeReviewDimension:
    """Scores for code review capability."""

    score: float = 0.5
    bug_detection: float = 0.5  # Finds actual bugs
    structured_output: float = 0.5  # Outputs valid review JSON
    style_consistency: float = 0.5  # Enforces style rules


@dataclass
class RuntimeAdjustment:
    """A single runtime adjustment to a dimension score.

    Tracks why and when a score was adjusted based on observed behavior.
    """

    dimension: str
    sub_dimension: str
    delta: float
    reason: str
    task_id: str | None = None
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class CalibrationRecord:
    """Runtime calibration history."""

    samples_evaluated: int = 0
    last_calibrated_at: str | None = None
    adjustments: list[RuntimeAdjustment] = field(default_factory=list)
    # Per-dimension accumulated delta (for quick lookup)
    accumulated_deltas: dict[str, dict[str, float]] = field(default_factory=dict)

    def add_adjustment(self, adjustment: RuntimeAdjustment) -> None:
        """Record a new adjustment and update accumulated deltas."""
        self.adjustments.append(adjustment)
        dim = adjustment.dimension
        sub = adjustment.sub_dimension
        if dim not in self.accumulated_deltas:
            self.accumulated_deltas[dim] = {}
        self.accumulated_deltas[dim][sub] = (
            self.accumulated_deltas[dim].get(sub, 0.0) + adjustment.delta
        )
        self.samples_evaluated += 1
        self.last_calibrated_at = datetime.now(timezone.utc).isoformat()

    def get_adjusted_score(self, dimension: str, sub_dimension: str, base_score: float) -> float:
        """Get base score adjusted by runtime observations."""
        delta = self.accumulated_deltas.get(dimension, {}).get(sub_dimension, 0.0)
        return max(0.0, min(1.0, base_score + delta))


@dataclass
class ModelCapability:
    """Complete capability profile for a language model.

    This is the central data structure that drives all adaptive behavior
    in PilotCode. It is populated by benchmark tests and refined by
    runtime calibration.
    """

    model_name: str = "unknown"
    evaluated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    overall_score: float = 0.5

    # Dimension scores
    planning: PlanningDimension = field(default_factory=PlanningDimension)
    task_completion: TaskCompletionDimension = field(default_factory=TaskCompletionDimension)
    json_formatting: JsonFormattingDimension = field(default_factory=JsonFormattingDimension)
    chain_of_thought: ChainOfThoughtDimension = field(default_factory=ChainOfThoughtDimension)
    code_review: CodeReviewDimension = field(default_factory=CodeReviewDimension)

    # Runtime calibration
    calibration: CalibrationRecord = field(default_factory=CalibrationRecord)

    # Version for schema evolution
    schema_version: int = 1

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return asdict(self)

    def to_json(self, indent: int = 2) -> str:
        """Serialize to JSON string."""
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ModelCapability:
        """Deserialize from dictionary."""
        # Handle schema migration if needed
        version = data.get("schema_version", 1)

        # Extract dimensions with defaults
        planning_data = data.get("planning", {})
        task_completion_data = data.get("task_completion", {})
        json_data = data.get("json_formatting", {})
        cot_data = data.get("chain_of_thought", {})
        review_data = data.get("code_review", {})
        calibration_data = data.get("calibration", {})

        return cls(
            model_name=data.get("model_name", "unknown"),
            evaluated_at=data.get("evaluated_at", datetime.now(timezone.utc).isoformat()),
            overall_score=data.get("overall_score", 0.5),
            planning=PlanningDimension(**planning_data),
            task_completion=TaskCompletionDimension(**task_completion_data),
            json_formatting=JsonFormattingDimension(**json_data),
            chain_of_thought=ChainOfThoughtDimension(**cot_data),
            code_review=CodeReviewDimension(**review_data),
            calibration=CalibrationRecord(
                samples_evaluated=calibration_data.get("samples_evaluated", 0),
                last_calibrated_at=calibration_data.get("last_calibrated_at"),
                adjustments=[
                    RuntimeAdjustment(**a) for a in calibration_data.get("adjustments", [])
                ],
                accumulated_deltas=calibration_data.get("accumulated_deltas", {}),
            ),
            schema_version=version,
        )

    @classmethod
    def from_json(cls, json_str: str) -> ModelCapability:
        """Deserialize from JSON string."""
        return cls.from_dict(json.loads(json_str))

    def save(self, path: str | Path) -> None:
        """Save capability profile to file."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.to_json(), encoding="utf-8")

    @classmethod
    def load(cls, path: str | Path) -> ModelCapability:
        """Load capability profile from file."""
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"Capability file not found: {path}")
        return cls.from_json(path.read_text(encoding="utf-8"))

    def get_effective_dimension(self, dimension_name: str) -> dict[str, float]:
        """Get dimension scores with runtime adjustments applied.

        Returns a dict of {sub_dimension: adjusted_score}.
        """
        dim_map = {
            "planning": self.planning,
            "task_completion": self.task_completion,
            "json_formatting": self.json_formatting,
            "chain_of_thought": self.chain_of_thought,
            "code_review": self.code_review,
        }
        dim = dim_map.get(dimension_name)
        if dim is None:
            return {}

        result = {}
        for key, val in asdict(dim).items():
            if key == "score":
                continue
            adjusted = self.calibration.get_adjusted_score(dimension_name, key, val)
            result[key] = adjusted
        # Also compute adjusted overall score for this dimension
        result["score"] = self.calibration.get_adjusted_score(dimension_name, "score", dim.score)
        return result

    def get_overall_effective_score(self) -> float:
        """Get overall score with runtime adjustments."""
        # Recompute from adjusted dimensions
        dim_scores = [
            self.get_effective_dimension("planning")["score"],
            self.get_effective_dimension("task_completion")["score"],
            self.get_effective_dimension("json_formatting")["score"],
            self.get_effective_dimension("chain_of_thought")["score"],
            self.get_effective_dimension("code_review")["score"],
        ]
        return sum(dim_scores) / len(dim_scores)

    def record_adjustment(
        self,
        dimension: str,
        sub_dimension: str,
        delta: float,
        reason: str,
        task_id: str | None = None,
    ) -> None:
        """Record a runtime adjustment to a dimension score."""
        adjustment = RuntimeAdjustment(
            dimension=dimension,
            sub_dimension=sub_dimension,
            delta=delta,
            reason=reason,
            task_id=task_id,
        )
        self.calibration.add_adjustment(adjustment)
        # Update overall score
        self.overall_score = self.get_overall_effective_score()

    def clone(self) -> ModelCapability:
        """Create a deep copy."""
        return deepcopy(self)
