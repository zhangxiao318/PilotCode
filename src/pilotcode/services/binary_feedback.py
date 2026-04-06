"""Binary Feedback mechanism for testing prompt stability.

This module implements Claude Code's binary feedback mechanism for testing
prompt stability. It sends two identical requests to the model and compares
the structured outputs (tool_use) to detect if the model is uncertain about
the response.

Original use case (from Claude Code):
- Only enabled when USER_TYPE === 'ant' (internal Anthropic testing)
- Used to identify prompts that need improvement
- Structured data (tool_use) comparison is more reliable than text comparison
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, AsyncIterator, Callable
import json
import os


class FeedbackResult(Enum):
    """Result of binary feedback comparison."""

    IDENTICAL = "identical"  # Both responses are exactly the same
    FUNCTIONALLY_SAME = "functional"  # Tool calls match, minor differences
    DIFFERENT = "different"  # Significant differences detected
    ERROR = "error"  # Error during comparison


class StabilityLevel(Enum):
    """Prompt stability assessment."""

    STABLE = "stable"  # Consistent responses
    UNSTABLE = "unstable"  # Variable responses, prompt needs work
    UNCERTAIN = "uncertain"  # Inconclusive result


@dataclass
class BinaryFeedbackAnalysis:
    """Analysis result from binary feedback."""

    result: FeedbackResult
    stability: StabilityLevel
    m1_response: dict[str, Any]
    m2_response: dict[str, Any]
    differences: list[str] = field(default_factory=list)
    tool_calls_match: bool = False
    text_content_similar: bool = False
    recommendation: str = ""


def _extract_tool_calls(response: dict[str, Any]) -> list[dict[str, Any]]:
    """Extract tool calls from response.

    Tool calls are more stable for comparison than text content.
    """
    tool_calls = []

    # Check for choices with tool_calls
    choices = response.get("choices", [])
    if not choices:
        return tool_calls

    message = choices[0].get("message", {})

    # Extract tool_calls
    if "tool_calls" in message:
        for tc in message["tool_calls"]:
            tool_calls.append(
                {
                    "id": tc.get("id", ""),
                    "name": tc.get("function", {}).get("name", ""),
                    "arguments": tc.get("function", {}).get("arguments", "{}"),
                }
            )

    # Also check for tool_use in content (Anthropic format)
    content = message.get("content", [])
    if isinstance(content, list):
        for block in content:
            if isinstance(block, dict) and block.get("type") == "tool_use":
                tool_calls.append(
                    {
                        "id": block.get("id", ""),
                        "name": block.get("name", ""),
                        "arguments": json.dumps(block.get("input", {})),
                    }
                )

    return tool_calls


def _extract_text_content(response: dict[str, Any]) -> str:
    """Extract text content from response."""
    choices = response.get("choices", [])
    if not choices:
        return ""

    message = choices[0].get("message", {})
    content = message.get("content", "")

    # Handle list content (Anthropic format)
    if isinstance(content, list):
        texts = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                texts.append(block.get("text", ""))
        content = " ".join(texts)

    return str(content).strip()


def _compare_tool_calls(
    tc1: list[dict[str, Any]], tc2: list[dict[str, Any]]
) -> tuple[bool, list[str]]:
    """Compare two sets of tool calls.

    Returns:
        (match, differences)
    """
    differences = []

    # Check count
    if len(tc1) != len(tc2):
        differences.append(f"Tool call count differs: {len(tc1)} vs {len(tc2)}")
        return False, differences

    if len(tc1) == 0:
        return True, differences

    # Compare each tool call
    for i, (t1, t2) in enumerate(zip(tc1, tc2)):
        # Compare name
        if t1.get("name") != t2.get("name"):
            differences.append(f"Tool {i}: name differs '{t1.get('name')}' vs '{t2.get('name')}'")
            continue

        # Compare arguments (parse JSON for normalization)
        try:
            args1 = json.loads(t1.get("arguments", "{}"))
            args2 = json.loads(t2.get("arguments", "{}"))
            if args1 != args2:
                differences.append(f"Tool {i}: arguments differ")
        except json.JSONDecodeError:
            # If not valid JSON, compare as strings
            if t1.get("arguments") != t2.get("arguments"):
                differences.append(f"Tool {i}: arguments differ (raw)")

    return len(differences) == 0, differences


def _calculate_text_similarity(text1: str, text2: str) -> float:
    """Calculate similarity between two texts (0.0 to 1.0).

    Uses a simple word-based Jaccard similarity.
    """
    if not text1 and not text2:
        return 1.0
    if not text1 or not text2:
        return 0.0

    # Normalize and tokenize
    words1 = set(text1.lower().split())
    words2 = set(text2.lower().split())

    if not words1 and not words2:
        return 1.0

    # Jaccard similarity
    intersection = len(words1 & words2)
    union = len(words1 | words2)

    return intersection / union if union > 0 else 0.0


def analyze_binary_feedback(
    m1_response: dict[str, Any], m2_response: dict[str, Any], text_similarity_threshold: float = 0.8
) -> BinaryFeedbackAnalysis:
    """Analyze two responses for binary feedback.

    Args:
        m1_response: First model response
        m2_response: Second model response
        text_similarity_threshold: Threshold for considering text similar

    Returns:
        BinaryFeedbackAnalysis with comparison results
    """
    differences = []

    # Extract tool calls (primary comparison)
    tc1 = _extract_tool_calls(m1_response)
    tc2 = _extract_tool_calls(m2_response)

    tool_calls_match, tc_diffs = _compare_tool_calls(tc1, tc2)
    differences.extend(tc_diffs)

    # If no tool calls, compare text content
    text1 = _extract_text_content(m1_response)
    text2 = _extract_text_content(m2_response)

    text_similarity = _calculate_text_similarity(text1, text2)
    text_content_similar = text_similarity >= text_similarity_threshold

    if not tc1 and not tc2:
        # No tool calls - rely on text comparison
        if text_content_similar:
            result = (
                FeedbackResult.IDENTICAL
                if text_similarity > 0.95
                else FeedbackResult.FUNCTIONALLY_SAME
            )
            stability = StabilityLevel.STABLE
        else:
            result = FeedbackResult.DIFFERENT
            stability = StabilityLevel.UNSTABLE
            differences.append(f"Text similarity: {text_similarity:.2%}")
    else:
        # Have tool calls - prioritize tool comparison
        if tool_calls_match:
            result = FeedbackResult.IDENTICAL
            stability = StabilityLevel.STABLE
        else:
            result = FeedbackResult.DIFFERENT
            stability = StabilityLevel.UNSTABLE

    # Generate recommendation
    if stability == StabilityLevel.STABLE:
        recommendation = "Prompt is stable - model produces consistent outputs"
    elif stability == StabilityLevel.UNSTABLE:
        recommendation = "Prompt may need improvement - model produces variable outputs"
    else:
        recommendation = "Inconclusive - manual review recommended"

    return BinaryFeedbackAnalysis(
        result=result,
        stability=stability,
        m1_response=m1_response,
        m2_response=m2_response,
        differences=differences,
        tool_calls_match=tool_calls_match,
        text_content_similar=text_content_similar,
        recommendation=recommendation,
    )


class BinaryFeedbackTester:
    """Tester for binary feedback mechanism."""

    def __init__(self, enabled: bool | None = None, text_similarity_threshold: float = 0.8):
        """Initialize binary feedback tester.

        Args:
            enabled: Whether binary feedback is enabled. If None, checks
                    PILOTCODE_BINARY_FEEDBACK env var.
            text_similarity_threshold: Threshold for text similarity
        """
        if enabled is None:
            # Check environment variable (like Claude Code's USER_TYPE === 'ant')
            enabled = os.environ.get("PILOTCODE_BINARY_FEEDBACK", "").lower() in (
                "1",
                "true",
                "yes",
            )

        self.enabled = enabled
        self.text_similarity_threshold = text_similarity_threshold
        self._history: list[BinaryFeedbackAnalysis] = []

    async def test_prompt(
        self, query_fn: Callable[[], AsyncIterator[dict[str, Any]]], num_runs: int = 2
    ) -> BinaryFeedbackAnalysis | None:
        """Test a prompt with binary feedback.

        Args:
            query_fn: Async function that yields model responses
            num_runs: Number of times to run (default 2 for binary)

        Returns:
            Analysis result or None if disabled
        """
        if not self.enabled:
            return None

        if num_runs < 2:
            raise ValueError("Need at least 2 runs for binary feedback")

        # Collect responses
        responses = []
        for _ in range(num_runs):
            response_parts = []
            async for part in query_fn():
                response_parts.append(part)

            # Combine parts into full response
            if response_parts:
                # Assume last part is complete response
                responses.append(response_parts[-1])

        if len(responses) < 2:
            return BinaryFeedbackAnalysis(
                result=FeedbackResult.ERROR,
                stability=StabilityLevel.UNCERTAIN,
                m1_response={},
                m2_response={},
                differences=["Insufficient responses collected"],
                recommendation="Error during binary feedback test",
            )

        # Analyze
        analysis = analyze_binary_feedback(
            responses[0], responses[1], self.text_similarity_threshold
        )

        self._history.append(analysis)
        return analysis

    async def test_prompt_simple(
        self, messages: list[dict[str, Any]], client, model: str | None = None
    ) -> BinaryFeedbackAnalysis | None:
        """Test a prompt using a model client.

        Args:
            messages: Messages to send
            client: Model client with chat_completion method
            model: Optional model override

        Returns:
            Analysis result or None if disabled
        """
        if not self.enabled:
            return None

        async def query_fn():
            response = await client.chat_completion(messages=messages, model=model, stream=False)
            yield response

        return await self.test_prompt(query_fn)

    def get_history(self) -> list[BinaryFeedbackAnalysis]:
        """Get history of all binary feedback tests."""
        return self._history.copy()

    def get_stability_report(self) -> dict[str, Any]:
        """Get overall stability report."""
        if not self._history:
            return {"total_tests": 0, "stable_rate": 0.0, "status": "no_data"}

        stable_count = sum(1 for a in self._history if a.stability == StabilityLevel.STABLE)

        total = len(self._history)
        stable_rate = stable_count / total

        return {
            "total_tests": total,
            "stable_count": stable_count,
            "unstable_count": total - stable_count,
            "stable_rate": stable_rate,
            "status": "stable" if stable_rate > 0.8 else "needs_improvement",
        }

    def clear_history(self) -> None:
        """Clear test history."""
        self._history.clear()


# Global instance
_binary_feedback_tester: BinaryFeedbackTester | None = None


def get_binary_feedback_tester(enabled: bool | None = None) -> BinaryFeedbackTester:
    """Get global binary feedback tester."""
    global _binary_feedback_tester
    if _binary_feedback_tester is None:
        _binary_feedback_tester = BinaryFeedbackTester(enabled=enabled)
    return _binary_feedback_tester


def is_binary_feedback_enabled() -> bool:
    """Check if binary feedback is enabled."""
    return os.environ.get("PILOTCODE_BINARY_FEEDBACK", "").lower() in ("1", "true", "yes")
