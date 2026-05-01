"""Tests for parameter_generator module."""

import pytest

from pilotcode.utils.parameter_generator import ParameterGenerator
from pilotcode.utils.models_config import ModelInfo, ModelProvider


class TestParameterGeneratorBasics:
    """Tests for basic protocol methods."""

    def test_anthropic_auth_headers(self):
        """Anthropic protocol uses x-api-key."""
        gen = ParameterGenerator("anthropic")
        headers = gen.get_auth_headers("sk-test")
        assert headers["x-api-key"] == "sk-test"
        assert headers["anthropic-version"] == "2023-06-01"

    def test_openai_auth_headers(self):
        """OpenAI protocol uses Bearer token."""
        gen = ParameterGenerator("openai")
        headers = gen.get_auth_headers("sk-test")
        assert headers["Authorization"] == "Bearer sk-test"

    def test_anthropic_endpoint(self):
        """Anthropic endpoint is /messages."""
        gen = ParameterGenerator("anthropic")
        assert gen.get_endpoint() == "/messages"

    def test_openai_endpoint(self):
        """OpenAI endpoint is /chat/completions."""
        gen = ParameterGenerator("openai")
        assert gen.get_endpoint() == "/chat/completions"


class TestParameterGeneratorTemperature:
    """Tests for temperature computation."""

    def test_claude_omits_temperature(self):
        """Claude models return None for temperature."""
        info = ModelInfo(
            name="anthropic",
            display_name="Claude",
            provider=ModelProvider.ANTHROPIC,
            base_url="",
            default_model="claude-3-5-sonnet",
            description="",
        )
        gen = ParameterGenerator("anthropic", info)
        assert gen.get_temperature(0.7) is None

    def test_qwen_temperature(self):
        """Qwen models use 0.55."""
        info = ModelInfo(
            name="qwen",
            display_name="Qwen",
            provider=ModelProvider.QWEN,
            base_url="",
            default_model="qwen-max",
            description="",
        )
        gen = ParameterGenerator("openai", info)
        assert gen.get_temperature(0.7) == 0.55

    def test_generic_temperature_pass_through(self):
        """Unknown models pass through original temperature."""
        gen = ParameterGenerator("openai")
        assert gen.get_temperature(0.7) == 0.7


class TestParameterGeneratorMaxTokens:
    """Tests for max_tokens computation."""

    def test_explicit_max_tokens(self):
        """Explicit max_tokens is respected."""
        gen = ParameterGenerator("openai")
        assert gen.get_max_tokens(1024) == 1024

    def test_deepseek_minimum(self):
        """DeepSeek enforces minimum of 8192."""
        info = ModelInfo(
            name="deepseek",
            display_name="DeepSeek",
            provider=ModelProvider.DEEPSEEK,
            base_url="",
            default_model="deepseek-v4-pro",
            description="",
        )
        gen = ParameterGenerator("openai", info)
        assert gen.get_max_tokens(2048) == 8192

    def test_model_info_fallback(self):
        """Fallback to model_info.max_tokens."""
        info = ModelInfo(
            name="custom",
            display_name="Custom",
            provider=ModelProvider.CUSTOM,
            base_url="",
            default_model="custom",
            description="",
            max_tokens=8192,
        )
        gen = ParameterGenerator("openai", info)
        assert gen.get_max_tokens(None) == 8192

    def test_default_fallback(self):
        """Final fallback is 4096."""
        gen = ParameterGenerator("openai")
        assert gen.get_max_tokens(None) == 4096


class TestParameterGeneratorTools:
    """Tests for tool conversion and parameters."""

    def test_anthropic_tool_format(self):
        """Anthropic uses flat tool schemas."""
        gen = ParameterGenerator("anthropic")
        tools = [
            {
                "name": "Bash",
                "description": "Run commands",
                "input_schema": {"type": "object"},
            }
        ]
        result = gen._convert_tools(tools)
        assert result[0]["name"] == "Bash"
        assert "input_schema" in result[0]
        assert "type" not in result[0]

    def test_openai_tool_format(self):
        """OpenAI uses function-wrapped schemas."""
        gen = ParameterGenerator("openai")
        tools = [
            {
                "name": "Bash",
                "description": "Run commands",
                "input_schema": {"type": "object"},
            }
        ]
        result = gen._convert_tools(tools)
        assert result[0]["type"] == "function"
        assert result[0]["function"]["name"] == "Bash"

    def test_anthropic_tool_choice(self):
        """Anthropic always sends tool_choice auto."""
        gen = ParameterGenerator("anthropic")
        params = gen.get_tool_params([{"name": "Bash"}])
        assert params["tool_choice"] == {"type": "auto"}

    def test_openai_tool_choice_supported(self):
        """OpenAI sends tool_choice when supported."""
        info = ModelInfo(
            name="openai",
            display_name="OpenAI",
            provider=ModelProvider.OPENAI,
            base_url="",
            default_model="gpt-4o",
            description="",
            supports_tool_choice=True,
        )
        gen = ParameterGenerator("openai", info)
        params = gen.get_tool_params([{"name": "Bash"}])
        assert params["tool_choice"] == "auto"

    def test_openai_tool_choice_unsupported(self):
        """OpenAI omits tool_choice when unsupported."""
        info = ModelInfo(
            name="deepseek",
            display_name="DeepSeek",
            provider=ModelProvider.DEEPSEEK,
            base_url="",
            default_model="deepseek-v4-pro",
            description="",
            supports_tool_choice=False,
        )
        gen = ParameterGenerator("openai", info)
        params = gen.get_tool_params([{"name": "Bash"}])
        assert "tool_choice" not in params


class TestParameterGeneratorStreamOptions:
    """Tests for stream options."""

    def test_openai_stream_includes_usage(self):
        """OpenAI streaming includes include_usage."""
        gen = ParameterGenerator("openai")
        opts = gen.get_stream_options(stream=True)
        assert opts == {"include_usage": True}

    def test_anthropic_stream_no_options(self):
        """Anthropic streaming has no special options."""
        gen = ParameterGenerator("anthropic")
        assert gen.get_stream_options(stream=True) is None

    def test_no_stream_no_options(self):
        """Non-streaming has no stream options."""
        gen = ParameterGenerator("openai")
        assert gen.get_stream_options(stream=False) is None


class TestParameterGeneratorPayload:
    """Tests for full payload assembly."""

    def test_anthropic_payload(self):
        """Anthropic payload structure."""
        gen = ParameterGenerator("anthropic")
        payload = gen.build_payload(
            model="claude-3",
            messages=[{"role": "user", "content": "hi"}],
            temperature=0.7,
            max_tokens=1024,
            stream=True,
            tools=None,
            system="Be helpful",
        )
        assert payload["model"] == "claude-3"
        assert payload["messages"][0]["role"] == "user"
        assert payload["system"] == "Be helpful"
        assert payload["stream"] is True
        assert payload["max_tokens"] == 1024
        assert "temperature" not in payload  # Claude omits temperature

    def test_anthropic_payload_with_tools(self):
        """Anthropic payload with tools."""
        gen = ParameterGenerator("anthropic")
        payload = gen.build_payload(
            model="claude-3",
            messages=[{"role": "user", "content": "hi"}],
            temperature=0.7,
            max_tokens=1024,
            stream=False,
            tools=[{"name": "Bash", "description": "Run", "input_schema": {}}],
            system=None,
        )
        assert "tools" in payload
        assert payload["tool_choice"] == {"type": "auto"}

    def test_openai_payload(self):
        """OpenAI payload structure."""
        gen = ParameterGenerator("openai")
        payload = gen.build_payload(
            model="gpt-4o",
            messages=[{"role": "user", "content": "hi"}],
            temperature=0.7,
            max_tokens=1024,
            stream=True,
            tools=None,
            system=None,
        )
        assert payload["model"] == "gpt-4o"
        assert payload["temperature"] == 0.7
        assert payload["stream_options"] == {"include_usage": True}
        assert "system" not in payload

    def test_openai_payload_with_tools(self):
        """OpenAI payload with tools."""
        gen = ParameterGenerator("openai")
        payload = gen.build_payload(
            model="gpt-4o",
            messages=[{"role": "user", "content": "hi"}],
            temperature=0.7,
            max_tokens=1024,
            stream=False,
            tools=[{"name": "Bash", "description": "Run", "input_schema": {}}],
            system=None,
        )
        assert payload["tools"][0]["type"] == "function"
        assert payload["tool_choice"] == "auto"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
