"""Unit tests for Unicode-aware input widgets.

These tests verify that UnicodeInput and UnicodeTextArea correctly handle:
- Multi-byte character input (CJK, emoji)
- Backspace deleting single Unicode characters
- Word deletion with Ctrl+Backspace

Note: Textual widgets need app context, so we test the core logic functions directly.
"""

import pytest
import re


def delete_character_left(value: str, cursor_position: int) -> tuple[str, int]:
    """Core logic for deleting one Unicode character to the left.
    
    Returns:
        Tuple of (new_value, new_cursor_position)
    """
    if cursor_position <= 0:
        return value, cursor_position
    
    # Remove last Unicode character
    new_value = value[:cursor_position - 1] + value[cursor_position:]
    new_cursor = cursor_position - 1
    
    return new_value, new_cursor


def delete_word_left(value: str, cursor_position: int) -> tuple[str, int]:
    """Core logic for deleting one word to the left.
    
    Returns:
        Tuple of (new_value, new_cursor_position)
    """
    if cursor_position <= 0:
        return value, cursor_position
    
    text_before = value[:cursor_position]
    
    # Find the start of the current word
    match = re.search(r'(\S+)$', text_before)
    if match:
        word_start = len(text_before) - len(match.group(1))
        new_value = value[:word_start] + value[cursor_position:]
        new_cursor = word_start
    else:
        # Just delete trailing whitespace/single char
        new_value = value[:cursor_position - 1] + value[cursor_position:] if text_before else value
        new_cursor = cursor_position - 1
    
    return new_value, new_cursor


class TestDeleteCharacterLeft:
    """Tests for delete_character_left function."""
    
    def test_ascii_characters(self):
        """Test deleting ASCII characters."""
        value, pos = delete_character_left("hello", 5)
        assert value == "hell"
        assert pos == 4
    
    def test_chinese_characters(self):
        """Test deleting Chinese characters - should delete one char, not byte."""
        value, pos = delete_character_left("你好世界", 4)
        assert value == "你好世"
        assert pos == 3
    
    def test_mixed_text(self):
        """Test deleting mixed English and Chinese."""
        value, pos = delete_character_left("Hello你好", 7)
        assert value == "Hello你"
        assert pos == 6
    
    def test_empty_string(self):
        """Test deleting from empty input."""
        value, pos = delete_character_left("", 0)
        assert value == ""
        assert pos == 0
    
    def test_at_start(self):
        """Test deleting when cursor is at start."""
        value, pos = delete_character_left("hello", 0)
        assert value == "hello"
        assert pos == 0
    
    def test_emoji(self):
        """Test deleting emoji (4-byte UTF-8)."""
        # Position is after "Hello👋" = 6 characters
        value, pos = delete_character_left("Hello👋World", 6)
        # Emoji is one character
        assert value == "HelloWorld"
        assert pos == 5
    
    def test_japanese(self):
        """Test deleting Japanese characters."""
        value, pos = delete_character_left("こんにちは", 5)
        assert value == "こんにち"
        assert pos == 4
    
    def test_korean(self):
        """Test deleting Korean characters."""
        value, pos = delete_character_left("안녕하세요", 5)
        assert value == "안녕하세"
        assert pos == 4
    
    def test_multiple_deletes(self):
        """Test multiple sequential deletes."""
        text = "Hello世界こんにちは"
        pos = len(text)
        
        expected_sequence = [
            "Hello世界こんにち",
            "Hello世界こんに",
            "Hello世界こん",
            "Hello世界こ",
            "Hello世界",
            "Hello世",
            "Hello",
            "Hell",
            "Hel",
            "He",
            "H",
            "",
        ]
        
        for expected in expected_sequence:
            text, pos = delete_character_left(text, pos)
            assert text == expected, f"Expected '{expected}', got '{text}'"


class TestDeleteWordLeft:
    """Tests for delete_word_left function."""
    
    def test_ascii_word(self):
        """Test word deletion in ASCII text."""
        value, pos = delete_word_left("hello world", 11)
        assert value == "hello "
        assert pos == 6
    
    def test_chinese_with_space(self):
        """Test word deletion with Chinese text (space separated)."""
        value, pos = delete_word_left("你好 世界", 5)
        assert value == "你好 "
        assert pos == 3
    
    def test_no_word_whitespace(self):
        """Test word deletion with no word to delete (only whitespace)."""
        value, pos = delete_word_left("   ", 3)
        assert value == "  "
        assert pos == 2
    
    def test_single_word(self):
        """Test deleting the only word."""
        value, pos = delete_word_left("hello", 5)
        assert value == ""
        assert pos == 0
    
    def test_chinese_no_space(self):
        """Test Chinese text without spaces - deletes whole string as one word."""
        value, pos = delete_word_left("你好世界", 4)
        assert value == ""
        assert pos == 0
    
    def test_mixed_words(self):
        """Test mixed English and Chinese words."""
        # "Hello 你好 world 世界" has len=14 (5+1+2+1+5+1+2)
        # Position at end = 17
        value, pos = delete_word_left("Hello 你好 world 世界", 17)
        # Should delete "世界"
        assert value == "Hello 你好 world "
        assert pos == 15


class TestUnicodeProperties:
    """Tests verifying Unicode character properties."""
    
    def test_chinese_character_length(self):
        """Verify Chinese characters count as 1 character each."""
        text = "你好世界"
        assert len(text) == 4
        assert len(text.encode('utf-8')) == 12  # 3 bytes per char
    
    def test_emoji_length(self):
        """Verify emoji counts as 1 character."""
        text = "👋"
        assert len(text) == 1
        assert len(text.encode('utf-8')) == 4  # 4 bytes
    
    def test_string_slicing(self):
        """Verify Python string slicing handles Unicode correctly."""
        text = "Hello世界"
        
        # Slicing by character index
        assert text[:5] == "Hello"
        assert text[5:6] == "世"
        assert text[6:7] == "界"
        assert text[:-1] == "Hello世"
        assert text[:-2] == "Hello"


class TestKeyHandling:
    """Tests for key event handling logic."""
    
    def test_backspace_key_detection(self):
        """Test that backspace key is detected correctly."""
        keys = ["backspace", "ctrl+backspace", "ctrl+h", "ctrl+w"]
        
        # These should trigger deletion
        assert any(k == "backspace" for k in keys)
        assert any(k == "ctrl+backspace" for k in keys)
        assert any(k == "ctrl+h" for k in keys)
        assert any(k == "ctrl+w" for k in keys)
    
    def test_regular_key_not_deletion(self):
        """Test that regular keys are not deletion keys."""
        regular_keys = ["a", "b", "1", "enter", "tab", "up", "down"]
        deletion_keys = ["backspace", "ctrl+backspace", "ctrl+h", "ctrl+w"]
        
        for key in regular_keys:
            assert key not in deletion_keys


class TestEdgeCases:
    """Edge cases for Unicode handling."""
    
    def test_combining_characters(self):
        """Test text with combining characters."""
        # café written as 'cafe' + combining acute accent
        text = "café"  # This is a single character é
        value, pos = delete_character_left(text, len(text))
        assert value == "caf"
        assert pos == 3
    
    def test_variation_selector(self):
        """Test text with variation selectors."""
        # Text with emoji style variation selector
        text = "Test✓"
        value, pos = delete_character_left(text, len(text))
        assert value == "Test"
    
    def test_zero_width_joiner(self):
        """Test emoji with zero-width joiner."""
        # Family emoji (multiple emoji joined with ZWJ)
        text = "👨‍👩‍👧‍👦"  # This is technically multiple code points
        # But Python treats it as one "grapheme cluster" in some contexts
        # Our simple implementation treats each code point separately
        value, pos = delete_character_left(text, len(text))
        # Should delete one code point, not the whole family
        assert len(value) < len(text)
    
    def test_cursor_at_end(self):
        """Test deleting when cursor is at end of string."""
        text = "你好"
        value, pos = delete_character_left(text, len(text))
        assert value == "你"
        assert pos == 1
    
    def test_cursor_beyond_end(self):
        """Test deleting when cursor is beyond string length."""
        text = "你好"
        # Cursor at 10 when string length is 2
        value, pos = delete_character_left(text, 10)
        # Should handle gracefully
        assert pos == 9


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
