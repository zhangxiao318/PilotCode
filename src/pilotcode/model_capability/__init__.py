"""Model capability assessment and adaptive configuration for PilotCode.

This module provides:
1. Benchmark-based capability evaluation (planning, execution, JSON, reasoning, review)
2. Runtime calibration that adjusts scores based on observed task outcomes
3. Adaptive configuration mapping that translates capability scores into
   concrete orchestration parameters (task granularity, verifier strategy, etc.)

Usage:
    # Evaluate a model
    from pilotcode.model_capability import evaluate_model, save_capability

    cap = await evaluate_model("deepseek-v4-pro")
    save_capability(cap, "model_capability.json")

    # Load and use for adaptive planning
    from pilotcode.model_capability import load_capability, AdaptiveConfigMapper

    cap = load_capability("model_capability.json")
    config = AdaptiveConfigMapper.from_capability(cap)

    # Runtime calibration during execution
    from pilotcode.model_capability import RuntimeCalibrator, TaskOutcome

    calibrator = RuntimeCalibrator(cap)
    calibrator.record_task_outcome(TaskOutcome(...))
"""

from .schema import (
    ModelCapability,
    PlanningDimension,
    TaskCompletionDimension,
    JsonFormattingDimension,
    ChainOfThoughtDimension,
    CodeReviewDimension,
    RuntimeAdjustment,
    CalibrationRecord,
    RuntimeStats,
    PlanningStrategy,
    TaskGranularity,
    VerifierStrategy,
)
from .base import BenchmarkResult
from .suite import run_all_benchmarks, ALL_BENCHMARKS
from .evaluator import (
    evaluate_capability,
    format_evaluation_report,
)
from .adaptive_config import (
    AdaptiveOrchestratorConfig,
    AdaptiveConfigMapper,
    apply_adaptive_config_to_strategy_config,
)
from .runtime_tracker import (
    RuntimeTracker,
    TaskOutcome,
    classify_failure,
    classify_planning_failure,
)

# Convenience functions for CLI and main usage

DEFAULT_CAPABILITY_PATH = "model_capability.json"


async def evaluate_model(model_name: str) -> ModelCapability:
    """Run full benchmark suite and return capability profile.

    Args:
        model_name: Identifier for the model being tested.

    Returns:
        ModelCapability with benchmark-derived scores.
    """
    from rich.console import Console

    console = Console()
    console.print(f"[bold]Evaluating model:[/bold] {model_name}")
    console.print(f"Running {len(ALL_BENCHMARKS)} benchmark tests...")

    def progress(name: str, current: int, total: int) -> None:
        console.print(f"  [{current}/{total}] {name}...")

    results = await run_all_benchmarks(progress_callback=progress)
    cap = evaluate_capability(model_name, results)

    console.print(f"\n[green]Evaluation complete. Overall score: {cap.overall_score:.1%}[/green]")
    return cap


def save_capability(cap: ModelCapability, path: str | None = None) -> None:
    """Save capability profile to file.

    Args:
        cap: Capability profile to save.
        path: File path. Defaults to DEFAULT_CAPABILITY_PATH.
    """
    path = path or DEFAULT_CAPABILITY_PATH
    cap.save(path)


def load_capability(path: str | None = None) -> ModelCapability:
    """Load capability profile from file.

    Args:
        path: File path. Defaults to DEFAULT_CAPABILITY_PATH.

    Returns:
        Loaded capability profile.

    Raises:
        FileNotFoundError: If no capability file exists.
    """
    from pathlib import Path

    path = path or DEFAULT_CAPABILITY_PATH

    # Try multiple locations
    from pilotcode.utils.paths import get_config_dir

    candidates = [
        Path(path),
        get_config_dir() / path,
        Path.cwd() / ".pilotcode" / path,
    ]

    for candidate in candidates:
        if candidate.exists():
            return ModelCapability.load(candidate)

    raise FileNotFoundError(
        f"No capability file found. Searched: {[str(c) for c in candidates]}.\n"
        f"Run 'pilotcode config --test' to generate one."
    )


def load_capability_or_default(
    path: str | None = None,
    model_name: str = "unknown",
) -> ModelCapability:
    """Load capability profile, or return a default strong-model profile.

    Default assumption: the user is running a capable model (e.g. GPT-4,
    DeepSeek-V4). The system starts with minimal framework intervention
    and only tightens control if runtime calibration detects weakness.

    If switching to a local/weak model, run 'pilotcode config --test capability'
    to generate an accurate profile.
    """
    try:
        cap = load_capability(path)
        # If the stored profile is for a different model, warn but still return it
        # (caller should check model_name match)
        return cap
    except FileNotFoundError:
        # Return a strong-model default — minimal framework overhead
        return ModelCapability(
            model_name=model_name,
            overall_score=0.88,
            planning=PlanningDimension(
                score=0.85,
                dag_correctness=0.88,
                task_granularity_appropriateness=0.82,
                dependency_accuracy=0.85,
            ),
            task_completion=TaskCompletionDimension(
                score=0.90,
                code_correctness=0.92,
                test_pass_rate=0.88,
            ),
            json_formatting=JsonFormattingDimension(
                score=0.92,
                valid_json_rate=0.95,
                schema_compliance=0.90,
                self_correction=0.90,
            ),
            chain_of_thought=ChainOfThoughtDimension(
                score=0.85,
                reasoning_depth=0.82,
                error_diagnosis=0.86,
                debugging_skill=0.88,
            ),
            code_review=CodeReviewDimension(
                score=0.88,
                bug_detection=0.86,
                structured_output=0.90,
                style_consistency=0.88,
            ),
        )


__all__ = [
    # Schema
    "ModelCapability",
    "PlanningDimension",
    "TaskCompletionDimension",
    "JsonFormattingDimension",
    "ChainOfThoughtDimension",
    "CodeReviewDimension",
    "RuntimeAdjustment",
    "CalibrationRecord",
    "RuntimeStats",
    "PlanningStrategy",
    "TaskGranularity",
    "VerifierStrategy",
    # Benchmark
    "BenchmarkResult",
    "run_all_benchmarks",
    "ALL_BENCHMARKS",
    # Evaluator
    "evaluate_capability",
    "format_evaluation_report",
    # Adaptive Config
    "AdaptiveOrchestratorConfig",
    "AdaptiveConfigMapper",
    "apply_adaptive_config_to_strategy_config",
    # Runtime Calibration
    "RuntimeTracker",
    "TaskOutcome",
    "classify_failure",
    "classify_planning_failure",
    # Convenience
    "evaluate_model",
    "save_capability",
    "load_capability",
    "load_capability_or_default",
    "DEFAULT_CAPABILITY_PATH",
]
