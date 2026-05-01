"""Code review dimension benchmarks (medium)."""

from __future__ import annotations

from typing import Any

from pilotcode.utils.model_client import Message

from .base import BenchmarkResult, _call_llm, _extract_json


async def test_bug_detection() -> BenchmarkResult:
    """Test detection of a subtle boundary / parsing bug."""
    prompt = '''Review this Python function for bugs. It looks correct at first glance.

```python
def parse_config(config_str):
    """Parse a key=value configuration string into a dictionary.
    
    Example:
        parse_config("host=localhost\\nport=5432")
        # returns {"host": "localhost", "port": "5432"}
    """
    result = {}
    for line in config_str.split("\\n"):
        line = line.strip()
        if "=" in line:
            key, value = line.split("=")
            result[key.strip()] = value.strip()
    return result
```

Output your review as JSON with these exact fields:
{"has_bug": true/false, "bug_description": "...", "severity": "high/medium/low", "fix": "..."}

The bug is subtle — it only manifests with certain inputs.
'''
    raw = await _call_llm(
        [Message(role="user", content=prompt)],
        temperature=0.2,
    )
    data = _extract_json(raw)
    if not data:
        return BenchmarkResult(
            test_name="bug_detection",
            dimension="code_review",
            sub_dimension="bug_detection",
            score=0.0,
            raw_output=raw[:400],
            error="No valid JSON",
        )

    has_bug = data.get("has_bug")
    description = data.get("bug_description", "").lower()
    fix = data.get("fix", "").lower()

    # The bug: split("=") splits on ALL equals signs, so "key=value=extra" loses the extra part.
    found_split_bug = any(
        kw in description
        for kw in [
            "split",
            "partition",
            "multiple",
            "extra",
            "value contains",
            "delimiter",
            "only splits once",
        ]
    )
    has_fix = any(
        kw in fix
        for kw in [
            "split('=', 1)",
            'split("=", 1)',
            "partition",
            "maxsplit",
        ]
    )

    score = (
        1.0
        if has_bug and found_split_bug and has_fix
        else 0.6 if has_bug and found_split_bug else 0.3 if has_bug else 0.0
    )

    return BenchmarkResult(
        test_name="bug_detection",
        dimension="code_review",
        sub_dimension="bug_detection",
        score=score,
        raw_output=raw[:400],
        metadata={
            "has_bug": has_bug,
            "found_split_bug": found_split_bug,
            "has_fix": has_fix,
        },
    )


async def test_review_structured_output() -> BenchmarkResult:
    """Test structured review of code with performance implications."""
    prompt = """Review this function for correctness, performance, and edge cases.

```python
def find_pairs_with_sum(nums, target):
    \"\"\"Return all unique pairs [a, b] where a + b == target and a <= b.\"\"\"
    result = []
    for i in range(len(nums)):
        for j in range(i + 1, len(nums)):
            if nums[i] + nums[j] == target:
                pair = sorted([nums[i], nums[j]])
                if pair not in result:
                    result.append(pair)
    return result
```

Output your review as JSON with these exact fields:
{
  "verdict": "APPROVE" or "NEEDS_REWORK",
  "score": 0-100,
  "correctness": "assessment of correctness",
  "performance": "assessment of performance (O(n^2) is obvious; is there a better approach?)",
  "edge_cases": ["list at least one edge case not handled well"],
  "issues": ["list specific issues or leave empty"]
}
"""
    raw = await _call_llm(
        [Message(role="user", content=prompt)],
        temperature=0.2,
    )
    data = _extract_json(raw)
    if not data:
        return BenchmarkResult(
            test_name="review_structured_output",
            dimension="code_review",
            sub_dimension="structured_output",
            score=0.0,
            raw_output=raw[:400],
            error="No valid JSON",
        )

    required = {"verdict", "score", "correctness", "performance", "edge_cases", "issues"}
    has_all = required.issubset(data.keys())
    types_ok = (
        isinstance(data.get("score"), (int, float))
        and isinstance(data.get("edge_cases"), list)
        and isinstance(data.get("issues"), list)
    )

    perf = data.get("performance", "").lower()
    mentions_hash_set = any(
        kw in perf for kw in ["hash", "set", "o(n)", "linear", "dictionary", "dict"]
    )

    score = (
        1.0
        if has_all and types_ok and mentions_hash_set
        else 0.7 if has_all and types_ok else 0.3 if has_all else 0.0
    )

    return BenchmarkResult(
        test_name="review_structured_output",
        dimension="code_review",
        sub_dimension="structured_output",
        score=score,
        raw_output=raw[:400],
        metadata={
            "has_all_keys": has_all,
            "types_ok": types_ok,
            "mentions_hash_set": mentions_hash_set,
        },
    )
