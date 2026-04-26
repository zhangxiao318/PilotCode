"""Provider-specific error pattern detection.

Inspired by OpenCode's provider/error.ts — covers 20+ LLM providers
with regex-based context-overflow identification.
"""

import re

# OpenCode-style comprehensive overflow pattern list.
# Each entry is a compiled regex matching a specific provider's error message.
OVERFLOW_PATTERNS: list[re.Pattern[str]] = [
    # Generic / OpenAI / DeepSeek / vLLM / OpenRouter
    re.compile(r"context_length_exceeded", re.IGNORECASE),
    re.compile(r"exceeds the context window", re.IGNORECASE),
    re.compile(r"maximum context length is \d+ tokens?", re.IGNORECASE),
    re.compile(r"context window exceeded", re.IGNORECASE),
    re.compile(r"reduce the length of the messages", re.IGNORECASE),
    re.compile(r"context[_ ]length[_ ]exceeded", re.IGNORECASE),
    re.compile(r"request entity too large", re.IGNORECASE),  # HTTP 413
    # Anthropic
    re.compile(r"prompt is too long", re.IGNORECASE),
    re.compile(r"input is too long for requested model", re.IGNORECASE),
    re.compile(r"token count \d+ exceeds maximum of \d+", re.IGNORECASE),
    # Google Gemini
    re.compile(r"input token count.*exceeds the maximum", re.IGNORECASE),
    re.compile(r"total tokens.*exceeds the limit", re.IGNORECASE),
    # xAI Grok
    re.compile(r"maximum prompt length is \d+", re.IGNORECASE),
    # Groq
    re.compile(r"reduce the length of the messages", re.IGNORECASE),
    re.compile(r"context length exceeded", re.IGNORECASE),
    # Ollama
    re.compile(r"prompt too long; exceeded.*context length", re.IGNORECASE),
    re.compile(r"context length exceeded", re.IGNORECASE),
    # Mistral / Cohere / Together
    re.compile(r"exceeds the limit of \d+", re.IGNORECASE),
    re.compile(r"too many tokens", re.IGNORECASE),
    # Amazon Bedrock
    re.compile(r"input is too long for requested model", re.IGNORECASE),
    re.compile(r"validationException.*input.*too long", re.IGNORECASE),
    # Kimi / Moonshot
    re.compile(r"exceeded model token limit", re.IGNORECASE),
    re.compile(r"context length is too long", re.IGNORECASE),
    # Azure OpenAI
    re.compile(r"context length.*exceeded", re.IGNORECASE),
    re.compile(r"token limit exceeded", re.IGNORECASE),
    # Cerebras (special: 400 with empty body)
    re.compile(r"context length", re.IGNORECASE),
    # Fireworks / Perplexity / Anyscale
    re.compile(r"max_tokens.*exceeded", re.IGNORECASE),
    re.compile(r"context.*too long", re.IGNORECASE),
    # Generic fallback patterns
    re.compile(r"message is too long", re.IGNORECASE),
    re.compile(r"prompt.*too long", re.IGNORECASE),
]


def is_context_overflow(status_code: int, body_text: str, error_code: str = "") -> bool:
    """Determine whether an API response indicates a context-window overflow.

    Checks:
    1. HTTP status codes that providers use for overflow (400, 413, 422).
    2. Compiled regex patterns against the response body text.
    3. The JSON error.code field (if available).

    Args:
        status_code: HTTP status code from the response.
        body_text: Decoded response body (up to ~2000 chars is fine).
        error_code: Provider-specific error code from JSON (e.g. 'context_length_exceeded').

    Returns:
        True if this is a context-overflow error, False otherwise.
    """
    # Fast-path: status codes that are *always* overflow-related
    if status_code == 413:
        return True

    # Many providers return 400 or 422 for overflow
    if status_code not in (400, 422):
        return False

    lower_body = body_text.lower()
    lower_code = error_code.lower()

    # Check compiled regex patterns against the body text
    for pattern in OVERFLOW_PATTERNS:
        if pattern.search(body_text):
            return True

    # Also check the structured error code
    if "context_length_exceeded" in lower_code:
        return True
    if "context_window" in lower_code:
        return True
    if "too_long" in lower_code:
        return True

    return False
