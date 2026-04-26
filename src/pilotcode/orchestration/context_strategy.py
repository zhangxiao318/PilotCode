"""Context strategy framework for P-EVR.

Adapts the Plan-Execute-Verify-Reflect pipeline based on available
LLM context window length. The core insight: with limited context,
the framework must aggressively decompose tasks; with abundant context,
the LLM can handle more planning and execution autonomously.

Usage:
    from pilotcode.orchestration.context_strategy import ContextStrategy, ContextStrategySelector

    strategy = ContextStrategySelector.select(context_budget=8192)
    # -> ContextStrategy.FRAMEWORK_HEAVY

    config = strategy.get_config()
    adjuster = MissionPlanAdjuster(strategy)
    adjusted_mission = adjuster.adjust(mission)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from .task_spec import Mission, TaskSpec, Phase, ComplexityLevel, Constraints


class ContextStrategy(Enum):
    """Strategy for balancing framework vs LLM control based on context budget.

    ┌─────────────────┬─────────────────────────────────────────────┐
    │ Strategy        │ When to use                                 │
    ├─────────────────┼─────────────────────────────────────────────┤
    │ FRAMEWORK_HEAVY │ context <= 12K: framework dominates Plan+DAG│
    │ BALANCED        │ 12K < context <= 48K: mixed responsibility  │
    │ LLM_HEAVY       │ context > 48K: LLM dominates, framework is  │
    │                 │   safety net (Verify + Reflect only)        │
    └─────────────────┴─────────────────────────────────────────────┘
    """

    FRAMEWORK_HEAVY = "framework_heavy"
    BALANCED = "balanced"
    LLM_HEAVY = "llm_heavy"


@dataclass(frozen=True)
class StrategyConfig:
    """Configuration parameters for a context strategy.

    These parameters control how aggressively the framework decomposes
    tasks, how much it constrains the LLM, and how much verification
    is applied.
    """

    # ---- Plan layer parameters ----
    max_tasks_per_phase: int  # Upper bound on tasks in a single phase
    max_files_per_task: int  # How many files a single task can touch
    force_dependency_declaration: bool  # Must declare all dependencies explicitly
    max_task_objective_tokens: int  # Approximate token limit for task objective

    # ---- Execute layer parameters ----
    max_turns_multiplier: float  # Multiplier for DEFAULT_TURN_LIMITS
    auto_worker_selection: bool  # Framework auto-selects worker type
    inject_objective_reminder_every: int  # Remind LLM of objective every N turns

    # ---- Verify layer parameters ----
    enable_l1: bool
    enable_l2: bool
    enable_l3: bool
    l3_complexity_threshold: int  # Min complexity to trigger L3 review
    auto_approve_very_simple: bool

    # ---- Reflect layer parameters ----
    max_rework_attempts: int
    enable_redesign: bool  # Allow triggering redesign on critical failures

    # ---- Plan prompt guidance ----
    plan_prompt_suffix: str  # Extra instructions injected into planner prompt


# Pre-defined configurations for each strategy
_FRAMEWORK_HEAVY_CONFIG = StrategyConfig(
    max_tasks_per_phase=4,
    max_files_per_task=2,
    force_dependency_declaration=True,
    max_task_objective_tokens=300,
    max_turns_multiplier=1.0,
    auto_worker_selection=True,
    inject_objective_reminder_every=2,
    enable_l1=True,
    enable_l2=True,
    enable_l3=False,  # Short context models usually weak at L3 review
    l3_complexity_threshold=5,
    auto_approve_very_simple=True,
    max_rework_attempts=2,  # Limited patience with weak models
    enable_redesign=False,
    plan_prompt_suffix=(
        "\n[CONTEXT CONSTRAINT] You are planning for a model with VERY LIMITED context (8K). "
        "CRITICAL RULES:\n"
        "- Each task MUST touch at most 2 files\n"
        "- Each task objective MUST be under 300 tokens\n"
        "- Break every feature into the SMALLEST possible sub-tasks\n"
        "- Prefer MORE phases with FEWER tasks each\n"
        "- Dependencies MUST be explicit and minimal\n"
        "- Avoid tasks that require reading large files (>200 lines)\n"
    ),
)

_BALANCED_CONFIG = StrategyConfig(
    max_tasks_per_phase=6,
    max_files_per_task=4,
    force_dependency_declaration=True,
    max_task_objective_tokens=600,
    max_turns_multiplier=1.2,
    auto_worker_selection=True,
    inject_objective_reminder_every=3,
    enable_l1=True,
    enable_l2=True,
    enable_l3=True,
    l3_complexity_threshold=3,
    auto_approve_very_simple=True,
    max_rework_attempts=3,
    enable_redesign=True,
    plan_prompt_suffix=(
        "\n[CONTEXT GUIDANCE] You are planning for a model with MODERATE context (32K). "
        "GUIDELINES:\n"
        "- Each task should touch at most 4 files\n"
        "- Task objectives can be moderately detailed\n"
        "- Balance granularity: not too fine, not too coarse\n"
        "- Include clear acceptance criteria for each task\n"
    ),
)

_LLM_HEAVY_CONFIG = StrategyConfig(
    max_tasks_per_phase=10,
    max_files_per_task=8,
    force_dependency_declaration=False,
    max_task_objective_tokens=1200,
    max_turns_multiplier=1.5,
    auto_worker_selection=False,  # Let LLM choose worker type
    inject_objective_reminder_every=5,
    enable_l1=True,
    enable_l2=True,
    enable_l3=True,
    l3_complexity_threshold=2,
    auto_approve_very_simple=False,  # Even simple tasks get verified
    max_rework_attempts=5,  # Strong models benefit from more retries
    enable_redesign=True,
    plan_prompt_suffix=(
        "\n[CONTEXT GUIDANCE] You are planning for a model with LARGE context (64K+). "
        "GUIDELINES:\n"
        "- You can group related work into larger tasks\n"
        "- Tasks may touch up to 8 files if logically related\n"
        "- Trust the model's ability to handle complex sub-tasks\n"
        "- Still define clear boundaries between phases\n"
        "- Include comprehensive acceptance criteria\n"
    ),
)

_STRATEGY_CONFIG_MAP: dict[ContextStrategy, StrategyConfig] = {
    ContextStrategy.FRAMEWORK_HEAVY: _FRAMEWORK_HEAVY_CONFIG,
    ContextStrategy.BALANCED: _BALANCED_CONFIG,
    ContextStrategy.LLM_HEAVY: _LLM_HEAVY_CONFIG,
}


class ContextStrategySelector:
    """Selects the optimal context strategy based on available context budget.

    The selection is based on empirical thresholds derived from E2E testing:
    - 8K models: struggle with multi-file reasoning, need aggressive decomposition
    - 32K models: capable of moderate planning, balanced approach works best
    - 64K+ models: can see entire codebases, framework acts as safety net
    """

    # Thresholds (in tokens)
    SHORT_CTX_THRESHOLD = 12_000  # <= 12K: FRAMEWORK_HEAVY
    LONG_CTX_THRESHOLD = 48_000  # > 48K: LLM_HEAVY

    @classmethod
    def select(
        cls,
        context_budget: int,
        capability: Any | None = None,
    ) -> ContextStrategy:
        """Select strategy based on context budget and optional model capability.

        Args:
            context_budget: Available context window size in tokens.
            capability: Optional ModelCapability to adjust thresholds dynamically.
                Lower capability scores shift selection toward FRAMEWORK_HEAVY
                (more decomposition, less reliance on model reasoning).

        Returns:
            The recommended ContextStrategy.
        """
        short_threshold = cls.SHORT_CTX_THRESHOLD
        long_threshold = cls.LONG_CTX_THRESHOLD

        # Adjust thresholds based on model capability
        if capability is not None:
            overall = getattr(capability, "overall_score", 0.5)
            if overall < 0.5:
                # Weak model: be more conservative
                short_threshold = int(cls.SHORT_CTX_THRESHOLD * 1.5)
                long_threshold = int(cls.LONG_CTX_THRESHOLD * 1.25)
            elif overall > 0.8:
                # Strong model: can handle more context
                short_threshold = int(cls.SHORT_CTX_THRESHOLD * 0.75)
                long_threshold = int(cls.LONG_CTX_THRESHOLD * 0.9)

        if context_budget <= short_threshold:
            return ContextStrategy.FRAMEWORK_HEAVY
        elif context_budget <= long_threshold:
            return ContextStrategy.BALANCED
        else:
            return ContextStrategy.LLM_HEAVY

    @classmethod
    def get_config(
        cls, strategy: ContextStrategy | None = None, context_budget: int | None = None
    ) -> StrategyConfig:
        """Get configuration for a strategy.

        Args:
            strategy: Explicit strategy. If None, inferred from context_budget.
            context_budget: Used to select strategy if strategy is None.

        Raises:
            ValueError: If neither strategy nor context_budget is provided.
        """
        if strategy is None:
            if context_budget is None:
                raise ValueError("Must provide either strategy or context_budget")
            strategy = cls.select(context_budget)
        return _STRATEGY_CONFIG_MAP[strategy]


class MissionPlanAdjuster:
    """Adjusts a Mission Plan based on the active context strategy.

    This is the key mechanism for context-aware adaptation:
    - FRAMEWORK_HEAVY: splits large tasks, enforces file limits, caps complexity
    - BALANCED: moderate adjustments
    - LLM_HEAVY: minimal intervention, trusts LLM's plan
    """

    def __init__(self, strategy: ContextStrategy | None = None, context_budget: int | None = None):
        if strategy is not None:
            self.strategy = strategy
            self.config = ContextStrategySelector.get_config(strategy=strategy)
        elif context_budget is not None:
            self.strategy = ContextStrategySelector.select(context_budget)
            self.config = ContextStrategySelector.get_config(context_budget=context_budget)
        else:
            self.strategy = ContextStrategy.BALANCED
            self.config = ContextStrategySelector.get_config(strategy=ContextStrategy.BALANCED)

    def adjust(self, mission: Mission) -> Mission:
        """Adjust mission plan according to strategy.

        Returns a new Mission with adjusted task granularity, constraints,
        and context budgets. Original mission is not modified.
        """
        adjusted = Mission(
            mission_id=mission.mission_id,
            title=mission.title,
            requirement=mission.requirement,
            metadata={**mission.metadata, "context_strategy": self.strategy.value},
            created_at=mission.created_at,
        )

        for phase in mission.phases:
            adj_phase = self._adjust_phase(phase)
            adjusted.phases.append(adj_phase)

        return adjusted

    def _adjust_phase(self, phase: Phase) -> Phase:
        """Adjust a single phase's tasks."""
        adj_phase = Phase(
            phase_id=phase.phase_id,
            title=phase.title,
            description=phase.description,
            dependencies=phase.dependencies,
            metadata={**phase.metadata},
        )

        # Collect all tasks
        tasks = list(phase.tasks)

        # FRAMEWORK_HEAVY: if too many tasks, suggest splitting into sub-phases
        # (but we keep them in same phase for simplicity, just enforce limits)
        for task in tasks:
            adj_task = self._adjust_task(task)
            adj_phase.tasks.append(adj_task)

        return adj_phase

    def _adjust_task(self, task: TaskSpec) -> TaskSpec:
        """Adjust a single task according to strategy config."""
        adj = TaskSpec(
            id=task.id,
            title=task.title,
            objective=task.objective,
            inputs=list(task.inputs),
            outputs=list(task.outputs),
            dependencies=list(task.dependencies),
            estimated_complexity=self._cap_complexity(task.estimated_complexity),
            acceptance_criteria=list(task.acceptance_criteria),
            constraints=self._adjust_constraints(task.constraints),
            context_budget=self._compute_task_context_budget(),
            phase_id=task.phase_id,
            worker_type=self._select_worker_type(task),
            metadata={**task.metadata, "strategy": self.strategy.value},
        )
        return adj

    def _cap_complexity(self, complexity: ComplexityLevel) -> ComplexityLevel:
        """Cap complexity based on strategy."""
        if self.strategy == ContextStrategy.FRAMEWORK_HEAVY:
            # Short context: nothing above MODERATE
            if complexity.value > ComplexityLevel.MODERATE.value:
                return ComplexityLevel.MODERATE
        elif self.strategy == ContextStrategy.BALANCED:
            # Medium context: nothing above COMPLEX
            if complexity.value > ComplexityLevel.COMPLEX.value:
                return ComplexityLevel.COMPLEX
        # LLM_HEAVY: no cap
        return complexity

    def _adjust_constraints(self, constraints: Constraints) -> Constraints:
        """Adjust constraints based on strategy."""
        max_lines = constraints.max_lines
        if max_lines is None:
            # Apply default limits per strategy
            if self.strategy == ContextStrategy.FRAMEWORK_HEAVY:
                max_lines = 150
            elif self.strategy == ContextStrategy.BALANCED:
                max_lines = 300
            else:
                max_lines = 500
        else:
            # Enforce upper bounds
            if self.strategy == ContextStrategy.FRAMEWORK_HEAVY:
                max_lines = min(max_lines, 150)
            elif self.strategy == ContextStrategy.BALANCED:
                max_lines = min(max_lines, 300)
            elif self.strategy == ContextStrategy.LLM_HEAVY:
                max_lines = min(max_lines, 500)

        return Constraints(
            max_lines=max_lines,
            must_use=list(constraints.must_use),
            must_not_use=list(constraints.must_not_use),
            patterns=list(constraints.patterns),
            forbidden_patterns=list(constraints.forbidden_patterns),
        )

    def _compute_task_context_budget(self) -> int:
        """Compute per-task context budget based on strategy."""
        if self.strategy == ContextStrategy.FRAMEWORK_HEAVY:
            return 6000  # Leave 2K for system prompt + tool results
        elif self.strategy == ContextStrategy.BALANCED:
            return 24000  # Leave 8K buffer
        else:
            return 56000  # Leave 8K buffer

    def _select_worker_type(self, task: TaskSpec) -> str:
        """Override worker type selection based on strategy."""
        if self.config.auto_worker_selection:
            # Framework decides based on capped complexity
            comp = self._cap_complexity(task.estimated_complexity)
            if comp == ComplexityLevel.VERY_SIMPLE:
                return "simple"
            elif comp in (ComplexityLevel.SIMPLE, ComplexityLevel.MODERATE):
                return "standard"
            else:
                return "complex"
        # LLM_HEAVY: trust the original worker_type or "auto"
        return task.worker_type

    def get_plan_prompt_suffix(self) -> str:
        """Get the prompt suffix to inject into planner system prompt."""
        return self.config.plan_prompt_suffix

    def apply_to_orchestrator_config(self, orch_config: Any) -> Any:
        """Apply strategy config to an OrchestratorConfig instance.

        Returns a modified copy of the config with strategy-aware settings.
        """
        orch_config.enable_l1_verification = self.config.enable_l1
        orch_config.enable_l2_verification = self.config.enable_l2
        orch_config.enable_l3_verification = self.config.enable_l3
        orch_config.max_rework_attempts = self.config.max_rework_attempts
        orch_config.auto_approve_simple = self.config.auto_approve_very_simple
        return orch_config


class StrategyMetrics:
    """Metrics collected during strategy execution for comparison."""

    def __init__(self, strategy: ContextStrategy, context_budget: int):
        self.strategy = strategy
        self.context_budget = context_budget
        self.total_tasks: int = 0
        self.total_phases: int = 0
        self.avg_task_complexity: float = 0.0
        self.avg_files_per_task: float = 0.0
        self.verification_pass_rate: float = 0.0
        self.rework_count: int = 0
        self.redesign_count: int = 0
        self.total_token_usage: int = 0
        self.total_time_seconds: float = 0.0
        self.tasks_completed: int = 0
        self.tasks_failed: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "strategy": self.strategy.value,
            "context_budget": self.context_budget,
            "total_tasks": self.total_tasks,
            "total_phases": self.total_phases,
            "avg_task_complexity": self.avg_task_complexity,
            "avg_files_per_task": self.avg_files_per_task,
            "verification_pass_rate": self.verification_pass_rate,
            "rework_count": self.rework_count,
            "redesign_count": self.redesign_count,
            "total_token_usage": self.total_token_usage,
            "total_time_seconds": self.total_time_seconds,
            "tasks_completed": self.tasks_completed,
            "tasks_failed": self.tasks_failed,
        }

    @classmethod
    def from_mission_execution(
        cls,
        strategy: ContextStrategy,
        context_budget: int,
        mission: Mission,
        tracker: Any,
    ) -> StrategyMetrics:
        """Compute metrics from a completed mission execution."""
        metrics = cls(strategy, context_budget)
        tasks = mission.all_tasks()
        metrics.total_tasks = len(tasks)
        metrics.total_phases = len(mission.phases)

        if tasks:
            complexities = [t.estimated_complexity.value for t in tasks]
            metrics.avg_task_complexity = sum(complexities) / len(complexities)

            file_counts = [len(t.inputs) + len(t.outputs) for t in tasks]
            metrics.avg_files_per_task = sum(file_counts) / len(file_counts)

        # Tracker stats would be populated here in production
        return metrics
