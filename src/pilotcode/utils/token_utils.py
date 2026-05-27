"""Token utility functions for calculating and managing token usage."""

import asyncio
import tiktoken
from typing import List, Dict, Any, Union
from pilotcode.utils.model_client import Message


def count_tokens(text: str, model_name: str = "gpt-3.5-turbo") -> int:
    """Count tokens in text using tiktoken with fallback."""
    try:
        encoding = tiktoken.encoding_for_model(model_name)
        return len(encoding.encode(text))
    except Exception:
        # Fallback: approximate token count (1 token ≈ 4 characters for English text)
        return max(1, len(text) // 4)


def count_messages_tokens(
    messages: List[Union[Message, Dict[str, Any]]], model_name: str = "gpt-3.5-turbo"
) -> int:
    """Count total tokens in a list of messages."""
    total_tokens = 0
    for message in messages:
        if isinstance(message, Message):
            content = message.content or ""
            total_tokens += count_tokens(content, model_name)
            # Add role token overhead
            total_tokens += count_tokens(message.role, model_name)
        elif isinstance(message, dict):
            content = message.get("content", "") or ""
            total_tokens += count_tokens(content, model_name)
            # Add role token overhead
            role = message.get("role", "")
            total_tokens += count_tokens(role, model_name)
    return total_tokens


def estimate_context_window(model_name: str = "gpt-3.5-turbo") -> int:
    """Estimate context window size for a model."""
    from pilotcode.utils.models_config import get_model_context_window

    try:
        # First try to get from model config
        context_window = get_model_context_window(model_name)
        if context_window > 0:
            return context_window
    except Exception:
        pass

    # Fallback to default values based on model name
    if "gpt-4o" in model_name or "gpt-4-turbo" in model_name:
        return 128000
    elif "gpt-4" in model_name:
        return 8192
    elif "gpt-3.5" in model_name:
        return 4096
    else:
        # Default fallback
        return 4096


def estimate_max_tokens(model_name: str = "gpt-3.5-turbo") -> int:
    """Estimate max tokens for output generation."""
    from pilotcode.utils.models_config import get_model_max_tokens

    try:
        # Try to get from model config
        max_tokens = get_model_max_tokens(model_name)
        if max_tokens > 0:
            return max_tokens
    except Exception:
        pass

    # Fallback to default values based on model name
    if "gpt-4o" in model_name or "gpt-4-turbo" in model_name:
        return 4096
    elif "gpt-4" in model_name:
        return 4096
    elif "gpt-3.5" in model_name:
        return 4096
    else:
        # Default fallback
        return 4096


async def safe_token_count(
    text: str, model_name: str = "gpt-3.5-turbo", max_retries: int = 3
) -> int:
    """Safely count tokens with retry mechanism."""
    for attempt in range(max_retries):
        try:
            return count_tokens(text, model_name)
        except Exception:
            if attempt < max_retries - 1:
                await asyncio.sleep(0.1 * (2**attempt))  # Exponential backoff
                continue
            else:
                # If all retries fail, return fallback count
                return max(1, len(text) // 4)
    return 0


async def get_context_token_usage(
    messages: List[Union[Message, Dict[str, Any]]], model_name: str = "gpt-3.5-turbo"
) -> Dict[str, int]:
    """Get detailed context token usage statistics."""
    total_tokens = count_messages_tokens(messages, model_name)
    context_window = estimate_context_window(model_name)
    max_output_tokens = estimate_max_tokens(model_name)

    return {
        "total_tokens": total_tokens,
        "context_window": context_window,
        "max_output_tokens": max_output_tokens,
        "remaining_tokens": max(0, context_window - total_tokens),
        "usage_percentage": (
            min(100, (total_tokens / context_window) * 100) if context_window > 0 else 0
        ),
    }


def get_model_specific_tokenizer(model_name: str) -> tiktoken.Encoding:
    """Get the appropriate tokenizer for a given model."""
    try:
        return tiktoken.encoding_for_model(model_name)
    except KeyError:
        # Fallback to cl100k_base if model-specific tokenizer not available
        return tiktoken.get_encoding("cl100k_base")
