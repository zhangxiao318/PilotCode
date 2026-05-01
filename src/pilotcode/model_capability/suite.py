"""Benchmark suite registry and runner."""

from __future__ import annotations

from typing import Any, Awaitable, Callable

from .base import BenchmarkConnectionError, BenchmarkResult
from .chain_of_thought import (
    test_debugging_skill,
    test_error_diagnosis,
    test_reasoning_depth,
)
from .code_review import test_bug_detection, test_review_structured_output
from .json_formatting import (
    test_json_in_complex_context,
    test_json_schema_compliance,
    test_json_self_correction,
)
from .planning import (
    test_planning_dependency_accuracy,
    test_planning_granularity,
    test_planning_json_validity,
)
from .task_completion import test_bug_fixing, test_code_generation_correctness

ALL_BENCHMARKS: list[Callable[[], Awaitable[BenchmarkResult]]] = [
    # Planning
    test_planning_json_validity,
    test_planning_dependency_accuracy,
    test_planning_granularity,
    # Task Completion
    test_code_generation_correctness,
    test_bug_fixing,
    # JSON Formatting
    test_json_schema_compliance,
    test_json_self_correction,
    test_json_in_complex_context,
    # Chain of Thought
    test_reasoning_depth,
    test_error_diagnosis,
    test_debugging_skill,
    # Code Review
    test_bug_detection,
    test_review_structured_output,
]

# Mapping from test function name to (dimension, sub_dimension)
_DIMENSION_MAP: dict[str, tuple[str, str]] = {
    "test_planning_json_validity": ("planning", "dag_correctness"),
    "test_planning_dependency_accuracy": ("planning", "dependency_accuracy"),
    "test_planning_granularity": ("planning", "task_granularity_appropriateness"),
    "test_code_generation_correctness": ("task_completion", "code_correctness"),
    "test_bug_fixing": ("task_completion", "code_correctness"),
    "test_json_schema_compliance": ("json_formatting", "schema_compliance"),
    "test_json_self_correction": ("json_formatting", "self_correction"),
    "test_json_in_complex_context": ("json_formatting", "valid_json_rate"),
    "test_reasoning_depth": ("chain_of_thought", "reasoning_depth"),
    "test_error_diagnosis": ("chain_of_thought", "error_diagnosis"),
    "test_debugging_skill": ("chain_of_thought", "debugging_skill"),
    "test_bug_detection": ("code_review", "bug_detection"),
    "test_review_structured_output": ("code_review", "structured_output"),
}


async def run_all_benchmarks(
    progress_callback: Callable[[str, int, int], None] | None = None,
) -> list[BenchmarkResult]:
    """Run all benchmark tests and return results.

    Args:
        progress_callback: Optional callback(name, current, total) for progress reporting.

    Returns:
        List of BenchmarkResult, one per test.
    """
    results: list[BenchmarkResult] = []
    total = len(ALL_BENCHMARKS)

    for i, test_fn in enumerate(ALL_BENCHMARKS):
        name = test_fn.__name__
        if progress_callback:
            progress_callback(name, i + 1, total)
        try:
            result = await test_fn()
        except BenchmarkConnectionError:
            raise
        except Exception as e:
            dim, sub_dim = _DIMENSION_MAP.get(name, ("unknown", "unknown"))
            result = BenchmarkResult(
                test_name=name,
                dimension=dim,
                sub_dimension=sub_dim,
                score=0.0,
                error=str(e),
            )
        results.append(result)

    return results
