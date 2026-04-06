"""Tests for token_estimation module."""

import pytest

from pilotcode.services.token_estimation import (
    TokenEstimator,
    get_token_estimator,
)


class TestTokenEstimator:
    """Tests for TokenEstimator."""
    
    @pytest.fixture
    def estimator(self):
        """Create TokenEstimator instance."""
        return TokenEstimator()
    
    def test_empty_text(self, estimator):
        """Test estimating empty text."""
        count = estimator.estimate("")
        
        assert count == 0
    
    def test_simple_text(self, estimator):
        """Test estimating simple text."""
        count = estimator.estimate("Hello world")
        
        # "Hello world" should be around 3 tokens
        assert count > 0
        assert count < 10
    
    def test_long_text(self, estimator):
        """Test estimating long text."""
        text = "This is a longer piece of text that should require more tokens. " * 10
        count = estimator.estimate(text)
        
        # Should be significantly more than short text
        assert count > 50
    
    def test_code_text(self, estimator):
        """Test estimating code text."""
        code = """
def hello_world():
    print("Hello, World!")
    return True
"""
        count_normal = estimator.estimate(code, is_code=False)
        count_code = estimator.estimate(code, is_code=True)
        
        # Code mode should give different estimate
        assert count_code > 0
    
    def test_special_characters(self, estimator):
        """Test estimating text with special characters."""
        text = "function() { return [1, 2, 3]; }"
        count = estimator.estimate(text)
        
        # Special characters should increase token count
        assert count > 0
    
    def test_whitespace_runs(self, estimator):
        """Test estimating text with multiple whitespaces."""
        text = "Word1    Word2     Word3"  # Multiple spaces
        count = estimator.estimate(text)
        
        assert count > 0
    
    def test_caching(self, estimator):
        """Test that short texts are cached."""
        text = "Short text for caching"
        
        # First estimate
        count1 = estimator.estimate(text)
        
        # Should be cached
        cache_key = f"{hash(text)}:False"
        assert cache_key in estimator._cache
        
        # Second estimate should use cache
        count2 = estimator.estimate(text)
        assert count1 == count2
    
    def test_no_caching_long_text(self, estimator):
        """Test that long texts are not cached."""
        text = "x" * 15000  # Very long text
        
        count = estimator.estimate(text)
        
        # Should not be in cache
        cache_key = f"{hash(text)}:False"
        assert cache_key not in estimator._cache
    
    def test_estimate_messages(self, estimator):
        """Test estimating messages."""
        messages = [
            {"role": "system", "content": "You are helpful"},
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there! How can I help?"},
        ]
        
        count = estimator.estimate_messages(messages)
        
        # Should account for message overhead
        assert count > 10  # More than just content
    
    def test_estimate_messages_with_none_content(self, estimator):
        """Test estimating messages with None content."""
        messages = [
            {"role": "assistant", "content": None},
        ]
        
        count = estimator.estimate_messages(messages)
        
        assert count >= 0
    
    def test_estimate_messages_with_dict_content(self, estimator):
        """Test estimating messages with dict content."""
        messages = [
            {"role": "assistant", "content": {"tool_call": "data"}},
        ]
        
        count = estimator.estimate_messages(messages)
        
        assert count >= 0


class TestTokenEstimatorAccuracy:
    """Tests for estimation accuracy."""
    
    @pytest.fixture
    def estimator(self):
        """Create TokenEstimator instance."""
        return TokenEstimator()
    
    def test_english_text_ratio(self, estimator):
        """Test English text token ratio."""
        # Average English text: ~4 chars per token
        text = "The quick brown fox jumps over the lazy dog"
        count = estimator.estimate(text)
        
        # Should be roughly chars / 4
        expected = len(text) / 4
        # Allow 50% margin
        assert count > expected * 0.5
        assert count < expected * 1.5
    
    def test_single_word(self, estimator):
        """Test single word."""
        count = estimator.estimate("Hello")
        
        # Single word should be 1-2 tokens
        assert count >= 1
        assert count <= 3
    
    def test_repeated_pattern(self, estimator):
        """Test repeated pattern."""
        text = "abc " * 100
        count = estimator.estimate(text)
        
        # Should scale linearly
        single_count = estimator.estimate("abc")
        assert count > single_count * 50  # Less than 100x due to pattern


class TestGlobalEstimator:
    """Tests for global token estimator."""
    
    def test_get_token_estimator_singleton(self):
        """Test that get_token_estimator returns singleton."""
        estimator1 = get_token_estimator()
        estimator2 = get_token_estimator()
        
        assert estimator1 is estimator2
    
    def test_global_estimator_has_cache(self):
        """Test global estimator has cache."""
        estimator = get_token_estimator()
        
        assert hasattr(estimator, '_cache')
        assert isinstance(estimator._cache, dict)


class TestConstants:
    """Tests for estimator constants."""
    
    def test_chars_per_token(self):
        """Test CHARS_PER_TOKEN constant."""
        assert TokenEstimator.CHARS_PER_TOKEN == 4.0
    
    def test_code_chars_per_token(self):
        """Test CODE_CHARS_PER_TOKEN constant."""
        assert TokenEstimator.CODE_CHARS_PER_TOKEN == 3.5
    
    def test_words_per_token(self):
        """Test WORDS_PER_TOKEN constant."""
        assert TokenEstimator.WORDS_PER_TOKEN == 0.75


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
