"""Layer 1: Code Understanding Capability.

Tests whether the bare LLM can:
- Explain what code does
- Identify bugs in code
- Summarize complex logic

Failure attribution: llm_capability (the model itself cannot reason about code).
"""

from __future__ import annotations

import asyncio
import pytest

from pilotcode.utils.model_client import Message

from .helpers import strip_thinking

# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


async def _chat(model_client, messages: list[Message], timeout: float = 60.0) -> str:
    """Send messages to the bare model and collect the full text response."""
    chunks: list[str] = []
    async for chunk in model_client.chat_completion(messages, tools=None, stream=True):
        delta = chunk.get("choices", [{}])[0].get("delta", {})
        content = delta.get("content")
        if content:
            chunks.append(content)
    return strip_thinking("".join(chunks))


# ---------------------------------------------------------------------------
# Test data
# ---------------------------------------------------------------------------

SIMPLE_FUNCTION = """
def count_vowels(text: str) -> int:
    vowels = "aeiouAEIOU"
    return sum(1 for ch in text if ch in vowels)
""".strip()

BUGGY_FUNCTION = """
def find_max(numbers):
    max_val = 0
    for n in numbers:
        if n > max_val:
            max_val = n
    return max_val
""".strip()

NESTED_LOGIC = """
def process_orders(orders):
    result = []
    for order in orders:
        if order["status"] == "pending":
            total = 0
            for item in order["items"]:
                price = item["price"]
                qty = item["quantity"]
                if item["category"] == "electronics":
                    price *= 0.9
                total += price * qty
            if total > 100:
                result.append({"id": order["id"], "total": round(total, 2)})
    return result
""".strip()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.llm_e2e
class TestCodeExplanation:
    """LLM should accurately explain what simple code does."""

    async def test_explain_simple_function(self, bare_llm_client, e2e_timeout):
        """Given a simple function, the model should explain its purpose."""
        messages = [
            Message(
                role="user",
                content=(
                    f"Explain what this Python function does in one sentence:\n\n"
                    f"```python\n{SIMPLE_FUNCTION}\n```"
                ),
            ),
        ]
        response = await asyncio.wait_for(
            _chat(bare_llm_client, messages),
            timeout=e2e_timeout,
        )
        # Should mention counting vowels or letters
        assert (
            "vowel" in response.lower() or "count" in response.lower()
        ), f"Expected explanation about vowels/counting, got: {response[:200]!r}"

    async def test_explain_nested_logic(self, bare_llm_client, e2e_timeout):
        """Given nested logic, the model should summarize key operations."""
        messages = [
            Message(
                role="user",
                content=(
                    f"Summarize what this function does in one sentence:\n\n"
                    f"```python\n{NESTED_LOGIC}\n```"
                ),
            ),
        ]
        response = await asyncio.wait_for(
            _chat(bare_llm_client, messages),
            timeout=e2e_timeout,
        )
        # Should mention pending orders, totals, or discounts
        keywords = ["pending", "order", "total", "discount", "electronics"]
        assert any(
            kw in response.lower() for kw in keywords
        ), f"Expected mention of orders/totals, got: {response[:200]!r}"


@pytest.mark.llm_e2e
class TestBugDetection:
    """LLM should identify obvious bugs in code."""

    async def test_detect_empty_list_bug(self, bare_llm_client, e2e_timeout):
        """The buggy function fails on all-negative lists (max_val starts at 0)."""
        messages = [
            Message(
                role="user",
                content=(
                    f"Find the bug in this Python function. Describe the bug in one sentence.\n\n"
                    f"```python\n{BUGGY_FUNCTION}\n```"
                ),
            ),
        ]
        response = await asyncio.wait_for(
            _chat(bare_llm_client, messages),
            timeout=e2e_timeout,
        )
        # Should mention negative numbers, empty list, or initial value
        keywords = ["negative", "empty", "initial", "zero", "0", "max_val"]
        assert any(
            kw in response.lower() for kw in keywords
        ), f"Expected mention of negative/empty/initial-value bug, got: {response[:200]!r}"
