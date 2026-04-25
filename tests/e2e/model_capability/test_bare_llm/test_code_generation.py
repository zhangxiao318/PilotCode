"""Layer 1: Code Generation Capability (HumanEval/MBPP-style).

Tests whether the bare LLM can generate correct Python functions from
natural language descriptions. Each task includes:
- A docstring-style description
- One or more test assertions

The model is asked to generate only the function body (no explanation).
The generated code is executed locally to verify correctness.

Failure attribution: llm_capability (the model cannot synthesize correct code).

Inspired by:
- HumanEval (Chen et al., 2021)
- MBPP (Austin et al., 2021)
"""

from __future__ import annotations

import asyncio
import pytest
import textwrap

from pilotcode.utils.model_client import Message

from .helpers import strip_thinking

# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


async def _generate_code(model_client, prompt: str, timeout: float) -> str:
    """Ask the model to generate code and extract it from the response."""
    messages = [
        Message(
            role="user",
            content=(
                f"{prompt}\n\n"
                "Write only the Python function. Do not include explanations, examples, or markdown. "
                "Start with 'def ' and end with the return statement."
            ),
        ),
    ]
    chunks: list[str] = []
    async for chunk in model_client.chat_completion(messages, tools=None, stream=True):
        delta = chunk.get("choices", [{}])[0].get("delta", {})
        content = delta.get("content")
        if content:
            chunks.append(content)
    return strip_thinking("".join(chunks))


def _extract_function(code_text: str) -> str:
    """Extract the first Python function from raw text."""
    lines = code_text.splitlines()
    result_lines: list[str] = []
    in_function = False
    base_indent = None

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("def "):
            in_function = True
            base_indent = len(line) - len(line.lstrip())
            result_lines.append(stripped)
            continue

        if in_function:
            if stripped == "" and not result_lines:
                continue
            if stripped == "" and result_lines and result_lines[-1].strip() == "":
                continue
            # Detect end of function: line at same or lower indent that is not blank
            current_indent = len(line) - len(line.lstrip())
            if stripped and current_indent <= base_indent and not stripped.startswith("def "):
                break
            result_lines.append(line)

    return "\n".join(result_lines)


def _safe_exec(function_code: str, test_code: str) -> tuple[bool, str]:
    """Execute generated function + test code in an isolated namespace.

    Returns (passed, error_message).
    """
    namespace: dict = {}
    full_code = textwrap.dedent(function_code) + "\n\n" + textwrap.dedent(test_code)
    try:
        exec(full_code, namespace)
        return True, ""
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"


# ---------------------------------------------------------------------------
# Test cases: (id, prompt, test_assertions)
# ---------------------------------------------------------------------------

CODE_GEN_CASES = [
    (
        "CG001",
        "Write a function has_duplicate(nums: list[int]) -> bool that returns True if the list contains any duplicate elements, otherwise False.",
        """
assert has_duplicate([1, 2, 3, 1]) == True
assert has_duplicate([1, 2, 3, 4]) == False
assert has_duplicate([]) == False
assert has_duplicate([1]) == False
""",
    ),
    (
        "CG002",
        "Write a function reverse_words(text: str) -> str that reverses each word in the string while keeping the words in their original order.",
        """
assert reverse_words("hello world") == "olleh dlrow"
assert reverse_words("Python") == "nohtyP"
assert reverse_words("") == ""
""",
    ),
    (
        "CG003",
        "Write a function factorial(n: int) -> int that returns the factorial of n. factorial(0) should return 1.",
        """
assert factorial(0) == 1
assert factorial(1) == 1
assert factorial(5) == 120
assert factorial(3) == 6
""",
    ),
    (
        "CG004",
        "Write a function is_palindrome(s: str) -> bool that returns True if the string is a palindrome (reads the same forwards and backwards), ignoring case and non-alphanumeric characters.",
        """
assert is_palindrome("A man, a plan, a canal: Panama") == True
assert is_palindrome("race a car") == False
assert is_palindrome("") == True
assert is_palindrome("a") == True
""",
    ),
    (
        "CG005",
        "Write a function merge_sorted_lists(a: list[int], b: list[int]) -> list[int] that merges two sorted lists into one sorted list.",
        """
assert merge_sorted_lists([1, 3, 5], [2, 4, 6]) == [1, 2, 3, 4, 5, 6]
assert merge_sorted_lists([], [1, 2]) == [1, 2]
assert merge_sorted_lists([1, 2, 3], []) == [1, 2, 3]
assert merge_sorted_lists([], []) == []
""",
    ),
]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.llm_e2e
class TestCodeGeneration:
    """HumanEval-style function generation with local execution verification."""

    @pytest.mark.parametrize(
        "case_id, prompt, tests", CODE_GEN_CASES, ids=lambda x: x[0] if isinstance(x, tuple) else x
    )
    async def test_generate_and_execute(self, bare_llm_client, e2e_timeout, case_id, prompt, tests):
        """Generate code and verify by executing assertions locally."""
        raw_response = await asyncio.wait_for(
            _generate_code(bare_llm_client, prompt, e2e_timeout),
            timeout=e2e_timeout,
        )

        function_code = _extract_function(raw_response)
        assert function_code.strip(), (
            f"[{case_id}] Could not extract a function from response. "
            f"Raw response: {raw_response[:300]!r}"
        )

        passed, error = _safe_exec(function_code, tests)
        assert passed, (
            f"[{case_id}] Generated code failed tests.\n"
            f"Function:\n{function_code}\n"
            f"Error: {error}"
        )
