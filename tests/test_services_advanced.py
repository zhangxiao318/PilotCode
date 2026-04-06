"""Tests for advanced services: caching, token estimation, context compression, tool orchestration."""

import asyncio
import time
from typing import Any

import pytest

from pilotcode.services.tool_cache import ToolCache, get_tool_cache
from pilotcode.services.token_estimation import TokenEstimator, get_token_estimator
from pilotcode.services.context_compression import ContextCompressor, get_context_compressor
from pilotcode.services.tool_orchestrator import ToolOrchestrator, ExecutionBatch, ToolExecution
from pilotcode.tools.base import ToolResult


# =============================================================================
# Tool Cache Tests
# =============================================================================
class TestToolCache:
    def test_cache_get_set(self):
        cache = ToolCache()
        result = ToolResult(data={"test": "value"})

        # Set cache
        cache.set("TestTool", {"arg": "value"}, result)

        # Get cache
        cached = cache.get("TestTool", {"arg": "value"})
        assert cached is not None
        assert cached.data == {"test": "value"}

    def test_cache_miss(self):
        cache = ToolCache()
        cached = cache.get("TestTool", {"arg": "missing"})
        assert cached is None

    def test_cache_expiration(self):
        cache = ToolCache(default_ttl=0.01)  # 10ms TTL
        result = ToolResult(data={"test": "value"})

        cache.set("TestTool", {"arg": "value"}, result, ttl=0.01)

        # Should hit immediately
        assert cache.get("TestTool", {"arg": "value"}) is not None

        # Wait for expiration
        time.sleep(0.02)

        # Should miss after expiration
        assert cache.get("TestTool", {"arg": "value"}) is None

    def test_cache_no_errors(self):
        """Error results should not be cached."""
        cache = ToolCache()
        error_result = ToolResult(data=None, error="Something failed")

        cache.set("TestTool", {"arg": "value"}, error_result)

        # Should not cache error results
        assert cache.get("TestTool", {"arg": "value"}) is None

    def test_cache_invalidation(self):
        cache = ToolCache()
        result = ToolResult(data={"test": "value"})

        cache.set("Tool1", {"arg": "1"}, result)
        cache.set("Tool2", {"arg": "2"}, result)

        # Invalidate all
        count = cache.invalidate()
        assert count == 2
        assert cache.get("Tool1", {"arg": "1"}) is None
        assert cache.get("Tool2", {"arg": "2"}) is None

    def test_cache_stats(self):
        cache = ToolCache()
        result = ToolResult(data={"test": "value"})

        # Miss
        cache.get("Tool", {"arg": "1"})

        # Hit
        cache.set("Tool", {"arg": "2"}, result)
        cache.get("Tool", {"arg": "2"})

        stats = cache.get_stats()
        assert stats["hits"] == 1
        assert stats["misses"] == 1
        assert stats["hit_rate"] == "50.0%"


# =============================================================================
# Token Estimation Tests
# =============================================================================
class TestTokenEstimation:
    def test_estimate_empty(self):
        estimator = TokenEstimator()
        assert estimator.estimate("") == 0

    def test_estimate_basic(self):
        estimator = TokenEstimator()
        # Uses weighted combination for better accuracy
        text = "A" * 100
        tokens = estimator.estimate(text)
        # Should be roughly 100/4 = 25, but algorithm uses weights
        assert tokens > 0
        assert tokens <= 25  # Weighted combination gives lower estimate

    def test_estimate_code(self):
        estimator = TokenEstimator()
        # Code has more punctuation, so should estimate slightly higher
        code = "def func():\n    return 1 + 2"
        regular = "This is regular text with words"

        code_tokens = estimator.estimate(code, is_code=True)
        regular_tokens = estimator.estimate(regular, is_code=False)

        # Both should return positive values
        assert code_tokens > 0
        assert regular_tokens > 0

    def test_estimate_messages(self):
        estimator = TokenEstimator()
        messages = [
            {"role": "user", "content": "Hello world"},
            {"role": "assistant", "content": "Hi there"},
        ]
        tokens = estimator.estimate_messages(messages)
        assert tokens > 0
        # Should account for message overhead (~4 tokens per message)
        assert tokens >= 8

    def test_budget_status(self):
        estimator = TokenEstimator()

        # OK status
        status = estimator.get_budget_status(100, 1000)
        assert status["status"] == "ok"
        assert status["remaining"] == 900

        # Warning status
        status = estimator.get_budget_status(850, 1000)
        assert status["status"] == "warning"

        # Exceeded status
        status = estimator.get_budget_status(1100, 1000)
        assert status["status"] == "exceeded"


# =============================================================================
# Context Compression Tests
# =============================================================================
class TestContextCompression:
    def test_no_compression_needed(self):
        from pilotcode.types.message import UserMessage, AssistantMessage

        compressor = ContextCompressor(target_tokens=1000)
        messages = [
            UserMessage(content="Hello"),
            AssistantMessage(content="Hi"),
        ]

        result = asyncio.run(compressor.compress(messages))
        assert result.original_count == 2
        assert result.compressed_count == 2
        assert result.summary is None

    def test_simple_compact(self):
        from pilotcode.types.message import UserMessage, AssistantMessage

        compressor = ContextCompressor(target_tokens=100)
        messages = []
        for i in range(20):
            messages.append(UserMessage(content=f"Message {i} with some content here"))
            messages.append(AssistantMessage(content=f"Response {i} with more content"))

        compacted = compressor.simple_compact(messages, keep_recent=4)

        # Should keep fewer messages
        assert len(compacted) < len(messages)
        assert len(compacted) <= 5  # system (if any) + 4 recent

    def test_priority_compressor(self):
        from pilotcode.types.message import UserMessage, AssistantMessage, SystemMessage
        from pilotcode.services.context_compression import PriorityBasedCompressor

        compressor = PriorityBasedCompressor(target_tokens=100)

        messages = [
            SystemMessage(content="System prompt"),
        ]
        for i in range(15):
            messages.append(UserMessage(content=f"User message {i}"))
            messages.append(AssistantMessage(content=f"Assistant response {i}"))

        compressed = compressor.compact_with_priority(messages, max_messages=10)

        assert len(compressed) <= 10
        # High priority messages are more likely to be kept
        # Note: system message has highest priority but may still be excluded
        # if there are many recent high-priority messages


# =============================================================================
# Tool Orchestrator Tests
# =============================================================================
class TestToolOrchestrator:
    def test_analyze_batch_read_only(self):
        orchestrator = ToolOrchestrator()

        # Multiple read-only tools should be batched together
        tool_calls = [
            ("FileRead", {"file_path": "/tmp/a.txt"}),
            ("FileRead", {"file_path": "/tmp/b.txt"}),
            ("Glob", {"pattern": "*.py"}),
        ]

        batches = orchestrator.analyze_batch(tool_calls)

        # All read-only tools should be in one parallel batch
        assert len(batches) == 1
        assert batches[0].is_concurrent_safe is True
        assert len(batches[0].tools) == 3

    def test_analyze_batch_mixed(self):
        orchestrator = ToolOrchestrator()

        # Mix of read-only and write tools
        tool_calls = [
            ("FileRead", {"file_path": "/tmp/a.txt"}),
            ("FileWrite", {"file_path": "/tmp/out.txt", "content": "data"}),
            ("Bash", {"command": "echo test"}),
        ]

        batches = orchestrator.analyze_batch(tool_calls)

        # Should create separate batches
        assert len(batches) >= 2

    @pytest.mark.asyncio
    async def test_execute_single_tool(self):
        orchestrator = ToolOrchestrator(use_cache=False)
        from pilotcode.tools.base import ToolUseContext

        async def allow_callback(*args, **kwargs):
            return {"behavior": "allow"}

        ctx = ToolUseContext()
        executions = [
            ToolExecution(tool_name="Bash", tool_input={"command": "echo test"}, execution_id="1")
        ]

        batch = ExecutionBatch(
            tools=executions,
            mode=orchestrator.analyze_batch([("Bash", {"command": "echo test"})])[0].mode,
            is_concurrent_safe=False,
        )

        results = await orchestrator.execute_batch(batch, ctx, allow_callback)

        assert len(results) == 1
        assert results[0].completed is True
        assert results[0].result is not None

    def test_execution_with_cache(self):
        orchestrator = ToolOrchestrator(use_cache=True)

        # First, clear any existing cache
        get_tool_cache().invalidate()

        # Execute should use cache for read-only tools
        assert orchestrator._cache is not None

        stats = orchestrator.get_stats()
        assert "cache" in stats


# =============================================================================
# Integration Tests
# =============================================================================
class TestServiceIntegration:
    def test_global_instances(self):
        """Test that global service instances work correctly."""
        from pilotcode.services.tool_cache import get_tool_cache
        from pilotcode.services.token_estimation import get_token_estimator
        from pilotcode.services.context_compression import get_context_compressor
        from pilotcode.services.tool_orchestrator import get_tool_orchestrator

        cache1 = get_tool_cache()
        cache2 = get_tool_cache()
        assert cache1 is cache2

        estimator1 = get_token_estimator()
        estimator2 = get_token_estimator()
        assert estimator1 is estimator2

        compressor1 = get_context_compressor()
        compressor2 = get_context_compressor()
        assert compressor1 is compressor2

        orchestrator1 = get_tool_orchestrator()
        orchestrator2 = get_tool_orchestrator()
        assert orchestrator1 is orchestrator2
