"""Benchmark suite for evaluating LLM capabilities.

Provides a set of standardized tests that measure a model's ability
across five dimensions: planning, task completion, JSON formatting,
chain of thought reasoning, and code review.
"""

from __future__ import annotations

import ast
import json
import re
from dataclasses import dataclass
from typing import Any, Callable, Awaitable

from pilotcode.utils.model_client import get_model_client, Message


@dataclass
class BenchmarkResult:
    """Result of a single benchmark test."""

    test_name: str
    dimension: str
    sub_dimension: str
    score: float  # 0.0 - 1.0
    raw_output: str = ""
    error: str | None = None
    metadata: dict[str, Any] = None

    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}


async def _call_llm(
    messages: list[Message],
    temperature: float = 0.3,
    max_tokens: int | None = None,
) -> str:
    """Helper to call LLM and accumulate response."""
    client = get_model_client()
    accumulated = ""
    async for chunk in client.chat_completion(
        messages=messages,
        temperature=temperature,
        stream=False,
        max_tokens=max_tokens,
    ):
        delta = chunk.get("choices", [{}])[0].get("delta", {})
        c = delta.get("content")
        if c:
            accumulated += c
    return accumulated.strip()


def _extract_json(text: str) -> dict[str, Any] | None:
    """Extract JSON object from text."""
    # Try direct parse first
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # Try regex extraction
    patterns = [
        r"```json\s*(.*?)\s*```",
        r"```\s*(.*?)\s*```",
        r"(\{[\s\S]*\})",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(1))
            except json.JSONDecodeError:
                continue
    return None


def _score_bool(condition: bool) -> float:
    return 1.0 if condition else 0.0


# ---------------------------------------------------------------------------
# Planning Dimension Tests
# ---------------------------------------------------------------------------

PLANNING_TEST_PROMPT = """You are a task planner. Given the following requirement, output a valid JSON plan.

Requirement: "Add a user authentication system with login, logout, and password reset features."

Output EXACTLY this JSON format (no markdown, no extra text):
{
  "phases": [
    {
      "phase_id": "phase_1",
      "title": "Phase title",
      "tasks": [
        {
          "task_id": "task_1",
          "title": "Task title",
          "objective": "What to do",
          "dependencies": []
        }
      ]
    }
  ]
}

Rules:
- Use snake_case for IDs
- Each task should be granular (single feature or file)
- Dependencies must reference existing task_ids only
- Include 2-4 phases
"""


async def test_planning_json_validity() -> BenchmarkResult:
    """Test if model outputs valid JSON plan."""
    raw = await _call_llm(
        [Message(role="user", content=PLANNING_TEST_PROMPT)],
        temperature=0.3,
        max_tokens=800,
    )
    data = _extract_json(raw)
    is_valid = data is not None and "phases" in data
    return BenchmarkResult(
        test_name="planning_json_validity",
        dimension="planning",
        sub_dimension="dag_correctness",
        score=_score_bool(is_valid),
        raw_output=raw[:500],
        metadata={"has_phases": is_valid},
    )


async def test_planning_dependency_accuracy() -> BenchmarkResult:
    """Test if model creates correct dependency relationships."""
    prompt = """Create a JSON plan for: "Build a web API with database layer, business logic, and REST endpoints. The database layer must be built before business logic, which must be built before REST endpoints."

Output format:
{
  "phases": [
    {
      "phase_id": "phase_1",
      "title": "...",
      "tasks": [
        {"task_id": "task_1", "title": "...", "objective": "...", "dependencies": []}
      ]
    }
  ]
}

CRITICAL: Task dependencies MUST form a valid DAG (no cycles, only reference existing task_ids).
"""
    raw = await _call_llm(
        [Message(role="user", content=prompt)],
        temperature=0.3,
        max_tokens=800,
    )
    data = _extract_json(raw)
    if not data or "phases" not in data:
        return BenchmarkResult(
            test_name="planning_dependency_accuracy",
            dimension="planning",
            sub_dimension="dependency_accuracy",
            score=0.0,
            raw_output=raw[:500],
            error="No valid JSON",
        )

    # Collect all task IDs and check dependencies
    all_task_ids: set[str] = set()
    all_deps: list[tuple[str, str]] = []  # (task_id, dep_id)
    for phase in data.get("phases", []):
        for task in phase.get("tasks", []):
            tid = task.get("task_id", "")
            all_task_ids.add(tid)
            for dep in task.get("dependencies", []):
                all_deps.append((tid, dep))

    # Check all deps reference existing tasks
    valid_deps = all(dep in all_task_ids for _, dep in all_deps)
    # Check for cycles (simple: if task_A depends on task_B, task_B should not depend on task_A)
    no_cycles = True
    dep_map: dict[str, set[str]] = {tid: set() for tid in all_task_ids}
    for tid, dep in all_deps:
        dep_map[tid].add(dep)
    for tid, deps in dep_map.items():
        for dep in deps:
            if tid in dep_map.get(dep, set()):
                no_cycles = False
                break

    score = 0.5 * _score_bool(valid_deps) + 0.5 * _score_bool(no_cycles)
    return BenchmarkResult(
        test_name="planning_dependency_accuracy",
        dimension="planning",
        sub_dimension="dependency_accuracy",
        score=score,
        raw_output=raw[:500],
        metadata={
            "valid_deps": valid_deps,
            "no_cycles": no_cycles,
            "task_count": len(all_task_ids),
        },
    )


async def test_planning_granularity() -> BenchmarkResult:
    """Test if model produces appropriately granular tasks."""
    prompt = """Plan: "Implement a todo list app with CRUD operations, user auth, and due dates."

Output JSON with phases and tasks. Keep tasks at a HIGH LEVEL (one phase per major component, one task per major feature). Aim for 3-5 phases and 3-8 tasks total.

Format:
{"phases": [{"phase_id": "...", "title": "...", "tasks": [{"task_id": "...", "title": "...", "objective": "..."}]}]}
"""
    raw = await _call_llm(
        [Message(role="user", content=prompt)],
        temperature=0.3,
        max_tokens=1000,
    )
    data = _extract_json(raw)
    if not data:
        return BenchmarkResult(
            test_name="planning_granularity",
            dimension="planning",
            sub_dimension="task_granularity_appropriateness",
            score=0.0,
            raw_output=raw[:500],
            error="No valid JSON",
        )

    task_count = sum(len(p.get("tasks", [])) for p in data.get("phases", []))
    # For a todo app, 3-8 tasks is reasonable granularity at high level.
    # Agentic models often produce detailed engineering plans (frontend, backend,
    # DB, tests, deployment) which is desirable for coding agents.
    if 3 <= task_count <= 8:
        score = 1.0
    elif 2 <= task_count <= 15:
        score = 0.85
    elif 1 <= task_count <= 25:
        score = 0.7
    elif 1 <= task_count <= 40:
        score = 0.5
    else:
        score = 0.3

    return BenchmarkResult(
        test_name="planning_granularity",
        dimension="planning",
        sub_dimension="task_granularity_appropriateness",
        score=score,
        raw_output=raw[:500],
        metadata={"task_count": task_count},
    )


# ---------------------------------------------------------------------------
# Task Completion Dimension Tests
# ---------------------------------------------------------------------------


async def test_code_generation_correctness() -> BenchmarkResult:
    """Test if model generates correct, executable code."""
    prompt = """Write a Python function `fibonacci(n)` that returns the nth Fibonacci number.
Requirements:
- Handle n=0 (return 0) and n=1 (return 1)
- Use an efficient approach (O(n) time or better)
- Include docstring

Output ONLY the function code, no explanation, no markdown.
"""
    raw = await _call_llm(
        [Message(role="user", content=prompt)],
        temperature=0.2,
        max_tokens=300,
    )
    code = raw.strip()
    # Remove markdown fences if present
    code = re.sub(r"^```python\s*", "", code)
    code = re.sub(r"\s*```$", "", code)

    # Try to parse and execute
    has_fibonacci = False
    error_msg = ""
    try:
        tree = ast.parse(code)
        func_names = [node.name for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)]
        has_fibonacci = "fibonacci" in func_names

        if has_fibonacci:
            local_ns: dict[str, Any] = {}
            exec(compile(tree, "<string>", "exec"), local_ns)
            fib = local_ns.get("fibonacci")
            if fib:
                results = [fib(0), fib(1), fib(2), fib(5), fib(10)]
                expected = [0, 1, 1, 5, 55]
                correct = results == expected
                score = 1.0 if correct else 0.5 if has_fibonacci else 0.0
                return BenchmarkResult(
                    test_name="code_generation_correctness",
                    dimension="task_completion",
                    sub_dimension="code_correctness",
                    score=score,
                    raw_output=code[:300],
                    metadata={
                        "has_function": has_fibonacci,
                        "test_results": results,
                        "expected": expected,
                    },
                )
    except Exception as e:
        error_msg = str(e)

    return BenchmarkResult(
        test_name="code_generation_correctness",
        dimension="task_completion",
        sub_dimension="code_correctness",
        score=0.0 if not has_fibonacci else 0.3,
        raw_output=code[:300],
        error=f"Execution failed: {error_msg}" if error_msg else "Could not execute",
    )


async def test_bug_fixing() -> BenchmarkResult:
    """Test if model can fix a simple bug."""
    buggy_code = '''def sum_even_numbers(numbers):
    """Return sum of all even numbers in the list."""
    total = 0
    for n in numbers:
        if n % 2 == 1:  # BUG: checks for odd, not even
            total += n
    return total
'''
    prompt = f"""Fix the bug in this Python function:

```python
{buggy_code}
```

Output ONLY the corrected function, no explanation.
"""
    raw = await _call_llm(
        [Message(role="user", content=prompt)],
        temperature=0.2,
        max_tokens=300,
    )
    code = raw.strip()
    code = re.sub(r"^```python\s*", "", code)
    code = re.sub(r"\s*```$", "", code)

    # Check if the fix is present
    fixed = "n % 2 == 0" in code or "not (n % 2)" in code or "n % 2 != 1" in code
    score = 1.0 if fixed else 0.5 if "even" in code.lower() else 0.0

    return BenchmarkResult(
        test_name="bug_fixing",
        dimension="task_completion",
        sub_dimension="code_correctness",
        score=score,
        raw_output=code[:300],
        metadata={"fixed": fixed},
    )


# ---------------------------------------------------------------------------
# JSON Formatting Dimension Tests
# ---------------------------------------------------------------------------


async def test_json_schema_compliance() -> BenchmarkResult:
    """Test if model outputs JSON matching a required schema."""
    prompt = """Output a JSON object with EXACTLY these fields:
{
  "name": "your name",
  "age": 25,
  "skills": ["skill1", "skill2"],
  "active": true
}

Output ONLY the JSON, no markdown, no explanation.
"""
    raw = await _call_llm(
        [Message(role="user", content=prompt)],
        temperature=0.1,
        max_tokens=200,
    )
    data = _extract_json(raw)
    if not data:
        return BenchmarkResult(
            test_name="json_schema_compliance",
            dimension="json_formatting",
            sub_dimension="schema_compliance",
            score=0.0,
            raw_output=raw[:300],
            error="No valid JSON",
        )

    required_keys = {"name", "age", "skills", "active"}
    has_all = required_keys.issubset(data.keys())
    types_ok = (
        isinstance(data.get("name"), str)
        and isinstance(data.get("age"), (int, float))
        and isinstance(data.get("skills"), list)
        and isinstance(data.get("active"), bool)
    )
    score = 1.0 if has_all and types_ok else 0.5 if has_all else 0.0

    return BenchmarkResult(
        test_name="json_schema_compliance",
        dimension="json_formatting",
        sub_dimension="schema_compliance",
        score=score,
        raw_output=raw[:300],
        metadata={"has_all_keys": has_all, "types_ok": types_ok},
    )


async def test_json_self_correction() -> BenchmarkResult:
    """Test if model can correct its own malformed JSON when prompted."""
    # First, deliberately ask for malformed output
    prompt1 = """Output a JSON object: {"status": "ok", "count": 5

Notice the missing closing brace. Output EXACTLY as shown.
"""
    raw1 = await _call_llm(
        [Message(role="user", content=prompt1)],
        temperature=0.1,
        max_tokens=100,
    )

    # Now ask to fix it
    prompt2 = f"""The following text is malformed JSON. Fix it and output valid JSON only:

{raw1}
"""
    raw2 = await _call_llm(
        [Message(role="user", content=prompt2)],
        temperature=0.1,
        max_tokens=100,
    )

    data = _extract_json(raw2)
    is_valid = data is not None and "status" in data

    return BenchmarkResult(
        test_name="json_self_correction",
        dimension="json_formatting",
        sub_dimension="self_correction",
        score=_score_bool(is_valid),
        raw_output=raw2[:300],
        metadata={"corrected": is_valid},
    )


async def test_json_in_complex_context() -> BenchmarkResult:
    """Test if model can output valid JSON within a complex reasoning context."""
    prompt = """Analyze the following scenario and output your analysis as JSON.

Scenario: A company has 100 employees. 60% work remotely. Of the remote workers, 30% are in engineering. The company plans to hire 20 more engineers next quarter.

Output JSON:
{
  "current_remote": <number>,
  "current_remote_engineers": <number>,
  "projected_engineers": <number>,
  "reasoning": "brief explanation"
}

Calculate correctly and output ONLY valid JSON.
"""
    raw = await _call_llm(
        [Message(role="user", content=prompt)],
        temperature=0.2,
        max_tokens=300,
    )
    data = _extract_json(raw)
    if not data:
        return BenchmarkResult(
            test_name="json_in_complex_context",
            dimension="json_formatting",
            sub_dimension="valid_json_rate",
            score=0.0,
            raw_output=raw[:300],
            error="No valid JSON",
        )

    # Check calculations
    current_remote = data.get("current_remote")
    current_eng = data.get("current_remote_engineers")
    projected = data.get("projected_engineers")

    math_ok = current_remote == 60 and current_eng == 18 and projected == 38
    has_reasoning = bool(data.get("reasoning"))

    score = 1.0 if math_ok and has_reasoning else 0.6 if has_reasoning else 0.3

    return BenchmarkResult(
        test_name="json_in_complex_context",
        dimension="json_formatting",
        sub_dimension="valid_json_rate",
        score=score,
        raw_output=raw[:300],
        metadata={
            "math_correct": math_ok,
            "has_reasoning": has_reasoning,
            "extracted": data,
        },
    )


# ---------------------------------------------------------------------------
# Chain of Thought Dimension Tests
# ---------------------------------------------------------------------------


async def test_reasoning_depth() -> BenchmarkResult:
    """Test multi-step reasoning ability."""
    prompt = """Solve this step by step:

A train travels 120 km in 2 hours. It then stops for 30 minutes. 
After that, it travels at 1.5x its original speed for 1.5 hours.
What is the total distance traveled?

Output your final answer as a single number on the last line, prefixed with "ANSWER: ".
"""
    raw = await _call_llm(
        [Message(role="user", content=prompt)],
        temperature=0.2,
        max_tokens=400,
    )
    # Expected: 120 + (60 * 1.5 * 1.5) = 120 + 135 = 255
    answer_match = re.search(r"ANSWER:\s*(\d+(?:\.\d+)?)", raw)
    if answer_match:
        try:
            answer = float(answer_match.group(1))
            correct = abs(answer - 255) < 1
            return BenchmarkResult(
                test_name="reasoning_depth",
                dimension="chain_of_thought",
                sub_dimension="reasoning_depth",
                score=_score_bool(correct),
                raw_output=raw[:400],
                metadata={"extracted_answer": answer, "expected": 255},
            )
        except ValueError:
            pass

    return BenchmarkResult(
        test_name="reasoning_depth",
        dimension="chain_of_thought",
        sub_dimension="reasoning_depth",
        score=0.0,
        raw_output=raw[:400],
        error="Could not extract valid answer",
    )


async def test_error_diagnosis() -> BenchmarkResult:
    """Test if model can diagnose code errors."""
    prompt = """This Python code has an error:

```python
def process_data(data):
    result = []
    for item in data:
        result.append(item.upper())
    return result

process_data([1, 2, 3])
```

What is the error and how would you fix it?
Output your answer in this JSON format:
{"error_type": "...", "explanation": "...", "fix": "..."}
"""
    raw = await _call_llm(
        [Message(role="user", content=prompt)],
        temperature=0.2,
        max_tokens=300,
    )
    data = _extract_json(raw)
    if not data:
        return BenchmarkResult(
            test_name="error_diagnosis",
            dimension="chain_of_thought",
            sub_dimension="error_diagnosis",
            score=0.0,
            raw_output=raw[:300],
            error="No valid JSON",
        )

    explanation = data.get("explanation", "").lower()
    fix = data.get("fix", "").lower()
    correct_concept = (
        "int" in explanation
        or "integer" in explanation
        or "number" in explanation
        or "not string" in explanation
        or "attribute" in explanation
    )
    has_fix = "str" in fix or "string" in fix or "convert" in fix or "check" in fix

    score = 1.0 if correct_concept and has_fix else 0.5 if correct_concept else 0.2

    return BenchmarkResult(
        test_name="error_diagnosis",
        dimension="chain_of_thought",
        sub_dimension="error_diagnosis",
        score=score,
        raw_output=raw[:300],
        metadata={"correct_concept": correct_concept, "has_fix": has_fix},
    )


async def test_debugging_skill() -> BenchmarkResult:
    """Test debugging ability with a subtle bug."""
    prompt = """Debug this function:

```python
def find_duplicates(items):
    seen = set()
    duplicates = []
    for item in items:
        if item in seen:
            duplicates.append(item)
        seen.add(item)
    return duplicates
```

The function is supposed to return each duplicate only once, but it returns duplicates multiple times.
Output the fixed function only, no explanation.
"""
    raw = await _call_llm(
        [Message(role="user", content=prompt)],
        temperature=0.2,
        max_tokens=300,
    )
    code = raw.strip()
    code = re.sub(r"^```python\s*", "", code)
    code = re.sub(r"\s*```$", "", code)

    # Correct fix: use a separate set/container for duplicates already reported
    fixed = (
        "duplicates_set" in code
        or "already_seen" in code
        or "reported" in code
        or "added" in code
        or "found" in code
        or "if item in seen and item not in duplicates" in code
        or "if item not in duplicates" in code
    )
    score = 1.0 if fixed else 0.3 if "find_duplicates" in code else 0.0

    return BenchmarkResult(
        test_name="debugging_skill",
        dimension="chain_of_thought",
        sub_dimension="debugging_skill",
        score=score,
        raw_output=code[:300],
        metadata={"fixed": fixed},
    )


# ---------------------------------------------------------------------------
# Code Review Dimension Tests
# ---------------------------------------------------------------------------


async def test_bug_detection() -> BenchmarkResult:
    """Test if model can detect bugs in code."""
    prompt = '''Review this code for bugs:

```python
def divide_all(numbers, divisor):
    """Divide each number by divisor."""
    return [n / divisor for n in numbers]
```

Output JSON: {"has_bug": true/false, "bug_description": "...", "severity": "high/medium/low"}
'''
    raw = await _call_llm(
        [Message(role="user", content=prompt)],
        temperature=0.2,
        max_tokens=200,
    )
    data = _extract_json(raw)
    if not data:
        return BenchmarkResult(
            test_name="bug_detection",
            dimension="code_review",
            sub_dimension="bug_detection",
            score=0.0,
            raw_output=raw[:300],
            error="No valid JSON",
        )

    has_bug = data.get("has_bug")
    description = data.get("bug_description", "").lower()
    found_zero_division = (
        "zero" in description or "divisor" in description or "division" in description
    )

    score = 1.0 if has_bug and found_zero_division else 0.5 if has_bug else 0.0

    return BenchmarkResult(
        test_name="bug_detection",
        dimension="code_review",
        sub_dimension="bug_detection",
        score=score,
        raw_output=raw[:300],
        metadata={"has_bug": has_bug, "found_zero_division": found_zero_division},
    )


async def test_review_structured_output() -> BenchmarkResult:
    """Test if model outputs structured review JSON."""
    prompt = """Review this code:

```python
def greet(name):
    return f"Hello, {name}!"
```

Output your review as JSON with these exact fields:
{"verdict": "APPROVE" or "NEEDS_REWORK", "score": 0-100, "feedback": "...", "issues": ["..."]}
"""
    raw = await _call_llm(
        [Message(role="user", content=prompt)],
        temperature=0.2,
        max_tokens=300,
    )
    data = _extract_json(raw)
    if not data:
        return BenchmarkResult(
            test_name="review_structured_output",
            dimension="code_review",
            sub_dimension="structured_output",
            score=0.0,
            raw_output=raw[:300],
            error="No valid JSON",
        )

    required = {"verdict", "score", "feedback", "issues"}
    has_all = required.issubset(data.keys())
    types_ok = isinstance(data.get("score"), (int, float)) and isinstance(data.get("issues"), list)
    score = 1.0 if has_all and types_ok else 0.5 if has_all else 0.0

    return BenchmarkResult(
        test_name="review_structured_output",
        dimension="code_review",
        sub_dimension="structured_output",
        score=score,
        raw_output=raw[:300],
        metadata={"has_all_keys": has_all, "types_ok": types_ok},
    )


# ---------------------------------------------------------------------------
# Benchmark Suite Registry
# ---------------------------------------------------------------------------

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
        except Exception as e:
            # Extract dimension info from the function defaults
            result = BenchmarkResult(
                test_name=name,
                dimension="unknown",
                sub_dimension="unknown",
                score=0.0,
                error=str(e),
            )
        results.append(result)

    return results
