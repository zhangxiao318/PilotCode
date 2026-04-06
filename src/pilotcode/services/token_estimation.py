"""Token estimation service.

Provides accurate token counting without external dependencies.
Uses a hybrid approach:
1. Character-based approximation for quick estimates
2. Word-based counting for better accuracy
3. Special handling for code (punctuation heavy)
"""

import re
from typing import Any


class TokenEstimator:
    """Estimate token counts for text."""

    # Approximate ratios based on OpenAI tokenizer behavior
    CHARS_PER_TOKEN = 4.0  # Average case
    CODE_CHARS_PER_TOKEN = 3.5  # Code has more punctuation
    WORDS_PER_TOKEN = 0.75  # Most words are ~1.33 tokens

    def __init__(self):
        self._cache: dict[str, int] = {}

    def estimate(self, text: str, is_code: bool = False) -> int:
        """Estimate token count for text.

        Args:
            text: Input text
            is_code: Whether text is code (affects punctuation handling)

        Returns:
            Estimated token count
        """
        if not text:
            return 0

        # Check cache for short texts
        cache_key = f"{hash(text)}:{is_code}"
        if cache_key in self._cache:
            return self._cache[cache_key]

        # Method 1: Character count
        chars_per_token = self.CODE_CHARS_PER_TOKEN if is_code else self.CHARS_PER_TOKEN
        char_estimate = len(text) / chars_per_token

        # Method 2: Word count
        words = len(text.split())
        word_estimate = words / self.WORDS_PER_TOKEN

        # Method 3: Count special tokens (punctuation, whitespace runs)
        special_tokens = len(re.findall(r"[{}()\[\];,.<>!=+\-*/&|^~`@#$%]", text))
        whitespace_runs = len(re.findall(r"\s{2,}", text))

        # Weighted combination (character-based is most reliable)
        estimate = int(
            char_estimate * 0.6 + word_estimate * 0.3 + (special_tokens + whitespace_runs) * 0.1
        )

        # Ensure minimum of 1 token for non-empty text
        estimate = max(1, estimate)

        # Cache for short texts
        if len(text) < 10000:
            self._cache[cache_key] = estimate

        return estimate

    def estimate_messages(self, messages: list[dict[str, Any]]) -> int:
        """Estimate tokens for a list of messages.

        Accounts for message formatting overhead (~4 tokens per message).
        """
        total = 0
        for msg in messages:
            content = msg.get("content", "")
            if isinstance(content, str):
                total += self.estimate(content)
            elif isinstance(content, list):
                for block in content:
                    if isinstance(block, dict):
                        text = block.get("text", "")
                        total += self.estimate(text)
            # Message overhead
            total += 4
        return total

    def get_budget_status(
        self, current_tokens: int, max_tokens: int, warning_threshold: float = 0.8
    ) -> dict[str, Any]:
        """Get token budget status.

        Returns:
            Dict with remaining, used_percentage, status
        """
        remaining = max_tokens - current_tokens
        used_percentage = current_tokens / max_tokens

        if used_percentage >= 1.0:
            status = "exceeded"
        elif used_percentage >= warning_threshold:
            status = "warning"
        elif used_percentage >= warning_threshold * 0.5:
            status = "caution"
        else:
            status = "ok"

        return {
            "current": current_tokens,
            "max": max_tokens,
            "remaining": remaining,
            "used_percentage": used_percentage,
            "status": status,
        }


# Global estimator
_estimator: TokenEstimator | None = None


def get_token_estimator() -> TokenEstimator:
    """Get global token estimator."""
    global _estimator
    if _estimator is None:
        _estimator = TokenEstimator()
    return _estimator


def estimate_tokens(text: str, is_code: bool = False) -> int:
    """Quick estimate of token count."""
    return get_token_estimator().estimate(text, is_code)
