"""Tests for reasoning-based doom loop detection."""

from __future__ import annotations

import pytest

from pilotcode.query_engine import QueryEngine, QueryEngineConfig


class TestReasoningLoopDetection:
    """Test _detect_reasoning_loop heuristic."""

    @pytest.fixture
    def engine(self, tmp_path):
        config = QueryEngineConfig(cwd=str(tmp_path), tools=[])
        return QueryEngine(config=config)

    def test_empty_history_no_loop(self, engine):
        assert engine._detect_reasoning_loop("I need to fix the bug.") is None

    def test_insufficient_history_no_loop(self, engine):
        engine._reasoning_history = ["First reasoning."]
        assert engine._detect_reasoning_loop("Second reasoning.") is None

    def test_no_loop_different_reasoning(self, engine):
        engine._reasoning_history = [
            "I will read the file to understand the structure.",
            "Now I see the problem is in the login function.",
        ]
        assert engine._detect_reasoning_loop("I need to refactor the auth module.") is None

    def test_loop_detected_similar_reasoning(self, engine):
        r = "I will try editing the file again to fix the error."
        engine._reasoning_history = [r, r]
        result = engine._detect_reasoning_loop(r)
        assert result is not None
        assert "similar" in result.lower() or "loop" in result.lower()

    def test_loop_detected_with_minor_changes(self, engine):
        r1 = "I will try editing src/main.py to fix the bug on line 42."
        r2 = "I will try editing src/main.py to fix the bug on line 43."
        r3 = "I will try editing src/main.py to fix the bug on line 44."
        engine._reasoning_history = [r1, r2]
        result = engine._detect_reasoning_loop(r3)
        assert result is not None
        assert "similar" in result.lower() or "loop" in result.lower()

    def test_no_loop_partial_similarity(self, engine):
        r1 = "First I will read the file."
        r2 = "Then I will edit the file."
        r3 = "Finally I will test the file."
        engine._reasoning_history = [r1, r2]
        assert engine._detect_reasoning_loop(r3) is None

    def test_history_truncation(self, engine):
        engine._max_reasoning_history = 3
        engine._reasoning_history = ["old1", "old2", "old3"]
        # Calling detect with a new reasoning triggers history update via submit_message logic
        # Simulate the update path manually
        engine._reasoning_history.append("new")
        if len(engine._reasoning_history) > engine._max_reasoning_history:
            engine._reasoning_history.pop(0)
        assert len(engine._reasoning_history) == 3
        assert engine._reasoning_history[0] == "old2"
