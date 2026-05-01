"""Parameter generator for provider-specific request parameters.

Inspired by opencode's ProviderTransform.options(), temperature(), topP(),
etc.  Centralises all provider-specific payload construction so that
ModelClient stays a thin HTTP orchestrator.
"""

from typing import Any


class ParameterGenerator:
    """Generate provider-specific request parameters and payload."""

    def __init__(self, api_protocol: str, model_info: Any = None, provider_name: str = "unknown"):
        self.api_protocol = api_protocol
        self.model_info = model_info
        self.provider_name = provider_name
        self.model_id = model_info.default_model if model_info else ""

    # ------------------------------------------------------------------
    # Protocol basics
    # ------------------------------------------------------------------

    def get_auth_headers(self, api_key: str) -> dict[str, str]:
        """Build authentication headers."""
        if self.api_protocol == "anthropic":
            return {
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "Content-Type": "application/json",
            }
        return {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

    def get_endpoint(self) -> str:
        """Get API endpoint path (relative to base_url)."""
        return "/messages" if self.api_protocol == "anthropic" else "/chat/completions"

    # ------------------------------------------------------------------
    # Parameter computation
    # ------------------------------------------------------------------

    def get_temperature(self, temperature: float) -> float | None:
        """Return temperature suitable for the model, or ``None`` to omit."""
        model_id = self.model_id.lower()
        if "claude" in model_id:
            return None  # Claude temperature tuning is usually counter-productive
        # Default for Anthropic protocol when model is unknown
        if self.api_protocol == "anthropic" and not model_id:
            return None
        if "qwen" in model_id:
            return 0.55
        if "gemini" in model_id:
            return 1.0
        if "kimi-k2" in model_id or "k2p5" in model_id or "k2.5" in model_id:
            return 1.0
        return temperature

    def get_top_p(self) -> float | None:
        """Return top_p override if the model needs it."""
        model_id = self.model_id.lower()
        if "qwen" in model_id:
            return 1.0
        if "gemini" in model_id or "kimi" in model_id:
            return 0.95
        return None

    def get_top_k(self) -> int | None:
        """Return top_k override if the model needs it."""
        model_id = self.model_id.lower()
        if "minimax-m2" in model_id:
            return 40 if any(s in model_id for s in ("m2.", "m25", "m21")) else 20
        if "gemini" in model_id:
            return 64
        return None

    def get_max_tokens(self, max_tokens: int | None) -> int:
        """Resolve max_tokens with fallback chain."""
        if max_tokens:
            # DeepSeek native: enforce practical minimum
            if "deepseek" in self.model_id.lower() and max_tokens < 4096:
                return 8192
            return max_tokens
        if self.model_info and getattr(self.model_info, "max_tokens", 0) > 0:
            return self.model_info.max_tokens
        return 4096

    def get_stream_options(self, stream: bool) -> dict[str, Any] | None:
        """Get stream-specific options."""
        if not stream:
            return None
        if self.api_protocol == "openai":
            return {"include_usage": True}
        return None

    def get_tool_params(self, tools: list[dict[str, Any]] | None) -> dict[str, Any]:
        """Get tool-related parameters."""
        if not tools:
            return {}

        result: dict[str, Any] = {"tools": self._convert_tools(tools)}

        if self.api_protocol == "anthropic":
            result["tool_choice"] = {"type": "auto"}
        else:
            supports = (
                getattr(self.model_info, "supports_tool_choice", True) if self.model_info else True
            )
            if supports:
                result["tool_choice"] = "auto"

        return result

    def _convert_tools(self, tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Convert tools to API format."""
        if self.api_protocol == "anthropic":
            return [
                {
                    "name": tool["name"],
                    "description": tool.get("description", ""),
                    "input_schema": tool.get("input_schema", tool.get("parameters", {})),
                }
                for tool in tools
            ]
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

    # ------------------------------------------------------------------
    # Full payload assembly
    # ------------------------------------------------------------------

    def build_payload(
        self,
        model: str,
        messages: list[dict[str, Any]],
        temperature: float,
        max_tokens: int | None,
        stream: bool,
        tools: list[dict[str, Any]] | None,
        system: str | None = None,
    ) -> dict[str, Any]:
        """Build complete request payload."""
        if self.api_protocol == "anthropic":
            return self._build_anthropic_payload(
                model, messages, system, temperature, max_tokens, stream, tools
            )
        return self._build_openai_payload(model, messages, temperature, max_tokens, stream, tools)

    def _build_anthropic_payload(
        self,
        model: str,
        messages: list[dict[str, Any]],
        system: str | None,
        temperature: float,
        max_tokens: int | None,
        stream: bool,
        tools: list[dict[str, Any]] | None,
    ) -> dict[str, Any]:
        """Build Anthropic /messages request payload."""
        payload: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "stream": stream,
        }

        if system:
            payload["system"] = system

        temp = self.get_temperature(temperature)
        if temp is not None:
            payload["temperature"] = temp

        payload["max_tokens"] = self.get_max_tokens(max_tokens)

        if tools:
            payload.update(self.get_tool_params(tools))

        return payload

    def _build_openai_payload(
        self,
        model: str,
        messages: list[dict[str, Any]],
        temperature: float,
        max_tokens: int | None,
        stream: bool,
        tools: list[dict[str, Any]] | None,
    ) -> dict[str, Any]:
        """Build OpenAI-compatible /chat/completions request payload."""
        payload: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "stream": stream,
        }

        stream_opts = self.get_stream_options(stream)
        if stream_opts:
            payload["stream_options"] = stream_opts

        payload["max_tokens"] = self.get_max_tokens(max_tokens)

        if tools:
            payload.update(self.get_tool_params(tools))

        return payload
