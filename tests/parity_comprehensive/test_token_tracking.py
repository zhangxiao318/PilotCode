"""Tests for token counting and auto-compact."""

from pilotcode.query_engine import QueryEngine, QueryEngineConfig
from pilotcode.types.message import UserMessage, AssistantMessage


class TestTokenCounting:
    def test_count_tokens_empty(self):
        engine = QueryEngine(QueryEngineConfig(cwd="."))
        # count_tokens now includes system prompt + tools, so it's > 0 even with no messages
        assert engine.count_tokens() > 0

    def test_count_tokens_with_messages(self):
        engine = QueryEngine(QueryEngineConfig(cwd="."))
        # Uses TokenEstimator which uses weighted combination
        engine.messages.append(UserMessage(content="Hello world"))  # 11 chars
        engine.messages.append(AssistantMessage(content="Hi there"))  # 8 chars
        tokens = engine.count_tokens()
        assert tokens > 0
        # TokenEstimator uses weighted algorithm, result varies

    def test_count_tokens_approximation(self):
        engine = QueryEngine(QueryEngineConfig(cwd="."))
        text = "A" * 100
        engine.messages.append(UserMessage(content=text))
        tokens = engine.count_tokens()
        # TokenEstimator uses weighted combination; includes system prompt + tools overhead
        assert tokens > 0
        # System prompt + tools is ~1800 tokens; 100 chars "A" is ~25 tokens
        assert tokens > 1000


class TestAutoCompact:
    def test_auto_compact_not_triggered_when_disabled(self):
        engine = QueryEngine(QueryEngineConfig(cwd=".", auto_compact=False, context_window=10))
        for i in range(10):
            engine.messages.append(UserMessage(content=f"Message {i}"))
        compacted = engine.auto_compact_if_needed()
        assert compacted is False
        assert len(engine.messages) == 10

    def test_auto_compact_triggered_when_over_limit(self):
        engine = QueryEngine(QueryEngineConfig(cwd=".", auto_compact=True, context_window=1))
        # Add many messages to exceed token limit
        for i in range(10):
            engine.messages.append(
                UserMessage(content=f"This is a longer message number {i} with many tokens")
            )
        compacted = engine.auto_compact_if_needed()
        assert compacted is True
        # Should keep fewer messages after compaction
        assert len(engine.messages) < 10
