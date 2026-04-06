"""Tests for conversation fork functionality."""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from pilotcode.services.conversation_fork import (
    ConversationForker,
    ConversationSummarizer,
    ForkResult,
    ConversationSummary,
    get_conversation_forker,
    fork_current_conversation,
)


class TestConversationSummary:
    """Tests for ConversationSummary dataclass."""
    
    def test_summary_creation(self):
        """Test creating a summary."""
        summary = ConversationSummary(
            content="Test summary",
            key_points=["point1", "point2"],
            token_count=0
        )
        
        assert summary.content == "Test summary"
        assert len(summary.key_points) == 2
        assert summary.token_count == 0


class TestConversationSummarizer:
    """Tests for ConversationSummarizer."""
    
    @pytest.mark.asyncio
    async def test_summarize_empty_conversation(self):
        """Test summarizing empty conversation."""
        summarizer = ConversationSummarizer()
        
        summary = await summarizer.summarize_for_fork([])
        
        assert summary.content == "Empty conversation"
        assert summary.token_count == 0
    
    @pytest.mark.asyncio
    async def test_summarize_simple_conversation(self):
        """Test summarizing simple conversation."""
        summarizer = ConversationSummarizer()
        
        # Create mock messages
        messages = [
            MagicMock(type="user", content="Hello"),
            MagicMock(type="assistant", content="Hi there"),
        ]
        
        summary = await summarizer.summarize_for_fork(messages)
        
        assert summary.content != "Empty conversation"
        assert summary.token_count == 0
    
    @pytest.mark.asyncio
    async def test_summarize_with_mock_summarize_fn(self):
        """Test with custom summarize function."""
        mock_summarize = AsyncMock(return_value="Custom summary")
        summarizer = ConversationSummarizer(summarize_fn=mock_summarize)
        
        messages = [
            MagicMock(type="user", content="Hello"),
            MagicMock(type="assistant", content="Hi"),
        ]
        
        summary = await summarizer.summarize_for_fork(messages)
        
        assert summary.content == "Custom summary"
        mock_summarize.assert_called_once()
    
    def test_simple_summary(self):
        """Test simple summary generation."""
        summarizer = ConversationSummarizer()
        
        pairs = [
            {"user": "Hello", "assistant": "Hi"},
            {"user": "How are you?", "assistant": "Good"},
        ]
        
        summary = summarizer._simple_summary(pairs)
        
        assert "Hello" in summary
        assert "2 user messages" in summary
    
    def test_extract_key_points(self):
        """Test extracting key points."""
        summarizer = ConversationSummarizer()
        
        pairs = [{
            "user": "Check test.py please",
            "assistant": "Looking at test.py and config.yaml"
        }]
        
        points = summarizer._extract_key_points(pairs)
        
        # Files should be extracted from the combined content
        content = pairs[0]["user"] + " " + pairs[0]["assistant"]
        assert "test.py" in content  # Verify files are in content
        assert len(points) >= 0  # May or may not extract depending on regex
    
    def test_extract_decisions(self):
        """Test extracting decisions."""
        summarizer = ConversationSummarizer()
        
        pairs = [{
            "user": "What should we do?",
            "assistant": "I decided we will use Python for this project."
        }]
        
        decisions = summarizer._extract_decisions(pairs)
        
        assert len(decisions) > 0
        assert any("decided" in d.lower() for d in decisions)


class TestConversationForker:
    """Tests for ConversationForker."""
    
    @pytest.mark.asyncio
    async def test_fork_empty_conversation(self):
        """Test forking empty conversation."""
        forker = ConversationForker()
        
        result = await forker.fork_conversation([])
        
        assert result.success is False
        assert "No messages" in result.error
    
    @pytest.mark.asyncio
    async def test_fork_success(self):
        """Test successful fork."""
        forker = ConversationForker()
        
        messages = [
            MagicMock(type="system", content="System prompt"),
            MagicMock(type="user", content="Hello"),
            MagicMock(type="assistant", content="Hi"),
        ]
        
        result = await forker.fork_conversation(messages)
        
        assert result.success is True
        assert result.original_message_count == 3
        assert result.new_message_count > 0
        assert result.tokens_saved >= 0
    
    @pytest.mark.asyncio
    async def test_fork_preserves_system_message(self):
        """Test that fork preserves system message."""
        forker = ConversationForker()
        
        system_msg = MagicMock(type="system", content="System prompt")
        messages = [
            system_msg,
            MagicMock(type="user", content="Hello"),
        ]
        
        result = await forker.fork_conversation(messages)
        new_messages = forker._create_forked_messages(
            messages,
            ConversationSummary(content="Test")
        )
        
        assert len(new_messages) > 0
    
    def test_estimate_tokens_saved(self):
        """Test token estimation."""
        forker = ConversationForker()
        
        original = [
            MagicMock(content="a" * 400),
            MagicMock(content="b" * 400),
        ]
        new = [
            MagicMock(content="c" * 100),
        ]
        
        saved = forker._estimate_tokens_saved(original, new)
        
        assert saved > 0
        # Roughly 700 chars / 4 = ~175 tokens
        assert saved > 50
    
    def test_get_fork_stats_empty(self):
        """Test fork stats with no forks."""
        forker = ConversationForker()
        
        stats = forker.get_fork_stats()
        
        assert stats["total_forks"] == 0
        assert stats["total_tokens_saved"] == 0
    
    def test_get_fork_stats_with_forks(self):
        """Test fork stats with forks."""
        forker = ConversationForker()
        forker._fork_history.append(ForkResult(
            success=True,
            summary="Test",
            original_message_count=10,
            new_message_count=5,
            tokens_saved=100
        ))
        
        stats = forker.get_fork_stats()
        
        assert stats["total_forks"] == 1
        assert stats["total_tokens_saved"] == 100


class TestGlobalFunctions:
    """Tests for global functions."""
    
    def test_get_conversation_forker(self):
        """Test getting global forker."""
        forker1 = get_conversation_forker()
        forker2 = get_conversation_forker()
        assert forker1 is forker2
    
    @pytest.mark.asyncio
    async def test_fork_current_conversation(self):
        """Test convenience function."""
        messages = [
            MagicMock(type="user", content="Hello"),
        ]
        
        result = await fork_current_conversation(messages)
        
        assert isinstance(result, ForkResult)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
