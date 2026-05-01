"""Tests for compensation engine and edit validator."""

import tempfile
from pathlib import Path

from pilotcode.model_capability.schema import (
    TaskGranularity,
    RuntimeStats,
    ModelCapability,
    PlanningDimension,
    TaskCompletionDimension,
    JsonFormattingDimension,
    ChainOfThoughtDimension,
    CodeReviewDimension,
)
from pilotcode.model_capability.adaptive_config import (
    AdaptiveOrchestratorConfig,
    AdaptiveConfigMapper,
)
from pilotcode.orchestration.adaptive_edit import (
    CompensationEngine,
    EditValidator,
)


class TestCompensationEngine:
    """Test capability-based compensation engine."""

    def _make_config(self, **kwargs) -> AdaptiveOrchestratorConfig:
        return AdaptiveOrchestratorConfig(**kwargs)

    def _make_cap(self, overall: float) -> ModelCapability:
        return ModelCapability(
            model_name="test",
            overall_score=overall,
            planning=PlanningDimension(score=overall),
            task_completion=TaskCompletionDimension(score=overall),
            json_formatting=JsonFormattingDimension(score=overall),
            chain_of_thought=ChainOfThoughtDimension(score=overall),
            code_review=CodeReviewDimension(score=overall),
        )

    def test_no_compensation_when_strong(self):
        config = self._make_config(
            enable_auto_verify=False,
            enable_smart_edit_planner=False,
            task_granularity=TaskGranularity.COARSE,
        )
        cap = self._make_cap(0.85)
        engine = CompensationEngine(config, cap)

        assert not engine.is_compensation_active
        assert engine.get_worker_prompt_suffix() == ""
        assert engine.get_planning_prompt_suffix() == ""

    def test_compensation_active_for_weak(self):
        config = self._make_config(
            enable_auto_verify=True,
            enable_smart_edit_planner=True,
            task_granularity=TaskGranularity.FINE,
            ask_user_on_critical_decisions=True,
        )
        cap = self._make_cap(0.50)
        engine = CompensationEngine(config, cap)

        assert engine.is_compensation_active
        suffix = engine.get_worker_prompt_suffix()
        assert "SmartEditPlanner" in suffix
        assert "auto-verify" in suffix
        assert "AskUser" in suffix

    def test_planning_compensation_for_fine_granularity(self):
        config = self._make_config(task_granularity=TaskGranularity.FINE)
        cap = self._make_cap(0.50)
        engine = CompensationEngine(config, cap)

        suffix = engine.get_planning_prompt_suffix()
        assert "PLANNING COMPENSATION" in suffix
        assert "granular" in suffix.lower()

    def test_no_planning_compensation_for_coarse(self):
        config = self._make_config(task_granularity=TaskGranularity.COARSE)
        cap = self._make_cap(0.85)
        engine = CompensationEngine(config, cap)

        assert engine.get_planning_prompt_suffix() == ""

    def test_worker_prompt_atomic_edits(self):
        config = self._make_config(max_edits_per_round=1, enable_auto_verify=True)
        cap = self._make_cap(0.50)
        engine = CompensationEngine(config, cap)

        suffix = engine.get_worker_prompt_suffix()
        assert "ONE atomic edit" in suffix

    def test_worker_prompt_grouped_edits(self):
        config = self._make_config(max_edits_per_round=3, enable_auto_verify=True)
        cap = self._make_cap(0.65)
        engine = CompensationEngine(config, cap)

        suffix = engine.get_worker_prompt_suffix()
        assert "atomic edits" in suffix
        assert "ONE atomic edit" not in suffix

    def test_edit_summary_for_checklist(self):
        config = self._make_config()
        cap = self._make_cap(0.50)
        engine = CompensationEngine(config, cap)
        checklist = [
            {"file_path": "a.py", "line_number": 10, "context": "foo()"},
            {"file_path": "b.py", "line_number": 20, "context": "bar()"},
        ]
        summary = engine.get_edit_summary_for_continue_prompt(checklist)

        assert "2 items remaining" in summary
        assert "a.py:10" in summary
        assert "b.py:20" in summary

    def test_edit_summary_empty_checklist(self):
        config = self._make_config()
        cap = self._make_cap(0.50)
        engine = CompensationEngine(config, cap)
        assert engine.get_edit_summary_for_continue_prompt(None) == ""
        assert engine.get_edit_summary_for_continue_prompt([]) == ""


class TestEditValidator:
    """Test post-edit validation logic."""

    def test_validate_syntax_ok(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write("def hello(): pass\n")
            path = f.name

        try:
            ok, err = EditValidator.validate_syntax(path)
            assert ok is True
            assert err is None
        finally:
            Path(path).unlink(missing_ok=True)

    def test_validate_syntax_error(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write("def hello(: pass\n")
            path = f.name

        try:
            ok, err = EditValidator.validate_syntax(path)
            assert ok is False
            assert err is not None
        finally:
            Path(path).unlink(missing_ok=True)

    def test_validate_syntax_skips_non_python(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("not python at all {{{")
            path = f.name

        try:
            ok, err = EditValidator.validate_syntax(path)
            assert ok is True
            assert err is None
        finally:
            Path(path).unlink(missing_ok=True)

    def test_check_completeness_finds_remaining(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            p = Path(tmpdir) / "test.py"
            p.write_text("old_func()\nold_func()\n")

            remaining = EditValidator.check_completeness([str(p)], "old_func", cwd=tmpdir)
            assert len(remaining) == 2
            assert remaining[0][0] == str(p)
            assert remaining[0][1] == 1
            assert remaining[1][1] == 2

    def test_check_completeness_none_remaining(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            p = Path(tmpdir) / "test.py"
            p.write_text("new_func()\nnew_func()\n")

            remaining = EditValidator.check_completeness([str(p)], "old_func", cwd=tmpdir)
            assert len(remaining) == 0

    def test_validate_full_pass(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            p = Path(tmpdir) / "test.py"
            p.write_text("def new(): pass\n")

            result = EditValidator.validate([str(p)], expected_pattern="old", cwd=tmpdir)
            assert result.passed is True
            assert result.syntax_ok is True
            assert result.completeness_ok is True
            assert result.nudge_message == ""

    def test_validate_completeness_fail(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            p = Path(tmpdir) / "test.py"
            p.write_text("def old(): pass\n")

            result = EditValidator.validate([str(p)], expected_pattern="old", cwd=tmpdir)
            assert result.passed is False
            assert result.syntax_ok is True
            assert result.completeness_ok is False
            assert "INCOMPLETE" in result.nudge_message
            assert "test.py" in result.nudge_message

    def test_validate_syntax_fail(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            p = Path(tmpdir) / "test.py"
            p.write_text("def old(: pass\n")

            result = EditValidator.validate([str(p)], expected_pattern="xxx", cwd=tmpdir)
            assert result.passed is False
            assert result.syntax_ok is False
            assert "CRITICAL" in result.nudge_message


class TestAdaptiveConfigMapperCompensation:
    """Test runtime-driven compensation via update_from_runtime."""

    def _make_stats(self, **kwargs) -> RuntimeStats:
        stats = RuntimeStats(window_size=5)
        for task_type, outcomes in kwargs.items():
            for success in outcomes:
                stats.record(task_type, success)
        return stats

    def test_planning_weak_gets_fine_granularity(self):
        config = AdaptiveConfigMapper.default_config()
        stats = self._make_stats(planning=[False, False, False])
        config = AdaptiveConfigMapper.update_from_runtime(config, stats)
        assert config.task_granularity == TaskGranularity.FINE
        assert config.planning_strategy.value == "phased"
        assert config.max_lines_per_task == 80

    def test_json_weak_gets_relaxed_schema(self):
        config = AdaptiveConfigMapper.default_config()
        stats = self._make_stats(json=[False, False, False])
        config = AdaptiveConfigMapper.update_from_runtime(config, stats)
        assert config.require_json_schema is False
        assert config.json_max_retries == 3

    def test_completion_weak_gets_auto_verify(self):
        config = AdaptiveConfigMapper.default_config()
        stats = self._make_stats(code=[False, False, False])
        config = AdaptiveConfigMapper.update_from_runtime(config, stats)
        assert config.enable_auto_verify is True
        assert config.verify_after_each_edit is True
        assert config.max_edits_per_round == 1

    def test_cot_weak_gets_ask_user(self):
        config = AdaptiveConfigMapper.default_config()
        stats = self._make_stats(reasoning=[False, False, False])
        config = AdaptiveConfigMapper.update_from_runtime(config, stats)
        assert config.ask_user_on_critical_decisions is True
        assert config.inject_objective_reminder_every == 1

    def test_review_weak_gets_enforced_tests(self):
        config = AdaptiveConfigMapper.default_config()
        stats = self._make_stats(review=[False, False, False])
        config = AdaptiveConfigMapper.update_from_runtime(config, stats)
        assert config.enforce_test_before_mark_complete is True
        assert config.verifier_strategy.value == "static_only"
