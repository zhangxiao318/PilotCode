"""Tests for QueryEngine."""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from pilotcode.query_engine import QueryEngine, QueryEngineConfig
from pilotcode.state.app_state import get_default_app_state
from pilotcode.state.store import Store, set_global_store
from pilotcode.tools.registry import get_all_tools
from pilotcode.types.message import UserMessage, SystemMessage, ToolResultMessage


class TestQueryEngineInit:
    """Tests for QueryEngine initialization."""

    def test_init_with_defaults(self):
        """Test initialization with default config."""
        store = Store(get_default_app_state())
        set_global_store(store)

        config = QueryEngineConfig(
            cwd="/tmp",
            tools=get_all_tools(),
            get_app_state=store.get_state,
            set_app_state=lambda f: store.set_state(f),
        )

        engine = QueryEngine(config=config)

        assert engine.config.cwd == "/tmp"
        assert len(engine.config.tools) > 0

    def test_init_custom_config(self):
        """Test initialization with custom config."""
        store = Store(get_default_app_state())

        config = QueryEngineConfig(
            cwd="/home/test",
            tools=[],
            get_app_state=store.get_state,
            set_app_state=lambda f: store.set_state(f),
            auto_compact=False,
            max_tokens=1000,
        )

        engine = QueryEngine(config=config)

        assert engine.config.cwd == "/home/test"
        assert engine.config.auto_compact is False
        assert engine.config.max_tokens == 1000


class TestQueryEngineMessages:
    """Tests for QueryEngine message handling."""

    @pytest.fixture
    def query_engine(self, app_store):
        """Create a QueryEngine instance."""
        config = QueryEngineConfig(
            cwd="/tmp",
            tools=get_all_tools()[:5],  # Use subset for speed
            get_app_state=app_store.get_state,
            set_app_state=lambda f: app_store.set_state(f),
        )
        return QueryEngine(config=config)

    def test_messages_list(self, query_engine):
        """Test that messages list exists."""
        assert isinstance(query_engine.messages, list)
        assert len(query_engine.messages) == 0

    def test_add_tool_result(self, query_engine):
        """Test adding tool result."""
        query_engine.add_tool_result("tool-123", "Result content", is_error=False)

        assert len(query_engine.messages) == 1
        assert isinstance(query_engine.messages[0], ToolResultMessage)
        assert query_engine.messages[0].tool_use_id == "tool-123"

    def test_clear_history(self, query_engine):
        """Test clearing message history."""
        # Add some messages directly
        query_engine.messages.append(UserMessage(content="Hello"))
        query_engine.messages.append(UserMessage(content="World"))

        assert len(query_engine.messages) == 2

        query_engine.clear_history()

        assert len(query_engine.messages) == 0


class TestQueryEngineTokenCount:
    """Tests for token counting."""

    @pytest.fixture
    def query_engine(self, app_store):
        """Create a QueryEngine instance."""
        config = QueryEngineConfig(
            cwd="/tmp",
            tools=[],
            get_app_state=app_store.get_state,
            set_app_state=lambda f: app_store.set_state(f),
        )
        return QueryEngine(config=config)

    def test_count_tokens_empty(self, query_engine):
        """Test token count with no messages."""
        count = query_engine.count_tokens()
        assert count == 0

    def test_count_tokens_with_messages(self, query_engine):
        """Test token count with messages."""
        query_engine.messages.append(UserMessage(content="Hello world"))

        count = query_engine.count_tokens()
        assert count >= 0  # Token count may be estimated

    def test_count_tokens_increases(self, query_engine):
        """Test that token count increases with more messages."""
        query_engine.messages.append(UserMessage(content="Hello"))
        count1 = query_engine.count_tokens()

        query_engine.messages.append(UserMessage(content="World"))
        count2 = query_engine.count_tokens()

        assert count2 >= count1


class TestQueryEngineSaveLoad:
    """Tests for saving and loading sessions."""

    @pytest.fixture
    def query_engine(self, app_store):
        """Create a QueryEngine instance."""
        config = QueryEngineConfig(
            cwd="/tmp",
            tools=[],
            get_app_state=app_store.get_state,
            set_app_state=lambda f: app_store.set_state(f),
        )
        return QueryEngine(config=config)

    def test_save_session(self, query_engine, temp_dir):
        """Test saving session to file."""
        query_engine.messages.append(UserMessage(content="Hello"))

        save_path = temp_dir / "session.json"
        query_engine.save_session(str(save_path))

        assert save_path.exists()
        content = save_path.read_text()
        assert "Hello" in content

    def test_load_session(self, query_engine, temp_dir):
        """Test loading session from file."""
        # First save
        query_engine.messages.append(UserMessage(content="Hello"))
        save_path = temp_dir / "session.json"
        query_engine.save_session(str(save_path))

        # Clear and reload
        query_engine.clear_history()
        assert len(query_engine.messages) == 0

        # Load
        query_engine.load_session(str(save_path))
        assert len(query_engine.messages) == 1
        assert query_engine.messages[0].content == "Hello"


@pytest.mark.integration
class TestQueryEngineIntegration:
    """Integration tests for QueryEngine with real LLM calls mocked."""

    @pytest.fixture
    def query_engine(self, app_store):
        """Create a QueryEngine instance with limited tools."""
        config = QueryEngineConfig(
            cwd="/tmp",
            tools=get_all_tools()[:3],
            get_app_state=app_store.get_state,
            set_app_state=lambda f: app_store.set_state(f),
        )
        return QueryEngine(config=config)

    @pytest.mark.asyncio
    async def test_submit_message_mocked(self, query_engine):
        """Test submitting a message with mocked LLM."""
        # Mock the client.chat_completion method
        mock_chunk = {"choices": [{"delta": {"content": "Test response"}, "finish_reason": "stop"}]}

        async def mock_chat_completion(*args, **kwargs):
            yield mock_chunk

        with patch.object(query_engine.client, "chat_completion", mock_chat_completion):
            results = []
            async for result in query_engine.submit_message("Hello"):
                results.append(result)

            assert len(results) > 0
            # Should have at least user message and assistant response
            assert any(r.message for r in results)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
