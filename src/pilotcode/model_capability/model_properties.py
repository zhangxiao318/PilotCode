"""Model property detection benchmarks (informational, no scoring)."""

from __future__ import annotations

from typing import Any

from pilotcode.utils.model_client import get_model_client, Message

from .base import BenchmarkResult, BenchmarkConnectionError


async def test_reasoning_support() -> BenchmarkResult:
    """Detect whether the model emits reasoning/thinking content."""
    prompt = "What is 23 + 47? Explain your reasoning step by step."
    client = get_model_client()

    try:
        chunk = None
        async for c in client.chat_completion(
            messages=[Message(role="user", content=prompt)],
            temperature=0.3,
            stream=False,
        ):
            chunk = c

        if chunk is None:
            return BenchmarkResult(
                test_name="reasoning_support",
                dimension="properties",
                sub_dimension="reasoning",
                score=0.0,
                error="No response from model",
            )

        delta = chunk.get("choices", [{}])[0].get("delta", {})
        reasoning = delta.get("reasoning_content")
        content = delta.get("content", "")

        if reasoning:
            return BenchmarkResult(
                test_name="reasoning_support",
                dimension="properties",
                sub_dimension="reasoning",
                score=1.0,
                metadata={
                    "supported": True,
                    "reasoning_preview": reasoning[:200],
                    "content_preview": content[:100] if content else "",
                },
            )

        # Also check for <thinking> tags in content (some models inline thinking)
        has_inline_thinking = "<think>" in content or "<thinking>" in content
        return BenchmarkResult(
            test_name="reasoning_support",
            dimension="properties",
            sub_dimension="reasoning",
            score=1.0,
            metadata={
                "supported": False,
                "inline_thinking_tags": has_inline_thinking,
                "content_preview": content[:200] if content else "",
            },
        )

    except Exception as e:
        from .base import _is_connection_error

        if _is_connection_error(e):
            raise BenchmarkConnectionError(str(e)) from e
        return BenchmarkResult(
            test_name="reasoning_support",
            dimension="properties",
            sub_dimension="reasoning",
            score=0.0,
            error=str(e),
        )


async def test_token_accuracy() -> BenchmarkResult:
    """Detect whether the API returns accurate token usage."""
    prompt = "Hello, world!"
    client = get_model_client()

    try:
        chunk = None
        async for c in client.chat_completion(
            messages=[Message(role="user", content=prompt)],
            temperature=0.0,
            stream=False,
        ):
            chunk = c

        if chunk is None:
            return BenchmarkResult(
                test_name="token_accuracy",
                dimension="properties",
                sub_dimension="token_usage",
                score=0.0,
                error="No response from model",
            )

        usage = chunk.get("usage")
        if not usage:
            return BenchmarkResult(
                test_name="token_accuracy",
                dimension="properties",
                sub_dimension="token_usage",
                score=1.0,
                metadata={
                    "usage_available": False,
                    "note": "API did not return usage field",
                },
            )

        prompt_tokens = usage.get("prompt_tokens")
        completion_tokens = usage.get("completion_tokens")
        total_tokens = usage.get("total_tokens")

        # Try local heuristic count for comparison
        local_prompt_estimate = len(prompt.split())  # very rough

        return BenchmarkResult(
            test_name="token_accuracy",
            dimension="properties",
            sub_dimension="token_usage",
            score=1.0,
            metadata={
                "usage_available": True,
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": total_tokens,
                "local_word_estimate": local_prompt_estimate,
                "note": (
                    f"prompt={prompt_tokens}, completion={completion_tokens}, total={total_tokens}"
                    if prompt_tokens is not None and completion_tokens is not None
                    else "Partial usage data"
                ),
            },
        )

    except Exception as e:
        from .base import _is_connection_error

        if _is_connection_error(e):
            raise BenchmarkConnectionError(str(e)) from e
        return BenchmarkResult(
            test_name="token_accuracy",
            dimension="properties",
            sub_dimension="token_usage",
            score=0.0,
            error=str(e),
        )
