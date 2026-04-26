"""Precise token counting using backend tokenizers.

OpenCode-style approach: prefer exact token counts from the actual backend
rather than heuristic estimates. Coverage by backend:

| Backend       | Tokenize Endpoint        | Accuracy | Notes                                  |
|---------------|--------------------------|----------|----------------------------------------|
| llama.cpp     | POST /tokenize           | Exact    | Native endpoint, always available      |
| vLLM          | POST /tokenize           | Exact    | Native endpoint (not /v1/tokenize)     |
| Ollama        | POST /api/tokenize       | Exact    | Requires Ollama >= 0.6 (PR #12030)     |
| OpenAI        | N/A                      | Offline  | tiktoken cl100k_base                   |
| Anthropic     | N/A                      | Offline  | transformers.AutoTokenizer fallback    |
| DeepSeek      | N/A                      | Offline  | transformers.AutoTokenizer fallback    |
| Other cloud   | N/A                      | Offline  | transformers or tiktoken fallback      |

For cloud providers without a tokenize endpoint, we fall back to:
1. transformers.AutoTokenizer (most accurate if model is known)
2. tiktoken (good for OpenAI-compatible tokenizers)
3. Heuristic estimator (len/4, last resort)
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)


class PreciseTokenizer:
    """Exact token counter that tries multiple backends.

    Caches /tokenize results to avoid hammering the backend with repeated
    identical requests.
    """

    def __init__(self, base_url: str = "", model_name: str = ""):
        self.base_url = base_url.rstrip("/")
        self.model_name = model_name
        self._transformers_tokenizer: Any = None
        self._tiktoken_encoder: Any = None
        self._cache: dict[str, int] = {}
        self._cache_max_size = 200

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def count_text(self, text: str) -> int | None:
        """Count tokens in a single text string.

        Returns exact count if any backend succeeds, else None.
        Results are cached to avoid repeated HTTP requests.
        """
        if not text:
            return 0

        cache_key = f"t:{hash(text)}"
        if cache_key in self._cache:
            return self._cache[cache_key]

        # Try backends in order
        result = (
            self._try_llamacpp_tokenize(text)
            or self._try_vllm_tokenize(text)
            or self._try_ollama_tokenize(text)
            or self._try_transformers(text)
            or self._try_tiktoken(text)
        )

        if result is not None:
            self._cache[cache_key] = result
            self._prune_cache()
        return result

    def _prune_cache(self):
        """Keep cache under max size (LRU-style by Python 3.7+ dict ordering)."""
        while len(self._cache) > self._cache_max_size:
            self._cache.pop(next(iter(self._cache)))

    def count_messages(self, messages: list[dict[str, Any]]) -> int | None:
        """Count tokens for a list of chat messages.

        For local backends (vLLM, llama.cpp), we can send the messages array
        directly to /tokenize and the backend applies the chat template.
        For others, we approximate by rendering ChatML and counting text.
        """
        return self.count_messages_with_tools(messages, tools=None)

    def count_messages_with_tools(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
    ) -> int | None:
        """Count tokens for messages + optional tools.

        vLLM supports ``tools`` directly in its /tokenize endpoint, giving
        an exact count of the full prompt including tool schemas.
        llama.cpp does not support tools in /tokenize, so we tokenize the
        messages and add the JSON-serialized tool schema on top.
        """
        if not messages and not tools:
            return 0

        # vLLM supports messages + tools together
        vllm_result = self._try_vllm_count_messages(messages, tools=tools)
        if vllm_result is not None:
            return vllm_result

        # llama.cpp: messages only, then add tools separately
        llama_result = self._try_llamacpp_count_messages(messages)
        if llama_result is not None:
            if tools:
                tool_tokens = self._count_tools_json(tools)
                if tool_tokens is not None:
                    llama_result += tool_tokens
            return llama_result

        # Ollama: same as llama.cpp
        ollama_result = self._try_ollama_count_messages(messages)
        if ollama_result is not None:
            if tools:
                tool_tokens = self._count_tools_json(tools)
                if tool_tokens is not None:
                    ollama_result += tool_tokens
            return ollama_result

        # Fallback: concatenate with delimiters and count as text
        text_parts = []
        for msg in messages:
            role = msg.get("role", "")
            content = msg.get("content", "")
            if isinstance(content, list):
                content = "\n".join(
                    str(block.get("text", "")) for block in content if isinstance(block, dict)
                )
            text_parts.append(f"{role}: {content}")
        if tools:
            try:
                import json

                text_parts.append(f"tools: {json.dumps(tools, ensure_ascii=False)}")
            except Exception:
                pass
        combined = "\n".join(text_parts)

        result = self.count_text(combined)
        if result is not None:
            return result + len(messages) * 4
        return None

    def _count_tools_json(self, tools: list[dict[str, Any]]) -> int | None:
        """Count tokens for tool schemas by serializing to JSON and tokenizing."""
        try:
            import json

            schema = json.dumps(tools, ensure_ascii=False)
            return self.count_text(schema)
        except Exception:
            return None

    # ------------------------------------------------------------------
    # llama.cpp
    # ------------------------------------------------------------------

    def _try_llamacpp_tokenize(self, text: str) -> int | None:
        if not self.base_url:
            return None
        root_url = self.base_url
        if root_url.endswith("/v1"):
            root_url = root_url[:-3]
        try:
            import httpx

            with httpx.Client(timeout=5.0) as client:
                resp = client.post(f"{root_url}/tokenize", json={"content": text})
                if resp.status_code == 200:
                    data = resp.json()
                    tokens = data.get("tokens")
                    if isinstance(tokens, list):
                        return len(tokens)
        except Exception as exc:
            logger.debug("llama.cpp /tokenize failed: %s", exc)
        return None

    def _try_llamacpp_count_messages(self, messages: list[dict[str, Any]]) -> int | None:
        if not self.base_url:
            return None
        # Render to ChatML-like format
        rendered = []
        for msg in messages:
            role = msg.get("role", "")
            content = msg.get("content", "")
            if isinstance(content, list):
                content = "\n".join(
                    str(block.get("text", "")) for block in content if isinstance(block, dict)
                )
            rendered.append(f"<|im_start|>{role}\n{content}<|im_end|>")
        rendered.append("<|im_start|>assistant")
        return self._try_llamacpp_tokenize("\n".join(rendered))

    # ------------------------------------------------------------------
    # vLLM
    # ------------------------------------------------------------------

    def _try_vllm_tokenize(self, text: str) -> int | None:
        if not self.base_url:
            return None
        root_url = self.base_url
        if root_url.endswith("/v1"):
            root_url = root_url[:-3]
        try:
            import httpx

            with httpx.Client(timeout=5.0) as client:
                resp = client.post(
                    f"{root_url}/tokenize",
                    json={"prompt": text, "model": self.model_name or "default"},
                )
                if resp.status_code == 200:
                    data = resp.json()
                    count = data.get("count")
                    if isinstance(count, int):
                        return count
                    tokens = data.get("tokens")
                    if isinstance(tokens, list):
                        return len(tokens)
        except Exception as exc:
            logger.debug("vLLM /tokenize failed: %s", exc)
        return None

    def _try_vllm_count_messages(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
    ) -> int | None:
        if not self.base_url:
            return None
        root_url = self.base_url
        if root_url.endswith("/v1"):
            root_url = root_url[:-3]
        try:
            import httpx

            payload: dict[str, Any] = {
                "messages": messages,
                "model": self.model_name or "default",
            }
            if tools:
                payload["tools"] = tools
            with httpx.Client(timeout=5.0) as client:
                resp = client.post(f"{root_url}/tokenize", json=payload)
                if resp.status_code == 200:
                    data = resp.json()
                    count = data.get("count")
                    # vLLM returns count; llama.cpp ignores 'messages' and returns empty tokens.
                    # Distinguish by checking count presence (vLLM specific).
                    if isinstance(count, int) and count > 0:
                        return count
                    # If count is present but 0, this is likely llama.cpp masquerading as vLLM.
                    if "count" in data:
                        return None
                    tokens = data.get("tokens")
                    if isinstance(tokens, list) and len(tokens) > 0:
                        return len(tokens)
        except Exception as exc:
            logger.debug("vLLM /tokenize (messages) failed: %s", exc)
        return None

    # ------------------------------------------------------------------
    # Ollama
    # ------------------------------------------------------------------

    def _try_ollama_tokenize(self, text: str) -> int | None:
        if not self.base_url:
            return None
        root_url = self.base_url
        if root_url.endswith("/v1"):
            root_url = root_url[:-3]
        try:
            import httpx

            with httpx.Client(timeout=5.0) as client:
                resp = client.post(
                    f"{root_url}/api/tokenize",
                    json={
                        "model": self.model_name or "default",
                        "prompt": text,
                    },
                )
                if resp.status_code == 200:
                    data = resp.json()
                    tokens = data.get("tokens")
                    if isinstance(tokens, list):
                        return len(tokens)
        except Exception as exc:
            logger.debug("Ollama /api/tokenize failed: %s", exc)
        return None

    def _try_ollama_count_messages(self, messages: list[dict[str, Any]]) -> int | None:
        # Ollama /api/tokenize takes a raw prompt; we'd need to render the chat template.
        # For now, use the same ChatML approximation as llama.cpp.
        if not self.base_url:
            return None
        rendered = []
        for msg in messages:
            role = msg.get("role", "")
            content = msg.get("content", "")
            if isinstance(content, list):
                content = "\n".join(
                    str(block.get("text", "")) for block in content if isinstance(block, dict)
                )
            rendered.append(f"<|im_start|>{role}\n{content}<|im_end|>")
        rendered.append("<|im_start|>assistant")
        return self._try_ollama_tokenize("\n".join(rendered))

    # ------------------------------------------------------------------
    # Offline fallbacks
    # ------------------------------------------------------------------

    def _try_transformers(self, text: str) -> int | None:
        if self._transformers_tokenizer is None:
            try:
                from transformers import AutoTokenizer

                model_name = self._infer_hf_model_name()
                if model_name:
                    self._transformers_tokenizer = AutoTokenizer.from_pretrained(
                        model_name, trust_remote_code=True
                    )
                    logger.info("Loaded transformers tokenizer: %s", model_name)
            except Exception as exc:
                logger.debug("transformers tokenizer not available: %s", exc)
                self._transformers_tokenizer = False  # type: ignore[assignment]

        if self._transformers_tokenizer is False:
            return None

        try:
            tokens = self._transformers_tokenizer.encode(text, add_special_tokens=False)
            return len(tokens)
        except Exception as exc:
            logger.debug("transformers tokenization failed: %s", exc)
            return None

    def _try_tiktoken(self, text: str) -> int | None:
        if self._tiktoken_encoder is None:
            try:
                import tiktoken

                self._tiktoken_encoder = tiktoken.get_encoding("cl100k_base")
                logger.info("Loaded tiktoken encoder: cl100k_base")
            except Exception as exc:
                logger.debug("tiktoken not available: %s", exc)
                self._tiktoken_encoder = False  # type: ignore[assignment]

        if self._tiktoken_encoder is False:
            return None

        try:
            tokens = self._tiktoken_encoder.encode(text)
            return len(tokens)
        except Exception as exc:
            logger.debug("tiktoken encoding failed: %s", exc)
            return None

    def _infer_hf_model_name(self) -> str | None:
        if self.base_url:
            root_url = self.base_url
            if root_url.endswith("/v1"):
                root_url = root_url[:-3]
            try:
                import httpx

                with httpx.Client(timeout=3.0) as client:
                    # Try llama.cpp /props first
                    resp = client.get(f"{root_url}/props")
                    if resp.status_code == 200:
                        data = resp.json()
                        model_path = data.get("model_path", "")
                        if model_path:
                            return self._map_model_path_to_hf(model_path)
            except Exception:
                pass
        return None

    @staticmethod
    def _map_model_path_to_hf(model_path: str) -> str | None:
        path_lower = model_path.lower()
        if "qwen3-coder" in path_lower:
            return "Qwen/Qwen3-Coder-30B-A3B"
        if "qwen3" in path_lower:
            return "Qwen/Qwen3-30B-A3B"
        if "qwen2.5-coder" in path_lower:
            return "Qwen/Qwen2.5-Coder-32B-Instruct"
        if "llama-3" in path_lower or "llama3" in path_lower:
            return "meta-llama/Meta-Llama-3-8B-Instruct"
        if "deepseek" in path_lower:
            return "deepseek-ai/DeepSeek-V3"
        return None


# Global instance cache
_tokenizer_instances: dict[str, PreciseTokenizer] = {}


def get_precise_tokenizer(base_url: str = "", model_name: str = "") -> PreciseTokenizer:
    """Get or create a PreciseTokenizer for the given base URL."""
    key = f"{base_url or 'default'}#{model_name or 'default'}"
    if key not in _tokenizer_instances:
        _tokenizer_instances[key] = PreciseTokenizer(base_url=base_url, model_name=model_name)
    return _tokenizer_instances[key]
