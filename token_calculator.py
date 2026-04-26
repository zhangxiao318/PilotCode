#!/usr/bin/env python3
"""
Basic token calculator supporting multiple calculation methods.
"""


import re
from typing import Union


def calculate_tokens(text: str, method: str = "char") -> int:
    """
    Calculate tokens from text using specified method.
    
    Args:
        text (str): Input text to calculate tokens for
        method (str): Calculation method ('char', 'word', 'chinese_char', 'chinese_word', or 'custom')
        
    Returns:
        int: Number of tokens
        
    Raises:
        ValueError: If method is not supported
    """
    if not isinstance(text, str):
        raise TypeError("Input text must be a string")
    
    if method == "char":
        return len(text)
    elif method == "word":
        # Split by whitespace and filter out empty strings
        words = re.split(r'\s+', text.strip())
        return len([w for w in words if w])
    elif method == "chinese_char":
        # For Chinese text, count each character as one token
        return len(text)
    elif method == "chinese_word":
        # For Chinese text, use jieba to tokenize into words
        try:
            import jieba
            words = list(jieba.cut(text))
            # Remove empty strings and return count
            return len([w for w in words if w.strip()])
        except ImportError:
            # Fallback to character counting if jieba is not available
            return len(text)
    elif method == "custom":
        # Custom tokenization using regex
        # This is a simple approach: split by whitespace and punctuation
        tokens = re.findall(r'\b\w+\b', text)
        return len(tokens)
    else:
        raise ValueError(f"Unsupported method: {method}. Use 'char', 'word', 'chinese_char', 'chinese_word', or 'custom'")

def calculate_tokens_with_context(text: str, method: str = "char", context_lines: int = 0) -> dict:
    """
    Calculate tokens with additional context information.
    
    Args:
        text (str): Input text to calculate tokens for
        method (str): Calculation method ('char', 'word', or 'custom')
        context_lines (int): Number of context lines to include
        
    Returns:
        dict: Dictionary containing token count and additional info
    """
    token_count = calculate_tokens(text, method)
    
    result = {
        "token_count": token_count,
        "method": method,
        "text_length": len(text)
    }
    
    if context_lines > 0:
        lines = text.split('\n')
        if len(lines) > context_lines * 2:
            result["context"] = {
                "first_lines": '\n'.join(lines[:context_lines]),
                "last_lines": '\n'.join(lines[-context_lines:])
            }
    
    return result


# Example usage and testing
if __name__ == "__main__":
    sample_text = "Hello world! This is a sample text for token calculation."
    
    print("Sample text:", sample_text)
    print(f"Character tokens: {calculate_tokens(sample_text, 'char')}")
    print(f"Word tokens: {calculate_tokens(sample_text, 'word')}")
    print(f"Custom tokens: {calculate_tokens(sample_text, 'custom')}")
    
    # Test with context
    result = calculate_tokens_with_context(sample_text, 'word', context_lines=1)
    print(f"Result with context: {result}")
    
    # Test edge cases
    print("\nTesting edge cases:")
    empty_str = ""
    print(f"Empty string: {calculate_tokens(empty_str, 'char')}")
    
    whitespace_str = "   \t\n  "
    print(f"Only whitespace: {calculate_tokens(whitespace_str, 'word')}")
    print(f"Special characters: {calculate_tokens('Hello, world! @#$%', 'custom')}")
    
    # Test error handling
    try:
        calculate_tokens(sample_text, 'invalid_method')
    except ValueError as e:
        print(f"Error handling test: {e}")