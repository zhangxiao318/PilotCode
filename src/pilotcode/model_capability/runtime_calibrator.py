"""Runtime capability calibrator.

Monitors task execution outcomes and dynamically adjusts model capability
scores based on observed behavior. This creates a feedback loop where
the system's understanding of the model improves as it works.

Key principles:
- Failures reduce confidence in relevant dimensions
- Successes increase confidence (but more slowly — conservative updates)
- Adjustments are bounded to prevent wild oscillation
- Adjustments are persisted alongside benchmark scores
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Callable

from .schema import ModelCapability, RuntimeAdjustment

# Patterns for classifying execution failures
_JSON_ERROR_PATTERNS = [
    r"json\.JSONDecodeError",
    r"Expecting.*delimiter",
    r"Extra data",
    r"invalid json",
    r"malformed json",
    r"解析.*json",
    r"JSON.*错误",
]

_SYNTAX_ERROR_PATTERNS = [
    r"SyntaxError",
    r"IndentationError",
    r"unexpected indent",
    r"invalid syntax",
    r"EOF.*while scanning",
]

_LOGIC_ERROR_PATTERNS = [
    r"AssertionError",
    r"ValueError",
    r"TypeError",
    r"AttributeError",
    r"IndexError",
    r"KeyError",
    r"NameError",
    r"RuntimeError",
    r"测试.*失败",
    r"assert.*failed",
]

_TIMEOUT_PATTERNS = [
    r"TimeoutError",
    r"asyncio\.TimeoutError",
    r"timed out",
    r"timeout",
]


def _matches_any(text: str, patterns: list[str]) -> bool:
    if not text:
        return False
    lowered = text.lower()
    for p in patterns:
        if re.search(p, text, re.IGNORECASE) or re.search(p, lowered):
            return True
    return False


def classify_failure(error_text: str | None, output_text: str | None = None) -> str:
    """Classify the type of failure from error/output text.

    Returns one of:
        - "json_error": Model produced malformed JSON
        - "syntax_error": Generated code has syntax errors
        - "logic_error": Generated code runs but behaves incorrectly
        - "timeout": Execution timed out
        - "unknown": Could not determine failure type
    """
    combined = ""
    if error_text:
        combined += error_text + "\n"
    if output_text:
        combined += output_text

    if not combined:
        return "unknown"

    if _matches_any(combined, _JSON_ERROR_PATTERNS):
        return "json_error"
    if _matches_any(combined, _SYNTAX_ERROR_PATTERNS):
        return "syntax_error"
    if _matches_any(combined, _TIMEOUT_PATTERNS):
        return "timeout"
    if _matches_any(combined, _LOGIC_ERROR_PATTERNS):
        return "logic_error"

    return "unknown"


def classify_planning_failure(raw_plan: str | None, parse_error: str | None = None) -> str:
    """Classify planning failure type.

    Returns one of:
        - "invalid_json": Plan is not valid JSON
        - "missing_fields": Required fields missing from plan
        - "invalid_dag": Dependency cycle or invalid topology
        - "poor_granularity": Tasks too coarse or too fine
        - "unknown": Could not determine
    """
    if not raw_plan:
        return "unknown"

    # Check for JSON issues
    try:
        data = json.loads(raw_plan)
    except json.JSONDecodeError:
        return "invalid_json"

    if not isinstance(data, dict):
        return "invalid_json"

    if "phases" not in data:
        return "missing_fields"

    # Check DAG validity (simple cycle check)
    all_task_ids = set()
    all_deps = []
    for phase in data.get("phases", []):
        for task in phase.get("tasks", []):
            tid = task.get("task_id", "")
            if tid:
                all_task_ids.add(tid)
            for dep in task.get("dependencies", []):
                all_deps.append((tid, dep))

    # Check for unresolved dependencies
    for _, dep in all_deps:
        if dep not in all_task_ids:
            return "invalid_dag"

    # Check for cycles
    dep_map: dict[str, set[str]] = {tid: set() for tid in all_task_ids}
    for tid, dep in all_deps:
        if tid in dep_map:
            dep_map[tid].add(dep)

    for tid, deps in dep_map.items():
        for dep in deps:
            if tid in dep_map.get(dep, set()):
                return "invalid_dag"

    # Check granularity (heuristic)
    task_count = sum(len(p.get("tasks", [])) for p in data.get("phases", []))
    if task_count < 2 or task_count > 20:
        return "poor_granularity"

    return "unknown"


@dataclass
class TaskOutcome:
    """Structured outcome of a single task execution."""

    task_id: str
    success: bool
    completion_percentage: float = 1.0  # 0.0 - 1.0, how much of task was completed
    correctness_score: float = 1.0  # 0.0 - 1.0, how correct the output was
    error_text: str | None = None
    output_text: str | None = None
    raw_llm_output: str | None = None  # For planning tasks
    metadata: dict[str, Any] = field(default_factory=dict)


class RuntimeCalibrator:
    """Calibrates model capability scores based on runtime observations.

    Usage:
        calibrator = RuntimeCalibrator(capability)
        calibrator.record_task_outcome(outcome)
        updated_cap = calibrator.get_calibrated_capability()
    """

    # Adjustment magnitudes
    FAILURE_PENALTY_BASE = -0.05
    SUCCESS_REWARD_BASE = +0.01
    MAX_ADJUSTMENT_PER_DIMENSION = 0.25  # Cap total adjustment to prevent runaway

    def __init__(self, base_capability: ModelCapability):
        self.base = base_capability
        self._capability = base_capability.clone()
        self._outcome_count = 0
        self._success_count = 0

    @property
    def capability(self) -> ModelCapability:
        return self._capability

    def record_task_outcome(self, outcome: TaskOutcome) -> None:
        """Record a task outcome and adjust capability scores.

        The adjustment considers:
        - Failure type → which dimension to penalize
        - Completion percentage → magnitude of adjustment
        - Correctness score → direction and magnitude
        """
        self._outcome_count += 1
        if outcome.success:
            self._success_count += 1

        if outcome.success and outcome.correctness_score >= 0.9:
            # Strong success — small positive reinforcement
            self._apply_success_reward(outcome)
        elif not outcome.success or outcome.correctness_score < 0.5:
            # Failure or poor correctness — investigate and penalize
            self._apply_failure_penalty(outcome)
        else:
            # Partial success — minor adjustments
            self._apply_partial_adjustment(outcome)

    def _apply_success_reward(self, outcome: TaskOutcome) -> None:
        """Apply small positive adjustment for clear success."""
        # Reward task completion dimension slightly
        self._adjust_if_not_capped(
            "task_completion",
            "code_correctness",
            self.SUCCESS_REWARD_BASE,
            f"Task {outcome.task_id} completed successfully with high correctness",
            outcome.task_id,
        )

    def _apply_failure_penalty(self, outcome: TaskOutcome) -> None:
        """Apply penalty based on failure classification."""
        failure_type = classify_failure(outcome.error_text, outcome.output_text)

        # Scale penalty by how badly it failed
        severity = 1.0 - outcome.completion_percentage
        penalty = self.FAILURE_PENALTY_BASE * (0.5 + severity)

        if failure_type == "json_error":
            self._adjust_if_not_capped(
                "json_formatting",
                "valid_json_rate",
                penalty,
                f"JSON parsing failed for task {outcome.task_id}: {outcome.error_text[:100]}",
                outcome.task_id,
            )
            # Also penalize schema compliance if we can tell it's a schema issue
            if outcome.error_text and "schema" in outcome.error_text.lower():
                self._adjust_if_not_capped(
                    "json_formatting",
                    "schema_compliance",
                    penalty * 0.5,
                    f"JSON schema non-compliance in task {outcome.task_id}",
                    outcome.task_id,
                )

        elif failure_type == "syntax_error":
            self._adjust_if_not_capped(
                "task_completion",
                "code_correctness",
                penalty,
                f"Syntax error in task {outcome.task_id}: {outcome.error_text[:100]}",
                outcome.task_id,
            )

        elif failure_type == "logic_error":
            self._adjust_if_not_capped(
                "task_completion",
                "code_correctness",
                penalty * 0.8,
                f"Logic error in task {outcome.task_id}",
                outcome.task_id,
            )
            self._adjust_if_not_capped(
                "chain_of_thought",
                "debugging_skill",
                penalty * 0.5,
                f"Model failed to produce correct logic for task {outcome.task_id}",
                outcome.task_id,
            )

        elif failure_type == "timeout":
            # Timeout often indicates the model is struggling with complexity
            self._adjust_if_not_capped(
                "chain_of_thought",
                "reasoning_depth",
                penalty * 0.5,
                f"Task {outcome.task_id} timed out — possible complexity mismatch",
                outcome.task_id,
            )

    def _apply_partial_adjustment(self, outcome: TaskOutcome) -> None:
        """Handle partial success (0.5 <= correctness < 0.9)."""
        # Small negative adjustment proportional to (1 - correctness)
        delta = -0.02 * (1.0 - outcome.correctness_score)
        self._adjust_if_not_capped(
            "task_completion",
            "code_correctness",
            delta,
            f"Task {outcome.task_id} partially correct ({outcome.correctness_score:.0%})",
            outcome.task_id,
        )

    def record_planning_outcome(
        self,
        task_id: str,
        raw_plan: str | None,
        parse_error: str | None = None,
        success: bool = False,
    ) -> None:
        """Record a planning-specific outcome and adjust planning dimension."""
        if success:
            self._adjust_if_not_capped(
                "planning",
                "dag_correctness",
                self.SUCCESS_REWARD_BASE,
                f"Planning succeeded for {task_id}",
                task_id,
            )
            return

        failure_type = classify_planning_failure(raw_plan, parse_error)
        penalty = self.FAILURE_PENALTY_BASE

        if failure_type == "invalid_json":
            self._adjust_if_not_capped(
                "json_formatting",
                "valid_json_rate",
                penalty,
                f"Planning produced invalid JSON for {task_id}",
                task_id,
            )
            self._adjust_if_not_capped(
                "planning",
                "dag_correctness",
                penalty * 0.5,
                f"Planning JSON unparseable for {task_id}",
                task_id,
            )

        elif failure_type == "missing_fields":
            self._adjust_if_not_capped(
                "json_formatting",
                "schema_compliance",
                penalty,
                f"Planning JSON missing required fields for {task_id}",
                task_id,
            )

        elif failure_type == "invalid_dag":
            self._adjust_if_not_capped(
                "planning",
                "dependency_accuracy",
                penalty,
                f"Planning produced invalid DAG for {task_id}",
                task_id,
            )
            self._adjust_if_not_capped(
                "planning",
                "dag_correctness",
                penalty * 0.7,
                f"Planning DAG topology error for {task_id}",
                task_id,
            )

        elif failure_type == "poor_granularity":
            self._adjust_if_not_capped(
                "planning",
                "task_granularity_appropriateness",
                penalty * 0.8,
                f"Planning granularity poor for {task_id}",
                task_id,
            )

    def record_verification_outcome(
        self,
        task_id: str,
        verifier_level: int,
        verifier_passed: bool,
        verifier_output_valid: bool,  # Was the verifier's output parseable?
    ) -> None:
        """Record a verification outcome and adjust code_review dimension."""
        if verifier_level == 3:
            if not verifier_output_valid:
                self._adjust_if_not_capped(
                    "code_review",
                    "structured_output",
                    self.FAILURE_PENALTY_BASE,
                    f"L3 verifier produced invalid output for {task_id}",
                    task_id,
                )
            elif not verifier_passed:
                # Verifier correctly rejected bad code — this is actually good
                # But if it keeps rejecting everything, that's bad too
                pass  # Neutral for now — hard to distinguish good vs bad rejections

    def _adjust_if_not_capped(
        self,
        dimension: str,
        sub_dimension: str,
        delta: float,
        reason: str,
        task_id: str | None = None,
    ) -> bool:
        """Apply adjustment only if dimension hasn't hit the cap.

        Returns True if adjustment was applied.
        """
        current_delta = self._capability.calibration.accumulated_deltas.get(dimension, {}).get(
            sub_dimension, 0.0
        )

        new_delta = current_delta + delta
        if abs(new_delta) > self.MAX_ADJUSTMENT_PER_DIMENSION:
            # Cap the adjustment
            new_delta = (
                self.MAX_ADJUSTMENT_PER_DIMENSION
                if new_delta > 0
                else -self.MAX_ADJUSTMENT_PER_DIMENSION
            )
            if new_delta == current_delta:
                return False  # Already at cap

        self._capability.record_adjustment(
            dimension=dimension,
            sub_dimension=sub_dimension,
            delta=delta,
            reason=reason,
            task_id=task_id,
        )
        return True

    def get_calibrated_capability(self) -> ModelCapability:
        """Get the current calibrated capability profile."""
        return self._capability.clone()

    def get_success_rate(self) -> float:
        """Get observed task success rate."""
        if self._outcome_count == 0:
            return 1.0
        return self._success_count / self._outcome_count

    def should_escalate_to_stronger_model(self) -> bool:
        """Determine if the current model is struggling too much.

        Returns True if success rate is critically low and multiple
        dimensions have been heavily penalized.
        """
        if self._outcome_count < 3:
            return False  # Not enough samples

        success_rate = self.get_success_rate()
        if success_rate > 0.5:
            return False

        # Count heavily penalized dimensions
        heavily_penalized = 0
        for dim_deltas in self._capability.calibration.accumulated_deltas.values():
            for delta in dim_deltas.values():
                if delta < -0.15:
                    heavily_penalized += 1

        return heavily_penalized >= 2

    def reset_calibration(self) -> None:
        """Reset runtime calibration to base benchmark scores."""
        self._capability = self.base.clone()
        self._outcome_count = 0
        self._success_count = 0
