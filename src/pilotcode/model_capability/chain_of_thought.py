"""Chain-of-thought dimension benchmarks (medium)."""

from __future__ import annotations

import ast
import re
from typing import Any

from pilotcode.utils.model_client import Message

from .base import BenchmarkResult, _call_llm, _extract_code, _extract_json, _score_bool


async def test_reasoning_depth() -> BenchmarkResult:
    """Test probability reasoning with combinatorics."""
    prompt = """Solve this probability problem step by step.

A bag contains 3 red balls, 5 blue balls, and 2 green balls (10 total).
You draw 3 balls at random WITHOUT replacement.

What is the probability of drawing AT LEAST ONE red ball?

Give your answer as a simplified fraction or exact decimal, and output it on the last line prefixed with "ANSWER: ".
"""
    raw = await _call_llm(
        [Message(role="user", content=prompt)],
        temperature=0.2,
    )
    # P(at least one red) = 1 - P(no red)
    # P(no red) = C(7,3) / C(10,3) = 35 / 120 = 7/24
    # P(at least one red) = 1 - 7/24 = 17/24 ≈ 0.70833
    expected = 17 / 24

    answer_match = re.search(r"ANSWER:\s*([\d./]+)", raw)
    if answer_match:
        try:
            val = answer_match.group(1)
            if "/" in val:
                num, den = val.split("/")
                answer = float(num) / float(den)
            else:
                answer = float(val)
            correct = abs(answer - expected) < 0.02
            return BenchmarkResult(
                test_name="reasoning_depth",
                dimension="chain_of_thought",
                sub_dimension="reasoning_depth",
                score=_score_bool(correct),
                raw_output=raw[:500],
                metadata={"extracted_answer": answer, "expected": expected},
            )
        except (ValueError, ZeroDivisionError):
            pass

    return BenchmarkResult(
        test_name="reasoning_depth",
        dimension="chain_of_thought",
        sub_dimension="reasoning_depth",
        score=0.0,
        raw_output=raw[:500],
        error="Could not extract valid answer",
    )


async def test_error_diagnosis() -> BenchmarkResult:
    """Test diagnosis of a closure/lazy-binding bug in async code."""
    prompt = """This Python code produces unexpected results. Identify the root cause and explain the fix.

```python
import asyncio

async def fetch_all(urls):
    tasks = []
    for url in urls:
        tasks.append(asyncio.create_task(download(url)))
    return await asyncio.gather(*tasks)

async def download(url):
    print(f"Downloading {url}")
    await asyncio.sleep(0.1)
    return f"Data from {url}"

async def main():
    urls = ["http://a.com", "http://b.com", "http://c.com"]
    results = await fetch_all(urls)
    print(results)

asyncio.run(main())
```

Expected: each result should correspond to its URL.
Actual: sometimes all results show the last URL.

Output your diagnosis in this JSON format:
{"root_cause": "...", "explanation": "...", "fix_code": "..."}

Note: the bug is NOT in the shown code above; it is a common pattern that looks like this but fails in a subtle way. The model must identify the *conceptual* bug pattern.

Hint: the real buggy code looks almost identical, but uses a lambda or default argument inside a loop.
"""
    raw = await _call_llm(
        [Message(role="user", content=prompt)],
        temperature=0.2,
    )
    data = _extract_json(raw)
    if not data:
        return BenchmarkResult(
            test_name="error_diagnosis",
            dimension="chain_of_thought",
            sub_dimension="error_diagnosis",
            score=0.0,
            raw_output=raw[:400],
            error="No valid JSON",
        )

    explanation = data.get("explanation", "").lower()
    root_cause = data.get("root_cause", "").lower()
    combined = explanation + " " + root_cause

    correct_concept = any(
        kw in combined
        for kw in [
            "late binding",
            "closure",
            "lambda",
            "default argument",
            "loop variable",
            "captured",
            "binding",
        ]
    )
    has_fix = bool(data.get("fix_code", "").strip())

    score = 1.0 if correct_concept and has_fix else 0.5 if correct_concept else 0.2

    return BenchmarkResult(
        test_name="error_diagnosis",
        dimension="chain_of_thought",
        sub_dimension="error_diagnosis",
        score=score,
        raw_output=raw[:400],
        metadata={"correct_concept": correct_concept, "has_fix": has_fix},
    )


async def test_debugging_skill() -> BenchmarkResult:
    """Test debugging with AST + execution validation on a subtle algorithm bug."""
    prompt = """Debug this function. It is supposed to find the index of the first occurrence of `target` in a sorted list `arr`, or return -1 if not found. It uses binary search.

```python
def binary_search(arr, target):
    left, right = 0, len(arr) - 1
    while left <= right:
        mid = (left + right) // 2
        if arr[mid] == target:
            return mid
        elif arr[mid] < target:
            left = mid + 1
        else:
            right = mid - 1
    return -1
```

The bug: when the list contains duplicates, this function does NOT guarantee returning the FIRST occurrence. Fix it so it always returns the leftmost index of `target`.

Output ONLY the corrected function, no explanation.
"""
    raw = await _call_llm(
        [Message(role="user", content=prompt)],
        temperature=0.2,
    )
    code = _extract_code(raw)

    error_msg = ""
    tests_passed = 0
    tests_total = 5
    try:
        tree = ast.parse(code)
        local_ns: dict[str, Any] = {}
        exec(compile(tree, "<string>", "exec"), local_ns)
        binary_search = local_ns.get("binary_search")

        if not binary_search:
            raise ValueError("binary_search function not found")

        test_cases = [
            ([1, 2, 3, 4, 5], 3, 2),
            ([1, 2, 2, 2, 3], 2, 1),
            ([1, 1, 1, 1, 1], 1, 0),
            ([1, 2, 3, 4, 5], 6, -1),
            ([], 1, -1),
        ]
        for arr, target, expected in test_cases:
            result = binary_search(arr, target)
            if result == expected:
                tests_passed += 1

    except Exception as e:
        error_msg = str(e)

    score = tests_passed / tests_total
    return BenchmarkResult(
        test_name="debugging_skill",
        dimension="chain_of_thought",
        sub_dimension="debugging_skill",
        score=score,
        raw_output=code[:400],
        error=error_msg if error_msg else None,
        metadata={"tests_passed": tests_passed, "tests_total": tests_total},
    )
