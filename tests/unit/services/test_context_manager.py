"""Tests for Context Manager service."""

import pytest
import tempfile
import os
from unittest.mock import MagicMock, patch

from pilotcode.services.context_manager import (
    ContextManager,
    ContextConfig,
    ContextMessage,
    ContextStats,
    ContextBudget,
    CompactStrategy,
    MessagePriority,
    get_context_manager,
    clear_context_manager,
    create_context_manager,
)


# Fixtures
@pytest.fixture
def basic_config():
    """Create basic context config."""
    return ContextConfig(
        max_tokens=1000,
        warning_threshold=0.8,
        critical_threshold=0.95,
        auto_compact=False,
    )


@pytest.fixture
def context_manager(basic_config):
    """Create a context manager."""
    return ContextManager(basic_config)


@pytest.fixture
def mock_token_estimator():
    """Create a mock token estimator."""

    def estimator(text: str) -> int:
        # Simple: 1 token per 4 characters
        return len(text) // 4 + 1

    return estimator


# Test ContextMessage
class TestContextMessage:
    """Test ContextMessage dataclass."""

    def test_message_creation(self):
        """Test creating a context message."""
        msg = ContextMessage(
            role="user",
            content="Hello",
            priority=MessagePriority.USER,
            tokens=10,
        )
        assert msg.role == "user"
        assert msg.content == "Hello"
        assert msg.priority == MessagePriority.USER
        assert msg.tokens == 10
        assert msg.id is not None
        assert msg.access_count == 0

    def test_message_touch(self):
        """Test touching a message updates access."""
        import time

        msg = ContextMessage(role="user", content="Hello")
        original_access = msg.last_access

        # Small delay to ensure time difference
        time.sleep(0.01)
        msg.touch()

        assert msg.access_count == 1
        assert msg.last_access >= original_access

    def test_message_to_dict(self):
        """Test message serialization."""
        msg = ContextMessage(
            role="user",
            content="Hello",
            priority=MessagePriority.USER,
            tokens=10,
        )

        data = msg.to_dict()

        assert data["role"] == "user"
        assert data["content"] == "Hello"
        assert data["priority"] == MessagePriority.USER.value
        assert data["tokens"] == 10

    def test_message_from_dict(self):
        """Test message deserialization."""
        data = {
            "role": "assistant",
            "content": "Hi",
            "priority": 5,
            "tokens": 5,
            "timestamp": 12345.0,
        }

        msg = ContextMessage.from_dict(data)

        assert msg.role == "assistant"
        assert msg.content == "Hi"
        assert msg.priority == MessagePriority.USER
        assert msg.tokens == 5


# Test ContextBudget
class TestContextBudget:
    """Test ContextBudget calculations."""

    def test_budget_limits(self):
        """Test budget limit calculations."""
        budget = ContextBudget(
            max_tokens=1000,
            warning_threshold=0.8,
            critical_threshold=0.95,
            reserved_tokens=100,
        )

        assert budget.warning_limit == 800
        assert budget.critical_limit == 950
        assert budget.available_tokens == 900


# Test ContextManager basic functionality
class TestContextManagerBasic:
    """Test basic ContextManager functionality."""

    def test_manager_creation(self, basic_config):
        """Test creating context manager."""
        manager = ContextManager(basic_config)

        assert manager.config == basic_config
        assert len(manager.messages) == 0
        assert manager.stats.total_tokens == 0

    def test_add_message(self, context_manager):
        """Test adding a message."""
        context_manager.set_token_estimator(lambda x: len(x))

        msg = context_manager.add_message("user", "Hello")

        assert msg.role == "user"
        assert msg.content == "Hello"
        assert len(context_manager.messages) == 1
        assert context_manager.stats.total_messages == 1

    def test_add_message_with_priority(self, context_manager):
        """Test adding message with specific priority."""
        msg = context_manager.add_message(
            "system", "System prompt", priority=MessagePriority.SYSTEM
        )

        assert msg.priority == MessagePriority.SYSTEM

    def test_default_priority(self, context_manager):
        """Test default priorities are assigned correctly."""
        user_msg = context_manager.add_message("user", "Hello")
        assistant_msg = context_manager.add_message("assistant", "Hi")
        system_msg = context_manager.add_message("system", "System")

        assert user_msg.priority == MessagePriority.USER
        assert assistant_msg.priority == MessagePriority.ASSISTANT
        assert system_msg.priority == MessagePriority.SYSTEM

    def test_get_messages(self, context_manager):
        """Test getting messages for API."""
        context_manager.add_message("user", "Hello")
        context_manager.add_message("assistant", "Hi")

        messages = context_manager.get_messages()

        assert len(messages) == 2
        assert messages[0]["role"] == "user"
        assert messages[1]["role"] == "assistant"

    def test_get_messages_with_limit(self, context_manager):
        """Test getting messages with limit."""
        for i in range(5):
            context_manager.add_message("user", f"Message {i}")

        messages = context_manager.get_messages(limit=3)

        assert len(messages) == 3

    def test_remove_message(self, context_manager):
        """Test removing a message by ID."""
        msg = context_manager.add_message("user", "Hello")

        result = context_manager.remove_message(msg.id)

        assert result is True
        assert len(context_manager.messages) == 0

    def test_remove_nonexistent_message(self, context_manager):
        """Test removing a non-existent message."""
        result = context_manager.remove_message("nonexistent-id")

        assert result is False

    def test_get_message(self, context_manager):
        """Test getting a specific message."""
        msg = context_manager.add_message("user", "Hello")

        retrieved = context_manager.get_message(msg.id)

        assert retrieved is not None
        assert retrieved.id == msg.id
        assert retrieved.access_count == 1  # Touch increments count


# Test token estimation
class TestTokenEstimation:
    """Test token estimation."""

    def test_custom_estimator(self, context_manager):
        """Test custom token estimator."""
        estimator = MagicMock(return_value=100)
        context_manager.set_token_estimator(estimator)

        msg = context_manager.add_message("user", "Hello")

        assert msg.tokens == 100
        estimator.assert_called_once_with("Hello")

    def test_default_estimator(self, context_manager):
        """Test default token estimator."""
        msg = context_manager.add_message("user", "Hello world!")

        # Default: len // 4 + 1 = 12 // 4 + 1 = 4
        assert msg.tokens == 4


# Test threshold detection
class TestThresholdDetection:
    """Test warning and critical threshold detection."""

    def test_warning_threshold(self, context_manager):
        """Test warning threshold detection."""
        # Warning at 800 tokens (80% of 1000)
        context_manager.set_token_estimator(lambda x: len(x) * 10)

        assert not context_manager.is_warning

        # Add message to reach warning threshold
        context_manager.add_message("user", "x" * 80)  # 800 tokens

        assert context_manager.is_warning

    def test_critical_threshold(self, context_manager):
        """Test critical threshold detection."""
        # Critical at 950 tokens (95% of 1000)
        context_manager.set_token_estimator(lambda x: len(x) * 10)

        assert not context_manager.is_critical

        # Add message to reach critical threshold
        context_manager.add_message("user", "x" * 95)  # 950 tokens

        assert context_manager.is_critical

    def test_usage_ratio(self, context_manager):
        """Test usage ratio calculation."""
        context_manager.set_token_estimator(lambda x: 500)

        context_manager.add_message("user", "Hello")

        assert context_manager.usage_ratio == 0.5


# Test compaction strategies
class TestCompactionStrategies:
    """Test context compaction strategies."""

    def test_fifo_compaction(self, context_manager):
        """Test FIFO compaction strategy."""
        context_manager.set_token_estimator(lambda x: 100)

        # Add more messages to ensure we have removable ones
        for i in range(10):
            context_manager.add_message("user", f"Message {i}")

        assert len(context_manager.messages) == 10
        initial_count = len(context_manager.messages)

        # Compact - should remove some messages
        removed = context_manager.compact(strategy=CompactStrategy.FIFO, target_ratio=0.3)

        # Should have removed some messages (preserves recent ones)
        assert len(removed) > 0
        assert len(context_manager.messages) < initial_count

    def test_priority_compaction(self, context_manager):
        """Test priority compaction strategy."""
        context_manager.set_token_estimator(lambda x: 100)

        # Add messages with different priorities (add more to ensure some get removed)
        context_manager.add_message("system", "System", priority=MessagePriority.SYSTEM)
        context_manager.add_message("user", "Low1", priority=MessagePriority.LOG)
        context_manager.add_message("user", "Low2", priority=MessagePriority.LOG)
        context_manager.add_message("user", "Normal", priority=MessagePriority.USER)
        context_manager.add_message(
            "assistant", "High", priority=MessagePriority.ASSISTANT_IMPORTANT
        )
        context_manager.add_message("user", "Extra", priority=MessagePriority.LOG)

        initial_count = len(context_manager.messages)

        # Compact
        removed = context_manager.compact(strategy=CompactStrategy.PRIORITY, target_ratio=0.3)

        # Should have removed some low priority messages
        assert len(removed) > 0
        removed_priorities = [m.priority for m in removed]
        assert MessagePriority.SYSTEM not in removed_priorities

    def test_lru_compaction(self, context_manager):
        """Test LRU compaction strategy."""
        context_manager.set_token_estimator(lambda x: 100)

        # Add more messages
        for i in range(10):
            context_manager.add_message("user", f"Message {i}")

        initial_count = len(context_manager.messages)

        # Access some messages
        context_manager.messages[-1].touch()
        context_manager.messages[-2].touch()

        # Compact
        removed = context_manager.compact(strategy=CompactStrategy.LRU, target_ratio=0.3)

        # Should remove some messages
        assert len(removed) > 0
        assert len(context_manager.messages) < initial_count

    def test_token_count_compaction(self, context_manager):
        """Test token count compaction strategy."""
        import time

        # Custom estimator that returns different sizes
        # Note: preserve_recent=2 means last 4 messages are protected
        # So we need more messages to ensure some can be removed
        sizes = [300, 250, 200, 150, 100, 80, 50]

        def estimator(text: str) -> int:
            return sizes.pop(0) if sizes else 100

        context_manager.set_token_estimator(estimator)

        # Add messages (7 messages, last 4 protected, first 3 removable)
        # Add small delay between messages to ensure unique IDs
        for i in range(7):
            context_manager.add_message("user", f"Message {i}")
            time.sleep(0.001)  # Ensure unique message IDs

        # Total tokens: 300+250+200+150+100+80+50 = 1130
        # Target with ratio 0.5 and max_tokens=1000: 500
        # Need to remove at least 630 tokens
        # Protected: last 4 = 150+100+80+50 = 380
        # Removable: first 3 = 300+250+200 = 750

        # Compact
        removed = context_manager.compact(strategy=CompactStrategy.TOKEN_COUNT, target_ratio=0.5)

        # Should remove largest messages (300, then 250, then check if enough)
        assert len(removed) > 0
        # Verify that largest messages were removed first
        removed_tokens = [m.tokens for m in removed]
        assert 300 in removed_tokens  # Largest should be removed


# Test callbacks
class TestCallbacks:
    """Test callback functionality."""

    def test_compact_callback(self, context_manager):
        """Test compact callback is called."""
        callback = MagicMock()
        context_manager.set_compact_callback(callback)
        context_manager.set_token_estimator(lambda x: 100)

        # Add more messages to ensure some get removed
        for i in range(10):
            context_manager.add_message("user", f"Message {i}")

        removed = context_manager.compact(target_ratio=0.3)

        # Callback should be called with removed messages
        if removed:
            callback.assert_called_once_with(removed)
        else:
            # If nothing was removed, callback shouldn't be called
            callback.assert_not_called()

    def test_warning_callback(self, context_manager):
        """Test warning callback is called."""
        callback = MagicMock()
        context_manager.set_warning_callback(callback)
        context_manager.set_token_estimator(lambda x: len(x) * 10)

        # Add message to trigger warning (800 tokens)
        context_manager.add_message("user", "x" * 80)

        callback.assert_called_once()
        args = callback.call_args[0]
        assert args[0] >= 800  # current tokens
        assert args[1] == 800  # warning limit


# Test persistence
class TestPersistence:
    """Test save/load functionality."""

    def test_save_and_load(self, context_manager, tmp_path):
        """Test saving and loading context."""
        context_manager.set_token_estimator(lambda x: 10)

        # Add messages
        context_manager.add_message("system", "System prompt")
        context_manager.add_message("user", "Hello")
        context_manager.add_message("assistant", "Hi there!")

        # Save
        filepath = tmp_path / "context.json"
        context_manager.save(str(filepath))

        assert filepath.exists()

        # Load
        loaded = ContextManager.load(str(filepath))

        assert len(loaded.messages) == 3
        assert loaded.messages[0].role == "system"
        assert loaded.messages[1].role == "user"
        assert loaded.messages[2].role == "assistant"

    def test_to_dict(self, context_manager):
        """Test serialization to dict."""
        context_manager.add_message("user", "Hello")

        data = context_manager.to_dict()

        assert "config" in data
        assert "messages" in data
        assert "stats" in data
        assert len(data["messages"]) == 1

    def test_from_dict(self):
        """Test deserialization from dict."""
        data = {
            "config": {
                "max_tokens": 2000,
                "warning_threshold": 0.7,
            },
            "messages": [
                {"role": "user", "content": "Hello", "priority": 5, "tokens": 10},
            ],
            "stats": {"total_messages": 1, "total_tokens": 10},
        }

        manager = ContextManager.from_dict(data)

        assert manager.config.max_tokens == 2000
        assert len(manager.messages) == 1


# Test statistics
class TestStatistics:
    """Test statistics tracking."""

    def test_message_counts(self, context_manager):
        """Test message count statistics."""
        context_manager.add_message("system", "System")
        context_manager.add_message("user", "Hello 1")
        context_manager.add_message("assistant", "Hi 1")
        context_manager.add_message("user", "Hello 2")
        context_manager.add_message("tool", "Tool result")

        stats = context_manager.get_stats()

        assert stats.total_messages == 5
        assert stats.system_messages == 1
        assert stats.user_messages == 2
        assert stats.assistant_messages == 1
        assert stats.tool_messages == 1

    def test_average_message_size(self, context_manager):
        """Test average message size calculation."""
        context_manager.set_token_estimator(lambda x: 10)

        context_manager.add_message("user", "Hello")
        context_manager.add_message("assistant", "Hi")

        stats = context_manager.get_stats()

        assert stats.average_message_size == 10.0


# Test global instance
class TestGlobalInstance:
    """Test global context manager instance."""

    def test_get_context_manager(self):
        """Test getting global instance."""
        clear_context_manager()

        manager1 = get_context_manager()
        manager2 = get_context_manager()

        assert manager1 is manager2

    def test_clear_context_manager(self):
        """Test clearing global instance."""
        manager1 = get_context_manager()
        clear_context_manager()
        manager2 = get_context_manager()

        assert manager1 is not manager2

    def test_create_context_manager(self):
        """Test creating new instance."""
        manager1 = create_context_manager()
        manager2 = create_context_manager()

        assert manager1 is not manager2


# Test edge cases
class TestEdgeCases:
    """Test edge cases."""

    def test_empty_context(self, context_manager):
        """Test operations on empty context."""
        assert len(context_manager) == 0
        assert context_manager.get_messages() == []

        removed = context_manager.compact()
        assert removed == []

    def test_clear_context(self, context_manager):
        """Test clearing context."""
        context_manager.add_message("user", "Hello")
        context_manager.add_message("assistant", "Hi")

        context_manager.clear()

        assert len(context_manager) == 0
        assert context_manager.stats.total_tokens == 0

    def test_representations(self, context_manager):
        """Test string representations."""
        context_manager.add_message("user", "Hello")

        repr_str = repr(context_manager)

        assert "ContextManager" in repr_str
        assert "messages=1" in repr_str

    def test_len_method(self, context_manager):
        """Test __len__ method."""
        assert len(context_manager) == 0

        context_manager.add_message("user", "Hello")
        assert len(context_manager) == 1


# Test auto-compaction
class TestAutoCompaction:
    """Test auto-compaction feature."""

    def test_auto_compact_enabled(self):
        """Test auto-compaction when enabled."""
        config = ContextConfig(
            max_tokens=1000,
            critical_threshold=0.5,  # Low threshold for testing
            auto_compact=True,
        )
        manager = ContextManager(config)
        manager.set_token_estimator(lambda x: 600)  # Exceeds 50% of 1000

        # This should trigger auto-compaction
        manager.add_message("user", "x" * 100)

        # Stats should show compaction occurred
        assert manager.stats.compact_count >= 1

    def test_auto_compact_disabled(self):
        """Test no auto-compaction when disabled."""
        config = ContextConfig(
            max_tokens=1000,
            critical_threshold=0.5,
            auto_compact=False,
        )
        manager = ContextManager(config)
        manager.set_token_estimator(lambda x: 600)

        manager.add_message("user", "x" * 100)

        # No compaction should occur
        assert manager.stats.compact_count == 0
