"""Model client for interacting with LLM APIs."""

import asyncio
import json
from pathlib import Path
from typing import Any, AsyncIterator
from dataclasses import dataclass
import httpx

from .config import get_global_config
from .models_config import get_model_info

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

        self.api_key = api_key or config.api_key or "sk-placeholder"

        # Determine model name: use provided, or config, or fallback
        model_key = model or config.default_model or "default"

        # For local models, use config directly without models.json lookup.
        # Local model config lives entirely in settings.json.
        from .config import is_local_url

        is_local = is_local_url(config.base_url or "")
        if is_local:
            self.model = model_key
        else:
            # Map model key to actual API model name (e.g., "qwen" -> "qwen-max")
            model_info = get_model_info(model_key)
            if model_info and model_info.default_model and model_info.default_model != "default":
                self.model = model_info.default_model
            elif model_key == "custom":
                # For custom models, detect provider from base_url
                config_base = config.base_url or ""
                if "dashscope" in config_base.lower() or "aliyun" in config_base.lower():
                    self.model = "qwen-max"  # Alibaba DashScope
                elif "deepseek" in config_base.lower():
                    self.model = "deepseek-chat"
                else:
                    self.model = "default"  # Fallback
            else:
                self.model = model_key

        # Determine base URL: use provided, or from config, or from model info as fallback
        if base_url:
            self.base_url = base_url
        elif config.base_url:
            # Respect user's explicit configuration first
            self.base_url = config.base_url
        elif model_info and model_info.base_url:
            # Use model-specific base URL as fallback
            self.base_url = model_info.base_url
        else:
            self.base_url = ""

        self.client = httpx.AsyncClient(
            base_url=self.base_url,
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
            timeout=300.0,
        )

    def _convert_messages(self, messages: list[Message]) -> list[dict[str, Any]]:
        """Convert messages to API format."""
        result = []
        for msg in messages:
            api_msg: dict[str, Any] = {"role": msg.role}

            if msg.content is not None:
                api_msg["content"] = msg.content

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
                api_msg["name"] = msg.name

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

    async def chat_completion(
        self,
        messages: list[Message],
        tools: list[dict[str, Any]] | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        stream: bool = True,
    ) -> AsyncIterator[dict[str, Any]]:
        """Send chat completion request."""
        payload = {
            "model": self.model,
            "messages": self._convert_messages(messages),
            "temperature": temperature,
            "stream": stream,
        }

        if tools:
            payload["tools"] = self._convert_tools(tools)
            payload["tool_choice"] = "auto"

        if max_tokens:
            payload["max_tokens"] = max_tokens

        if stream:
            async with self.client.stream("POST", "/chat/completions", json=payload) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if line.startswith("data: "):
                        data = line[6:]
                        if data == "[DONE]":
                            break
                        try:
                            chunk = json.loads(data)
                            # Check for API errors
                            if chunk.get("error"):
                                raise Exception(f"API Error: {chunk['error']}")
                            yield chunk
                        except json.JSONDecodeError:
                            continue
        else:
            response = await self.client.post("/chat/completions", json=payload)
            response.raise_for_status()
            data = response.json()

            # Yield as a single chunk
            yield {
                "choices": [
                    {
                        "delta": data["choices"][0]["message"],
                        "finish_reason": data["choices"][0].get("finish_reason"),
                    }
                ]
            }

    async def fetch_model_capabilities(self) -> dict[str, Any] | None:
        """Fetch model capabilities from the API.

        Probes multiple backend-specific endpoints to get actual model metadata
        (context window, max tokens, etc.) rather than relying on static
        configuration. Supports llama-server, vLLM, Ollama, TGI, LiteLLM,
        and standard OpenAI-compatible endpoints.

        Returns:
            Dict with capability info, or None if the API doesn't expose it.
        """
        import asyncio

        cap: dict[str, Any] = {}

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
        except Exception:
            pass

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
            except Exception:
                pass

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
            except Exception:
                pass

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
                ):
                    continue

            if model_data:
                # Detect vLLM backend from metadata
                owned_by = model_data.get("owned_by", "")
                root = model_data.get("root", "")
                if owned_by == "vllm" or "vllm" in str(root).lower():
                    cap["_provider"] = "vllm"
                    cap["_backend"] = "vllm"

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

        return cap if cap else None

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
        # Don't try to close the old async client synchronously —
        # just let the old loop's cleanup handle it.
        _client = ModelClient(api_key, base_url, model)
    return _client
