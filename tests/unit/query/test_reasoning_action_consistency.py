"""Tests for reasoning-action consistency check."""

from __future__ import annotations

import pytest

from pilotcode.query_engine import QueryEngine, QueryEngineConfig


class TestReasoningActionConsistency:
    """Test _check_reasoning_action_consistency heuristic."""

    @pytest.fixture
    def engine(self, tmp_path):
        config = QueryEngineConfig(cwd=str(tmp_path), tools=[])
        return QueryEngine(config=config)

    def test_no_files_in_reasoning(self, engine):
        reasoning = "I need to understand the problem first."
        tool_calls = {}
        assert engine._check_reasoning_action_consistency(reasoning, tool_calls) is None

    def test_matched_files(self, engine):
        reasoning = "I will edit src/main.py to fix the bug."
        tool_calls = {
            0: {
                "id": "tc_1",
                "name": "FileEdit",
                "arguments": '{"file_path": "src/main.py", "old_string": "x", "new_string": "y"}',
            }
        }
        assert engine._check_reasoning_action_consistency(reasoning, tool_calls) is None

    def test_missed_file(self, engine):
        reasoning = "I will edit src/main.py and src/utils.py to fix the bug."
        tool_calls = {
            0: {
                "id": "tc_1",
                "name": "FileEdit",
                "arguments": '{"file_path": "src/main.py", "old_string": "x", "new_string": "y"}',
            }
        }
        result = engine._check_reasoning_action_consistency(reasoning, tool_calls)
        assert result is not None
        assert "src/utils.py" in result

    def test_multiple_missed_files_truncated(self, engine):
        reasoning = "I will edit a.py, b.py, c.py, d.py, e.py."
        tool_calls = {
            0: {
                "id": "tc_1",
                "name": "FileEdit",
                "arguments": '{"file_path": "a.py", "old_string": "x", "new_string": "y"}',
            }
        }
        result = engine._check_reasoning_action_consistency(reasoning, tool_calls)
        assert result is not None
        # 4 missed files (b,c,d,e), show first 3, so (+1 more)
        assert "+1 more" in result

    def test_chinese_reasoning(self, engine):
        reasoning = "我需要修改 src/main.py 和 src/config.py 来处理这个问题。"
        tool_calls = {
            0: {
                "id": "tc_1",
                "name": "FileEdit",
                "arguments": '{"file_path": "src/main.py", "old_string": "x", "new_string": "y"}',
            }
        }
        result = engine._check_reasoning_action_consistency(reasoning, tool_calls)
        assert result is not None
        assert "src/config.py" in result

    def test_no_tool_calls(self, engine):
        reasoning = "I will edit src/main.py."
        tool_calls = {}
        result = engine._check_reasoning_action_consistency(reasoning, tool_calls)
        assert result is not None
        assert "src/main.py" in result
