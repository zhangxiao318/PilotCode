"""Capability evaluator: converts benchmark results into ModelCapability scores.

Aggregates individual benchmark test scores into dimension-level scores
and produces a complete ModelCapability profile.
"""

from __future__ import annotations


from .schema import (
    ModelCapability,
    PlanningDimension,
    TaskCompletionDimension,
    JsonFormattingDimension,
    ChainOfThoughtDimension,
    CodeReviewDimension,
)
from .benchmark import BenchmarkResult


def _average(scores: list[float]) -> float:
    return sum(scores) / len(scores) if scores else 0.0


def evaluate_capability(
    model_name: str,
    results: list[BenchmarkResult],
    existing: ModelCapability | None = None,
) -> ModelCapability:
    """Evaluate model capability from benchmark results.

    Args:
        model_name: Name of the model being evaluated.
        results: List of benchmark test results.
        existing: Optional existing capability to merge with (for re-evaluation).

    Returns:
        A ModelCapability with scores derived from benchmark results.
    """
    # Group results by dimension and sub-dimension
    dim_scores: dict[str, dict[str, list[float]]] = {}
    for r in results:
        dim = r.dimension
        sub = r.sub_dimension
        if dim not in dim_scores:
            dim_scores[dim] = {}
        if sub not in dim_scores[dim]:
            dim_scores[dim][sub] = []
        dim_scores[dim][sub].append(r.score)

    def _dim_avg(dim_name: str, sub_scores: dict[str, list[float]], default: float = 0.0) -> float:
        all_scores = []
        for scores in sub_scores.values():
            all_scores.extend(scores)
        return _average(all_scores) if all_scores else default

    def _sub_avg(dim_name: str, sub_name: str) -> float:
        scores = dim_scores.get(dim_name, {}).get(sub_name, [])
        return _average(scores)

    # Build dimensions
    planning = PlanningDimension(
        score=_dim_avg("planning", dim_scores.get("planning", {})),
        dag_correctness=_sub_avg("planning", "dag_correctness"),
        task_granularity_appropriateness=_sub_avg("planning", "task_granularity_appropriateness"),
        dependency_accuracy=_sub_avg("planning", "dependency_accuracy"),
    )

    task_completion_score = _dim_avg("task_completion", dim_scores.get("task_completion", {}))
    task_completion = TaskCompletionDimension(
        score=task_completion_score,
        code_correctness=_sub_avg("task_completion", "code_correctness"),
        test_pass_rate=_sub_avg("task_completion", "test_pass_rate") or task_completion_score,
    )

    json_formatting = JsonFormattingDimension(
        score=_dim_avg("json_formatting", dim_scores.get("json_formatting", {})),
        valid_json_rate=_sub_avg("json_formatting", "valid_json_rate"),
        schema_compliance=_sub_avg("json_formatting", "schema_compliance"),
        self_correction=_sub_avg("json_formatting", "self_correction"),
    )

    chain_of_thought = ChainOfThoughtDimension(
        score=_dim_avg("chain_of_thought", dim_scores.get("chain_of_thought", {})),
        reasoning_depth=_sub_avg("chain_of_thought", "reasoning_depth"),
        error_diagnosis=_sub_avg("chain_of_thought", "error_diagnosis"),
        debugging_skill=_sub_avg("chain_of_thought", "debugging_skill"),
    )

    code_review_score = _dim_avg("code_review", dim_scores.get("code_review", {}))
    code_review = CodeReviewDimension(
        score=code_review_score,
        bug_detection=_sub_avg("code_review", "bug_detection"),
        structured_output=_sub_avg("code_review", "structured_output"),
        style_consistency=_sub_avg("code_review", "style_consistency") or code_review_score,
    )

    overall = _average(
        [
            planning.score,
            task_completion.score,
            json_formatting.score,
            chain_of_thought.score,
            code_review.score,
        ]
    )

    cap = ModelCapability(
        model_name=model_name,
        overall_score=round(overall, 3),
        planning=planning,
        task_completion=task_completion,
        json_formatting=json_formatting,
        chain_of_thought=chain_of_thought,
        code_review=code_review,
    )

    # If existing capability provided, merge calibration history
    if existing is not None:
        cap.calibration = existing.calibration

    return cap


def format_evaluation_report(results: list[BenchmarkResult], cap: ModelCapability) -> str:
    """Format a human-readable evaluation report.

    Args:
        results: Individual test results.
        cap: Aggregated capability profile.

    Returns:
        Markdown-formatted report string.
    """
    lines = [
        f"# Model Capability Evaluation: {cap.model_name}",
        "",
        f"**Overall Score:** {cap.overall_score:.1%}",
        f"**Evaluated At:** {cap.evaluated_at}",
        "",
        "## Dimension Scores",
        "",
        "| Dimension | Score |",
        "|-----------|-------|",
        f"| Planning | {cap.planning.score:.1%} |",
        f"| Task Completion | {cap.task_completion.score:.1%} |",
        f"| JSON Formatting | {cap.json_formatting.score:.1%} |",
        f"| Chain of Thought | {cap.chain_of_thought.score:.1%} |",
        f"| Code Review | {cap.code_review.score:.1%} |",
        "",
        "## Sub-dimension Breakdown",
        "",
        "### Planning",
        f"- DAG Correctness: {cap.planning.dag_correctness:.1%}",
        f"- Task Granularity: {cap.planning.task_granularity_appropriateness:.1%}",
        f"- Dependency Accuracy: {cap.planning.dependency_accuracy:.1%}",
        "",
        "### Task Completion",
        f"- Code Correctness: {cap.task_completion.code_correctness:.1%}",
        f"- Test Pass Rate: {cap.task_completion.test_pass_rate:.1%}",
        "",
        "### JSON Formatting",
        f"- Valid JSON Rate: {cap.json_formatting.valid_json_rate:.1%}",
        f"- Schema Compliance: {cap.json_formatting.schema_compliance:.1%}",
        f"- Self Correction: {cap.json_formatting.self_correction:.1%}",
        "",
        "### Chain of Thought",
        f"- Reasoning Depth: {cap.chain_of_thought.reasoning_depth:.1%}",
        f"- Error Diagnosis: {cap.chain_of_thought.error_diagnosis:.1%}",
        f"- Debugging Skill: {cap.chain_of_thought.debugging_skill:.1%}",
        "",
        "### Code Review",
        f"- Bug Detection: {cap.code_review.bug_detection:.1%}",
        f"- Structured Output: {cap.code_review.structured_output:.1%}",
        f"- Style Consistency: {cap.code_review.style_consistency:.1%}",
        "",
        "## Individual Test Results",
        "",
        "| Test | Dimension | Score | Notes |",
        "|------|-----------|-------|-------|",
    ]

    for r in results:
        notes = r.error if r.error else ""
        if r.metadata:
            meta = ", ".join(f"{k}={v}" for k, v in r.metadata.items() if not isinstance(v, list))
            notes = notes or meta
        lines.append(
            f"| {r.test_name} | {r.dimension}/{r.sub_dimension} | {r.score:.1%} | {notes} |"
        )

    lines.append("")
    return "\n".join(lines)
