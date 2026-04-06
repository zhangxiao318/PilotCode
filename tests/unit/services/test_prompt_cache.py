"""Tests for Prompt Cache system."""

import pytest
import tempfile
import shutil
import time
from pathlib import Path

from pilotcode.services.prompt_cache import (
    CacheEntry,
    CacheStats,
    PromptCache,
    CacheAwareMessageBuilder,
    get_prompt_cache,
    clear_prompt_cache,
)


class TestCacheEntry:
    """Test CacheEntry dataclass."""

    def test_creation(self):
        """Test CacheEntry creation."""
        entry = CacheEntry(
            cache_key="abc123",
            messages_hash="msg_hash",
            response="Hello world",
            model="claude-3-opus",
            tokens_input=100,
            tokens_output=50,
        )

        assert entry.cache_key == "abc123"
        assert entry.response == "Hello world"
        assert entry.total_tokens == 150
        assert entry.access_count == 0

    def test_age_calculation(self):
        """Test age calculation."""
        entry = CacheEntry(
            cache_key="test",
            messages_hash="hash",
            response="test",
            model="test",
            tokens_input=10,
            tokens_output=10,
            created_at=time.time() - 3600,  # 1 hour ago
        )

        assert 0.99 < entry.age_hours < 1.01

    def test_serialization(self):
        """Test dict serialization."""
        entry = CacheEntry(
            cache_key="key",
            messages_hash="hash",
            response="response",
            model="model",
            tokens_input=10,
            tokens_output=20,
        )

        data = entry.to_dict()
        restored = CacheEntry.from_dict(data)

        assert restored.cache_key == entry.cache_key
        assert restored.response == entry.response
        assert restored.tokens_input == entry.tokens_input


class TestPromptCache:
    """Test PromptCache functionality."""

    @pytest.fixture
    def temp_dir(self):
        """Create temporary directory."""
        path = tempfile.mkdtemp()
        yield path
        shutil.rmtree(path)

    @pytest.fixture
    def cache(self, temp_dir):
        """Create cache instance with temp directory."""
        cache = PromptCache(max_size=100, persist=False)
        return cache

    def test_basic_put_and_get(self, cache):
        """Test basic cache operations."""
        messages = [{"role": "user", "content": "Hello"}]
        model = "gpt-4"

        # Initially not in cache
        assert cache.get(messages, model) is None

        # Put in cache
        cache.put(messages, model, "Hi there!", 10, 5)

        # Should be in cache
        entry = cache.get(messages, model)
        assert entry is not None
        assert entry.response == "Hi there!"
        assert entry.tokens_input == 10
        assert entry.tokens_output == 5

    def test_cache_miss_different_messages(self, cache):
        """Test cache miss with different messages."""
        messages1 = [{"role": "user", "content": "Hello"}]
        messages2 = [{"role": "user", "content": "World"}]
        model = "gpt-4"

        cache.put(messages1, model, "Response 1", 10, 5)

        # Different messages should miss
        assert cache.get(messages2, model) is None

    def test_cache_miss_different_model(self, cache):
        """Test cache miss with different model."""
        messages = [{"role": "user", "content": "Hello"}]

        cache.put(messages, "gpt-4", "Response", 10, 5)

        # Different model should miss
        assert cache.get(messages, "claude-3") is None

    def test_lru_eviction(self):
        """Test LRU eviction policy."""
        cache = PromptCache(max_size=3, persist=False)

        # Add 3 entries
        for i in range(3):
            messages = [{"role": "user", "content": f"Message {i}"}]
            cache.put(messages, "model", f"Response {i}", 10, 5)

        # All should be in cache
        for i in range(3):
            messages = [{"role": "user", "content": f"Message {i}"}]
            assert cache.get(messages, "model") is not None

        # Access first entry to update LRU
        messages0 = [{"role": "user", "content": "Message 0"}]
        cache.get(messages0, "model")

        # Add 4th entry - should evict Message 1 (oldest unused)
        messages3 = [{"role": "user", "content": "Message 3"}]
        cache.put(messages3, "model", "Response 3", 10, 5)

        # Message 0 and 2 should be in cache
        assert cache.get(messages0, "model") is not None
        messages2 = [{"role": "user", "content": "Message 2"}]
        assert cache.get(messages2, "model") is not None

        # Message 1 should be evicted
        messages1 = [{"role": "user", "content": "Message 1"}]
        assert cache.get(messages1, "model") is None

    def test_ttl_expiration(self):
        """Test TTL expiration."""
        # Use negative TTL to force immediate expiration
        cache = PromptCache(max_size=100, ttl_hours=-0.001, persist=False)

        messages = [{"role": "user", "content": "Hello"}]
        cache.put(messages, "model", "Response", 10, 5)

        # Should be expired immediately due to negative TTL
        assert cache.get(messages, "model") is None

    def test_access_count_tracking(self, cache):
        """Test access count tracking."""
        messages = [{"role": "user", "content": "Hello"}]
        model = "gpt-4"

        cache.put(messages, model, "Hi!", 10, 5)

        # Access multiple times
        for _ in range(5):
            entry = cache.get(messages, model)

        assert entry.access_count == 5

    def test_invalidation_by_model(self, cache):
        """Test invalidation by model."""
        messages1 = [{"role": "user", "content": "Hello"}]
        messages2 = [{"role": "user", "content": "World"}]

        cache.put(messages1, "gpt-4", "Response 1", 10, 5)
        cache.put(messages2, "claude-3", "Response 2", 10, 5)

        # Invalidate only gpt-4
        count = cache.invalidate("gpt-4")
        assert count == 1

        assert cache.get(messages1, "gpt-4") is None
        assert cache.get(messages2, "claude-3") is not None

    def test_full_invalidation(self, cache):
        """Test full cache invalidation."""
        cache.put([{"role": "user", "content": "A"}], "model", "A", 10, 5)
        cache.put([{"role": "user", "content": "B"}], "model", "B", 10, 5)

        cache.clear()

        assert cache.get([{"role": "user", "content": "A"}], "model") is None
        assert cache.get([{"role": "user", "content": "B"}], "model") is None

    def test_stats_tracking(self, cache):
        """Test statistics tracking."""
        messages = [{"role": "user", "content": "Hello"}]

        # Miss
        cache.get(messages, "model")

        # Put
        cache.put(messages, "model", "Hi!", 100, 50)

        # Hit (2 hits, each saves 150 tokens)
        cache.get(messages, "model")
        cache.get(messages, "model")

        stats = cache.get_stats()

        assert stats.hits == 2
        assert stats.misses == 1
        assert stats.total_entries == 1
        # Each hit saves total_tokens (100 + 50) = 150, so 2 hits = 300
        assert stats.total_tokens_saved == 300  # (100 + 50) * 2 hits
        assert stats.hit_rate == 2 / 3

    def test_persistence(self, temp_dir):
        """Test disk persistence."""
        cache = PromptCache(max_size=100, persist=True)
        cache._cache_dir = Path(temp_dir)

        messages = [{"role": "user", "content": "Hello"}]
        cache.put(messages, "gpt-4", "Hi there!", 10, 5)

        # Save to disk
        cache._save_entry_to_disk(cache._cache[cache._generate_cache_key(messages, "gpt-4")])

        # Create new cache instance
        cache2 = PromptCache(max_size=100, persist=True)
        cache2._cache_dir = Path(temp_dir)
        cache2._load_from_disk()

        # Should have loaded entry
        entry = cache2.get(messages, "gpt-4")
        assert entry is not None
        assert entry.response == "Hi there!"


class TestCacheAwareMessageBuilder:
    """Test CacheAwareMessageBuilder."""

    @pytest.fixture
    def builder(self):
        """Create builder instance."""
        cache = PromptCache(persist=False)
        return CacheAwareMessageBuilder(cache)

    def test_build_messages(self, builder):
        """Test message building."""
        messages = builder.build_messages(
            system_message="You are helpful",
            conversation_history=[{"role": "assistant", "content": "Hi"}],
            user_message="Hello",
            model="gpt-4",
        )

        assert len(messages) == 3
        assert messages[0]["role"] == "system"
        assert messages[1]["role"] == "assistant"
        assert messages[2]["role"] == "user"

    def test_cache_hit_optimization(self, builder):
        """Test cache hit detection."""
        messages = [
            {"role": "system", "content": "You are helpful"},
            {"role": "user", "content": "Hello"},
        ]

        # Pre-populate cache
        builder.cache.put(messages, "gpt-4", "Hi!", 10, 5)

        # Build same messages
        result = builder.build_messages(
            system_message="You are helpful",
            conversation_history=[],
            user_message="Hello",
            model="gpt-4",
        )

        # Should return same structure
        assert result == messages

        # Verify cache hit
        stats = builder.cache.get_stats()
        assert stats.hits == 1

    def test_detect_cache_break(self, builder):
        """Test cache break detection."""
        old = [
            {"role": "user", "content": "A"},
            {"role": "assistant", "content": "B"},
            {"role": "user", "content": "C"},
        ]

        new = [
            {"role": "user", "content": "A"},
            {"role": "assistant", "content": "B"},
            {"role": "user", "content": "D"},  # Changed
        ]

        break_idx = builder.detect_cache_break(old, new)
        assert break_idx == 2

    def test_no_cache_break(self, builder):
        """Test when there's no cache break."""
        old = [{"role": "user", "content": "A"}, {"role": "assistant", "content": "B"}]

        new = [{"role": "user", "content": "A"}, {"role": "assistant", "content": "B"}]

        break_idx = builder.detect_cache_break(old, new)
        assert break_idx == -1


class TestGlobalInstance:
    """Test global instance functions."""

    def test_get_prompt_cache(self):
        """Test getting global cache."""
        clear_prompt_cache()

        cache1 = get_prompt_cache()
        cache2 = get_prompt_cache()

        assert cache1 is cache2

    def test_clear_prompt_cache(self):
        """Test clearing global cache."""
        cache = get_prompt_cache()
        cache.put([{"role": "user", "content": "test"}], "model", "response", 10, 5)

        clear_prompt_cache()

        cache2 = get_prompt_cache()
        assert cache2 is not cache


class TestCacheWithComplexMessages:
    """Test cache with complex message structures."""

    def test_nested_content(self):
        """Test caching with nested content."""
        cache = PromptCache(persist=False)

        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "Hello"},
                    {"type": "image_url", "image_url": {"url": "http://example.com/img.png"}},
                ],
            }
        ]

        cache.put(messages, "model", "Response", 100, 50)
        entry = cache.get(messages, "model")

        assert entry is not None
        assert entry.response == "Response"

    def test_tool_calls_in_messages(self):
        """Test caching with tool calls."""
        cache = PromptCache(persist=False)

        messages = [
            {"role": "user", "content": "What's the weather?"},
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {
                        "id": "1",
                        "type": "function",
                        "function": {"name": "get_weather", "arguments": "{}"},
                    }
                ],
            },
            {"role": "tool", "tool_call_id": "1", "content": "Sunny"},
        ]

        cache.put(messages, "model", "The weather is sunny", 50, 10)
        entry = cache.get(messages, "model")

        assert entry is not None

    def test_unicode_content(self):
        """Test caching with unicode content."""
        cache = PromptCache(persist=False)

        messages = [{"role": "user", "content": "你好，世界！🌍"}]

        cache.put(messages, "model", "你好！👋", 10, 5)
        entry = cache.get(messages, "model")

        assert entry is not None
        assert entry.response == "你好！👋"


class TestCacheStats:
    """Test CacheStats functionality."""

    def test_cost_estimation(self):
        """Test cost estimation."""
        stats = CacheStats(hits=100, misses=50, total_tokens_saved=100000)  # 100K tokens

        # Rough estimate: $0.01 per 1K tokens
        assert stats.estimated_cost_saved == 1.0  # $1.00

    def test_hit_rate_calculation(self):
        """Test hit rate calculation."""
        stats = CacheStats(hits=75, misses=25)
        assert stats.hit_rate == 0.75

        # Empty stats
        stats2 = CacheStats()
        assert stats2.hit_rate == 0.0
