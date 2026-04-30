"""Model client for interacting with LLM APIs."""

import asyncio
import json
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any, AsyncIterator
from dataclasses import dataclass
import httpx

from .config import get_global_config
from .models_config import get_model_info
from ..provider.error_patterns import is_context_overflow

# ------------------------------------------------------------------
# Custom exceptions for LLM API errors
# ------------------------------------------------------------------


class LLMError(Exception):
    """Base class for LLM API errors."""

    def __init__(self, message: str, status_code: int | None = None, body: str | None = None):
        super().__init__(message)
        self.status_code = status_code
        self.body = body


class ContextWindowError(LLMError):
    """Raised when the request exceeds the model's context window."""

    pass


class RateLimitError(LLMError):
    """Raised when the API rate limit is exceeded (429)."""

    def __init__(
        self,
        message: str,
        status_code: int | None = None,
        body: str | None = None,
        retry_after: float | None = None,
    ):
        super().__init__(message, status_code, body)
        self.retry_after = retry_after


class AuthError(LLMError):
    """Raised on authentication/authorization failure (401/403)."""

    pass


class ServerError(LLMError):
    """Raised on server-side errors (5xx)."""

    pass


def _parse_retry_after(raw: str) -> float | None:
    """Parse a Retry-After header value.

    Supports:
    1. Seconds (e.g. "5", "120")
    2. HTTP Date (e.g. "Wed, 21 Oct 2025 07:28:00 GMT")

    Returns the delay in seconds, or None if unparseable.
    """
    # 1. Try seconds
    try:
        return float(raw)
    except ValueError:
        pass

    # 2. Try HTTP Date
    try:
        dt = parsedate_to_datetime(raw)
        return max(0.0, (dt - datetime.now(timezone.utc)).total_seconds())
    except Exception:
        pass

    return None


# Provider inference keywords mapped to canonical provider names
_PROVIDER_KEYWORDS: dict[str, str] = {
    "qwen": "qwen",
    "deepseek": "deepseek",
    "glm": "zhipu",
    "moonshot": "moonshot",
    "baichuan": "baichuan",
    "doubao": "doubao",
    "llama": "custom",
    "mistral": "custom",
    "phi": "custom",
    "gemma": "custom",
    "yi": "custom",
    "command": "custom",
}


def _infer_provider(name: str) -> str | None:
    """Infer provider from model name or path."""
    lowered = name.lower()
    for keyword, provider in _PROVIDER_KEYWORDS.items():
        if keyword in lowered:
            return provider
    return None


@dataclass
class ToolCall:
    """A tool call from the model."""

    id: str
    name: str
    arguments: dict[str, Any]


@dataclass
class ToolResult:
    """Result of a tool call."""

    tool_call_id: str
    content: str
    is_error: bool = False


@dataclass
class Message:
    """Message for API."""

    role: str  # "system", "user", "assistant", "tool"
    content: str | list[dict[str, Any]] | None = None
    tool_calls: list[ToolCall] | None = None
    tool_call_id: str | None = None
    name: str | None = None
    reasoning_content: str | None = None  # DeepSeek thinking mode requires echoing this back


class ModelClient:
    """Client for interacting with LLM APIs (OpenAI-compatible)."""

    def __init__(
        self, api_key: str | None = None, base_url: str | None = None, model: str | None = None
    ):
        # Record the event loop this client is bound to
        try:
            self._loop = asyncio.get_running_loop()
        except RuntimeError:
            self._loop = None
        config = get_global_config()

        # Determine model name: use provided, or config, or fallback
        model_key = model or config.default_model or "default"

        # For multi-model routing: if a specific model is requested and has
        # overrides in settings.json, use the per-model config.
        model_override = config.get_model_config(model_key) if model else {}
        effective_api_key = (
            api_key or model_override.get("api_key") or config.api_key or "sk-placeholder"
        )
        effective_base_url = base_url or model_override.get("base_url") or config.base_url or ""

        self.api_key = effective_api_key

        # For local models, use config directly without models.json lookup.
        # Local model config lives entirely in settings.json.
        from .config import is_local_url

        is_local = is_local_url(effective_base_url)
        if not is_local and model_key in ("ollama", "vllm"):
            is_local = True

        if is_local:
            self.model = model_key
        else:
            config_base = effective_base_url.lower()

            # Provider-aware model selection: when base_url points to a known
            # provider but default_model belongs to another, auto-correct.
            if "deepseek" in config_base and not model_key.startswith("deepseek"):
                self.model = "deepseek-v4-pro"
            elif (
                "dashscope" in config_base or "aliyun" in config_base
            ) and not model_key.startswith("qwen"):
                self.model = "qwen-max"
            else:
                # Map model key to actual API model name (e.g., "qwen" -> "qwen-max")
                model_info = get_model_info(model_key)
                if (
                    model_info
                    and model_info.default_model
                    and model_info.default_model != "default"
                ):
                    self.model = model_info.default_model
                elif model_key == "custom":
                    self.model = "default"
                else:
                    self.model = model_key

        # Determine base URL: use provided, or from config, or from model info as fallback
        self._model_info = get_model_info(model_key)
        if effective_base_url:
            self.base_url = effective_base_url
        elif self._model_info and self._model_info.base_url:
            self.base_url = self._model_info.base_url
        else:
            self.base_url = ""

        # Local models often use self-signed HTTPS certs; disable verification.
        verify_ssl = not is_local

        # Use model-specific timeout if available, otherwise default 300s
        timeout = self._model_info.timeout if self._model_info else 300.0
        if model_override and "timeout" in model_override:
            try:
                timeout = float(model_override["timeout"])
            except ValueError:
                pass

        # Use granular timeouts to prevent indefinite hangs on half-closed
        # connections (e.g. CLOSE-WAIT) while still allowing long generations.
        # read=60s means any single read operation that stalls >60s will abort.
        self.client = httpx.AsyncClient(
            base_url=self.base_url,
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
            timeout=httpx.Timeout(timeout, connect=10.0, read=300.0, write=10.0, pool=5.0),
            verify=verify_ssl,
        )

        # Provider flags for provider-specific handling
        self._provider_name = self._model_info.provider.value if self._model_info else "unknown"
        self._is_deepseek = self._provider_name == "deepseek"

    def _convert_messages(
        self, messages: list[Message] | list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Convert messages to API format.

        If messages are already API dicts they are returned as-is (after
        provider-specific field ordering for DeepSeek).
        """
        result = []
        for msg in messages:
            # Already an API dict — apply provider-specific fixes only
            if isinstance(msg, dict):
                api_msg = dict(msg)
                if (
                    self._is_deepseek
                    and api_msg.get("role") == "assistant"
                    and "reasoning_content" in api_msg
                ):
                    # Ensure reasoning_content appears before content for DeepSeek
                    rc = api_msg.pop("reasoning_content")
                    api_msg = {"role": api_msg["role"], "reasoning_content": rc, **api_msg}
                result.append(api_msg)
                continue

            api_msg: dict[str, Any] = {"role": msg.role}

            # DeepSeek thinking mode: echo reasoning_content back on assistant messages.
            # Insert immediately after role/content to satisfy provider field-order expectations.
            if self._is_deepseek and msg.reasoning_content and msg.role == "assistant":
                api_msg["reasoning_content"] = msg.reasoning_content

            # OpenAI-compatible APIs require 'content' to be present (can be empty string)
            api_msg["content"] = msg.content if msg.content is not None else ""

            if msg.tool_calls:
                api_msg["tool_calls"] = [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {"name": tc.name, "arguments": json.dumps(tc.arguments)},
                    }
                    for tc in msg.tool_calls
                ]

            if msg.tool_call_id:
                api_msg["tool_call_id"] = msg.tool_call_id
                # Do NOT add "name" here — OpenAI tool messages do not accept this field.

            result.append(api_msg)

        return result

    def _convert_tools(self, tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Convert tools to API format."""
        return [
            {
                "type": "function",
                "function": {
                    "name": tool["name"],
                    "description": tool.get("description", ""),
                    "parameters": tool.get("input_schema", {}),
                },
            }
            for tool in tools
        ]

    def _classify_error(
        self, status_code: int, body: bytes, headers: httpx.Headers | None = None
    ) -> LLMError:
        """Classify an HTTP error into a typed exception.

        Parses the response body to detect provider-specific error codes
        (e.g., OpenAI's 'context_length_exceeded', DeepSeek's variants).
        """
        text = body.decode("utf-8", errors="replace")[:2000]
        message = f"{self._provider_name.upper()} API error {status_code}: {text}"

        # Parse JSON body for structured error info
        error_code = ""
        try:
            data = json.loads(body)
            err = data.get("error", {})
            if isinstance(err, dict):
                error_code = err.get("code", "")
            elif isinstance(err, str):
                error_code = err
        except (json.JSONDecodeError, AttributeError):
            pass

        # 429 Rate Limit
        if status_code == 429:
            retry_after: float | None = None
            if headers:
                raw = headers.get("retry-after") or headers.get("x-ratelimit-reset")
                if raw:
                    retry_after = _parse_retry_after(raw)
            return RateLimitError(message, status_code, text, retry_after)

        # 401/403 Auth
        if status_code in (401, 403):
            return AuthError(message, status_code, text)

        # Context window exceeded: can be 413, 400, or 422 depending on provider
        if is_context_overflow(status_code, text, error_code):
            return ContextWindowError(message, status_code, text)

        # 5xx Server errors
        if status_code >= 500:
            return ServerError(message, status_code, text)

        # Fallback to generic LLMError for unhandled 4xx
        return LLMError(message, status_code, text)

    async def chat_completion(
        self,
        messages: list[Message] | list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        stream: bool = True,
    ) -> AsyncIterator[dict[str, Any]]:
        """Send chat completion request.

        Accepts either internal Message dataclasses or raw API dicts
        (e.g. from types.message.to_api_format).
        """
        payload = {
            "model": self.model,
            "messages": self._convert_messages(messages),
            "temperature": temperature,
            "stream": stream,
        }

        # Ask the backend to include usage in the stream (OpenAI-compatible).
        # Most modern backends (llama.cpp server, vLLM, etc.) honour this.
        if stream:
            payload["stream_options"] = {"include_usage": True}

        if tools:
            payload["tools"] = self._convert_tools(tools)
            # Only send tool_choice if the provider supports it
            supports_tool_choice = (
                self._model_info.supports_tool_choice if self._model_info else True
            )
            if supports_tool_choice:
                payload["tool_choice"] = "auto"

        if max_tokens:
            # DeepSeek reasoning models (V4, R1, etc.) emit reasoning_content
            # before the final answer.  A small max_tokens limit often
            # leaves no budget for actual content, producing empty replies.
            # Bump to a safe floor when the caller requested a small cap.
            if (
                self.model
                and "deepseek" in self.model.lower()
                and max_tokens < 4096
            ):
                max_tokens = 8192
            payload["max_tokens"] = max_tokens

        max_retries = 3
        base_delay = 1.0
        last_exception: Exception | None = None

        for attempt in range(max_retries):
            try:
                if stream:
                    async with self.client.stream(
                        "POST", "/chat/completions", json=payload
                    ) as response:
                        if response.status_code >= 400:
                            body = await response.aread()
                            raise self._classify_error(response.status_code, body, response.headers)
                        # Defensive counter: if the remote side closes the
                        # connection but aiter_lines() keeps yielding empty
                        # strings we could spin forever.  Bail after too many.
                        _empty_line_count = 0
                        _max_empty_lines = 500
                        _stream_read_timeout = 120  # seconds

                        async def _aiter_lines_with_timeout(resp, to):
                            it = resp.aiter_lines().__aiter__()
                            while True:
                                try:
                                    line = await asyncio.wait_for(it.__anext__(), timeout=to)
                                    yield line
                                except asyncio.TimeoutError:
                                    raise LLMError(
                                        f"Stream read timed out: no data received for {to}s"
                                    )
                                except StopAsyncIteration:
                                    break

                        async for line in _aiter_lines_with_timeout(response, _stream_read_timeout):
                            if not line:
                                _empty_line_count += 1
                                if _empty_line_count > _max_empty_lines:
                                    raise LLMError(
                                        "Stream broke: excessive empty lines from "
                                        "half-closed connection (CLOSE-WAIT)."
                                    )
                                continue
                            _empty_line_count = 0
                            if line.startswith("data: "):
                                data = line[6:]
                                if data == "[DONE]":
                                    break
                                try:
                                    chunk = json.loads(data)
                                    # Check for API errors embedded in stream
                                    if chunk.get("error"):
                                        err_msg = chunk["error"]
                                        if isinstance(err_msg, dict):
                                            code = err_msg.get("code", "")
                                            msg = err_msg.get("message", str(err_msg))
                                        else:
                                            code = ""
                                            msg = str(err_msg)
                                        raise self._classify_error(
                                            400,
                                            json.dumps(
                                                {"error": {"code": code, "message": msg}}
                                            ).encode(),
                                        )
                                    yield chunk
                                except json.JSONDecodeError:
                                    continue
                    return
                else:
                    response = await self.client.post("/chat/completions", json=payload)
                    try:
                        response.raise_for_status()
                    except httpx.HTTPStatusError as exc:
                        body = await response.aread()
                        raise self._classify_error(
                            response.status_code, body, response.headers
                        ) from exc
                    data = response.json()

                    # Yield as a single chunk, preserving usage when available
                    api_choices = data.get("choices") or []
                    api_choice = api_choices[0] if api_choices else {}
                    api_message = api_choice.get("message") or {}
                    chunk: dict[str, Any] = {
                        "choices": [
                            {
                                "delta": api_message,
                                "finish_reason": api_choice.get("finish_reason"),
                            }
                        ]
                    }
                    if "usage" in data:
                        chunk["usage"] = data["usage"]
                    yield chunk
                    return
            except Exception as exc:
                last_exception = exc
                # Retry only on server errors and transient network issues.
                # ContextWindowError, RateLimitError, and AuthError are
                # forwarded immediately so callers can handle them specifically.
                is_retryable = isinstance(
                    exc,
                    (ServerError, httpx.ConnectError, httpx.TimeoutException, httpx.NetworkError),
                )
                if not is_retryable or attempt == max_retries - 1:
                    raise
                delay = base_delay * (2**attempt)
                await asyncio.sleep(delay)
        if last_exception:
            raise last_exception

    async def fetch_model_capabilities(self) -> dict[str, Any] | None:
        """Fetch model capabilities from the API.

        Probes multiple backend-specific endpoints to get actual model metadata
        (context window, max tokens, etc.) rather than relying on static
        configuration. Supports llama-server, vLLM, Ollama, TGI, LiteLLM,
        and standard OpenAI-compatible endpoints.

        Returns:
            Dict with capability info. If the API doesn't expose metadata,
            returns a dict with ``_error`` key explaining why (connection
            refused, SSL error, timeout, etc.) so callers can surface the
            reason to the user.
        """
        import asyncio

        cap: dict[str, Any] = {}
        last_error: str | None = None

        # Derive root URL (strip trailing /v1 so we can hit backend-specific
        # endpoints like /props or /api/show).
        base = str(self.client.base_url).rstrip("/")
        root_url = base
        if root_url.endswith("/v1"):
            root_url = root_url[:-3]

        # ------------------------------------------------------------------
        # 1. llama.cpp / llama-server  ->  GET /props
        #    Returns: default_generation_settings.n_ctx, model_path, etc.
        # ------------------------------------------------------------------
        try:
            resp = await self.client.get(f"{root_url}/props", timeout=5.0, follow_redirects=True)
            if resp.status_code == 200:
                data = resp.json()
                dgs = data.get("default_generation_settings", {})
                n_ctx = dgs.get("n_ctx")
                if n_ctx is not None:
                    cap["context_window"] = int(n_ctx)
                # max_tokens from params (llama-server uses -1 for infinite)
                params = dgs.get("params", {})
                max_tok = params.get("max_tokens", params.get("n_predict"))
                if max_tok is not None and max_tok > 0:
                    cap["max_tokens"] = int(max_tok)
                # vision from modalities
                modalities = data.get("modalities", {})
                if "vision" in modalities:
                    cap["supports_vision"] = bool(modalities["vision"])
                # model path gives us display name hint
                model_path = data.get("model_path")
                if model_path:
                    cap["display_name"] = Path(model_path).stem
                    inferred = _infer_provider(cap["display_name"])
                    if inferred:
                        cap["_provider"] = inferred
                if "_provider" not in cap:
                    cap["_provider"] = "custom"
                cap["_backend"] = "llama-server"
        except Exception as e:
            last_error = f"llama-server /props: {type(e).__name__}: {e}"

        # ------------------------------------------------------------------
        # 2. Ollama  ->  POST /api/show
        #    Returns: model_info.{family}.context_length
        # ------------------------------------------------------------------
        if "context_window" not in cap:
            try:
                resp = await self.client.post(
                    f"{root_url}/api/show",
                    json={"model": self.model},
                    timeout=5.0,
                    follow_redirects=True,
                )
                if resp.status_code == 200:
                    data = resp.json()
                    model_info = data.get("model_info", {})
                    details = data.get("details", {})
                    family = details.get("family", "")
                    # Try family-specific context length key
                    if family:
                        ctx_key = f"{family}.context_length"
                        val = model_info.get(ctx_key)
                        if val is not None:
                            cap["context_window"] = int(val)
                    # Fallback: any key ending with context_length
                    if "context_window" not in cap:
                        for k, v in model_info.items():
                            if k.endswith(".context_length") and v is not None:
                                cap["context_window"] = int(v)
                                break
                    # Ollama capabilities array
                    capabilities = data.get("capabilities", [])
                    cap["supports_vision"] = "vision" in capabilities
                    # display name from Ollama details
                    details = data.get("details", {})
                    ollama_name = details.get("name") or details.get("model")
                    if ollama_name:
                        cap["display_name"] = ollama_name
                    cap["_provider"] = "ollama"
                    cap["_backend"] = "ollama"
            except Exception as e:
                last_error = f"Ollama /api/show: {type(e).__name__}: {e}"

        # ------------------------------------------------------------------
        # 3. LiteLLM proxy  ->  GET /model/info
        # ------------------------------------------------------------------
        if "context_window" not in cap:
            try:
                resp = await self.client.get(
                    f"{root_url}/model/info", timeout=5.0, follow_redirects=True
                )
                if resp.status_code == 200:
                    data = resp.json()
                    mi = data.get("model_info", {})
                    # Try exact model name, then first match
                    info = mi.get(self.model) or next(iter(mi.values()), None)
                    if isinstance(info, dict):
                        ctx = info.get("max_input_tokens") or info.get("max_tokens")
                        if ctx is not None:
                            cap["context_window"] = int(ctx)
                        out = info.get("max_output_tokens")
                        if out is not None:
                            cap["max_tokens"] = int(out)
                        if "supports_vision" in info:
                            cap["supports_vision"] = bool(info["supports_vision"])
                        cap["_backend"] = "litellm"
            except Exception as e:
                last_error = f"LiteLLM /model/info: {type(e).__name__}: {e}"

        # ------------------------------------------------------------------
        # 4. Standard OpenAI-compatible  ->  GET /v1/models / /models/{id}
        #    (vLLM, TGI, SGLang, cloud providers, etc.)
        # ------------------------------------------------------------------
        if "context_window" not in cap or "max_tokens" not in cap:
            model_data = None
            # Build candidate endpoints.  If base_url already ends in /v1 the
            # httpx client resolves /v1/models correctly; otherwise many
            # backends (vLLM, TGI, etc.) only expose the /v1 prefix.
            base_has_v1 = str(self.client.base_url).rstrip("/").endswith("/v1")
            candidates: list[str] = []
            for prefix in [""] if base_has_v1 else ["/v1", ""]:
                candidates.append(f"{prefix}/models/{self.model}")
                candidates.append(f"{prefix}/models")
            # Deduplicate while preserving order
            seen = set()
            endpoints = []
            for e in candidates:
                if e not in seen:
                    seen.add(e)
                    endpoints.append(e)

            for endpoint in endpoints:
                try:
                    resp = await self.client.get(endpoint, timeout=5.0)
                    if resp.status_code == 200:
                        data = resp.json()
                        if endpoint.endswith("/models"):
                            models = data.get("data", [])
                            for m in models:
                                if m.get("id") == self.model:
                                    model_data = m
                                    break
                            # Fallback: if no exact match, take the first model
                            if model_data is None and models:
                                model_data = models[0]
                        else:
                            model_data = data
                        break
                except (
                    httpx.HTTPStatusError,
                    httpx.RequestError,
                    json.JSONDecodeError,
                    asyncio.TimeoutError,
                ) as e:
                    last_error = f"OpenAI-compatible {endpoint}: {type(e).__name__}: {e}"
                    continue

            if model_data:
                # Detect known cloud providers from metadata
                owned_by = model_data.get("owned_by", "")
                root = model_data.get("root", "")
                if owned_by == "vllm" or "vllm" in str(root).lower():
                    cap["_provider"] = "vllm"
                    cap["_backend"] = "vllm"
                elif owned_by == "deepseek":
                    cap["_provider"] = "deepseek"
                    cap["_backend"] = "deepseek"

                # context window
                if "context_window" not in cap:
                    for key in (
                        "context_length",
                        "context_window",
                        "max_model_len",
                        "max_context_length",
                        "num_ctx",
                        "n_ctx",
                    ):
                        val = model_data.get(key)
                        if val is not None:
                            try:
                                cap["context_window"] = int(val)
                                break
                            except (ValueError, TypeError):
                                pass
                    if "context_window" not in cap:
                        for nested_key in ("meta", "info", "details", "capabilities"):
                            nested = model_data.get(nested_key)
                            if isinstance(nested, dict):
                                for key in (
                                    "context_length",
                                    "context_window",
                                    "max_model_len",
                                    "max_context_length",
                                    "num_ctx",
                                    "n_ctx",
                                ):
                                    val = nested.get(key)
                                    if val is not None:
                                        try:
                                            cap["context_window"] = int(val)
                                            break
                                        except (ValueError, TypeError):
                                            pass
                            if "context_window" in cap:
                                break

                # max tokens
                if "max_tokens" not in cap:
                    for key in ("max_tokens", "max_output_tokens", "max_new_tokens"):
                        val = model_data.get(key)
                        if val is not None:
                            try:
                                cap["max_tokens"] = int(val)
                                break
                            except (ValueError, TypeError):
                                pass
                    if "max_tokens" not in cap:
                        for nested_key in ("meta", "info", "details", "capabilities"):
                            nested = model_data.get(nested_key)
                            if isinstance(nested, dict):
                                for key in ("max_tokens", "max_output_tokens", "max_new_tokens"):
                                    val = nested.get(key)
                                    if val is not None:
                                        try:
                                            cap["max_tokens"] = int(val)
                                            break
                                        except (ValueError, TypeError):
                                            pass
                            if "max_tokens" in cap:
                                break

                # tool / vision support
                if "supports_tools" not in cap:
                    for key in ("supports_tools", "supports_function_calling", "tool_call"):
                        val = model_data.get(key)
                        if val is not None:
                            cap["supports_tools"] = bool(val)
                            break
                    if "supports_tools" not in cap:
                        for nested_key in ("meta", "info", "details", "capabilities"):
                            nested = model_data.get(nested_key)
                            if isinstance(nested, dict):
                                for key in (
                                    "supports_tools",
                                    "supports_function_calling",
                                    "tool_call",
                                ):
                                    val = nested.get(key)
                                    if val is not None:
                                        cap["supports_tools"] = bool(val)
                                        break
                            if "supports_tools" in cap:
                                break

                if "supports_vision" not in cap:
                    for key in ("supports_vision", "vision", "multimodal"):
                        val = model_data.get(key)
                        if val is not None:
                            cap["supports_vision"] = bool(val)
                            break
                    if "supports_vision" not in cap:
                        for nested_key in ("meta", "info", "details", "capabilities"):
                            nested = model_data.get(nested_key)
                            if isinstance(nested, dict):
                                for key in ("supports_vision", "vision", "multimodal"):
                                    val = nested.get(key)
                                    if val is not None:
                                        cap["supports_vision"] = bool(val)
                                        break
                            if "supports_vision" in cap:
                                break

                # display name and model id from API response
                if model_data:
                    model_id = model_data.get("id")
                    if model_id:
                        cap["model_id"] = model_id
                        if "display_name" not in cap:
                            cap["display_name"] = model_id

                if "_backend" not in cap:
                    cap["_backend"] = "openai-compatible"

        # Fallback provider inference from display name
        if "_provider" not in cap and cap.get("display_name"):
            inferred = _infer_provider(cap["display_name"])
            if inferred:
                cap["_provider"] = inferred

        # ------------------------------------------------------------------
        # Universal fallback: if the API didn't expose capability fields,
        # back-fill from the static models.json configuration.
        # This applies to all cloud providers (deepseek, openai, qwen, etc.)
        # whose /models endpoint may be sparse.
        # ------------------------------------------------------------------
        from .models_config import get_model_info

        static = get_model_info(self.model)
        if static:
            if "context_window" not in cap and static.context_window:
                cap["context_window"] = static.context_window
            if "max_tokens" not in cap and static.max_tokens:
                cap["max_tokens"] = static.max_tokens
            if "supports_tools" not in cap:
                cap["supports_tools"] = static.supports_tools
            if "supports_vision" not in cap:
                cap["supports_vision"] = static.supports_vision
            if "supports_tool_choice" not in cap:
                cap["supports_tool_choice"] = static.supports_tool_choice
            if "display_name" not in cap and static.display_name:
                cap["display_name"] = static.display_name
            if "timeout" not in cap and static.timeout:
                cap["timeout"] = static.timeout

        if cap:
            return cap
        if last_error:
            return {"_error": last_error}
        return None

    async def close(self) -> None:
        """Close the client."""
        await self.client.aclose()


# Global client
_client: ModelClient | None = None


def get_model_client(
    api_key: str | None = None, base_url: str | None = None, model: str | None = None
) -> ModelClient:
    """Get or create model client.

    If no parameters are provided, uses configuration from settings.
    Recreates the client if the event loop has changed (prevents 'Event loop is closed').
    """
    global _client

    # Check if we need a new client because the event loop changed
    try:
        current_loop = asyncio.get_running_loop()
    except RuntimeError:
        current_loop = None

    if _client is None or getattr(_client, "_loop", None) != current_loop:
        # Prevent the old client's connection pool from trying to close
        # on a dead event loop during garbage collection (causes
        # RuntimeError: Event loop is closed).
        if _client is not None:
            _client.client = None  # type: ignore[assignment]
        _client = ModelClient(api_key, base_url, model)
    return _client
