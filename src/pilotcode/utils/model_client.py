"""Model client for interacting with LLM APIs."""

import asyncio
import json
from typing import Any, AsyncIterator
from dataclasses import dataclass
import httpx

from .config import get_global_config
from .models_config import get_model_info


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

        # Determine base URL: use provided, or from model info, or from config
        if base_url:
            self.base_url = base_url
        elif model_info and model_info.base_url:
            # Use model-specific base URL if available
            self.base_url = model_info.base_url
        else:
            self.base_url = config.base_url

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

        Tries to query the /models or /models/{model_id} endpoint to get
        actual model metadata (context window, max tokens, etc.) from the
        server rather than relying on static configuration.

        Returns:
            Dict with capability info, or None if the API doesn't expose it.
        """
        import asyncio

        cap: dict[str, Any] = {}

        # Try /models/{model_id} first (OpenAI compatible)
        model_data = None
        for endpoint in [f"/models/{self.model}", "/models"]:
            try:
                resp = await self.client.get(endpoint, timeout=10.0)
                if resp.status_code == 200:
                    data = resp.json()
                    if endpoint.endswith("/models"):
                        # List response — find the matching model
                        for m in data.get("data", []):
                            if m.get("id") == self.model:
                                model_data = m
                                break
                        # Fallback: take first model if only one exists
                        if model_data is None and len(data.get("data", [])) == 1:
                            model_data = data["data"][0]
                    else:
                        model_data = data
                    break
            except (httpx.HTTPStatusError, httpx.RequestError, json.JSONDecodeError):
                continue
            except asyncio.TimeoutError:
                continue

        if not model_data:
            return None

        # --- Extract context window ---
        # Different providers use different field names
        for key in ("context_length", "context_window", "max_model_len",
                    "max_context_length", "num_ctx", "n_ctx"):
            val = model_data.get(key)
            if val is not None:
                try:
                    cap["context_window"] = int(val)
                    break
                except (ValueError, TypeError):
                    pass

        # Some providers nest it under a "meta" or "info" dict
        if "context_window" not in cap:
            for nested_key in ("meta", "info", "details", "capabilities"):
                nested = model_data.get(nested_key)
                if isinstance(nested, dict):
                    for key in ("context_length", "context_window", "max_model_len",
                                "max_context_length", "num_ctx", "n_ctx"):
                        val = nested.get(key)
                        if val is not None:
                            try:
                                cap["context_window"] = int(val)
                                break
                            except (ValueError, TypeError):
                                pass
                if "context_window" in cap:
                    break

        # --- Extract max output tokens ---
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

        # --- Extract tool / vision support ---
        for key in ("supports_tools", "supports_function_calling", "tool_call"):
            val = model_data.get(key)
            if val is not None:
                cap["supports_tools"] = bool(val)
                break
        if "supports_tools" not in cap:
            for nested_key in ("meta", "info", "details", "capabilities"):
                nested = model_data.get(nested_key)
                if isinstance(nested, dict):
                    for key in ("supports_tools", "supports_function_calling", "tool_call"):
                        val = nested.get(key)
                        if val is not None:
                            cap["supports_tools"] = bool(val)
                            break
                if "supports_tools" in cap:
                    break

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
