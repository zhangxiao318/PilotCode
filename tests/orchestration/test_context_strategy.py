"""Unit tests for the ContextStrategy framework.

Tests strategy selection, plan adjustment, and configuration application
without requiring LLM calls.
"""

import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from pilotcode.orchestration.context_strategy import (
    ContextStrategy,
    ContextStrategySelector,
    MissionPlanAdjuster,
    StrategyMetrics,
    StrategyConfig,
)
from pilotcode.orchestration.task_spec import (
    Mission,
    Phase,
    TaskSpec,
    ComplexityLevel,
    Constraints,
    AcceptanceCriterion,
)

# =============================================================================
# ContextStrategySelector Tests
# =============================================================================


class TestContextStrategySelector:
    """Tests for strategy selection based on context budget."""

    @pytest.mark.parametrize(
        "budget,expected",
        [
            (4096, ContextStrategy.FRAMEWORK_HEAVY),
            (8192, ContextStrategy.FRAMEWORK_HEAVY),
            (12000, ContextStrategy.FRAMEWORK_HEAVY),
            (12001, ContextStrategy.BALANCED),
            (16000, ContextStrategy.BALANCED),
            (32000, ContextStrategy.BALANCED),
            (48000, ContextStrategy.BALANCED),
            (48001, ContextStrategy.LLM_HEAVY),
            (64000, ContextStrategy.LLM_HEAVY),
            (128000, ContextStrategy.LLM_HEAVY),
        ],
    )
    def test_select(self, budget: int, expected: ContextStrategy) -> None:
        """Strategy selection respects threshold boundaries."""
        result = ContextStrategySelector.select(budget)
        assert result == expected, f"Expected {expected.value} for {budget}, got {result.value}"

    def test_get_config_by_strategy(self) -> None:
        """Get config for each strategy directly."""
        for strategy in ContextStrategy:
            config = ContextStrategySelector.get_config(strategy=strategy)
            assert isinstance(config, StrategyConfig)
            assert config.max_tasks_per_phase > 0

    def test_get_config_by_budget(self) -> None:
        """Get config inferred from budget."""
        config = ContextStrategySelector.get_config(context_budget=8192)
        assert config.max_tasks_per_phase == 4  # FRAMEWORK_HEAVY value

    def test_get_config_raises_without_args(self) -> None:
        """Must provide either strategy or budget."""
        with pytest.raises(ValueError, match="Must provide either strategy or context_budget"):
            ContextStrategySelector.get_config()


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def sample_mission() -> Mission:
    """Create a sample mission with varied task complexities."""
    return Mission(
        mission_id="test_mission",
        title="Test Mission",
        requirement="Implement a user auth system",
        phases=[
            Phase(
                phase_id="phase_1",
                title="Infrastructure",
                description="Setup base",
                tasks=[
                    TaskSpec(
                        id="task_1_1",
                        title="Config module",
                        objective="Create config loader",
                        inputs=["src/config/base.py"],
                        outputs=["src/config/loader.py"],
                        estimated_complexity=ComplexityLevel.SIMPLE,
                        constraints=Constraints(max_lines=300),
                    ),
                    TaskSpec(
                        id="task_1_2",
                        title="Database schema",
                        objective="Design user schema with 15 fields",
                        inputs=["src/models/base.py"],
                        outputs=["src/models/user.py", "src/models/migration.sql"],
                        estimated_complexity=ComplexityLevel.COMPLEX,
                        constraints=Constraints(max_lines=500),
                    ),
                ],
            ),
            Phase(
                phase_id="phase_2",
                title="API Layer",
                description="Build endpoints",
                tasks=[
                    TaskSpec(
                        id="task_2_1",
                        title="Auth endpoints",
                        objective="Implement login/register/refresh with JWT",
                        inputs=["src/models/user.py"],
                        outputs=[
                            "src/api/auth.py",
                            "src/api/register.py",
                            "src/api/login.py",
                            "src/api/refresh.py",
                        ],
                        dependencies=["task_1_2"],
                        estimated_complexity=ComplexityLevel.VERY_COMPLEX,
                        constraints=Constraints(max_lines=800),
                    ),
                ],
            ),
        ],
    )


# =============================================================================
# MissionPlanAdjuster Tests
# =============================================================================


class TestMissionPlanAdjuster:
    """Tests for plan adjustment based on strategy."""

    def test_framework_heavy_caps_complexity(self, sample_mission: Mission) -> None:
        """FRAMEWORK_HEAVY caps complexity at MODERATE."""
        adjuster = MissionPlanAdjuster(strategy=ContextStrategy.FRAMEWORK_HEAVY)
        adjusted = adjuster.adjust(sample_mission)

        for task in adjusted.all_tasks():
            assert (
                task.estimated_complexity.value <= ComplexityLevel.MODERATE.value
            ), f"Task {task.id} complexity {task.estimated_complexity} exceeds MODERATE"

    def test_framework_heavy_limits_max_lines(self, sample_mission: Mission) -> None:
        """FRAMEWORK_HEAVY enforces max_lines <= 150."""
        adjuster = MissionPlanAdjuster(strategy=ContextStrategy.FRAMEWORK_HEAVY)
        adjusted = adjuster.adjust(sample_mission)

        for task in adjusted.all_tasks():
            assert task.constraints.max_lines is not None
            assert (
                task.constraints.max_lines <= 150
            ), f"Task {task.id} max_lines {task.constraints.max_lines} exceeds 150"

    def test_framework_heavy_reduces_context_budget(self, sample_mission: Mission) -> None:
        """FRAMEWORK_HEAVY sets per-task context budget to 6K."""
        adjuster = MissionPlanAdjuster(strategy=ContextStrategy.FRAMEWORK_HEAVY)
        adjusted = adjuster.adjust(sample_mission)

        for task in adjusted.all_tasks():
            assert (
                task.context_budget == 6000
            ), f"Task {task.id} context_budget {task.context_budget} != 6000"

    def test_llm_heavy_preserves_high_complexity(self, sample_mission: Mission) -> None:
        """LLM_HEAVY does not cap complexity."""
        adjuster = MissionPlanAdjuster(strategy=ContextStrategy.LLM_HEAVY)
        adjusted = adjuster.adjust(sample_mission)

        complex_task = adjusted.get_task("task_2_1")
        assert complex_task is not None
        assert complex_task.estimated_complexity == ComplexityLevel.VERY_COMPLEX

    def test_llm_heavy_allows_larger_max_lines(self, sample_mission: Mission) -> None:
        """LLM_HEAVY allows max_lines up to 500."""
        adjuster = MissionPlanAdjuster(strategy=ContextStrategy.LLM_HEAVY)
        adjusted = adjuster.adjust(sample_mission)

        for task in adjusted.all_tasks():
            if task.constraints.max_lines is not None:
                assert (
                    task.constraints.max_lines <= 500
                ), f"Task {task.id} max_lines {task.constraints.max_lines} exceeds 500"

    def test_llm_heavy_increases_context_budget(self, sample_mission: Mission) -> None:
        """LLM_HEAVY sets per-task context budget to 56K."""
        adjuster = MissionPlanAdjuster(strategy=ContextStrategy.LLM_HEAVY)
        adjusted = adjuster.adjust(sample_mission)

        for task in adjusted.all_tasks():
            assert (
                task.context_budget == 56000
            ), f"Task {task.id} context_budget {task.context_budget} != 56000"

    def test_balanced_middle_ground(self, sample_mission: Mission) -> None:
        """BALANCED is between the two extremes."""
        adjuster = MissionPlanAdjuster(strategy=ContextStrategy.BALANCED)
        adjusted = adjuster.adjust(sample_mission)

        # Complexity capped at COMPLEX
        for task in adjusted.all_tasks():
            assert task.estimated_complexity.value <= ComplexityLevel.COMPLEX.value

        # max_lines capped at 300
        for task in adjusted.all_tasks():
            if task.constraints.max_lines is not None:
                assert task.constraints.max_lines <= 300

        # context budget at 24K
        for task in adjusted.all_tasks():
            assert task.context_budget == 24000

    def test_metadata_tagging(self, sample_mission: Mission) -> None:
        """Adjusted tasks get strategy metadata."""
        adjuster = MissionPlanAdjuster(strategy=ContextStrategy.FRAMEWORK_HEAVY)
        adjusted = adjuster.adjust(sample_mission)

        assert adjusted.metadata.get("context_strategy") == "framework_heavy"
        for task in adjusted.all_tasks():
            assert task.metadata.get("strategy") == "framework_heavy"

    def test_original_not_modified(self, sample_mission: Mission) -> None:
        """adjust() returns a new Mission without modifying original."""
        original_complexity = sample_mission.get_task("task_2_1").estimated_complexity
        adjuster = MissionPlanAdjuster(strategy=ContextStrategy.FRAMEWORK_HEAVY)
        adjusted = adjuster.adjust(sample_mission)

        # Original unchanged
        assert sample_mission.get_task("task_2_1").estimated_complexity == original_complexity
        # Adjusted changed
        assert adjusted.get_task("task_2_1").estimated_complexity != original_complexity

    def test_prompt_suffix_varies_by_strategy(self) -> None:
        """Different strategies produce different prompt suffixes."""
        fh = MissionPlanAdjuster(strategy=ContextStrategy.FRAMEWORK_HEAVY)
        bal = MissionPlanAdjuster(strategy=ContextStrategy.BALANCED)
        lh = MissionPlanAdjuster(strategy=ContextStrategy.LLM_HEAVY)

        fh_suffix = fh.get_plan_prompt_suffix()
        bal_suffix = bal.get_plan_prompt_suffix()
        lh_suffix = lh.get_plan_prompt_suffix()

        assert "8K" in fh_suffix or "VERY LIMITED" in fh_suffix
        assert "32K" in bal_suffix or "MODERATE" in bal_suffix
        assert "64K" in lh_suffix or "LARGE" in lh_suffix

    def test_budget_based_initialization(self, sample_mission: Mission) -> None:
        """Can initialize with budget instead of explicit strategy."""
        adjuster = MissionPlanAdjuster(context_budget=8192)
        assert adjuster.strategy == ContextStrategy.FRAMEWORK_HEAVY

        adjuster2 = MissionPlanAdjuster(context_budget=64000)
        assert adjuster2.strategy == ContextStrategy.LLM_HEAVY


# =============================================================================
# StrategyConfig Tests
# =============================================================================


class TestStrategyConfig:
    """Tests for strategy configuration parameters."""

    def test_framework_heavy_has_strictest_limits(self) -> None:
        """FRAMEWORK_HEAVY should have the most restrictive parameters."""
        fh = ContextStrategySelector.get_config(strategy=ContextStrategy.FRAMEWORK_HEAVY)
        bal = ContextStrategySelector.get_config(strategy=ContextStrategy.BALANCED)
        lh = ContextStrategySelector.get_config(strategy=ContextStrategy.LLM_HEAVY)

        assert fh.max_tasks_per_phase < bal.max_tasks_per_phase <= lh.max_tasks_per_phase
        assert fh.max_files_per_task < bal.max_files_per_task <= lh.max_files_per_task
        assert (
            fh.max_task_objective_tokens
            < bal.max_task_objective_tokens
            <= lh.max_task_objective_tokens
        )
        assert fh.max_rework_attempts <= bal.max_rework_attempts <= lh.max_rework_attempts

    def test_l3_enabled_for_balanced_and_llm(self) -> None:
        """L3 review enabled for BALANCED and LLM_HEAVY, disabled for FRAMEWORK_HEAVY."""
        fh = ContextStrategySelector.get_config(strategy=ContextStrategy.FRAMEWORK_HEAVY)
        bal = ContextStrategySelector.get_config(strategy=ContextStrategy.BALANCED)
        lh = ContextStrategySelector.get_config(strategy=ContextStrategy.LLM_HEAVY)

        assert fh.enable_l3 is False
        assert bal.enable_l3 is True
        assert lh.enable_l3 is True

    def test_redesign_disabled_for_framework_heavy(self) -> None:
        """Redesign only enabled for BALANCED and LLM_HEAVY."""
        fh = ContextStrategySelector.get_config(strategy=ContextStrategy.FRAMEWORK_HEAVY)
        bal = ContextStrategySelector.get_config(strategy=ContextStrategy.BALANCED)

        assert fh.enable_redesign is False
        assert bal.enable_redesign is True


# =============================================================================
# StrategyMetrics Tests
# =============================================================================


class TestStrategyMetrics:
    """Tests for strategy metrics collection."""

    def test_basic_metrics(self) -> None:
        """Metrics object stores strategy and budget."""
        m = StrategyMetrics(ContextStrategy.BALANCED, 32000)
        assert m.strategy == ContextStrategy.BALANCED
        assert m.context_budget == 32000
        assert m.total_tasks == 0

    def test_to_dict(self) -> None:
        """Metrics serialize to dict."""
        m = StrategyMetrics(ContextStrategy.FRAMEWORK_HEAVY, 8192)
        m.total_tasks = 5
        m.total_phases = 2
        m.tasks_completed = 4
        m.tasks_failed = 1

        d = m.to_dict()
        assert d["strategy"] == "framework_heavy"
        assert d["context_budget"] == 8192
        assert d["total_tasks"] == 5
        assert d["tasks_completed"] == 4
        assert d["tasks_failed"] == 1

    def test_from_mission_execution(self, sample_mission: Mission) -> None:
        """Metrics can be computed from mission."""
        # Use a mock tracker (None is acceptable for basic metrics)
        m = StrategyMetrics.from_mission_execution(
            ContextStrategy.BALANCED,
            32000,
            sample_mission,
            None,
        )
        assert m.total_tasks == 3
        assert m.total_phases == 2
        assert m.avg_task_complexity == (2 + 4 + 5) / 3


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
