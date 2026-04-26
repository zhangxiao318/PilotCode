"""Adaptive configuration mapper.

Translates ModelCapability scores into concrete orchestration parameters:
- Task granularity
- Planning strategy
- Verifier strategy
- Retry policies
- Context strategy adjustments
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .schema import (
    ModelCapability,
    PlanningStrategy,
    TaskGranularity,
    VerifierStrategy,
)


@dataclass
class AdaptiveOrchestratorConfig:
    """Runtime configuration derived from model capability.

    This is the concrete output of the adaptive system — a set of parameters
    that the orchestrator, adapter, and verifiers consume to adjust their
    behavior to the current model's strengths and weaknesses.
    """

    # Planning
    planning_strategy: PlanningStrategy = PlanningStrategy.PHASED
    max_tasks_per_phase: int = 4
    max_files_per_task: int = 2
    force_dependency_declaration: bool = True

    # Execution
    max_turns_multiplier: float = 1.0
    auto_worker_selection: bool = True
    inject_objective_reminder_every: int = 3
    enable_self_correction: bool = True
    max_self_correction_attempts: int = 2

    # Verification
    verifier_strategy: VerifierStrategy = VerifierStrategy.SIMPLIFIED_L3
    enable_l1: bool = True
    enable_l2: bool = True
    enable_l3: bool = True
    l3_complexity_threshold: int = 3
    auto_approve_very_simple: bool = False

    # Retry & Reflect
    max_rework_attempts: int = 2
    enable_redesign: bool = False
    redesign_threshold: float = 0.3  # overall_score below this triggers redesign

    # Task granularity
    task_granularity: TaskGranularity = TaskGranularity.MEDIUM
    max_lines_per_task: int = 150
    max_task_objective_tokens: int = 500

    # JSON output handling
    require_json_schema: bool = True
    json_retry_on_failure: bool = True
    json_max_retries: int = 2

    # Monitoring
    stagnation_threshold_seconds: float = 60.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "planning_strategy": self.planning_strategy.value,
            "max_tasks_per_phase": self.max_tasks_per_phase,
            "max_files_per_task": self.max_files_per_task,
            "force_dependency_declaration": self.force_dependency_declaration,
            "max_turns_multiplier": self.max_turns_multiplier,
            "auto_worker_selection": self.auto_worker_selection,
            "inject_objective_reminder_every": self.inject_objective_reminder_every,
            "enable_self_correction": self.enable_self_correction,
            "max_self_correction_attempts": self.max_self_correction_attempts,
            "verifier_strategy": self.verifier_strategy.value,
            "enable_l1": self.enable_l1,
            "enable_l2": self.enable_l2,
            "enable_l3": self.enable_l3,
            "l3_complexity_threshold": self.l3_complexity_threshold,
            "auto_approve_very_simple": self.auto_approve_very_simple,
            "max_rework_attempts": self.max_rework_attempts,
            "enable_redesign": self.enable_redesign,
            "redesign_threshold": self.redesign_threshold,
            "task_granularity": self.task_granularity.value,
            "max_lines_per_task": self.max_lines_per_task,
            "max_task_objective_tokens": self.max_task_objective_tokens,
            "require_json_schema": self.require_json_schema,
            "json_retry_on_failure": self.json_retry_on_failure,
            "json_max_retries": self.json_max_retries,
            "stagnation_threshold_seconds": self.stagnation_threshold_seconds,
        }


class AdaptiveConfigMapper:
    """Maps ModelCapability scores to AdaptiveOrchestratorConfig.

    The mapping logic is based on empirical thresholds derived from
    internal benchmark testing across multiple model families.
    """

    # Thresholds for dimension scores
    STRONG_THRESHOLD = 0.80
    MODERATE_THRESHOLD = 0.55
    WEAK_THRESHOLD = 0.30

    @classmethod
    def from_capability(cls, capability: ModelCapability) -> AdaptiveOrchestratorConfig:
        """Generate adaptive configuration from a capability profile.

        Uses effective scores (base + runtime calibration) for the mapping.
        """
        config = AdaptiveOrchestratorConfig()

        # Get effective dimension scores
        planning_eff = capability.get_effective_dimension("planning")["score"]
        completion_eff = capability.get_effective_dimension("task_completion")["score"]
        json_eff = capability.get_effective_dimension("json_formatting")["score"]
        cot_eff = capability.get_effective_dimension("chain_of_thought")["score"]
        review_eff = capability.get_effective_dimension("code_review")["score"]
        overall = capability.get_overall_effective_score()

        # --- Planning Strategy ---
        config.planning_strategy = cls._select_planning_strategy(planning_eff, cot_eff)

        # --- Task Granularity ---
        config.task_granularity = cls._select_task_granularity(planning_eff, completion_eff)
        config.max_lines_per_task = {
            TaskGranularity.FINE: 80,
            TaskGranularity.MEDIUM: 150,
            TaskGranularity.COARSE: 300,
        }[config.task_granularity]
        config.max_files_per_task = {
            TaskGranularity.FINE: 1,
            TaskGranularity.MEDIUM: 2,
            TaskGranularity.COARSE: 4,
        }[config.task_granularity]

        # --- Phase/Task Limits ---
        config.max_tasks_per_phase = cls._map_range(planning_eff, 3, 8)
        config.max_task_objective_tokens = cls._map_range(planning_eff, 300, 800)

        # --- Verifier Strategy ---
        config.verifier_strategy = cls._select_verifier_strategy(review_eff, json_eff)
        config.enable_l3 = config.verifier_strategy != VerifierStrategy.STATIC_ONLY
        config.l3_complexity_threshold = cls._map_range(review_eff, 2, 5)

        # --- Self-Correction ---
        config.enable_self_correction = json_eff > cls.WEAK_THRESHOLD
        config.json_max_retries = cls._map_range(json_eff, 3, 0)
        config.json_retry_on_failure = json_eff < cls.STRONG_THRESHOLD
        config.require_json_schema = json_eff > cls.MODERATE_THRESHOLD

        # --- Retry & Redesign ---
        config.max_rework_attempts = cls._map_range(overall, 1, 4)
        config.enable_redesign = (
            overall > cls.MODERATE_THRESHOLD and cot_eff > cls.MODERATE_THRESHOLD
        )
        config.redesign_threshold = cls._map_range(overall, 0.15, 0.40)

        # --- Execution Hints ---
        config.max_turns_multiplier = cls._map_float(overall, 0.7, 1.5)
        config.inject_objective_reminder_every = cls._map_range(completion_eff, 2, 5)
        config.auto_approve_very_simple = overall > cls.STRONG_THRESHOLD

        # --- Stagnation Detection ---
        config.stagnation_threshold_seconds = cls._map_float(overall, 30.0, 120.0)

        return config

    @classmethod
    def _select_planning_strategy(cls, planning_score: float, cot_score: float) -> PlanningStrategy:
        if planning_score > cls.STRONG_THRESHOLD and cot_score > cls.MODERATE_THRESHOLD:
            return PlanningStrategy.FULL_DAG
        elif planning_score > cls.WEAK_THRESHOLD:
            return PlanningStrategy.PHASED
        else:
            return PlanningStrategy.TEMPLATE_BASED

    @classmethod
    def _select_task_granularity(
        cls, planning_score: float, completion_score: float
    ) -> TaskGranularity:
        avg = (planning_score + completion_score) / 2
        if avg > cls.STRONG_THRESHOLD:
            return TaskGranularity.COARSE
        elif avg > cls.MODERATE_THRESHOLD:
            return TaskGranularity.MEDIUM
        else:
            return TaskGranularity.FINE

    @classmethod
    def _select_verifier_strategy(cls, review_score: float, json_score: float) -> VerifierStrategy:
        if review_score > cls.STRONG_THRESHOLD and json_score > cls.MODERATE_THRESHOLD:
            return VerifierStrategy.FULL_L3
        elif review_score > cls.MODERATE_THRESHOLD:
            return VerifierStrategy.SIMPLIFIED_L3
        else:
            return VerifierStrategy.STATIC_ONLY

    @staticmethod
    def _map_range(score: float, min_val: int, max_val: int) -> int:
        """Map a 0.0-1.0 score to an integer range [min_val, max_val]."""
        clamped = max(0.0, min(1.0, score))
        return int(min_val + (max_val - min_val) * clamped)

    @staticmethod
    def _map_float(score: float, min_val: float, max_val: float) -> float:
        """Map a 0.0-1.0 score to a float range [min_val, max_val]."""
        clamped = max(0.0, min(1.0, score))
        return min_val + (max_val - min_val) * clamped


def apply_adaptive_config_to_strategy_config(
    adaptive: AdaptiveOrchestratorConfig,
    strategy_config: Any,  # StrategyConfig from context_strategy
) -> None:
    """Apply adaptive configuration to an existing StrategyConfig object.

    This bridges the new adaptive system with the existing context_strategy module.
    """
    strategy_config.max_tasks_per_phase = adaptive.max_tasks_per_phase
    strategy_config.max_files_per_task = adaptive.max_files_per_task
    strategy_config.force_dependency_declaration = adaptive.force_dependency_declaration
    strategy_config.max_turns_multiplier = adaptive.max_turns_multiplier
    strategy_config.auto_worker_selection = adaptive.auto_worker_selection
    strategy_config.inject_objective_reminder_every = adaptive.inject_objective_reminder_every
    strategy_config.enable_l1 = adaptive.enable_l1
    strategy_config.enable_l2 = adaptive.enable_l2
    strategy_config.enable_l3 = adaptive.enable_l3
    strategy_config.l3_complexity_threshold = adaptive.l3_complexity_threshold
    strategy_config.auto_approve_very_simple = adaptive.auto_approve_very_simple
    strategy_config.max_rework_attempts = adaptive.max_rework_attempts
    strategy_config.enable_redesign = adaptive.enable_redesign
