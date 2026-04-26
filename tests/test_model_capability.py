"""Tests for model capability assessment and adaptive configuration."""

import json
import tempfile
from pathlib import Path

import pytest

from pilotcode.model_capability.schema import (
    ModelCapability,
    PlanningDimension,
    TaskCompletionDimension,
    JsonFormattingDimension,
    ChainOfThoughtDimension,
    CodeReviewDimension,
    RuntimeAdjustment,
    CalibrationRecord,
    PlanningStrategy,
    TaskGranularity,
    VerifierStrategy,
)
from pilotcode.model_capability.evaluator import evaluate_capability
from pilotcode.model_capability.benchmark import BenchmarkResult
from pilotcode.model_capability.adaptive_config import (
    AdaptiveConfigMapper,
    AdaptiveOrchestratorConfig,
)
from pilotcode.model_capability.runtime_calibrator import (
    RuntimeCalibrator,
    TaskOutcome,
    classify_failure,
    classify_planning_failure,
)


class TestModelCapabilitySchema:
    """Test ModelCapability data model."""

    def test_default_scores(self):
        cap = ModelCapability(model_name="test")
        assert cap.overall_score == 0.5
        assert cap.planning.score == 0.5
        assert cap.task_completion.score == 0.5

    def test_to_json_roundtrip(self):
        cap = ModelCapability(
            model_name="deepseek-v4-pro",
            overall_score=0.88,
            planning=PlanningDimension(score=0.85),
        )
        json_str = cap.to_json()
        restored = ModelCapability.from_json(json_str)
        assert restored.model_name == "deepseek-v4-pro"
        assert restored.overall_score == 0.88
        assert restored.planning.score == 0.85

    def test_save_and_load(self):
        cap = ModelCapability(model_name="gpt-4")
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            path = f.name
        try:
            cap.save(path)
            loaded = ModelCapability.load(path)
            assert loaded.model_name == "gpt-4"
        finally:
            Path(path).unlink(missing_ok=True)

    def test_runtime_adjustment(self):
        cap = ModelCapability(model_name="test")
        cap.record_adjustment(
            dimension="json_formatting",
            sub_dimension="valid_json_rate",
            delta=-0.05,
            reason="JSON parse failed",
        )
        effective = cap.get_effective_dimension("json_formatting")
        assert effective["valid_json_rate"] == 0.45  # 0.5 - 0.05
        assert cap.calibration.samples_evaluated == 1

    def test_adjustment_cap(self):
        cap = ModelCapability(model_name="test")
        # Apply many negative adjustments
        for _ in range(10):
            cap.record_adjustment(
                dimension="json_formatting",
                sub_dimension="valid_json_rate",
                delta=-0.05,
                reason="fail",
            )
        effective = cap.get_effective_dimension("json_formatting")
        # Score should be clamped to 0.0
        assert effective["valid_json_rate"] < 0.01  # Clamped to near-zero


class TestEvaluateCapability:
    """Test capability evaluation from benchmark results."""

    def test_evaluate_from_results(self):
        results = [
            BenchmarkResult(
                test_name="planning_json",
                dimension="planning",
                sub_dimension="dag_correctness",
                score=1.0,
            ),
            BenchmarkResult(
                test_name="planning_deps",
                dimension="planning",
                sub_dimension="dependency_accuracy",
                score=0.5,
            ),
            BenchmarkResult(
                test_name="code_gen",
                dimension="task_completion",
                sub_dimension="code_correctness",
                score=0.8,
            ),
        ]
        cap = evaluate_capability("test-model", results)
        assert cap.model_name == "test-model"
        # Planning score = average of 1.0 and 0.5 = 0.75
        assert cap.planning.score == 0.75
        assert cap.task_completion.score == 0.8
        # Overall = average of planning, task_completion, and defaults for others
        assert cap.overall_score > 0.5

    def test_evaluate_preserves_existing_calibration(self):
        existing = ModelCapability(model_name="test")
        existing.record_adjustment("json_formatting", "valid_json_rate", -0.1, "test")

        results = [
            BenchmarkResult(
                test_name="json_test",
                dimension="json_formatting",
                sub_dimension="valid_json_rate",
                score=1.0,
            )
        ]
        cap = evaluate_capability("test-model", results, existing=existing)
        assert cap.calibration.accumulated_deltas["json_formatting"]["valid_json_rate"] == -0.1


class TestAdaptiveConfigMapper:
    """Test adaptive configuration mapping."""

    def test_strong_model_full_dag(self):
        cap = ModelCapability(
            model_name="strong",
            overall_score=0.9,
            planning=PlanningDimension(score=0.9),
            task_completion=TaskCompletionDimension(score=0.9),
            chain_of_thought=ChainOfThoughtDimension(score=0.9),
            code_review=CodeReviewDimension(score=0.9),
            json_formatting=JsonFormattingDimension(score=0.9),
        )
        config = AdaptiveConfigMapper.from_capability(cap)
        assert config.planning_strategy == PlanningStrategy.FULL_DAG
        assert config.verifier_strategy == VerifierStrategy.FULL_L3
        assert config.task_granularity == TaskGranularity.COARSE

    def test_weak_model_template_based(self):
        cap = ModelCapability(
            model_name="weak",
            overall_score=0.3,
            planning=PlanningDimension(score=0.3),
            chain_of_thought=ChainOfThoughtDimension(score=0.3),
            code_review=CodeReviewDimension(score=0.2),
            json_formatting=JsonFormattingDimension(score=0.3),
        )
        config = AdaptiveConfigMapper.from_capability(cap)
        assert config.planning_strategy == PlanningStrategy.TEMPLATE_BASED
        assert config.verifier_strategy == VerifierStrategy.STATIC_ONLY
        assert config.task_granularity == TaskGranularity.FINE

    def test_moderate_model_phased(self):
        cap = ModelCapability(
            model_name="moderate",
            overall_score=0.6,
            planning=PlanningDimension(score=0.6),
            chain_of_thought=ChainOfThoughtDimension(score=0.6),
            code_review=CodeReviewDimension(score=0.6),
            json_formatting=JsonFormattingDimension(score=0.6),
        )
        config = AdaptiveConfigMapper.from_capability(cap)
        assert config.planning_strategy == PlanningStrategy.PHASED

    def test_config_to_dict(self):
        config = AdaptiveOrchestratorConfig()
        d = config.to_dict()
        assert "planning_strategy" in d
        assert "verifier_strategy" in d
        assert "task_granularity" in d


class TestRuntimeCalibrator:
    """Test runtime capability calibration."""

    def test_record_success(self):
        cap = ModelCapability(model_name="test")
        cal = RuntimeCalibrator(cap)
        outcome = TaskOutcome(
            task_id="t1",
            success=True,
            completion_percentage=1.0,
            correctness_score=1.0,
        )
        cal.record_task_outcome(outcome)
        assert cal.get_success_rate() == 1.0
        # Small positive adjustment to task_completion
        effective = cal.capability.get_effective_dimension("task_completion")
        assert effective["code_correctness"] > 0.5

    def test_record_json_failure(self):
        cap = ModelCapability(model_name="test")
        cal = RuntimeCalibrator(cap)
        outcome = TaskOutcome(
            task_id="t1",
            success=False,
            completion_percentage=0.0,
            correctness_score=0.0,
            error_text="json.JSONDecodeError: Expecting ',' delimiter",
        )
        cal.record_task_outcome(outcome)
        effective = cal.capability.get_effective_dimension("json_formatting")
        assert effective["valid_json_rate"] < 0.5

    def test_record_syntax_failure(self):
        cap = ModelCapability(model_name="test")
        cal = RuntimeCalibrator(cap)
        outcome = TaskOutcome(
            task_id="t1",
            success=False,
            error_text="SyntaxError: invalid syntax",
        )
        cal.record_task_outcome(outcome)
        effective = cal.capability.get_effective_dimension("task_completion")
        assert effective["code_correctness"] < 0.5

    def test_should_escalate(self):
        cap = ModelCapability(model_name="test")
        cal = RuntimeCalibrator(cap)
        # Not enough samples
        assert not cal.should_escalate_to_stronger_model()

        # Many failures across multiple dimensions (completion=0 to get full penalty)
        for i in range(4):
            cal.record_task_outcome(
                TaskOutcome(
                    task_id=f"t{i}",
                    success=False,
                    completion_percentage=0.0,
                    error_text="SyntaxError",
                )
            )
        for i in range(4):
            cal.record_task_outcome(
                TaskOutcome(
                    task_id=f"t{i+4}",
                    success=False,
                    completion_percentage=0.0,
                    error_text="json.JSONDecodeError",
                )
            )
        for i in range(4):
            cal.record_task_outcome(
                TaskOutcome(
                    task_id=f"t{i+8}",
                    success=False,
                    completion_percentage=0.0,
                    error_text="AssertionError",
                )
            )
        assert cal.should_escalate_to_stronger_model()

    def test_classify_failure(self):
        assert classify_failure("json.JSONDecodeError") == "json_error"
        assert classify_failure("SyntaxError: bad syntax") == "syntax_error"
        assert classify_failure("AssertionError") == "logic_error"
        assert classify_failure("asyncio.TimeoutError") == "timeout"
        assert classify_failure("") == "unknown"

    def test_classify_planning_failure(self):
        bad_json = "not json at all"
        assert classify_planning_failure(bad_json) == "invalid_json"

        valid_plan = json.dumps(
            {
                "phases": [
                    {
                        "phase_id": "p1",
                        "title": "Test",
                        "tasks": [
                            {
                                "task_id": "t1",
                                "title": "Task 1",
                                "objective": "Do it",
                                "dependencies": [],
                            },
                            {
                                "task_id": "t2",
                                "title": "Task 2",
                                "objective": "Do more",
                                "dependencies": ["t1"],
                            },
                            {
                                "task_id": "t3",
                                "title": "Task 3",
                                "objective": "Finish",
                                "dependencies": ["t2"],
                            },
                        ],
                    }
                ]
            }
        )
        assert classify_planning_failure(valid_plan) == "unknown"


class TestLoadCapabilityOrDefault:
    """Test loading capability with fallback."""

    def test_default_is_strong_model(self):
        from pilotcode.model_capability import load_capability_or_default

        cap = load_capability_or_default(model_name="test")
        assert cap.overall_score == 0.88
        assert cap.planning.score == 0.85
        assert cap.json_formatting.score == 0.92

    def test_load_existing(self):
        from pilotcode.model_capability import load_capability_or_default, save_capability

        cap = ModelCapability(model_name="custom", overall_score=0.3)
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            path = f.name
        try:
            save_capability(cap, path)
            loaded = load_capability_or_default(path=path, model_name="other")
            assert loaded.model_name == "custom"
            assert loaded.overall_score == 0.3
        finally:
            Path(path).unlink(missing_ok=True)
