"""Adaptive configuration mapper — now driven by runtime success rates.

The old approach used benchmark scores to statically restrict model behaviour.
That proved unnecessary for modern models (9B scores 92%+).  The new approach:

1. Start with optimistic defaults (assume the model is capable).
2. Track actual success rates per task type at runtime.
3. If a task type consistently fails, tighten ONLY that type's strategy.
4. If success rates recover, keep the defaults.

This means the framework never artificially limits a strong model, but it
reacts quickly when a model genuinely struggles with a specific task type.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .schema import (
    ModelCapability,
    PlanningStrategy,
    RuntimeStats,
    TaskGranularity,
    VerifierStrategy,
)


@dataclass
class AdaptiveOrchestratorConfig:
    """Runtime configuration consumed by the orchestrator, adapter, verifiers."""

    # Planning
    planning_strategy: PlanningStrategy = PlanningStrategy.FULL_DAG
    max_tasks_per_phase: int = 8
    max_files_per_task: int = 4
    force_dependency_declaration: bool = True

    # Execution
    max_turns_multiplier: float = 1.0
    auto_worker_selection: bool = True
    inject_objective_reminder_every: int = 3
    enable_self_correction: bool = True
    max_self_correction_attempts: int = 2

    # Verification
    verifier_strategy: VerifierStrategy = VerifierStrategy.FULL_L3
    enable_l1: bool = True
    enable_l2: bool = True
    enable_l3: bool = True
    l3_complexity_threshold: int = 3
    auto_approve_very_simple: bool = False

    # Retry & Reflect
    max_rework_attempts: int = 4
    enable_redesign: bool = True
    redesign_threshold: float = 0.3

    # Task granularity
    task_granularity: TaskGranularity = TaskGranularity.COARSE
    max_lines_per_task: int = 300
    max_task_objective_tokens: int = 800

    # JSON output handling
    require_json_schema: bool = True
    json_retry_on_failure: bool = True
    json_max_retries: int = 2

    # Weak-model compensation (execution)
    enable_auto_verify: bool = False
    verify_after_each_edit: bool = False
    max_edits_per_round: int = 5
    enable_smart_edit_planner: bool = True

    # Weak-model compensation (critical decisions)
    ask_user_on_critical_decisions: bool = False
    enforce_test_before_mark_complete: bool = False

    # Monitoring
    stagnation_threshold_seconds: float = 120.0

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
            "enable_auto_verify": self.enable_auto_verify,
            "verify_after_each_edit": self.verify_after_each_edit,
            "max_edits_per_round": self.max_edits_per_round,
            "enable_smart_edit_planner": self.enable_smart_edit_planner,
            "ask_user_on_critical_decisions": self.ask_user_on_critical_decisions,
            "enforce_test_before_mark_complete": self.enforce_test_before_mark_complete,
        }


class AdaptiveConfigMapper:
    """Maps runtime success rates to AdaptiveOrchestratorConfig.

    Benchmark scores are kept for reference but no longer drive config.
    """

    @classmethod
    def default_config(cls) -> AdaptiveOrchestratorConfig:
        """Return optimistic defaults (assume capable model)."""
        return AdaptiveOrchestratorConfig()

    @classmethod
    def from_capability(cls, capability: ModelCapability) -> AdaptiveOrchestratorConfig:
        """Generate config from a capability profile.

        DEPRECATED: benchmark scores are no longer used to restrict config.
        Returns the same optimistic default for all models.
        """
        # pylint: disable=unused-argument
        return cls.default_config()

    @classmethod
    def update_from_runtime(
        cls,
        config: AdaptiveOrchestratorConfig,
        stats: RuntimeStats,
    ) -> AdaptiveOrchestratorConfig:
        """Adjust config based on observed runtime success rates.

        Only tightens strategy for task types that are actually failing
        at runtime.  Keeps defaults for well-performing types.
        """
        # JSON struggling → more retries, drop schema requirements
        if stats.is_struggling("json", threshold=0.5):
            config.json_max_retries = 3
            config.require_json_schema = False
            config.json_retry_on_failure = True
            config.verifier_strategy = VerifierStrategy.SIMPLIFIED_L3

        # Code struggling → atomic edits, auto-verify
        if stats.is_struggling("code", threshold=0.5):
            config.enable_auto_verify = True
            config.verify_after_each_edit = True
            config.max_edits_per_round = 1
            config.enable_smart_edit_planner = True
            config.max_rework_attempts = 2

        # Planning struggling → simpler planning
        if stats.is_struggling("planning", threshold=0.5):
            config.planning_strategy = PlanningStrategy.PHASED
            config.max_tasks_per_phase = 3
            config.task_granularity = TaskGranularity.FINE
            config.max_lines_per_task = 80
            config.max_files_per_task = 1
            config.force_dependency_declaration = False

        # Reasoning struggling → frequent reminders, user confirmation
        if stats.is_struggling("reasoning", threshold=0.5):
            config.inject_objective_reminder_every = 1
            config.ask_user_on_critical_decisions = True
            config.enable_self_correction = False
            config.max_rework_attempts = 1

        # Review / verification struggling → enforce tests
        if stats.is_struggling("review", threshold=0.5):
            config.enforce_test_before_mark_complete = True
            config.auto_approve_very_simple = False
            config.verifier_strategy = VerifierStrategy.STATIC_ONLY

        return config


def apply_adaptive_config_to_strategy_config(
    adaptive: AdaptiveOrchestratorConfig,
    strategy_config: Any,
) -> Any:
    """Apply adaptive configuration to a StrategyConfig object.

    Returns a new StrategyConfig because the original is a frozen dataclass.
    """
    from dataclasses import replace

    return replace(
        strategy_config,
        max_tasks_per_phase=adaptive.max_tasks_per_phase,
        max_files_per_task=adaptive.max_files_per_task,
        force_dependency_declaration=adaptive.force_dependency_declaration,
        max_turns_multiplier=adaptive.max_turns_multiplier,
        auto_worker_selection=adaptive.auto_worker_selection,
        inject_objective_reminder_every=adaptive.inject_objective_reminder_every,
        enable_l1=adaptive.enable_l1,
        enable_l2=adaptive.enable_l2,
        enable_l3=adaptive.enable_l3,
        l3_complexity_threshold=adaptive.l3_complexity_threshold,
        auto_approve_very_simple=adaptive.auto_approve_very_simple,
        max_rework_attempts=adaptive.max_rework_attempts,
        enable_redesign=adaptive.enable_redesign,
    )
