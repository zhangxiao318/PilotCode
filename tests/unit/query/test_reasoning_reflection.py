"""Tests for low-cost reasoning reflection."""

from __future__ import annotations

import pytest

from pilotcode.query_engine import QueryEngine, QueryEngineConfig


class TestReasoningReflection:
    """Test _reflect_on_reasoning heuristic rules."""

    @pytest.fixture
    def engine(self, tmp_path):
        config = QueryEngineConfig(cwd=str(tmp_path), tools=[])
        return QueryEngine(config=config)

    def test_no_defects(self, engine):
        reasoning = "I analyzed the code and found the bug is in the auth module."
        assert engine._reflect_on_reasoning(reasoning) is None

    def test_guess_without_verification(self, engine):
        reasoning = "I guess the problem is in the database layer. Let me fix it."
        result = engine._reflect_on_reasoning(reasoning)
        assert result is not None
        assert "guess" in result.lower() or "verify" in result.lower()

    def test_guess_with_verification_ok(self, engine):
        reasoning = (
            "I guess the problem is in the database layer. I will verify this by checking the logs."
        )
        assert engine._reflect_on_reasoning(reasoning) is None

    def test_retry_loop(self, engine):
        reasoning = "Let me try again. I will retry the edit. Try again with a different approach."
        result = engine._reflect_on_reasoning(reasoning)
        assert result is not None
        assert "retry" in result.lower() or "retried" in result.lower()

    def test_fix_without_root_cause(self, engine):
        reasoning = "I will fix the bug by changing the return value."
        result = engine._reflect_on_reasoning(reasoning)
        assert result is not None
        assert "root cause" in result.lower()

    def test_fix_with_root_cause_ok(self, engine):
        reasoning = "The root cause is a null pointer. I will fix it by adding a check."
        assert engine._reflect_on_reasoning(reasoning) is None

    def test_multiple_defects_truncated(self, engine):
        reasoning = (
            "I guess the problem. Let me try again. Retry. Try again. "
            "I will fix it directly without analysis."
        )
        result = engine._reflect_on_reasoning(reasoning)
        assert result is not None
        # Should contain at most 3 defects (check line count)
        lines = [line for line in result.split("\n") if line.strip() and line.strip()[0].isdigit()]
        assert len(lines) <= 3

    def test_chinese_guess_without_verify(self, engine):
        reasoning = "我猜测问题在数据库层。直接修改代码试试。"
        result = engine._reflect_on_reasoning(reasoning)
        assert result is not None
        assert "验证" in result or "verify" in result.lower()
