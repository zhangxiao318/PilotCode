#!/usr/bin/env python3
"""
Test script for Chinese token calculation methods.
"""

from token_calculator import calculate_tokens

# Test Chinese text
chinese_text = "这是一个测试文本，用于测试中文分词和字符计数。"

print("Testing Chinese token calculation methods:")
print(f"Text: {chinese_text}")
print(f"Character tokens: {calculate_tokens(chinese_text, 'chinese_char')}")
print(f"Word tokens (using jieba): {calculate_tokens(chinese_text, 'chinese_word')}")

# Test with English text to ensure existing functionality still works
english_text = "This is a test text for token calculation."
print(f"\nTesting English text:")
print(f"Text: {english_text}")
print(f"Character tokens: {calculate_tokens(english_text, 'char')}")
print(f"Word tokens: {calculate_tokens(english_text, 'word')}")
print(f"Custom tokens: {calculate_tokens(english_text, 'custom')}")