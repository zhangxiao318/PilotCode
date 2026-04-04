"""Tests for token counting and auto-compact."""

import pytest

from pilotcode.query_engine import QueryEngine, QueryEngineConfig
from pilotcode.types.message import UserMessage, AssistantMessage


class TestTokenCounting:
    def test_count_tokens_empty(self):
        engine = QueryEngine(QueryEngineConfig(cwd="."))
        assert engine.count_tokens() == 0

    def test_count_tokens_with_messages(self):
        engine = QueryEngine(QueryEngineConfig(cwd="."))
        # 4 chars ~ 1 token
        engine.messages.append(UserMessage(content="Hello world"))  # 11 chars
        engine.messages.append(AssistantMessage(content="Hi there"))  # 8 chars
        assert engine.count_tokens() == 19 // 4  # 4

    def test_count_tokens_approximation(self):
        engine = QueryEngine(QueryEngineConfig(cwd="."))
        text = "A" * 100
        engine.messages.append(UserMessage(content=text))
        assert engine.count_tokens() == 25


class TestAutoCompact:
    def test_auto_compact_not_triggered_when_disabled(self):
        engine = QueryEngine(QueryEngineConfig(cwd=".", auto_compact=False, max_tokens=10))
        for i in range(10):
            engine.messages.append(UserMessage(content=f"Message {i}"))
        compacted = engine.auto_compact_if_needed()
        assert compacted is False
        assert len(engine.messages) == 10

    def test_auto_compact_triggered_when_over_limit(self):
        engine = QueryEngine(QueryEngineConfig(cwd=".", auto_compact=True, max_tokens=1))
        # Add many messages to exceed token limit
        for i in range(10):
            engine.messages.append(UserMessage(content=f"This is a longer message number {i} with many tokens"))
        compacted = engine.auto_compact_if_needed()
        assert compacted is True
        # Should keep fewer messages after compaction
        assert len(engine.messages) < 10
