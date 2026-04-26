"""Token estimation service.

OpenCode-style approach: prefer exact token counts from the backend tokenizer
when available, fall back to heuristic estimation only when necessary.

Coverage:
- llama.cpp / vLLM / Ollama: exact via /tokenize or /api/tokenize
- Cloud APIs (OpenAI/Anthropic/DeepSeek): exact via API usage field
- Fallback: heuristic (char/word/punctuation weighted)
"""

import re
from typing import Any


class TokenEstimator:
    """Estimate token counts for text.

    Tries precise backends first, falls back to heuristic.
    """

    # Approximate ratios based on OpenAI tokenizer behavior
    CHARS_PER_TOKEN = 4.0
    CODE_CHARS_PER_TOKEN = 3.5
    WORDS_PER_TOKEN = 0.75

    def __init__(self, base_url: str = "", model_name: str = ""):
        self._cache: dict[str, int] = {}
        self._base_url = base_url
        self._model_name = model_name
        self._precise: Any = None

    def _get_precise(self) -> Any:
        """Lazy-load PreciseTokenizer."""
        if self._precise is None:
            try:
                from .precise_tokenizer import get_precise_tokenizer
                self._precise = get_precise_tokenizer(self._base_url, self._model_name)
            except Exception:
                self._precise = False
        return self._precise if self._precise is not False else None

    # Provider-specific CJK token ratios (chars per token)
    PROVIDER_CJK_RATIOS: dict[str, float] = {
        "openai": 1.5,
        "anthropic": 1.3,
        "deepseek": 1.8,
        "qwen": 1.5,
        "zhipu": 1.5,
        "moonshot": 1.5,
        "baichuan": 1.5,
        "doubao": 1.5,
        "gemini": 1.5,
        "grok": 1.5,
    }

    def estimate(self, text: str, is_code: bool = False, provider: str = "") -> int:
        """Estimate token count for text.

        Priority:
        1. Precise backend tokenizer (llama.cpp / vLLM / Ollama /transformers / tiktoken)
        2. Heuristic estimation
        """
        if not text:
            return 0

        # Try precise tokenizer first
        precise = self._get_precise()
        if precise is not None:
            try:
                count = precise.count_text(text)
                if count is not None:
                    return count
            except Exception:
                pass

        # Fallback to heuristic
        return self._heuristic_estimate(text, is_code, provider)

    def estimate_messages(self, messages: list[dict[str, Any]]) -> int:
        """Estimate tokens for a list of messages.

        Tries backend message tokenization first (vLLM supports this natively),
        falls back to text rendering + overhead.
        """
        precise = self._get_precise()
        if precise is not None:
            try:
                count = precise.count_messages(messages)
                if count is not None:
                    return count
            except Exception:
                pass

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
            total += 4
        return total

    def _heuristic_estimate(self, text: str, is_code: bool = False, provider: str = "") -> int:
        """Pure heuristic estimate (original algorithm)."""
        cache_key = f"{hash(text)}:{is_code}:{provider}"
        if cache_key in self._cache:
            return self._cache[cache_key]

        cjk_chars = len(re.findall(r"[\u4e00-\u9fff\u3000-\u303f\uff00-\uffef]", text))
        cjk_ratio = cjk_chars / len(text) if text else 0

        if cjk_ratio > 0.3:
            base_ratio = self.PROVIDER_CJK_RATIOS.get(provider.lower(), 1.5)
            chars_per_token = base_ratio if not is_code else base_ratio + 0.5
        else:
            chars_per_token = self.CODE_CHARS_PER_TOKEN if is_code else self.CHARS_PER_TOKEN
        char_estimate = len(text) / chars_per_token

        words = len(text.split())
        word_estimate = words / self.WORDS_PER_TOKEN

        special_tokens = len(re.findall(r"[{}()\[\];,.<>!=+\-*/&|^~`@#$%]", text))
        whitespace_runs = len(re.findall(r"\s{2,}", text))

        estimate = int(
            char_estimate * 0.6 + word_estimate * 0.3 + (special_tokens + whitespace_runs) * 0.1
        )
        estimate = max(1, estimate)

        if len(text) < 10000:
            self._cache[cache_key] = estimate

        return estimate

    def get_budget_status(
        self, current_tokens: int, max_tokens: int, warning_threshold: float = 0.8
    ) -> dict[str, Any]:
        """Get token budget status."""
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


def get_token_estimator(base_url: str = "", model_name: str = "") -> TokenEstimator:
    """Get global token estimator.

    Args:
        base_url: Backend base URL so the estimator can try precise tokenization.
        model_name: Model name for backend-specific tokenization.
    """
    global _estimator
    if _estimator is None:
        _estimator = TokenEstimator(base_url=base_url, model_name=model_name)
    return _estimator


def estimate_tokens(text: str, is_code: bool = False) -> int:
    """Quick estimate of token count."""
    return get_token_estimator().estimate(text, is_code)
