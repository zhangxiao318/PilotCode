"""Layer 1: Instruction Following Capability.

Tests whether the bare LLM respects explicit constraints:
- Format requirements (JSON, numbered list)
- Negation (do not explain, do not use tools)
- Length constraints (one-word answer)

Failure attribution: llm_capability (the model ignores or misunderstands instructions).
"""

from __future__ import annotations

import asyncio
import pytest

from pilotcode.utils.model_client import Message

from .helpers import strip_thinking


async def _chat(model_client, messages: list[Message], timeout: float = 60.0) -> str:
    """Send messages to the bare model and collect the full text response."""
    chunks: list[str] = []
    async for chunk in model_client.chat_completion(messages, tools=None, stream=True):
        delta = chunk.get("choices", [{}])[0].get("delta", {})
        content = delta.get("content")
        if content:
            chunks.append(content)
    return strip_thinking("".join(chunks))


@pytest.mark.llm_e2e
class TestFormatConstraints:
    """LLM should follow output format instructions."""

    async def test_json_format(self, bare_llm_client, e2e_timeout):
        """User asks for JSON; model should output valid JSON."""
        messages = [
            Message(
                role="user",
                content=(
                    "List 3 common Python built-in functions. "
                    "Respond ONLY as a JSON array of strings, no other text."
                ),
            ),
        ]
        response = await asyncio.wait_for(
            _chat(bare_llm_client, messages),
            timeout=e2e_timeout,
        )
        stripped = response.strip()
        assert stripped.startswith("[") and stripped.endswith(
            "]"
        ), f"Expected JSON array, got: {response[:200]!r}"

    async def test_numbered_list_format(self, bare_llm_client, e2e_timeout):
        """User asks for a numbered list."""
        messages = [
            Message(
                role="user",
                content=(
                    "Name 3 Python data types. Use numbered format (1. 2. 3.). " "No other text."
                ),
            ),
        ]
        response = await asyncio.wait_for(
            _chat(bare_llm_client, messages),
            timeout=e2e_timeout,
        )
        assert (
            "1." in response and "2." in response and "3." in response
        ), f"Expected numbered list, got: {response[:200]!r}"


@pytest.mark.llm_e2e
class TestNegation:
    """LLM should respect negative instructions."""

    async def test_do_not_explain(self, bare_llm_client, e2e_timeout):
        """User asks for a one-word answer; model should not ramble."""
        messages = [
            Message(
                role="user",
                content=(
                    "Is Python an interpreted language? Answer with exactly one word: Yes or No. "
                    "Do not explain."
                ),
            ),
        ]
        response = await asyncio.wait_for(
            _chat(bare_llm_client, messages),
            timeout=e2e_timeout,
        )
        stripped = response.strip()
        # Allow slight punctuation
        assert (
            len(stripped) < 10
        ), f"Expected short answer, got: {stripped!r} (length={len(stripped)})"
        assert (
            "yes" in stripped.lower() or "no" in stripped.lower()
        ), f"Expected Yes/No, got: {stripped!r}"

    async def test_do_not_use_code(self, bare_llm_client, e2e_timeout):
        """User asks a conceptual question with 'do not write code'."""
        messages = [
            Message(
                role="user",
                content=("Explain what a decorator is in Python. Do not write any code."),
            ),
        ]
        response = await asyncio.wait_for(
            _chat(bare_llm_client, messages),
            timeout=e2e_timeout,
        )
        # Should not contain code block markers
        assert "```" not in response, f"Should not contain code blocks, got: {response[:200]!r}"
        assert (
            "def " not in response
        ), f"Should not contain function definitions, got: {response[:200]!r}"


@pytest.mark.llm_e2e
class TestLengthConstraints:
    """LLM should respect length constraints."""

    async def test_answer_in_ten_words(self, bare_llm_client, e2e_timeout):
        """User asks for a very short answer."""
        messages = [
            Message(
                role="user", content=("What is the capital of France? Answer in 5 words or fewer.")
            ),
        ]
        response = await asyncio.wait_for(
            _chat(bare_llm_client, messages),
            timeout=e2e_timeout,
        )
        word_count = len(response.strip().split())
        assert (
            word_count <= 8
        ), f"Expected <= 8 words, got {word_count}: {response!r}"  # allow 3-word margin
