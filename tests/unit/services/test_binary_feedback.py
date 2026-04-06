"""Tests for binary feedback mechanism."""

import pytest
from unittest.mock import AsyncMock, patch

from pilotcode.services.binary_feedback import (
    BinaryFeedbackTester,
    BinaryFeedbackAnalysis,
    FeedbackResult,
    StabilityLevel,
    analyze_binary_feedback,
    get_binary_feedback_tester,
    is_binary_feedback_enabled,
    _extract_tool_calls,
    _extract_text_content,
    _compare_tool_calls,
    _calculate_text_similarity,
)


class TestFeedbackResult:
    """Tests for FeedbackResult enum."""

    def test_enum_values(self):
        """Test enum values."""
        assert FeedbackResult.IDENTICAL.value == "identical"
        assert FeedbackResult.DIFFERENT.value == "different"
        assert FeedbackResult.ERROR.value == "error"


class TestStabilityLevel:
    """Tests for StabilityLevel enum."""

    def test_enum_values(self):
        """Test enum values."""
        assert StabilityLevel.STABLE.value == "stable"
        assert StabilityLevel.UNSTABLE.value == "unstable"


class TestExtractToolCalls:
    """Tests for tool call extraction."""

    def test_extract_from_openai_format(self):
        """Test extracting tool calls from OpenAI format."""
        response = {
            "choices": [
                {
                    "message": {
                        "tool_calls": [
                            {
                                "id": "call_1",
                                "function": {"name": "test_tool", "arguments": '{"key": "value"}'},
                            }
                        ]
                    }
                }
            ]
        }

        calls = _extract_tool_calls(response)
        assert len(calls) == 1
        assert calls[0]["name"] == "test_tool"
        assert calls[0]["arguments"] == '{"key": "value"}'

    def test_extract_from_anthropic_format(self):
        """Test extracting tool calls from Anthropic format."""
        response = {
            "choices": [
                {
                    "message": {
                        "content": [
                            {
                                "type": "tool_use",
                                "id": "call_1",
                                "name": "test_tool",
                                "input": {"key": "value"},
                            }
                        ]
                    }
                }
            ]
        }

        calls = _extract_tool_calls(response)
        assert len(calls) == 1
        assert calls[0]["name"] == "test_tool"

    def test_empty_response(self):
        """Test extracting from empty response."""
        response = {}
        calls = _extract_tool_calls(response)
        assert calls == []


class TestExtractTextContent:
    """Tests for text content extraction."""

    def test_extract_text(self):
        """Test extracting text content."""
        response = {"choices": [{"message": {"content": "Hello world"}}]}

        text = _extract_text_content(response)
        assert text == "Hello world"

    def test_extract_anthropic_list(self):
        """Test extracting from Anthropic list format."""
        response = {
            "choices": [
                {
                    "message": {
                        "content": [
                            {"type": "text", "text": "Hello"},
                            {"type": "text", "text": "world"},
                        ]
                    }
                }
            ]
        }

        text = _extract_text_content(response)
        assert "Hello" in text
        assert "world" in text


class TestCompareToolCalls:
    """Tests for tool call comparison."""

    def test_identical_calls(self):
        """Test comparing identical tool calls."""
        tc1 = [{"name": "tool1", "arguments": '{"a": 1}'}]
        tc2 = [{"name": "tool1", "arguments": '{"a": 1}'}]

        match, diffs = _compare_tool_calls(tc1, tc2)
        assert match is True
        assert diffs == []

    def test_different_count(self):
        """Test comparing different count of tool calls."""
        tc1 = [{"name": "tool1", "arguments": "{}"}]
        tc2 = []

        match, diffs = _compare_tool_calls(tc1, tc2)
        assert match is False
        assert len(diffs) > 0

    def test_different_name(self):
        """Test comparing tool calls with different names."""
        tc1 = [{"name": "tool1", "arguments": "{}"}]
        tc2 = [{"name": "tool2", "arguments": "{}"}]

        match, diffs = _compare_tool_calls(tc1, tc2)
        assert match is False
        assert any("name differs" in d for d in diffs)


class TestTextSimilarity:
    """Tests for text similarity calculation."""

    def test_identical_texts(self):
        """Test identical texts have 1.0 similarity."""
        sim = _calculate_text_similarity("hello world", "hello world")
        assert sim == 1.0

    def test_completely_different(self):
        """Test completely different texts have 0 similarity."""
        sim = _calculate_text_similarity("abc", "xyz")
        assert sim == 0.0

    def test_partial_similarity(self):
        """Test partial similarity."""
        sim = _calculate_text_similarity("hello world foo", "hello world bar")
        assert 0 < sim < 1

    def test_empty_texts(self):
        """Test empty texts."""
        assert _calculate_text_similarity("", "") == 1.0
        assert _calculate_text_similarity("hello", "") == 0.0


class TestAnalyzeBinaryFeedback:
    """Tests for binary feedback analysis."""

    def test_identical_responses(self):
        """Test analyzing identical responses."""
        response = {"choices": [{"message": {"content": "Hello"}}]}

        analysis = analyze_binary_feedback(response, response)

        assert analysis.result == FeedbackResult.IDENTICAL
        assert analysis.stability == StabilityLevel.STABLE
        # tool_calls_match is True when both have no tool calls (matching state)
        assert analysis.tool_calls_match is True  # Both have no tool calls = match
        assert analysis.text_content_similar is True

    def test_different_text_responses(self):
        """Test analyzing different text responses."""
        r1 = {"choices": [{"message": {"content": "Hello world foo"}}]}
        r2 = {"choices": [{"message": {"content": "Goodbye world bar"}}]}

        analysis = analyze_binary_feedback(r1, r2, text_similarity_threshold=0.9)

        assert analysis.result == FeedbackResult.DIFFERENT
        assert analysis.stability == StabilityLevel.UNSTABLE

    def test_matching_tool_calls(self):
        """Test analyzing matching tool calls."""
        r1 = {
            "choices": [
                {
                    "message": {
                        "tool_calls": [{"id": "1", "function": {"name": "test", "arguments": "{}"}}]
                    }
                }
            ]
        }
        r2 = {
            "choices": [
                {
                    "message": {
                        "tool_calls": [{"id": "2", "function": {"name": "test", "arguments": "{}"}}]
                    }
                }
            ]
        }

        analysis = analyze_binary_feedback(r1, r2)

        assert analysis.result == FeedbackResult.IDENTICAL
        assert analysis.stability == StabilityLevel.STABLE
        assert analysis.tool_calls_match is True

    def test_different_tool_calls(self):
        """Test analyzing different tool calls."""
        r1 = {
            "choices": [
                {
                    "message": {
                        "tool_calls": [
                            {"id": "1", "function": {"name": "tool1", "arguments": "{}"}}
                        ]
                    }
                }
            ]
        }
        r2 = {
            "choices": [
                {
                    "message": {
                        "tool_calls": [
                            {"id": "2", "function": {"name": "tool2", "arguments": "{}"}}
                        ]
                    }
                }
            ]
        }

        analysis = analyze_binary_feedback(r1, r2)

        assert analysis.result == FeedbackResult.DIFFERENT
        assert analysis.stability == StabilityLevel.UNSTABLE
        assert analysis.tool_calls_match is False


class TestBinaryFeedbackTester:
    """Tests for BinaryFeedbackTester."""

    def test_disabled_by_default(self):
        """Test that tester is disabled by default."""
        tester = BinaryFeedbackTester(enabled=False)
        assert tester.enabled is False

    def test_enabled_via_env(self, monkeypatch):
        """Test enabling via environment variable."""
        monkeypatch.setenv("PILOTCODE_BINARY_FEEDBACK", "1")
        tester = BinaryFeedbackTester()
        assert tester.enabled is True

    @pytest.mark.asyncio
    async def test_test_prompt_disabled(self):
        """Test that test_prompt returns None when disabled."""
        tester = BinaryFeedbackTester(enabled=False)

        async def mock_query():
            yield {"response": "test"}

        result = await tester.test_prompt(mock_query)
        assert result is None

    @pytest.mark.asyncio
    async def test_test_prompt_error(self):
        """Test test_prompt with insufficient responses - should raise ValueError."""
        tester = BinaryFeedbackTester(enabled=True)

        async def mock_query():
            yield {"response": "test"}

        with pytest.raises(ValueError, match="Need at least 2 runs"):
            await tester.test_prompt(mock_query, num_runs=1)

    def test_get_stability_report_empty(self):
        """Test stability report with no history."""
        tester = BinaryFeedbackTester(enabled=True)
        report = tester.get_stability_report()

        assert report["total_tests"] == 0
        assert report["status"] == "no_data"

    def test_clear_history(self):
        """Test clearing history."""
        tester = BinaryFeedbackTester(enabled=True)
        tester._history.append(
            BinaryFeedbackAnalysis(
                result=FeedbackResult.IDENTICAL,
                stability=StabilityLevel.STABLE,
                m1_response={},
                m2_response={},
            )
        )

        tester.clear_history()
        assert len(tester._history) == 0


class TestGlobalFunctions:
    """Tests for global functions."""

    def test_get_binary_feedback_tester(self):
        """Test getting global tester."""
        tester1 = get_binary_feedback_tester()
        tester2 = get_binary_feedback_tester()
        assert tester1 is tester2

    def test_is_binary_feedback_enabled_default(self):
        """Test default state of binary feedback."""
        assert is_binary_feedback_enabled() is False

    def test_is_binary_feedback_enabled_with_env(self, monkeypatch):
        """Test binary feedback enabled with env var."""
        monkeypatch.setenv("PILOTCODE_BINARY_FEEDBACK", "true")
        assert is_binary_feedback_enabled() is True

        monkeypatch.setenv("PILOTCODE_BINARY_FEEDBACK", "1")
        assert is_binary_feedback_enabled() is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
