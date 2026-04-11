"""Tests for task-aware compression module."""

import pytest
from unittest.mock import Mock, patch

from pilotcode.services.task_aware_compression import (
    SemanticClustering,
    TaskAwareCompressor,
    TaskContext,
    CompressionMode,
    TaskAwareCompressionResult,
    RetentionDecision,
    get_task_aware_compressor,
    reset_task_aware_compressor,
)
from pilotcode.services.context_manager import ContextMessage, MessagePriority


class TestSemanticClustering:
    """Tests for semantic clustering."""
    
    def test_cluster_similar_messages(self):
        clusterer = SemanticClustering()
        
        messages = [
            ContextMessage(role="user", content="How do I implement login?"),
            ContextMessage(role="user", content="How to implement login feature?"),
            ContextMessage(role="user", content="What's the weather today?"),
        ]
        
        clusters = clusterer.cluster_messages(messages)
        
        # Should group similar messages
        assert len(clusters) < len(messages)
    
    def test_cluster_unique_messages(self):
        clusterer = SemanticClustering()
        
        messages = [
            ContextMessage(role="user", content="Completely unique content A"),
            ContextMessage(role="user", content="Totally different content B"),
            ContextMessage(role="user", content="Nothing in common here C"),
        ]
        
        clusters = clusterer.cluster_messages(messages)
        
        # Each should be in its own cluster
        assert len(clusters) == 3
    
    def test_select_diverse_samples(self):
        clusterer = SemanticClustering()
        
        messages = [
            ContextMessage(role="user", content="Msg 1", id="m1"),
            ContextMessage(role="user", content="Msg 2", id="m2"),
            ContextMessage(role="user", content="Msg 3", id="m3"),
        ]
        
        clusters = [[messages[0], messages[1]], [messages[2]]]
        scores = {"m1": 0.9, "m2": 0.8, "m3": 0.7}
        
        selected = clusterer.select_diverse_samples(clusters, scores, total_budget=2)
        
        assert len(selected) == 2
        # Should pick from different clusters for diversity
        assert messages[0] in selected or messages[1] in selected
        assert messages[2] in selected


class TestTaskAwareCompressor:
    """Tests for task-aware compressor."""
    
    def test_empty_messages(self):
        compressor = TaskAwareCompressor()
        task_context = TaskContext(description="Test task")
        
        result = compressor.compress_with_task_context(
            [], task_context, target_tokens=1000
        )
        
        assert result.original_messages == 0
        assert result.retained_messages == 0
    
    def test_no_compression_needed(self):
        compressor = TaskAwareCompressor()
        
        messages = [
            ContextMessage(role="user", content="Short message"),
        ]
        
        task_context = TaskContext(description="Test")
        result = compressor.compress_with_task_context(
            messages, task_context, target_tokens=10000
        )
        
        assert result.original_messages == result.retained_messages
        assert result.value_retention_rate == 1.0
    
    def test_compression_occurs(self):
        compressor = TaskAwareCompressor()
        
        # Create many messages that exceed token limit
        messages = [
            ContextMessage(role="user", content=f"Message {i} with some content" * 50)
            for i in range(20)
        ]
        
        task_context = TaskContext(
            description="Implement authentication",
            current_files=["src/auth.py"],
        )
        
        result = compressor.compress_with_task_context(
            messages, task_context, target_tokens=1000
        )
        
        assert result.compressed_tokens < result.original_tokens
        assert result.retained_messages < result.original_messages
    
    def test_preserve_recent_messages(self):
        compressor = TaskAwareCompressor()
        
        messages = [
            ContextMessage(role="user", content=f"Old message {i}")
            for i in range(10)
        ] + [
            ContextMessage(role="user", content=f"Recent message {i}")
            for i in range(4)
        ]
        
        task_context = TaskContext(description="Test")
        result = compressor.compress_with_task_context(
            messages, task_context, target_tokens=500, preserve_recent=2
        )
        
        # Should preserve at least recent messages
        assert result.retained_messages >= 4  # 2 pairs = 4 messages
    
    def test_determine_mode(self):
        compressor = TaskAwareCompressor()
        
        assert compressor._determine_mode(1.0) == CompressionMode.LIGHT
        assert compressor._determine_mode(1.15) == CompressionMode.MODERATE
        assert compressor._determine_mode(1.25) == CompressionMode.AGGRESSIVE
        assert compressor._determine_mode(1.6) == CompressionMode.EMERGENCY
    
    def test_compress_by_task_type(self):
        compressor = TaskAwareCompressor()
        
        messages = [
            ContextMessage(role="user", content="Debug this error")
            for _ in range(10)
        ]
        
        result = compressor.compress_by_task_type(
            messages=messages,
            task_type="debug",
            task_description="Fix authentication bug",
            current_files=["src/auth.py"],
            target_tokens=500,
        )
        
        assert isinstance(result, TaskAwareCompressionResult)
        assert result.task_context.task_type == "debug"
    
    def test_make_decisions(self):
        compressor = TaskAwareCompressor()
        
        messages = [
            ContextMessage(role="user", content="Important", id="m1"),
            ContextMessage(role="user", content="Less important", id="m2"),
        ]
        
        selected = [messages[0]]
        scores = {"m1": 0.9, "m2": 0.3}
        task_context = TaskContext(description="Test")
        
        decisions = compressor._make_decisions(messages, selected, scores, task_context)
        
        assert len(decisions) == 2
        assert decisions[0].retained is True
        assert decisions[1].retained is False
    
    def test_summarize_message(self):
        compressor = TaskAwareCompressor()
        
        # Long tool result
        msg = ContextMessage(
            role="tool",
            content="A" * 1000,
            id="tool_1"
        )
        
        summarized = compressor._summarize_message(msg)
        
        assert summarized is not None
        assert summarized.summarized is True
        assert len(summarized.content) < len(msg.content)
        assert "[Tool result:" in summarized.content
    
    def test_summarize_short_message_skipped(self):
        compressor = TaskAwareCompressor()
        
        msg = ContextMessage(
            role="user",
            content="Short",
            id="msg_1"
        )
        
        summarized = compressor._summarize_message(msg)
        
        assert summarized is None  # Too short to summarize


class TestTaskContext:
    """Tests for TaskContext."""
    
    def test_to_summary(self):
        context = TaskContext(
            description="Implement login",
            goal_keywords=["auth", "jwt", "security"],
        )
        
        summary = context.to_summary()
        
        assert "Implement login" in summary
        assert "auth" in summary
    
    def test_empty_context(self):
        context = TaskContext()
        
        summary = context.to_summary()
        
        assert summary == ""


class TestCompressionResult:
    """Tests for TaskAwareCompressionResult."""
    
    def test_to_dict(self):
        result = TaskAwareCompressionResult(
            original_messages=10,
            retained_messages=6,
            summarized_messages=2,
            removed_messages=2,
            original_tokens=5000,
            compressed_tokens=3000,
            value_retention_rate=0.8,
            compression_mode=CompressionMode.MODERATE,
        )
        
        d = result.to_dict()
        
        assert d["original_messages"] == 10
        assert d["retained_messages"] == 6
        assert d["value_retention_rate"] == 0.8
        assert d["compression_mode"] == "moderate"
        assert d["token_reduction"] == 0.4  # (5000-3000)/5000


class TestGlobalCompressor:
    """Tests for global compressor."""
    
    def test_singleton(self):
        reset_task_aware_compressor()
        
        c1 = get_task_aware_compressor()
        c2 = get_task_aware_compressor()
        
        assert c1 is c2
        
        reset_task_aware_compressor()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
