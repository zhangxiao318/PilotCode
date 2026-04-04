"""Model client for interacting with LLM APIs."""

import os
import json
from typing import Any, AsyncIterator
from dataclasses import dataclass
from enum import Enum
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
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None
    ):
        config = get_global_config()
        
        self.api_key = api_key or config.api_key or "sk-placeholder"
        
        # Determine model name: use provided, or config, or fallback
        model_key = model or config.default_model or "default"
        
        # Map model key to actual API model name (e.g., "qwen" -> "qwen-max")
        model_info = get_model_info(model_key)
        if model_info and model_info.default_model:
            self.model = model_info.default_model
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
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            },
            timeout=300.0
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
                        "function": {
                            "name": tc.name,
                            "arguments": json.dumps(tc.arguments)
                        }
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
                    "parameters": tool.get("input_schema", {})
                }
            }
            for tool in tools
        ]
    
    async def chat_completion(
        self,
        messages: list[Message],
        tools: list[dict[str, Any]] | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        stream: bool = True
    ) -> AsyncIterator[dict[str, Any]]:
        """Send chat completion request."""
        payload = {
            "model": self.model,
            "messages": self._convert_messages(messages),
            "temperature": temperature,
            "stream": stream
        }
        
        if tools:
            payload["tools"] = self._convert_tools(tools)
            payload["tool_choice"] = "auto"
        
        if max_tokens:
            payload["max_tokens"] = max_tokens
        
        if stream:
            async with self.client.stream(
                "POST",
                "/chat/completions",
                json=payload
            ) as response:
                async for line in response.aiter_lines():
                    if line.startswith("data: "):
                        data = line[6:]
                        if data == "[DONE]":
                            break
                        try:
                            yield json.loads(data)
                        except json.JSONDecodeError:
                            continue
        else:
            response = await self.client.post("/chat/completions", json=payload)
            response.raise_for_status()
            data = response.json()
            
            # Yield as a single chunk
            yield {
                "choices": [{
                    "delta": data["choices"][0]["message"],
                    "finish_reason": data["choices"][0].get("finish_reason")
                }]
            }
    
    async def close(self) -> None:
        """Close the client."""
        await self.client.aclose()


# Global client
_client: ModelClient | None = None


def get_model_client(
    api_key: str | None = None,
    base_url: str | None = None,
    model: str | None = None
) -> ModelClient:
    """Get or create model client.
    
    If no parameters are provided, uses configuration from settings.
    """
    global _client
    if _client is None:
        _client = ModelClient(api_key, base_url, model)
    return _client
